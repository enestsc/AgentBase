import copy
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from agentbase import local
from agentbase.config import DEFAULT
from agentbase.fs import AgentBaseError


class EndpointTests(unittest.TestCase):
    def test_loopback_endpoints_are_accepted(self):
        self.assertEqual(local.endpoint_url("http://127.0.0.1:11434"), "http://127.0.0.1:11434/api/chat")
        self.assertEqual(local.endpoint_url("http://localhost"), "http://127.0.0.1:11434/api/chat")
        self.assertEqual(local.endpoint_url("http://127.0.0.1:8080/"), "http://127.0.0.1:8080/api/chat")
        self.assertEqual(local.endpoint_url("http://[::1]:9000"), "http://[::1]:9000/api/chat")

    def test_unsafe_endpoints_are_rejected(self):
        # Girdi dışarı sızabileceği için uzak host, TLS'li şema, kimlik bilgisi, path/query hep ret.
        for bad in ("http://example.com", "http://192.168.1.5:11434", "https://127.0.0.1:11434",
                    "http://user:pw@127.0.0.1", "http://127.0.0.1/api", "http://127.0.0.1?x=1",
                    "http://127.0.0.1#f", "http://127.0.0.1:70000", "ftp://127.0.0.1", "", "127.0.0.1"):
            with self.subTest(endpoint=bad), self.assertRaises(AgentBaseError):
                local.endpoint_url(bad)

    def test_port_zero_is_rejected_not_defaulted(self):
        # Port 0 geçersizdir; sessizce 11434'e düşmemeli. Port hiç verilmezse varsayılan geçerli kalır.
        with self.assertRaises(AgentBaseError):
            local.endpoint_url("http://127.0.0.1:0")
        self.assertTrue(local.endpoint_url("http://127.0.0.1").endswith(":11434/api/chat"))


class PrepareRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "note.txt").write_text("hello world", encoding="utf-8")
        self.config = copy.deepcopy(DEFAULT)
        self.config["local_model"].update(enabled=True, model="llama3")

    def prepare(self, action="summarize", path="note.txt", consent=True):
        return local.prepare_request(self.root, self.config, action, path, consent=consent)

    def test_valid_request_is_built(self):
        url, payload = self.prepare()
        self.assertEqual(url, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(payload["model"], "llama3")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"][1]["content"], "hello world")

    def test_disabled_by_default(self):
        self.config["local_model"]["enabled"] = False
        with self.assertRaisesRegex(AgentBaseError, "disabled"):
            self.prepare()

    def test_missing_consent_is_refused(self):
        with self.assertRaisesRegex(AgentBaseError, "--consent"):
            self.prepare(consent=False)

    def test_cloud_or_empty_model_is_refused(self):
        # "cloud" etiketli modeller veriyi dışarı gönderebilir; yerel garanti bozulur.
        for model in ("llama3:cloud", "GPT-OSS-CLOUD", "  "):
            self.config["local_model"]["model"] = model
            with self.subTest(model=model), self.assertRaisesRegex(AgentBaseError, "local model"):
                self.prepare()

    def test_oversized_input_is_refused(self):
        self.config["local_model"]["max_input_chars"] = 5
        with self.assertRaisesRegex(AgentBaseError, "character budget"):
            self.prepare()

    def test_secret_path_and_unknown_action_are_refused(self):
        (self.root / ".env").write_text("X=1", encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "refused"):
            self.prepare(path=".env")
        with self.assertRaisesRegex(AgentBaseError, "summarize and classify"):
            self.prepare(action="delete")


class FakeOllama(BaseHTTPRequestHandler):
    # Gerçek Ollama yerine 127.0.0.1'de sahte sunucu: ağ/model bağımlılığı olmadan hızlı test.
    seen = []
    target_hits = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/api/chat":
            FakeOllama.seen.append(json.loads(body))
            reply = json.dumps({"message": {"role": "assistant", "content": "özet"}, "done": True,
                                "prompt_eval_count": 3, "eval_count": 4}).encode()
            self.send_response(200)
        elif self.path == "/redirect":
            self.send_response(307)
            self.send_header("Location", "/target")
            reply = b""
        elif self.path == "/bad":
            reply = b"not json"
            self.send_response(200)
        elif self.path == "/target":
            FakeOllama.target_hits.append(body)
            reply = b"{}"
            self.send_response(200)
        else:
            reply = b""
            self.send_response(500)
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)


class RequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeOllama.seen.clear()
        FakeOllama.target_hits.clear()

    def test_successful_response_is_untrusted_proposal(self):
        result = local.request(self.base + "/api/chat", {"model": "llama3", "messages": []}, 5)
        self.assertEqual(result["proposal"], "özet")
        self.assertIs(result["trusted"], False)
        self.assertEqual(result["files_changed"], [])
        self.assertEqual(result["usage"], {"prompt_eval_count": 3, "eval_count": 4})
        self.assertEqual(FakeOllama.seen[0]["model"], "llama3")

    def test_redirect_is_refused_and_not_followed(self):
        # Yönlendirme izlenirse girdi başka bir hedefe sızabilir; hedefe istek ulaşmamalı.
        with self.assertRaisesRegex(AgentBaseError, "redirect refused"):
            local.request(self.base + "/redirect", {"model": "m"}, 5)
        self.assertEqual(FakeOllama.target_hits, [])

    def test_http_error_and_invalid_body_become_agentbase_errors(self):
        with self.assertRaisesRegex(AgentBaseError, "HTTP 500"):
            local.request(self.base + "/boom", {"model": "m"}, 5)
        with self.assertRaisesRegex(AgentBaseError, "unavailable or invalid"):
            local.request(self.base + "/bad", {"model": "m"}, 5)


if __name__ == "__main__":
    unittest.main()

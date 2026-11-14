import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from agentbase import usage
from agentbase.fs import AgentBaseError

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


def capture(source="codex-exec-v1", event_id="turn-1", **changes):
    value = {"schema_version": 1, "source": source, "timestamp": NOW.isoformat(), "provider_version": "fixture-v1",
             "session_id": "s1", "event_id": event_id, "project_id": "p1",
             "event": {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 50}}}
    value.update(changes)
    return value


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def enable(self, *sources):
        usage.configure(self.root, list(sources) or sorted(usage.SOURCES), retention_days=3650)

    def test_collection_requires_opt_in_per_source(self):
        with self.assertRaisesRegex(AgentBaseError, "disabled"):
            usage.ingest(self.root, [capture()], now=NOW)
        self.enable("claude-api-request-v1")
        with self.assertRaisesRegex(AgentBaseError, "not opted in"):
            usage.ingest(self.root, [capture()], now=NOW)
        self.assertFalse((self.root / usage.DATA).exists())

    def test_codex_import_unknown_attribution_and_duplicates(self):
        self.enable()
        value = capture()
        usage.ingest(self.root, [value], now=NOW)
        result = usage.ingest(self.root, [value], now=NOW)
        self.assertEqual(result["duplicates"], 1)
        report = usage.report(self.root, now=NOW, timezone="UTC", by="agent_id")
        self.assertEqual(report["totals"]["input_tokens"]["known_total"], 100)
        self.assertIsNone(report["totals"]["reasoning_tokens"]["known_total"])
        self.assertIn("unattributed", report["groups"])
        self.assertIsNone(usage.records(self.root)[0]["model"])
        value["event"]["usage"]["input_tokens"] = 110
        with self.assertRaisesRegex(AgentBaseError, "reused"):
            usage.ingest(self.root, [value], now=NOW)

    def test_explicit_correlation_and_privacy_allowlist(self):
        self.enable()
        value = capture(agentbase_correlation={"id": "task-1", "agent_id": "debugger", "skill_id": "verify"}, prompt="PRIVATE PROMPT", credentials="SECRET")
        value["event"]["tool_output"] = "PRIVATE CODE"
        usage.ingest(self.root, [value], now=NOW)
        stored = (self.root / usage.DATA).read_text()
        for private in ("PRIVATE", "SECRET", "tool_output", "prompt", "credentials"):
            self.assertNotIn(private, stored)
        self.assertEqual(usage.records(self.root)[0]["agent_id"], "debugger")

    def test_claude_api_event_and_statusline_context_are_separate(self):
        self.enable()
        value = capture("claude-api-request-v1", event={"event.name": "api_request", "input_tokens": 80,
                        "output_tokens": 12, "cache_read_tokens": 90, "model": "unknown-model", "cost_usd": 0.001})
        context = capture("claude-statusline-v1", session_id="s2", event={"session_id": "s2", "context_window": {
                          "total_input_tokens": 8000, "total_output_tokens": 10, "context_window_size": 100000},
                          "cost": {"total_cost_usd": 1.2}})
        usage.ingest(self.root, [value, context], now=NOW)
        report = usage.report(self.root, now=NOW)
        self.assertEqual(report["totals"]["input_tokens"]["known_total"], 80)
        self.assertEqual(report["totals"]["input_tokens"]["unknown_records"], 1)
        self.assertEqual(usage.records(self.root)[1]["context_tokens"], 8010)
        self.assertTrue(all(r["billed_usd"] is None for r in usage.records(self.root)))

    def test_cumulative_deltas_and_reset_unknown(self):
        self.enable()

        def event(n, hour):
            return capture("codex-app-server-v1", event_id=f"e{hour}", timestamp=f"2026-11-10T{hour}:00:00Z", event={
                "method": "thread/tokenUsage/updated", "params": {"threadId": "s1", "tokenUsage": {"total": {"inputTokens": n, "outputTokens": n}}}})

        usage.ingest(self.root, [event(100, 10), event(150, 11), event(20, 12)], now=NOW)
        report = usage.report(self.root, now=NOW)
        self.assertEqual(report["totals"]["input_tokens"]["known_total"], 50)
        self.assertEqual(report["totals"]["input_tokens"]["unknown_records"], 2)
        self.assertTrue(any("decreased" in w for w in report["warnings"]))

    def test_context_capture_does_not_suppress_request_consumption(self):
        self.enable()
        api = capture("claude-api-request-v1", event={"event.name": "api_request", "input_tokens": 10})
        context = capture("claude-statusline-v1", event={"session_id": "s1"})
        usage.ingest(self.root, [api, context], now=NOW)
        report = usage.report(self.root, now=NOW)
        self.assertEqual(report["records"], 2)
        self.assertEqual(report["totals"]["input_tokens"]["known_total"], 10)

    def test_competing_token_sources_same_session_excluded(self):
        self.enable()
        snapshot = capture("codex-app-server-v1", event={"method": "thread/tokenUsage/updated", "params": {
            "threadId": "s1", "tokenUsage": {"total": {"inputTokens": 100}}}})
        usage.ingest(self.root, [capture(), snapshot], now=NOW)
        report = usage.report(self.root, now=NOW)
        self.assertEqual(report["records"], 0)
        self.assertTrue(any("Multiple sources" in w for w in report["warnings"]))

    def test_timezone_day_boundary_and_export(self):
        self.enable()
        value = capture(timestamp="2026-11-09T23:30:00-02:00")
        usage.ingest(self.root, [value], now=NOW)
        self.assertEqual(usage.report(self.root, period="today", timezone="UTC", now=NOW)["records"], 1)
        self.assertIn("2026-11-10", usage.report(self.root, timezone="UTC", now=NOW)["daily"])
        self.assertIn("input_tokens", usage.export(self.root, csv_format=True))
        self.assertEqual(len(usage.export(self.root)["records"]), 1)
        with self.assertRaises(AgentBaseError):
            usage.normalize(capture(timestamp="2026-11-10T10:00:00"))

    def test_retention_deletion_and_disabled_sources(self):
        self.enable()
        usage.ingest(self.root, [capture(), capture(event_id="old", timestamp="2020-01-01T00:00:00Z")], now=NOW)
        usage.configure(self.root, sorted(usage.SOURCES), retention_days=30)
        usage.ingest(self.root, [], now=NOW)
        self.assertEqual(len(usage.records(self.root)), 1)
        self.assertEqual(usage.delete(self.root, all_data=True)["deleted"], 1)
        usage.configure(self.root, [])
        self.assertEqual(usage.report(self.root, now=NOW)["records"], 0)

    def test_invalid_numeric_data_rejects_entire_import(self):
        self.enable()
        for invalid in (-1, True, "10", float("nan")):
            value = capture(event={"type": "turn.completed", "usage": {"input_tokens": invalid}})
            with self.subTest(invalid=invalid), self.assertRaises(AgentBaseError):
                usage.ingest(self.root, [capture(), value], now=NOW)
        self.assertFalse((self.root / usage.DATA).exists())
        with self.assertRaises(AgentBaseError):
            usage.ingest(self.root, None, now=NOW)

    def test_csv_export_neutralizes_formula_identifiers(self):
        self.enable()
        usage.ingest(self.root, [capture(model="=1+1")], now=NOW)
        self.assertIn("'=1+1", usage.export(self.root, csv_format=True))

    def test_stdin_status_observations_are_private_and_deduplicated(self):
        self.enable("claude-statusline-v1")
        event = {"session_id": "s1", "context_window": {"total_input_tokens": 20, "total_output_tokens": 3},
                 "workspace": {"current_dir": "PRIVATE_PATH"}, "transcript_path": "PRIVATE_LOG", "api_key": "SECRET"}
        first = usage.capture_event(self.root, "claude-statusline-v1", event, project_id="p1", provider_version="fixture", now=NOW)
        original = usage.normalize
        def reordered(envelope):
            return dict(reversed(list(original(envelope).items())))
        with patch("agentbase.usage.normalize", side_effect=reordered):
            second = usage.capture_event(self.root, "claude-statusline-v1", event, project_id="p1", provider_version="fixture", now=NOW + timedelta(seconds=1))
        self.assertEqual(first["imported"], 1)
        self.assertEqual(second["duplicates"], 1)
        body = (self.root / usage.DATA).read_text()
        self.assertNotIn("PRIVATE", body)
        self.assertNotIn("SECRET", body)
        self.assertEqual(usage.records(self.root)[0]["context_tokens"], 23)
        usage.configure(self.root, [])
        with self.assertRaisesRegex(AgentBaseError, "opted in"):
            usage.capture_event(self.root, "claude-statusline-v1", event, project_id="p1", provider_version="fixture")

    def test_incremental_capture_requires_stable_identity(self):
        self.enable()
        event = capture()["event"]
        with self.assertRaisesRegex(AgentBaseError, "event-id"):
            usage.capture_event(self.root, "codex-exec-v1", event, project_id="p1", provider_version="fixture", session_id="s1")
        usage.capture_event(self.root, "codex-exec-v1", event, project_id="p1", provider_version="fixture", session_id="s1", event_id="turn-1", now=NOW)
        usage.capture_event(self.root, "codex-exec-v1", event, project_id="p1", provider_version="fixture", session_id="s1", event_id="turn-2", now=NOW)
        self.assertEqual(usage.report(self.root, now=NOW)["totals"]["input_tokens"]["known_total"], 200)

    def test_cross_day_cumulative_intervals_are_not_assigned_to_one_day(self):
        self.enable()
        def sample(n, date):
            return capture("codex-app-server-v1", event_id=f"e{n}", timestamp=date, event={"method": "thread/tokenUsage/updated", "params": {
                "threadId": "s1", "tokenUsage": {"total": {"inputTokens": n}}}})
        usage.ingest(self.root, [sample(100, "2026-11-09T23:59:00Z"), sample(150, "2026-11-10T00:01:00Z")], now=NOW)
        report = usage.report(self.root, now=NOW, timezone="UTC")
        self.assertEqual(report["totals"]["input_tokens"]["known_total"], 50)
        self.assertIsNone(report["daily"]["2026-11-10"]["input_tokens"]["known_total"])
        self.assertEqual(report["unallocated_intervals"][0]["tokens"]["input_tokens"], 50)
        self.assertIsNone(usage.report(self.root, now=NOW, timezone="UTC", period="today")["totals"]["input_tokens"]["known_total"])

    def test_cumulative_attribution_changes_remain_unattributed(self):
        self.enable()
        samples = []
        for n, role in ((100, "debugger"), (150, "code-reviewer")):
            samples.append(capture("codex-app-server-v1", event_id=str(n), timestamp=f"2026-11-10T{10 if n == 100 else 11}:00:00Z",
                agentbase_correlation={"id": role, "agent_id": role}, event={"method": "thread/tokenUsage/updated", "params": {
                    "threadId": "s1", "tokenUsage": {"total": {"inputTokens": n}}}}))
        usage.ingest(self.root, samples, now=NOW)
        report = usage.report(self.root, now=NOW, by="agent_id")
        self.assertEqual(set(report["groups"]), {"unattributed"})
        self.assertEqual(report["groups"]["unattributed"]["input_tokens"]["known_total"], 50)


if __name__ == "__main__":
    unittest.main()

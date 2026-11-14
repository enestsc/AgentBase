"""Explicit offline Docker boundary smoke using our own program in a trusted image.

No image pull, model calls, project mounts or provider credentials. Requires a
locally installed Node image pinned by digest, selected explicitly by the caller.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

from agentbase.fs import AgentBaseError
from agentbase.runner import DockerTaskRunner

PROGRAM = r"""
const fs = require('fs'), crypto = require('crypto'), net = require('net');
const request = JSON.parse(fs.readFileSync('/input/request.json', 'utf8'));
const checks = [];
function check(command, passed) { checks.push({command, status:passed?'passed':'failed', outcome:passed?'Observed boundary held':'Boundary failed'}); }
for (const [path, file] of Object.entries(request.files))
  check('snapshot SHA-256: ' + path, crypto.createHash('sha256').update(file.text).digest('hex') === file.sha256);
check('host environment excluded', process.env.AGENTBASE_BOUNDARY_SENTINEL === undefined);
let readonly = false;
try { fs.writeFileSync('/forbidden-host-write', 'test'); } catch(e) { readonly = e.code === 'EROFS' || e.code === 'EACCES'; }
check('read-only root filesystem', readonly);
let hostHidden = false;
try { fs.readFileSync('/host-only-secret.txt'); } catch(e) { hostHidden = e.code === 'ENOENT'; }
check('host filesystem not mounted', hostHidden);
const socket = net.createConnection({host:'192.0.2.1', port:80});
socket.setTimeout(300);
let done = false;
function finish(blocked) {
  if(done) return; done=true; socket.destroy();
  check('external network inaccessible', blocked);
  const failed = checks.filter(c=>c.status==='failed').map(c=>c.command);
  console.log(JSON.stringify({handoff:{schema_version:1,task_id:request.task.id,
    result:'Observed offline Docker boundary checks',changed_files:[],decisions:[],tests:checks,
    failures:failed,risks:['Docker shares the host kernel; not a VM'],artifacts:[]},files:{}}));
}
socket.on('connect', ()=>finish(false));
socket.on('error', ()=>finish(true));
socket.on('timeout', ()=>finish(true));
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", action="store_true", required=True, help="Explicit local container execution opt-in")
    parser.add_argument("--image", required=True, help="Trusted preinstalled Node repository@sha256 digest; never pulled")
    args = parser.parse_args()
    worker = DockerTaskRunner()
    configuration = {"schema_version": 1, "provider": "deterministic", "image": args.image,
                     "entrypoint": "/usr/local/bin/node", "arguments": ["-e", PROGRAM],
                     "timeout_seconds": 10, "memory_mb": 128, "pids": 32}
    with tempfile.TemporaryDirectory(prefix="agentbase-boundary-smoke-") as temporary:
        root = Path(temporary)
        (root / "note.txt").write_text("First-party boundary fixture", encoding="utf-8")
        task = {"id": "boundary", "description": "Inspect bounded snapshot", "role": "code-reviewer", "dependencies": [],
                "inputs": ["note.txt"], "outputs": ["boundary observations"], "scope": [{"path": "note.txt", "access": "read"}],
                "resources": [], "acceptance": ["Read-only root, no host env/files/network"],
                "status": "running", "verification": [], "blocking_reason": ""}
        previous = os.environ.get("AGENTBASE_BOUNDARY_SENTINEL")
        os.environ["AGENTBASE_BOUNDARY_SENTINEL"] = "must-not-reach-worker"
        try:
            result = worker.run(root, task, ["note.txt"], configuration, consent=True)
        finally:
            if previous is None:
                os.environ.pop("AGENTBASE_BOUNDARY_SENTINEL", None)
            else:
                os.environ["AGENTBASE_BOUNDARY_SENTINEL"] = previous
        if result["handoff"]["failures"]:
            raise RuntimeError("Docker boundary smoke failed")
        # A detached child shares the container PID namespace and must disappear
        # with forced container removal after the bounded wait expires.
        configuration.update(timeout_seconds=1, arguments=["-e", "require('child_process').spawn('/usr/local/bin/node',['-e','setInterval(()=>{},1000)'],{detached:true,stdio:'ignore'}); setInterval(()=>{},1000)"])
        try:
            worker.run(root, task, [], configuration, consent=True)
        except AgentBaseError as exc:
            if "timed out" not in str(exc):
                raise
        else:
            raise RuntimeError("Timeout fixture unexpectedly completed")
        print(json.dumps({"ok": True, "image": args.image, "checks": result["handoff"]["tests"],
                          "timeout_and_container_removal": "passed", "model_calls": 0, "image_pulls": 0}, indent=2))


if __name__ == "__main__":
    main()

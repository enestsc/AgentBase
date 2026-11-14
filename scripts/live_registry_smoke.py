"""Explicit network-only smoke: inspect/install/audit/remove in a disposable project.

No imported scripts execute. Fail on any finding requiring acknowledgement.
Not part of offline CI; run with PYTHONPATH=src and --network explicitly.
"""

import argparse
import tempfile
from pathlib import Path

from agentbase import registry
from agentbase.fs import AgentBaseError, json_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", action="store_true", required=True)
    args = parser.parse_args()
    if not args.network:
        parser.error("Explicit --network is required")
    with tempfile.TemporaryDirectory(prefix="agentbase-registry-smoke-") as temporary:
        root = Path(temporary)
        record, files = registry.fetch("https://github.com/obra/superpowers", "22f0b463e7a5e579904dd6211a520321035526f7", "skills/verification-before-completion")
        record["targets"] = ["codex", "claude"]
        preview = registry.apply(root, record, files)
        if preview["required_acknowledgements"] or preview["conflicts"]:
            raise AgentBaseError("Smoke stopped for manual review; no findings are automatically acknowledged.")
        registry.apply(root, record, files, dry_run=False, expected_plan=preview["plan_id"])
        audit = registry.audit(root)
        if not audit["ok"]:
            raise AgentBaseError("Installed skill failed integrity audit.")
        registry.remove(root, record["id"], dry_run=False)
        if registry.load(root)["skills"]:
            raise AgentBaseError("Removal did not clear installed skill index.")
        print(json_text({"ok": True, "commit": record["commit"], "targets": record["targets"],
                         "license": record["license"], "files": len(files), "executed_imported_code": False,
                         "project": "disposable temporary directory; removed after test"}))


if __name__ == "__main__":
    main()

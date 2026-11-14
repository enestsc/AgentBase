"""Pinned, bounded GitHub skill import with review plans and hash-owned files.

No Git subprocesses, hooks, archive extraction, dependency installation or inference.
Only explicit operations contact fixed GitHub HTTPS endpoints; redirects are rejected.
"""

from __future__ import annotations

import io
import json
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .catalog import asset, skills
from .dependencies import inspect as inspect_dependencies
from .fs import AgentBaseError, batch_write, confined, digest, json_text, project_lock, read_json, relative
from .skill_security import NAME, finding, licenses, metadata, scan

LOCK = ".agentbase/skills.lock.json"
MAX_DOWNLOAD = 20_000_000
MAX_EXPANDED = 32_000_000
MAX_FILE = 2_000_000
MAX_FILES = 2000
MAX_LOCK = 3_900_000
SHA = re.compile(r"[a-f0-9]{40}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
TARGETS = {"codex": ".agents/skills", "claude": ".claude/skills"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AgentBaseError("GitHub redirect refused; use the current repository URL.")


def download(url: str, ceiling: int = MAX_DOWNLOAD) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {"api.github.com", "codeload.github.com"}:
        raise AgentBaseError("Only fixed GitHub HTTPS endpoints are permitted.")
    request = urllib.request.Request(url, headers={"User-Agent": "AgentBase/0.1", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            data = response.read(ceiling + 1)
        if len(data) > ceiling:
            raise AgentBaseError("GitHub response exceeds download limit.")
        return data
    except (OSError, urllib.error.URLError) as exc:
        raise AgentBaseError(f"GitHub request failed ({type(exc).__name__}); no installation changed.") from exc


def repository(url: str) -> str:
    if not isinstance(url, str) or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/)?", url):
        raise AgentBaseError("Use https://github.com/owner/repository without credentials, query or fragment.")
    result = url.rstrip("/").removesuffix(".git")
    if any(part in {".", ".."} for part in result.split("/")[3:]):
        raise AgentBaseError("Invalid GitHub repository.")
    return result


def resolve(url: str, ref: str) -> tuple[str, str]:
    url = repository(url)
    if not isinstance(ref, str) or not ref.strip() or len(ref) > 200 or any(ord(c) < 32 for c in ref):
        raise AgentBaseError("A bounded nonempty Git ref is required.")
    try:
        value = json.loads(download(f"https://api.github.com/repos/{url.split('github.com/')[1]}/commits/{urllib.parse.quote(ref, safe='')}", 1_000_000))
        sha = value["sha"]
    except (ValueError, KeyError, TypeError) as exc:
        raise AgentBaseError("Invalid GitHub commit response.") from exc
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise AgentBaseError("GitHub did not return a full immutable commit SHA.")
    if SHA.fullmatch(ref) and ref != sha:
        raise AgentBaseError("Resolved commit differs from the requested pin.")
    return url, sha


def archive(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_DOWNLOAD:
        raise AgentBaseError("Archive exceeds compressed limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as source:
            entries = source.infolist()
            if not entries or len(entries) > MAX_FILES or sum(i.file_size for i in entries) > MAX_EXPANDED:
                raise AgentBaseError("Archive exceeds file count or expanded size limit.")
            files, seen, roots = {}, set(), set()
            for item in entries:
                name = relative(item.filename)
                folded = name.casefold()
                if folded in seen:
                    raise AgentBaseError("Duplicate/case-colliding archive path.")
                seen.add(folded)
                parts = name.split("/")
                roots.add(parts[0])
                mode = item.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in {0, stat.S_IFREG, stat.S_IFDIR} or item.flag_bits & 1:
                    raise AgentBaseError("Archive links, special files and encryption are refused.")
                if item.file_size > MAX_FILE or item.file_size > max(item.compress_size, 1) * 200:
                    raise AgentBaseError("Archive file exceeds size/compression-ratio limit.")
                if any(p in {".git", ".hg", ".svn"} for p in parts):
                    raise AgentBaseError("VCS internals are refused in archives.")
                if item.is_dir():
                    continue
                if len(parts) < 2:
                    raise AgentBaseError("Archive must have one repository root directory.")
                files["/".join(parts[1:])] = source.read(item)
            if len(roots) != 1:
                raise AgentBaseError("Archive must contain exactly one repository root.")
            # A file must not also be an ancestor of another file.
            folded_files = {p.casefold() for p in files}
            if any(str(parent).casefold() in folded_files for p in files for parent in PurePosixPath(p).parents if str(parent) != "."):
                raise AgentBaseError("Archive file/directory collision.")
            return files
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError) as exc:
        raise AgentBaseError("Invalid or unsupported ZIP archive.") from exc


def fetch(url: str, ref: str = "HEAD", path: str | None = None, *, yaml_parser: str = "stdlib") -> tuple[dict, dict[str, bytes]]:
    url, sha = resolve(url, ref)
    files = archive(download(f"https://codeload.github.com/{url.split('github.com/')[1]}/zip/{sha}"))
    candidates = sorted(str(PurePosixPath(p).parent) for p in files if PurePosixPath(p).name == "SKILL.md")
    if path is None:
        if len(candidates) != 1:
            raise AgentBaseError("Select --path from skill candidates: " + (", ".join(candidates) or "none"))
        path = candidates[0]
    if path != ".":
        path = relative(path)
    if path not in candidates:
        raise AgentBaseError("Selected directory has no SKILL.md.")
    prefix = "" if path == "." else path + "/"
    selected = {p[len(prefix):]: data for p, data in files.items() if p.startswith(prefix)}
    try:
        info = metadata(selected["SKILL.md"].decode("utf-8"), PurePosixPath(path).name if path != "." else None, parser=yaml_parser)
    except UnicodeError as exc:
        raise AgentBaseError("SKILL.md must be UTF-8.") from exc
    if info["name"] in skills() or info["name"].startswith("agentbase-"):
        raise AgentBaseError("Third-party skills cannot shadow reserved AgentBase names.")
    license_info = licenses(files, "" if path == "." else path)
    for name, content in license_info.pop("files").items():
        destination = "source-notices/" + name
        if destination in selected:
            raise AgentBaseError("Source notice destination conflict.")
        selected[destination] = content
    findings = scan(selected)
    if license_info["status"] != "identified":
        findings.append(finding("license-unresolved", "high", "SKILL.md", "Missing, ambiguous or unrecognized license", "Resolve usage rights before installation; acknowledgement does not grant rights."))
    record = {"id": info["name"], "repository": url, "commit": sha, "requested_ref": ref,
              "subdirectory": path, "installed_at": datetime.now(UTC).isoformat(), "license": license_info,
              "metadata": info, "dependencies": info["dependencies"], "findings": findings,
              "hashes": {p: digest(v) for p, v in selected.items()}, "targets": []}
    return record, selected


def validate_record(record: dict, name: str) -> None:
    required = {"id", "repository", "commit", "requested_ref", "subdirectory", "installed_at", "license", "metadata", "dependencies", "findings", "hashes", "targets"}
    if (not isinstance(record, dict) or set(record) != required or record.get("id") != name
            or not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name) or name.startswith("agentbase-")):
        raise AgentBaseError("Invalid skill lock identity.")
    ref = record["requested_ref"]
    if not isinstance(ref, str) or not ref.strip() or len(ref) > 200 or any(ord(c) < 32 for c in ref):
        raise AgentBaseError("Invalid requested Git ref in skill lock.")
    if (not isinstance(record["metadata"], dict) or record["metadata"].get("name") != name
            or not isinstance(record["metadata"].get("providers"), list)
            or any(not isinstance(t, str) or t not in TARGETS for t in record["metadata"]["providers"])
            or not isinstance(record["license"], dict) or not isinstance(record["findings"], list)
            or not isinstance(record["dependencies"], list)
            or any(not isinstance(d, str) for d in record["dependencies"])):
        raise AgentBaseError("Invalid skill metadata, findings or dependencies in lock.")
    for entry in record["findings"]:
        if (not isinstance(entry, dict) or set(entry) != {"id", "rule", "severity", "file", "evidence", "action"}
                or any(not isinstance(v, str) for v in entry.values()) or entry["severity"] not in {"high", "medium", "low"}):
            raise AgentBaseError("Invalid skill security finding.")
    if not isinstance(record.get("commit"), str) or not SHA.fullmatch(record["commit"]):
        raise AgentBaseError("Invalid skill commit pin.")
    repository(record.get("repository"))
    if record.get("subdirectory") != ".":
        relative(record.get("subdirectory"))
    targets = record.get("targets")
    if (not isinstance(targets, list) or not targets or any(not isinstance(t, str) or t not in TARGETS for t in targets)
            or len(set(targets)) != len(targets)):
        raise AgentBaseError("Invalid provider targets in lockfile.")
    hashes = record.get("hashes")
    if not isinstance(hashes, dict) or not hashes or len(hashes) > MAX_FILES or "SKILL.md" not in hashes:
        raise AgentBaseError("Invalid skill file inventory.")
    seen = set()
    for path, hash_value in hashes.items():
        relative(path)
        if path.casefold() in seen or not isinstance(hash_value, str) or not HASH.fullmatch(hash_value):
            raise AgentBaseError("Invalid or duplicate file hash in skill lock.")
        seen.add(path.casefold())


def load(root: Path) -> dict:
    if not confined(root, LOCK).exists():
        return {"schema_version": 1, "skills": {}, "history": {}}
    value = read_json(confined(root, LOCK))
    if set(value) != {"schema_version", "skills", "history"} or value["schema_version"] != 1:
        raise AgentBaseError("Unsupported skill lock schema.")
    if not isinstance(value["skills"], dict) or not isinstance(value["history"], dict) or len(value["skills"]) > 100:
        raise AgentBaseError("Invalid skill index.")
    for name, record in value["skills"].items():
        validate_record(record, name)
    for name, records in value["history"].items():
        if name not in value["skills"] or not isinstance(records, list) or len(records) > 5:
            raise AgentBaseError("Invalid rollback history.")
        for record in records:
            validate_record(record, name)
    return value


def destinations(record: dict) -> dict[str, str]:
    return {f"{TARGETS[t]}/{record['id']}/{path}": path for t in record["targets"] for path in record["hashes"]}


def modifications(root: Path, record: dict) -> list[str]:
    changed = []
    for name, path in destinations(record).items():
        file = confined(root, name)
        if not file.is_file() or file.stat().st_size > MAX_FILE or digest(file.read_bytes()) != record["hashes"][path]:
            changed.append(name)
    # Untracked files inside an installed skill prevent update/removal too.
    owned = set(destinations(record))
    for target in record["targets"]:
        base = confined(root, f"{TARGETS[target]}/{record['id']}")
        if base.is_dir():
            for file in base.rglob("*"):
                name = file.relative_to(root).as_posix()
                confined(root, name)
                if file.is_file() and name not in owned:
                    changed.append(name)
    return sorted(set(changed))


def plan(root: Path, record: dict, files: dict[str, bytes], old: dict | None = None) -> tuple[dict, dict]:
    validate_record(record, record["id"])
    if set(record["targets"]) - set(record["metadata"]["providers"]):
        raise AgentBaseError("Skill declares incompatible provider targets.")
    if set(files) != set(record["hashes"]) or any(digest(v) != record["hashes"][p] for p, v in files.items()):
        raise AgentBaseError("Skill snapshot hash mismatch.")
    if old and modifications(root, old):
        raise AgentBaseError("Local modifications or missing installed files; preserve/restore them before changing skill.")
    existing = destinations(old) if old else {}
    changes = {p: None for p in existing}
    conflicts = []
    for dest, source in destinations(record).items():
        if dest not in existing and confined(root, dest).exists():
            conflicts.append(dest)
        changes[dest] = files[source]
    # Refuse any preexisting unmanaged skill directory, including empty directories.
    if old is None:
        conflicts += [f"{TARGETS[t]}/{record['id']}" for t in record["targets"]
                      if confined(root, f"{TARGETS[t]}/{record['id']}").exists()]
    for path, data in files.items():
        dest = f".agentbase/registry/{record['id']}/{record['commit']}/{path}"
        target = confined(root, dest)
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            conflicts.append(dest)
        changes[dest] = data
    report = {"skill": record["id"], "repository": record["repository"], "commit": record["commit"],
              "previous_commit": old["commit"] if old else None, "license": record["license"],
              "dependencies": record["dependencies"], "targets": record["targets"],
              "dependency_availability": inspect_dependencies(record["dependencies"], installed_skills=load(root)["skills"]),
              "compatibility": record["metadata"].get("compatibility", "not declared"),
              "scripts": [p for p in record["findings"] if p["rule"] == "script"],
              "findings": record["findings"], "conflicts": sorted(set(conflicts)),
              "permissions": ["project file writes"], "executes_code": False,
              "files": [{"path": p, "action": "remove" if v is None else "write"} for p, v in changes.items()],
              "required_acknowledgements": [f["id"] for f in record["findings"] if f["severity"] == "high"],
              "scan_note": "No issues detected by implemented checks does not guarantee safety."}
    report["plan_id"] = digest(json_text({"record": {k: v for k, v in record.items() if k != "installed_at"}, "files": report["files"]}))
    return report, changes


def apply(root: Path, record: dict, files: dict[str, bytes], *, dry_run: bool = True,
          acknowledgements: list[str] = (), update: bool = False, expected_plan: str | None = None) -> dict:
    def prepare():
        lock = load(root)
        old = lock["skills"].get(record["id"])
        if update != (old is not None):
            raise AgentBaseError("Skill already installed; use update." if old else "Skill not installed.")
        report, changes = plan(root, record, files, old)
        if not dry_run:
            if expected_plan != report["plan_id"]:
                raise AgentBaseError("Review the plan, then use --apply --plan-id with its exact plan_id; upstream changes require a new review.")
            if report["conflicts"]:
                raise AgentBaseError("Skill installation conflicts: " + ", ".join(report["conflicts"]))
            if set(report["required_acknowledgements"]) - set(acknowledgements):
                raise AgentBaseError("Explicit --acknowledge ID required for each high-severity finding in the reviewed plan.")
            if old:
                lock["history"][record["id"]] = (lock["history"].get(record["id"], []) + [old])[-5:]
            lock["skills"][record["id"]] = record
            if len(lock["skills"]) > 100:
                raise AgentBaseError("Skill index exceeds 100 installations.")
            lock_text = json_text(lock)
            if len(lock_text.encode("utf-8")) > MAX_LOCK:
                raise AgentBaseError("Skill lock exceeds storage limit; archive older installations before adding more.")
            changes[LOCK] = lock_text  # lock last, expose interrupted-file drift
            batch_write(root, changes)
        return report | {"dry_run": dry_run}
    if dry_run:
        return prepare()
    with project_lock(root):
        return prepare()


def add(root: Path, url: str, *, ref: str = "HEAD", path: str | None = None,
        targets: list[str] | None = None, yaml_parser: str = "stdlib", **options) -> dict:
    record, files = fetch(url, ref, path, yaml_parser=yaml_parser)
    record["targets"] = targets or ["codex", "claude"]
    if set(record["targets"]) - set(record["metadata"]["providers"]):
        raise AgentBaseError("Skill declares incompatible provider targets.")
    return apply(root, record, files, **options)


def update(root: Path, name: str, *, ref: str | None = None, yaml_parser: str = "stdlib", **options) -> dict:
    old = load(root)["skills"].get(name)
    if not old:
        raise AgentBaseError("Skill not installed.")
    record, files = fetch(old["repository"], ref or old["requested_ref"], old["subdirectory"], yaml_parser=yaml_parser)
    if record["id"] != name:
        raise AgentBaseError("Upstream renamed the skill; install separately after review.")
    record["targets"] = old["targets"]
    if set(record["targets"]) - set(record["metadata"]["providers"]):
        raise AgentBaseError("Updated skill declares incompatible providers.")
    return apply(root, record, files, update=True, **options)


def rollback(root: Path, name: str, **options) -> dict:
    lock = load(root)
    history = lock["history"].get(name, [])
    if not history:
        raise AgentBaseError("No recorded rollback version.")
    record = deepcopy(history[-1])
    files = {p: confined(root, f".agentbase/registry/{name}/{record['commit']}/{p}").read_bytes() for p in record["hashes"]}
    record["findings"] = scan(files)
    if record["license"].get("status") != "identified":
        record["findings"].append(finding("license-unresolved", "high", "SKILL.md", "Missing, ambiguous or unrecognized license", "Resolve usage rights before installation; acknowledgement does not grant rights."))
    return apply(root, record, files, update=True, **options)


def remove(root: Path, name: str, *, dry_run: bool = True) -> dict:
    def prepare():
        lock = load(root)
        record = lock["skills"].get(name)
        if not record:
            raise AgentBaseError("Skill not installed.")
        if modifications(root, record):
            raise AgentBaseError("Local modifications or missing files; removal refused.")
        changes = {p: None for p in destinations(record)}
        if not dry_run:
            del lock["skills"][name]
            lock["history"].pop(name, None)
            changes[LOCK] = json_text(lock)
            batch_write(root, changes)
            for target in record["targets"]:
                base = confined(root, f"{TARGETS[target]}/{name}")
                for directory in sorted((p for p in base.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                    directory.rmdir()
                base.rmdir()
        return {"dry_run": dry_run, "remove": list(changes), "snapshots_retained": True}
    if dry_run:
        return prepare()
    with project_lock(root):
        return prepare()


def restore(root: Path, exported: dict, *, dry_run: bool = True, acknowledgements: list[str] = (),
            expected_plan: str | None = None, yaml_parser: str = "stdlib") -> dict:
    records = exported.get("skills", {})
    if exported.get("schema_version") != 1 or not isinstance(records, dict) or not 1 <= len(records) <= 100:
        raise AgentBaseError("Restore requires a schema_version 1 lock containing 1..100 skills.")
    # Validate everything before fetching; then stage all source bytes before any writes.
    for name, old in records.items():
        validate_record(old, name)
    staged, byte_count = [], 0
    for name, old in sorted(records.items()):
        record, files = fetch(old["repository"], old["commit"], old["subdirectory"], yaml_parser=yaml_parser)
        record["targets"] = old["targets"]
        record["requested_ref"] = old["requested_ref"]
        if record["id"] != name or record["hashes"] != old["hashes"]:
            raise AgentBaseError("Restored source does not match exported hashes/identity.")
        byte_count += sum(len(v) for v in files.values()) * (len(record["targets"]) + 1)
        if byte_count > 96_000_000:
            raise AgentBaseError("Restore transaction exceeds staged byte limit.")
        staged.append((record, files))

    def prepare():
        lock = load(root)
        reports, changes = [], {}
        for record, files in staged:
            name = record["id"]
            old = lock["skills"].get(name)
            if old and all(record[k] == old[k] for k in record if k != "installed_at"):
                record = deepcopy(old)
            report, writes = plan(root, record, files, old)
            if set(changes) & set(writes):
                raise AgentBaseError("Overlapping skill restore destinations.")
            changes.update(writes)
            reports.append(report)
            if old and old != record:
                lock["history"][name] = (lock["history"].get(name, []) + [old])[-5:]
            lock["skills"][name] = record
        if len(lock["skills"]) > 100:
            raise AgentBaseError("Skill index exceeds 100 installations.")
        body = json_text(lock)
        if len(body.encode("utf-8")) > MAX_LOCK:
            raise AgentBaseError("Skill lock exceeds storage limit.")
        required = sorted({a for r in reports for a in r["required_acknowledgements"]})
        conflicts = sorted({c for r in reports for c in r["conflicts"]})
        plan_id = digest(json_text([r["plan_id"] for r in reports]))
        if not dry_run:
            if expected_plan != plan_id:
                raise AgentBaseError("Review the entire restore plan, then use --apply --plan-id with its exact plan_id.")
            if conflicts:
                raise AgentBaseError("Skill installation conflicts: " + ", ".join(conflicts))
            if set(required) - set(acknowledgements):
                raise AgentBaseError("Explicit --acknowledge ID required for every high-severity restore finding.")
            changes[LOCK] = body
            batch_write(root, changes)
        return {"dry_run": dry_run, "plan_id": plan_id, "skills": reports, "conflicts": conflicts,
                "required_acknowledgements": required, "staged_bytes": byte_count, "executes_code": False}
    if dry_run:
        return prepare()
    with project_lock(root):
        return prepare()


def audit(root: Path) -> dict:
    result = []
    installed = load(root)["skills"]
    for name, record in installed.items():
        changed = modifications(root, record)
        snapshots = []
        for p, expected in record["hashes"].items():
            file = confined(root, f".agentbase/registry/{name}/{record['commit']}/{p}")
            if not file.is_file() or file.stat().st_size > MAX_FILE or digest(file.read_bytes()) != expected:
                snapshots.append(p)
        result.append({"id": name, "commit": record["commit"], "repository": record["repository"],
                       "modified_files": changed, "damaged_snapshots": snapshots,
                       "license": record["license"], "dependencies": record["dependencies"],
                       "dependency_availability": inspect_dependencies(record["dependencies"], installed_skills=installed),
                       "findings": record["findings"], "trust": "unreviewed-community"})
    return {"ok": all(not r["modified_files"] and not r["damaged_snapshots"] for r in result), "skills": result,
            "dependency_note": "Presence checks only; versions/capabilities are not verified. Dependencies are never installed or executed."}


def search(query: str = "") -> dict:
    return {"skills": [{"id": name, "trust": "official-agentbase", "source": "packaged"}
                       for name, text in skills().items() if query.casefold() in (name + text).casefold()],
            "sources": [entry for entry in json.loads(asset("sources.json"))
                        if query.casefold() in json_text(entry).casefold()],
            "note": "Offline curated discovery links only; no remote search, current availability or third-party approval implied."}

"""Bounded explicit retrieval and a secret-aware source inventory."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import limits
from .fs import AgentBaseError, confined, digest, relative

EXCLUDED_DIRS = {".git", ".agentbase", ".agents", ".codex", ".claude", "node_modules", "vendor",
                 ".venv", "venv", "__pycache__", "dist", "build", "target", ".next", ".idea"}
TEXT_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt",
                 ".go", ".rs", ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".vue", ".svelte",
                 ".json", ".toml", ".yaml", ".yml", ".xml", ".md", ".sql", ".sh", ".ps1"}


def sensitive(name: str) -> bool:
    parts = name.lower().split("/")
    return any(p.startswith(".env") or p in {".ssh", ".aws", "secrets", "credentials", "private",
                "auth.json", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"} or
               p.endswith((".pem", ".key", ".p12", ".pfx", ".keystore")) for p in parts)


def read_source(root: Path, name: str, max_bytes: int) -> tuple[str | None, str | None]:
    if sensitive(name):
        return None, "common secret path excluded"
    try:
        path = confined(root, name)
        if not path.is_file():
            return None, "not a regular file"
        if path.stat().st_size > max_bytes:
            return None, "file exceeds profile byte limit"
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            return None, "file grew beyond byte limit"
        if b"\0" in raw:
            return None, "binary file excluded"
        return raw.decode("utf-8"), None
    except (OSError, UnicodeError, AgentBaseError):
        return None, "unreadable, non-UTF-8 or linked path"


def retrieve(root: Path, names: list[str], config: dict) -> dict:
    budget = limits(config)
    accepted, skipped, seen_paths, seen_hashes = [], [], set(), set()
    total = 0
    for raw_name in names:
        name = relative(raw_name)
        if name.casefold() in seen_paths:
            skipped.append({"path": name, "reason": "duplicate path"})
            continue
        seen_paths.add(name.casefold())
        content, error = read_source(root, name, budget["max_file_bytes"])
        if error:
            skipped.append({"path": name, "reason": error})
            continue
        checksum = digest(content)
        size = len(content.encode("utf-8"))
        if checksum in seen_hashes:
            skipped.append({"path": name, "reason": "duplicate content"})
        elif total + size > budget["max_document_bytes"] or len(accepted) >= budget["max_files"]:
            skipped.append({"path": name, "reason": "aggregate context budget exceeded"})
        else:
            total += size
            seen_hashes.add(checksum)
            accepted.append({"path": name, "sha256": checksum, "bytes": size, "text": content})
    return {"profile": config["context_profile"], "bytes": total,
            "estimated_tokens": (sum(len(item["text"]) for item in accepted) + 3) // 4,
            "estimate_method": "characters / 4, rounded up; not a provider token count",
            "files": accepted, "skipped": skipped}


def candidate_paths(root: Path) -> tuple[list[str], bool, str]:
    """Honor Git ignores when available; deterministic bounded fallback otherwise."""
    try:
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                                 "--exclude-standard"], capture_output=True, timeout=10, check=False)
        if result.returncode == 0 and result.stdout:
            names = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
            return names[:10_000], len(names) > 10_000, "git ls-files (respects Git ignores)"
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        pass
    names = []
    for directory, subdirs, files in os.walk(root, followlinks=False):
        subdirs[:] = sorted(name for name in subdirs if name not in EXCLUDED_DIRS and not sensitive(name)
                            and not (Path(directory) / name).is_symlink()
                            and not (hasattr(Path(directory) / name, "is_junction") and
                                     (Path(directory) / name).is_junction()))
        for name in sorted(files):
            names.append((Path(directory) / name).relative_to(root).as_posix())
            if len(names) >= 10_000:
                return sorted(names), True, "bounded filesystem walk (Git ignores unavailable)"
    return sorted(names), False, "filesystem walk (Git ignores unavailable)"


def inventory(root: Path, config: dict) -> dict:
    budget = limits(config)
    paths, truncated, method = candidate_paths(root)
    found, skipped = {}, []
    for name in paths:
        if any(p in EXCLUDED_DIRS for p in name.split("/")) or sensitive(name):
            continue
        path = Path(name)
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ("Dockerfile", "Makefile"):
            continue
        if len(found) >= budget["max_files"]:
            truncated = True
            break
        content, error = read_source(root, name, budget["max_file_bytes"])
        if error:
            skipped.append({"path": name, "reason": error})
        else:
            found[name] = {"text": content, "sha256": digest(content),
                           "bytes": len(content.encode("utf-8"))}
    return {"files": found, "skipped": skipped, "truncated": truncated, "method": method}

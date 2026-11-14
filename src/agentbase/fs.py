"""Confined paths, exclusive cooperative locks, and recoverable file batches."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path


class AgentBaseError(ValueError):
    """An actionable user/configuration error."""


def relative(value: str, *, root_scope: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AgentBaseError("Use a nonempty project-relative POSIX path.")
    if value == "." and root_scope:
        return value
    parts = value.rstrip("/").split("/")
    if any(p in ("", ".", "..") or re.search(r'[<>:"|?*\x00-\x1f]', p) for p in parts):
        raise AgentBaseError(f"Unsafe relative path: {value!r}")
    if any(p.endswith((" ", ".")) or p.split(".")[0].upper() in
           {"CON", "PRN", "AUX", "NUL", *{f"COM{i}" for i in range(1, 10)},
            *{f"LPT{i}" for i in range(1, 10)}} for p in parts):
        raise AgentBaseError(f"Nonportable relative path: {value!r}")
    return "/".join(parts)


def confined(root: Path, name: str) -> Path:
    name = relative(name)
    root = root.resolve()
    target = root / name
    for item in [target, *target.parents]:
        if item == root:
            break
        # Junctions/reparse points on Windows must not bypass confinement either.
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise AgentBaseError(f"Refusing linked project path: {name}")
    if not target.resolve().is_relative_to(root):
        raise AgentBaseError(f"Path leaves project: {name}")
    return target


def digest(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def read_json(path: Path) -> dict:
    try:
        if path.stat().st_size > 4_000_000:
            raise AgentBaseError(f"JSON file exceeds 4 MB: {path.name}")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AgentBaseError(f"Cannot read JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise AgentBaseError(f"Expected JSON object in {path.name}")
    return value


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".agentbase-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def project_lock(root: Path):
    path = confined(root, ".agentbase/write.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise AgentBaseError("AgentBase writer active or stale .agentbase/write.lock. "
                             "Check the recorded PID before manually removing a stale lock.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json_text({"pid": os.getpid()}))
        yield
    finally:
        path.unlink(missing_ok=True)


def batch_write(root: Path, changes: dict[str, str | bytes | None]) -> None:
    """Caller holds project_lock. Preflight all paths; roll back ordinary I/O failures.

    Per-file replacement is atomic. A process/power failure across files is not a
    filesystem transaction; the installer manifest is written last to expose drift.
    """
    paths = {name: confined(root, name) for name in changes}
    created_parents = {parent for path in paths.values() for parent in path.parents
                       if parent != root.resolve() and parent.is_relative_to(root.resolve()) and not parent.exists()}
    previous = {}
    for name, path in paths.items():
        if path.exists() and not path.is_file():
            raise AgentBaseError(f"Expected regular file: {name}")
        previous[name] = path.read_bytes() if path.exists() else None
    touched = []
    try:
        for name, content in changes.items():
            touched.append(name)
            if content is None:
                paths[name].unlink(missing_ok=True)
            else:
                atomic_write(paths[name], content.encode("utf-8") if isinstance(content, str) else content)
    except OSError:
        for name in reversed(touched):
            if previous[name] is None:
                paths[name].unlink(missing_ok=True)
            else:
                atomic_write(paths[name], previous[name])
        # Preserve preexisting empty directories, but leave retries unblocked by
        # empty skill destinations created by this failed batch.
        for directory in sorted(created_parents, key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise

"""Read-only dependency presence checks; never import or execute declared tools."""

from __future__ import annotations

import os
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def inspect(declarations: list[str], *, installed_skills=()) -> list[dict]:
    results = []
    for declaration in declarations:
        kind, _, name = declaration.partition(":")
        status, evidence = "unknown", None
        if declaration == "Python 3.11+":
            status, evidence = ("available" if sys.version_info >= (3, 11) else "missing"), sys.version.split()[0]
        elif kind == "skill" and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            status = "available" if name in installed_skills else "missing"
        elif kind == "python-dist" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name):
            try:
                evidence, status = version(name), "available"
            except PackageNotFoundError:
                status = "missing"
        elif kind == "tool" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name):
            status = "missing"
            # No shell, which() current-directory search, version probes or imports.
            suffixes = [""] if os.name != "nt" else os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
            for directory in os.get_exec_path():
                base = Path(directory)
                if not base.is_absolute() or base.resolve() == Path.cwd().resolve():
                    continue
                if any((base / (name + suffix)).is_file() and os.access(base / (name + suffix), os.X_OK) for suffix in suffixes):
                    status = "available"
                    break
        results.append({"declaration": declaration, "status": status, "version": evidence})
    return results

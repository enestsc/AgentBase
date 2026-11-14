"""Incremental static facts. Cached imports resolve against the current inventory."""

from __future__ import annotations

import ast
import re
from pathlib import Path, PurePosixPath

from .fs import AgentBaseError, confined, digest, json_text, read_json

INDEX = ".agentbase/reports/structural-index.json"
ENGINE = "agentbase-static-v1"


def file_facts(name: str, text: str) -> dict:
    symbols, imports, calls, errors = [], [], [], []
    if name.endswith(".py"):
        try:
            tree = ast.parse(text, filename=name)
        except (SyntaxError, ValueError, RecursionError):
            return {"symbols": [], "imports": [], "calls": [], "errors": [name + ": Python syntax could not be parsed"]}
        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def visit_FunctionDef(self, node):
                self.symbol(node, "function")

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, node):
                self.symbol(node, "class")

            def symbol(self, node, kind):
                symbols.append({"file": name, "line": node.lineno, "name": ".".join([*self.stack, node.name]), "kind": kind})
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_Call(self, node):
                if isinstance(node.func, ast.Name):
                    callee = node.func.id
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    callee = node.func.value.id + "." + node.func.attr
                else:
                    callee = None
                if callee:
                    calls.append({"file": name, "line": node.lineno, "caller": ".".join(self.stack) or "<module>",
                                  "callee": callee, "kind": "Python lexical call candidate; target/runtime unverified"})
                self.generic_visit(node)
        try:
            Visitor().visit(tree)
        except RecursionError:
            errors.append(name + ": nested symbols/calls truncated")
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = node.module or ""
                if node.level:
                    parent = list(PurePosixPath(name).parent.parts)
                    if node.level > len(parent):
                        continue
                    if node.level > 1:
                        parent = parent[:-(node.level - 1)]
                    prefix = ".".join(parent + ([prefix] if prefix else []))
                modules = [prefix] + [prefix + "." + a.name for a in node.names]
            imports.extend({"module": module, "line": node.lineno, "kind": "Python static import"} for module in modules)
    elif PurePosixPath(name).suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        for match in re.finditer(r'''(?:from\s*|require\(\s*|import\s*)["'](\.[^"']+)["']''', text):
            imports.append({"module": match[1], "line": text.count("\n", 0, match.start()) + 1, "kind": "JS/TS lexical import (heuristic)"})
    if len(symbols) > 500 or len(imports) > 1000 or len(calls) > 1000:
        errors.append(name + ": per-file facts truncated")
    return {"symbols": symbols[:500], "imports": imports[:1000], "calls": calls[:1000], "errors": errors}


def load_index(root: Path) -> dict:
    path = confined(root, INDEX)
    if not path.exists():
        return {}
    value = read_json(path)
    if (set(value) != {"engine", "files", "sha256"} or value["engine"] != ENGINE or not isinstance(value["files"], dict)
            or value["sha256"] != digest(json_text(value["files"]))):
        raise AgentBaseError("Preserving invalid/edited structural index; move it before rebuilding.")
    for name, record in value["files"].items():
        confined(root, name)
        if (not isinstance(record, dict) or set(record) != {"sha256", "facts"} or not isinstance(record["facts"], dict)
                or set(record["facts"]) != {"symbols", "imports", "calls", "errors"}
                or any(not isinstance(v, list) for v in record["facts"].values())):
            raise AgentBaseError("Invalid structural index entry.")
        facts = record["facts"]
        for key, fields, maximum in (("symbols", {"file", "line", "name", "kind"}, 500),
                                     ("imports", {"module", "line", "kind"}, 1000),
                                     ("calls", {"file", "line", "caller", "callee", "kind"}, 1000)):
            if len(facts[key]) > maximum:
                raise AgentBaseError("Structural index fact limit exceeded.")
            for entry in facts[key]:
                if (not isinstance(entry, dict) or set(entry) != fields or type(entry["line"]) is not int or entry["line"] < 1
                        or any(not isinstance(v, str) or len(v) > 4000 for k, v in entry.items() if k != "line")
                        or ("file" in entry and entry["file"] != name)):
                    raise AgentBaseError("Invalid cached structural fact.")
        if len(facts["errors"]) > 10 or any(not isinstance(e, str) for e in facts["errors"]):
            raise AgentBaseError("Invalid cached parse limitations.")
    return value["files"]


def analyze_source(source: dict, cached: dict | None = None) -> dict:
    cached = cached or {}
    files, index, parsed, reused = source["files"], {}, 0, 0
    for name, item in files.items():
        if name in cached and cached[name]["sha256"] == item["sha256"]:
            facts = cached[name]["facts"]
            reused += 1
        else:
            facts = file_facts(name, item["text"])
            parsed += 1
        index[name] = {"sha256": item["sha256"], "facts": facts}
    module_map = {}
    for name in files:
        if name.endswith(".py"):
            bits = list(PurePosixPath(name).with_suffix("").parts)
            if bits[-1] == "__init__":
                bits.pop()
            module_map[".".join(bits)] = name
            if bits and bits[0] == "src":
                module_map[".".join(bits[1:])] = name
    symbols, edges, calls, errors = [], [], [], []
    for name, entry in index.items():
        facts = entry["facts"]
        symbols.extend(facts["symbols"])
        calls.extend(facts["calls"])
        errors.extend(facts["errors"])
        for item in facts["imports"]:
            if item["kind"] == "Python static import":
                target = module_map.get(item["module"])
            else:
                parts, escaped = [], False
                for part in str(PurePosixPath(name).parent / item["module"]).split("/"):
                    if part == "..":
                        if not parts:
                            escaped = True
                            break
                        parts.pop()
                    elif part != ".":
                        parts.append(part)
                base = "/".join(parts)
                candidates = [base] + [base + ext for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")] + [
                    base + "/index" + ext for ext in (".ts", ".tsx", ".js", ".jsx")]
                target = next((p for p in candidates if p in files), None) if not escaped else None
            if target and target != name:
                edges.append({"source": name, "target": target, "line": item["line"], "kind": item["kind"]})
    unique = {(e["source"], e["target"], e["line"], e["kind"]): e for e in edges}
    return {"symbols": symbols, "edges": [unique[k] for k in sorted(unique)], "calls": calls, "errors": errors,
            "index": {"engine": ENGINE, "files": index, "sha256": digest(json_text(index))},
            "cache": {"parsed": parsed, "reused": reused, "removed": len(set(cached) - set(files))}}


def index_changes(result: dict) -> dict[str, str]:
    text = json_text(result["index"])
    if len(text.encode("utf-8")) > 3_500_000:
        raise AgentBaseError("Structural index exceeds 3.5 MB; reduce the inventory profile.")
    return {INDEX: text}

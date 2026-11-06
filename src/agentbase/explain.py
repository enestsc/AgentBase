"""Evidence-backed structural maps. Static references are not runtime architecture."""

from __future__ import annotations

import ast
import html
import json
import re
from pathlib import Path, PurePosixPath

from .config import limits
from .context import inventory
from .fs import AgentBaseError, confined, digest

REPORT = ".agentbase/reports/project.md"
MARKER = "<!-- agentbase:structural-report -->"


def analyze(source: dict) -> tuple[list[dict], list[dict], list[str]]:
    files = source["files"]
    symbols, edges, errors = [], [], []
    module_map = {}
    for name in files:
        if name.endswith(".py"):
            path = PurePosixPath(name)
            bits = list(path.with_suffix("").parts)
            if bits[-1] == "__init__":
                bits.pop()
            module_map[".".join(bits)] = name
            if bits and bits[0] == "src":
                module_map[".".join(bits[1:])] = name
    for name, item in files.items():
        text = item["text"]
        if name.endswith(".py"):
            try:
                tree = ast.parse(text, filename=name)
            except (SyntaxError, ValueError, RecursionError):
                errors.append(name + ": Python syntax could not be parsed")
                continue
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append({"file": name, "line": node.lineno, "name": node.name,
                                    "kind": "class" if isinstance(node, ast.ClassDef) else "function"})
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    prefix = node.module or ""
                    if node.level:
                        parent = list(PurePosixPath(name).parent.parts)
                        if node.level > len(parent):
                            continue
                        if node.level > 1:
                            parent = parent[:-(node.level - 1)]
                        prefix = ".".join(parent + ([prefix] if prefix else []))
                    modules = [prefix] + [prefix + "." + alias.name for alias in node.names]
                for module in modules:
                    target = module_map.get(module)
                    if target and target != name:
                        edges.append({"source": name, "target": target, "line": node.lineno,
                                      "kind": "Python static import"})
        elif PurePosixPath(name).suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            # A lexical heuristic, explicitly labeled; comments/dynamic imports can confuse it.
            for match in re.finditer(r'''(?:from\s*|require\(\s*|import\s*)["'](\.[^"']+)["']''', text):
                raw = str(PurePosixPath(name).parent / match[1])
                parts = []
                for part in raw.split("/"):
                    if part == "..":
                        if parts:
                            parts.pop()
                    elif part != ".":
                        parts.append(part)
                base = "/".join(parts)
                candidates = [base] + [base + ext for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs")] + [
                    base + "/index" + ext for ext in (".ts", ".tsx", ".js", ".jsx")]
                target = next((p for p in candidates if p in files), None)
                if target and target != name:
                    edges.append({"source": name, "target": target, "line": text.count("\n", 0, match.start()) + 1,
                                  "kind": "JS/TS lexical import (heuristic)"})
    unique = {(e["source"], e["target"], e["line"], e["kind"]): e for e in edges}
    return symbols, [unique[k] for k in sorted(unique)], errors


def project_report(root: Path, config: dict) -> tuple[str, dict]:
    source = inventory(root, config)
    symbols, edges, errors = analyze(source)
    evidence = {name: {"sha256": info["sha256"], "bytes": info["bytes"]}
                for name, info in source["files"].items()}
    lines = [MARKER, "# Project structural map", "",
             "Generated from repository files; no application code or model was executed.",
             "Purpose and feature behavior require source walkthroughs using the explain-project skill.", "",
             f"Discovery: {source['method']}. Inspected {len(evidence)} files.",
             f"Inventory truncated: {source['truncated']}. Skipped unreadable/oversized files: {len(source['skipped'])}.",
             "Common secret paths, linked files, generated output and provider installations are excluded.", "",
             "## Observed file map", "", "| File | Bytes | SHA-256 prefix |", "| --- | ---: | --- |"]
    for name, info in list(evidence.items())[:60]:
        safe_name = name.replace("|", "&#124;").replace("`", "&#96;")
        lines.append(f"| `{safe_name}` | {info['bytes']} | `{info['sha256'][:12]}` |")
    if len(evidence) > 60:
        lines += ["", "File table capped at 60; use targeted context retrieval for remaining files."]
    lines += ["", "## Python top-level symbols", ""]
    lines += [f"- `{s['file']}:{s['line']}`: {s['kind']} `{s['name']}`" for s in symbols[:50]] or ["No Python symbols resolved."]
    lines += ["", "## Resolved local import graph", "",
              "Edges are static/lexical references, not proven runtime calls. Python dynamic loading,",
              "JS aliases, Java/Spring wiring and other languages need targeted host analysis.", ""]
    graph_edges, nodes = [], []
    for edge in edges:
        proposed = set(nodes) | {edge["source"], edge["target"]}
        if len(proposed) <= 24 and len(graph_edges) < 40:
            nodes = sorted(proposed)
            graph_edges.append(edge)
    if graph_edges:
        ids = {name: f"n{i}" for i, name in enumerate(nodes)}
        lines += ["```mermaid", "flowchart LR"]
        for name in nodes:
            label = json.dumps(html.escape(name), ensure_ascii=False)
            lines.append(f"  {ids[name]}[{label}]")
        for edge in graph_edges:
            lines.append(f"  {ids[edge['source']]} --> {ids[edge['target']]}")
        lines += ["```", "", "Import evidence:", ""]
        lines += [f"- `{e['source']}:{e['line']}` → `{e['target']}` ({e['kind']})" for e in graph_edges]
    else:
        lines += ["No local import edges resolved; this does not establish that components are independent."]
    lines += ["", "## Next reads and verification", "",
              "Read the project's README and relevant dependency manifests, then trace an entry point",
              "to its called components and tests. Cite source locations for semantic claims.",
              "No tests were run by this command. No runtime/deployment architecture is inferred."]
    if errors:
        lines += ["", "Parse limitations:", *["- " + error for error in errors[:10]]]
    report = "\n".join(lines) + "\n"
    cap = limits(config)["max_document_bytes"]
    if len(report.encode("utf-8")) > cap:
        # Preserve complete Markdown blocks; omit the largest optional section first.
        start = report.index("## Resolved local import graph")
        end = report.index("## Next reads and verification")
        report = report[:start] + "Import graph omitted to fit context budget. Retrieve selected source files.\n\n" + report[end:]
    if len(report.encode("utf-8")) > cap:
        report = MARKER + "\n# Project structural map\n\nReport exceeds the configured document budget. "
        report += f"Inspected {len(evidence)} files; use a larger budget or targeted context retrieval.\n"
    return report, {"schema_version": 1, "files": evidence, "truncated": source["truncated"],
                    "report_sha256": digest(report)}


def report_changes(root: Path, report: str) -> dict[str, str]:
    path = confined(root, REPORT)
    if path.exists() and not path.read_text(encoding="utf-8").startswith(MARKER):
        raise AgentBaseError("Preserving unmarked project report; move it before generating this report.")
    return {REPORT: report}

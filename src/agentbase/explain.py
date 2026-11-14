"""Evidence-backed structural maps. Static references are not runtime architecture."""

from __future__ import annotations

import html
import json
from pathlib import Path

from .config import limits
from .context import inventory
from .fs import AgentBaseError, confined, digest
from .intelligence import analyze_source, load_index

REPORT = ".agentbase/reports/project.md"
MARKER = "<!-- agentbase:structural-report -->"


def analyze(source: dict) -> tuple[list[dict], list[dict], list[str]]:
    result = analyze_source(source)
    return result["symbols"], result["edges"], result["errors"]


def project_report(root: Path, config: dict, *, feature: str | None = None) -> tuple[str, dict]:
    source = inventory(root, config)
    structural = analyze_source(source, load_index(root))
    symbols, edges, errors = structural["symbols"], structural["edges"], structural["errors"]
    if feature is not None:
        if not feature.strip() or len(feature) > 100:
            raise AgentBaseError("Feature query must contain 1..100 characters.")
        matches = {n for n, f in source["files"].items() if feature.casefold() in (n + "\n" + f["text"]).casefold()}
        neighbors = {e[k] for e in edges if e["source"] in matches or e["target"] in matches for k in ("source", "target")}
        selected = matches | neighbors
        source = source | {"files": {n: f for n, f in source["files"].items() if n in selected}}
        symbols = [s for s in symbols if s["file"] in selected]
        edges = [e for e in edges if e["source"] in selected and e["target"] in selected]
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
    if feature is not None:
        lines += ["", "Feature query: " + html.escape(repr(feature)) + ". Lexical matches and one-hop import neighbors only; semantic relevance is unverified."]
    if len(evidence) > 60:
        lines += ["", "File table capped at 60; use targeted context retrieval for remaining files."]
    lines += ["", "## Python symbols", ""]
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
    calls = [c for c in structural["calls"] if c["file"] in evidence]
    if calls:
        lines += ["", "Lexical call candidates (targets and runtime dispatch unverified):", ""]
        lines += [f"- `{c['file']}:{c['line']}`: `{c['caller']}` references `{c['callee']}`" for c in calls[:25]]
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
                    "report_sha256": digest(report), "structural": structural, "feature": feature}


def report_changes(root: Path, report: str) -> dict[str, str]:
    path = confined(root, REPORT)
    if path.exists() and not path.read_text(encoding="utf-8").startswith(MARKER):
        raise AgentBaseError("Preserving unmarked project report; move it before generating this report.")
    return {REPORT: report}

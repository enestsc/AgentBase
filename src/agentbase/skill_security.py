"""Deterministic inspection of untrusted skill bytes. Never executes content."""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from .fs import AgentBaseError, digest

NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def scalar(value: str) -> str:
    """Conservative YAML string subset; unsupported syntax fails closed."""
    value = value.strip()
    if value.startswith('"'):
        try:
            result = json.loads(value)
        except ValueError as exc:
            raise AgentBaseError("Use JSON-compatible double-quoted YAML strings.") from exc
        if not isinstance(result, str):
            raise AgentBaseError("Expected a metadata string.")
        return result
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if not value or value[0] in "!&*[{>|'" or ": " in value:
        raise AgentBaseError("Unsupported YAML syntax; use plain/quoted strings or block scalars.")
    return value.split(" #", 1)[0].rstrip()


def yaml_mapping(text: str) -> dict:
    """Opt-in SafeLoader syntax, with bounded nodes and no aliases/tags/duplicates."""
    try:
        import yaml
    except ImportError as exc:
        raise AgentBaseError("Optional YAML parser unavailable; install agentbase-toolkit[yaml] explicitly or use stdlib syntax.") from exc
    try:
        tokens = list(yaml.scan(text))
        if len(tokens) > 4096 or any(isinstance(t, (yaml.AliasToken, yaml.AnchorToken, yaml.TagToken)) for t in tokens):
            raise AgentBaseError("YAML aliases, anchors, explicit tags or excessive nodes are refused.")
        node = yaml.compose(text, Loader=yaml.SafeLoader)

        def convert(item, depth=0):
            if depth > 2:
                raise AgentBaseError("Skill metadata must be a shallow string mapping.")
            if isinstance(item, yaml.ScalarNode) and item.tag == "tag:yaml.org,2002:str":
                return item.value
            if not isinstance(item, yaml.MappingNode) or item.tag != "tag:yaml.org,2002:map":
                raise AgentBaseError("Skill YAML values must be strings or string mappings.")
            result = {}
            for key, value in item.value:
                name = convert(key, depth + 1)
                if not isinstance(name, str) or name in result:
                    raise AgentBaseError("Duplicate/non-string YAML mapping key.")
                result[name] = convert(value, depth + 1)
            return result
        return convert(node)
    except (yaml.YAMLError, RecursionError) as exc:
        raise AgentBaseError("Invalid or excessively nested safe YAML frontmatter.") from exc


def metadata(text: str, directory: str | None = None, *, parser: str = "stdlib") -> dict:
    lines = text.replace("\r\n", "\n").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise AgentBaseError("SKILL.md requires YAML frontmatter.")
    end = lines.index("---", 1)
    if len("\n".join(lines[1:end]).encode("utf-8")) > 65_536:
        raise AgentBaseError("Skill frontmatter exceeds 64 KiB.")
    if parser not in {"stdlib", "pyyaml"}:
        raise AgentBaseError("Unknown YAML parser.")
    result, i = {}, 1
    allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    if parser == "pyyaml":
        result = yaml_mapping("\n".join(lines[1:end]))
        i = end
    while i < end:
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([a-z-]+):\s*(.*)", line)
        if not match or match[1] not in allowed or match[1] in result:
            raise AgentBaseError("Unsupported/duplicate skill frontmatter key or indentation.")
        key, value = match.groups()
        if key == "metadata":
            if value:
                raise AgentBaseError("metadata must be an indented string mapping.")
            mapping = {}
            while i < end and (lines[i].startswith("  ") or not lines[i].strip()):
                if lines[i].strip():
                    pair = re.fullmatch(r"  ([A-Za-z0-9_.-]+):\s*(.+)", lines[i])
                    if not pair or pair[1] in mapping:
                        raise AgentBaseError("Invalid metadata mapping.")
                    mapping[pair[1]] = scalar(pair[2])
                i += 1
            result[key] = mapping
        elif value in {"|", ">", "|-", ">-"}:
            block = []
            while i < end and (lines[i].startswith("  ") or not lines[i].strip()):
                block.append(lines[i][2:] if lines[i] else "")
                i += 1
            result[key] = ("\n" if value.startswith("|") else " ").join(block).strip()
        else:
            result[key] = scalar(value)
    if (not isinstance(result, dict) or set(result) - allowed
            or any(not isinstance(v, str) for k, v in result.items() if k != "metadata")
            or not isinstance(result.get("metadata", {}), dict)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in result.get("metadata", {}).items())):
        raise AgentBaseError("Skill frontmatter requires supported string fields and string metadata mapping.")
    name, description = result.get("name", ""), result.get("description", "")
    if len(name) > 64 or not NAME.fullmatch(name) or (directory is not None and name != directory):
        raise AgentBaseError("Skill name must be portable lowercase kebab-case and match its directory.")
    if not description.strip() or len(description) > 1024 or not "\n".join(lines[end + 1:]).strip():
        raise AgentBaseError("Skill requires description (1..1024 characters) and instruction body.")
    if "compatibility" in result and not 1 <= len(result["compatibility"].strip()) <= 500:
        raise AgentBaseError("compatibility must contain 1..500 characters.")
    for key in ("agentbase-dependencies", "agentbase-providers"):
        raw = result.get("metadata", {}).get(key, "[]" if key.endswith("dependencies") else '["codex", "claude"]')
        try:
            values = json.loads(raw)
        except ValueError as exc:
            raise AgentBaseError(f"metadata.{key} must contain a JSON string array.") from exc
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise AgentBaseError(f"Invalid {key}.")
        if key.endswith("providers") and (not values or set(values) - {"codex", "claude"}):
            raise AgentBaseError("Unknown provider compatibility.")
        result[key.removeprefix("agentbase-")] = values
    return result


RULES = [
    ("destructive", "high", r"\b(?:rm\s+-[rf]|Remove-Item|rmtree|unlink\(|format\s+[a-z]:)", "Review destructive filesystem operations."),
    ("network", "high", r"\b(?:curl|wget|Invoke-WebRequest|requests\.|urllib\.|fetch\(|https?://)", "Review network destinations and transmitted data."),
    ("credentials", "high", r"(?:os\.environ|process\.env|\$env:|API_KEY|PRIVATE.KEY|credentials|\.ssh/)", "Remove credential access or explicitly review its necessity."),
    ("execution", "high", r"(?:subprocess|os\.system|child_process|Invoke-Expression|\beval\(|\bexec\(|\bbash\s|\bpowershell\s)", "Review external command execution; no imported code is run by AgentBase."),
    ("dependency-install", "high", r"(?:pip\s+install|npm\s+(?:install|ci)|postinstall|preinstall|setup\.py)", "Review dependency provenance and installation hooks separately."),
    ("instruction-override", "high", r"(?:ignore.{0,40}(?:previous|prior|system|instructions)|override.{0,30}(?:policy|instructions)|disable.{0,30}(?:sandbox|security)|exfiltrat)", "Treat instructions as untrusted; reject attempts to override host policy."),
]


def finding(rule: str, severity: str, path: str, evidence: str, action: str) -> dict:
    return {"id": digest(rule + path + evidence)[:16], "rule": rule, "severity": severity,
            "file": path, "evidence": evidence[:180], "action": action}


def scan(files: dict[str, bytes]) -> list[dict]:
    findings = []
    for path, data in sorted(files.items()):
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in {".exe", ".dll", ".so", ".dylib", ".com", ".msi", ".bin", ".pyc"} or data.startswith((b"MZ", b"\x7fELF")):
            raise AgentBaseError(f"Executable binary is not accepted: {path}")
        if (suffix in {".sh", ".ps1", ".bat", ".cmd", ".py", ".js", ".mjs", ".cjs", ".ts", ".rb"}
                or "scripts" in PurePosixPath(path).parts or data.startswith(b"#!")):
            findings.append(finding("script", "high", path, "Executable source included", "Review script before exposing it to a provider; acknowledgement enables installation, never execution."))
        if any(p.startswith(".") for p in PurePosixPath(path).parts):
            findings.append(finding("hidden-file", "medium", path, "Hidden path included", "Inspect hidden configuration."))
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            findings.append(finding("binary-asset", "medium", path, "Non-UTF-8 asset", "Inspect binary asset manually."))
            continue
        for rule, severity, pattern, action in RULES:
            match = re.search(pattern, text, re.I)
            if match:
                line = text[:match.start()].count("\n") + 1
                findings.append(finding(rule, severity, path, f"line {line}: {match[0]}", action))
    return findings


def licenses(files: dict[str, bytes], subdir: str) -> dict:
    """Keep notices at root and every ancestor; an SPDX label is not legal advice."""
    parents = {""}
    parts = subdir.split("/") if subdir else []
    parents.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    notices = {path: data for path, data in files.items() if ("" if str(PurePosixPath(path).parent) == "." else str(PurePosixPath(path).parent)) in parents
               and re.match(r"^(?:LICENSE|LICENCE|COPYING|NOTICE|AUTHORS)(?:[._-].*)?$", PurePosixPath(path).name, re.I)}
    identified, unresolved = set(), not any(re.match(r"^(LICENSE|LICENCE|COPYING)", PurePosixPath(p).name, re.I) for p in notices)
    for path, data in notices.items():
        text = data.decode("utf-8", errors="replace")
        normalized = re.sub(r"\s+", " ", text)
        found = set()
        for spdx, signature in [("MIT", "Permission is hereby granted, free of charge"),
                                ("Apache-2.0", "Apache License, Version 2.0"), ("BSD-3-Clause", "Neither the name"),
                                ("ISC", "Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee")]:
            if signature in text or (spdx == "Apache-2.0" and re.search(r"Apache License,? Version 2\.0", normalized)):
                found.add(spdx)
        if ("Redistribution and use in source and binary forms" in normalized
                and "Redistributions of source code must retain" in normalized
                and "Redistributions in binary form must reproduce" in normalized
                and "Neither the name" not in text):
            found.add("BSD-2-Clause")
        declared = re.findall(r"SPDX-License-Identifier:\s*([^\r\n]+)", text)
        for declaration in declared:
            if declaration.strip() in {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "CC0-1.0"}:
                found.add(declaration.strip())
            else:
                unresolved = True
        identified.update(found)
        if re.search(r"Commons Clause|Noncommercial|non-commercial|Business Source|additional restrictions", text, re.I):
            unresolved = True
        if re.match(r"^(LICENSE|LICENCE|COPYING)", PurePosixPath(path).name, re.I) and not found:
            unresolved = True
    return {"status": "identified" if len(identified) == 1 and not unresolved else "unresolved", "spdx_candidates": sorted(identified),
            "notices": sorted(notices), "files": notices}

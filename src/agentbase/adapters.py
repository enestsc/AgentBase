"""Generate provider-native discovery files from canonical role/skill content."""

import json

from .catalog import asset, role_prompt, roles, skills


def render(providers: list[str], *, role_ids: list[str] | None = None,
           skill_ids: list[str] | None = None) -> dict[str, str]:
    result = {".agentbase/policy.md": asset("policy.md")}
    for role in roles():
        if role_ids is not None and role["id"] not in role_ids:
            continue
        name = "agentbase-" + role["id"]
        body = role_prompt(role)
        result[f".agentbase/roles/{role['id']}.md"] = body
        if "codex" in providers:
            # JSON strings are a subset of TOML basic strings (including escapes).
            result[f".codex/agents/{name}.toml"] = "\n".join(
                f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in {
                    "name": name, "description": role["trigger"],
                    **role["model_recommendations"]["codex"],
                    "developer_instructions": body,
                }.items()) + "\n"
        if "claude" in providers:
            tools = ("Read, Grep, Glob, WebFetch, WebSearch" if role["access"] == "read" else
                     "Read, Grep, Glob, Edit, Write, Bash, PowerShell")
            result[f".claude/agents/{name}.md"] = (
                f"---\nname: {name}\ndescription: {json.dumps(role['trigger'])}\n"
                f"tools: {tools}\n"
                + "".join(f"{key}: {value}\n" for key, value in role["model_recommendations"]["claude"].items())
                + f"---\n\n{body}"
            )
    for name, body in skills().items():
        if skill_ids is not None and name not in skill_ids:
            continue
        if "codex" in providers:
            result[f".agents/skills/{name}/SKILL.md"] = body
        if "claude" in providers:
            result[f".claude/skills/{name}/SKILL.md"] = body
    return result


def instruction_bodies(providers: list[str]) -> dict[str, str]:
    # Claude uses native @ imports. Codex receives the same compact bootstrap inline.
    result = {"AGENTS.md": asset("bootstrap.md")} if "codex" in providers else {}
    if "claude" in providers:
        if "codex" in providers:
            result["CLAUDE.md"] = "@AGENTS.md\n"
        else:
            result["CLAUDE.md"] = asset("bootstrap.md")
    return result

"""Load the packaged canonical definitions, never the target project's versions."""

import json
from importlib.resources import files


def asset(name: str) -> str:
    return files("agentbase").joinpath("assets", name).read_text(encoding="utf-8")


def roles() -> list[dict]:
    return json.loads(asset("roles.json"))


def skills() -> dict[str, str]:
    directory = files("agentbase").joinpath("assets", "skills")
    return {item.name: item.joinpath("SKILL.md").read_text(encoding="utf-8")
            for item in sorted(directory.iterdir(), key=lambda item: item.name) if item.is_dir()}


def role_prompt(role: dict) -> str:
    return (
        f"# {role['title']} (Level {role['level']})\n\n"
        + "\n\n".join(f"{label}: {role[key]}" for label, key in (
            ("Primary responsibility", "responsibility"), ("Trigger", "trigger"),
            ("Non-responsibilities", "excludes"), ("Required inputs", "inputs"),
            ("Expected outputs", "outputs")))
        + f"\n\nRelevant skills (load only as needed): {', '.join(role['skills'])}.\n"
        + "\nAllowed tools: " + ("repository search/read and approved documentation lookup. "
            "No edits or commands with side effects." if role["access"] == "read" else
            "repository search/read, scoped edits and authorized checks. No external mutation without authorization.")
        + "\n\nOwnership: use only the assigned task scope. Read .agentbase/policy.md for coordination. "
        "Do not write shared task state, contracts or memory unless explicitly assigned as the sole writer. "
        "Do not delegate. Provider permissions may be broader than this policy.\n"
        + "\nHandoff: task ID, result, files changed, decisions, tests with observed results, failures, "
        "remaining risks and artifacts needed by dependents. Do not forward full history.\n"
        + "\nValidation: check the task acceptance criteria using repository evidence. "
        "Mark unexecuted checks and uncertainties explicitly. Escalate scope conflicts, missing inputs, "
        "failed checks and authorization needs to the Orchestrator.\n"
    )

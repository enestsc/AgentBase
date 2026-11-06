"""Versioned, deliberately small project configuration."""

from copy import deepcopy
from pathlib import Path

from .fs import AgentBaseError, confined, read_json

PROFILES = {
    "minimal": {"max_document_bytes": 12_000, "max_file_bytes": 40_000,
                "max_files": 200, "max_handoff_chars": 3_000, "memory_max_chars": 12_000},
    "balanced": {"max_document_bytes": 32_000, "max_file_bytes": 100_000,
                 "max_files": 1000, "max_handoff_chars": 6_000, "memory_max_chars": 24_000},
    "deep": {"max_document_bytes": 96_000, "max_file_bytes": 250_000,
             "max_files": 3000, "max_handoff_chars": 12_000, "memory_max_chars": 48_000},
}
DEFAULT = {
    "schema_version": 1,
    "providers": ["codex", "claude"],
    "context_profile": "balanced",
    "context_overrides": {},
    "execution": {"mode": "sequential", "max_concurrency": 1},
    "local_model": {"enabled": False, "endpoint": "http://127.0.0.1:11434",
                    "model": "", "timeout_seconds": 30, "max_input_chars": 8000},
}


def validate_config(value: dict) -> dict:
    if set(value) != set(DEFAULT) or value.get("schema_version") != 1:
        raise AgentBaseError("Unsupported configuration schema/keys; use schema_version 1.")
    providers = value["providers"]
    if (not isinstance(providers, list) or not providers or
            any(p not in ("codex", "claude") for p in providers) or len(set(providers)) != len(providers)):
        raise AgentBaseError("providers must contain codex and/or claude without duplicates.")
    if value["context_profile"] not in PROFILES:
        raise AgentBaseError("context_profile must be minimal, balanced, or deep.")
    overrides = value["context_overrides"]
    if not isinstance(overrides, dict) or set(overrides) - set(PROFILES["balanced"]):
        raise AgentBaseError("Unknown context override.")
    for key, number in overrides.items():
        if type(number) is not int or not 1 <= number <= 1_000_000:
            raise AgentBaseError(f"context_overrides.{key} must be a positive bounded integer.")
    execution = value["execution"]
    if not isinstance(execution, dict) or set(execution) != {"mode", "max_concurrency"}:
        raise AgentBaseError("execution needs mode and max_concurrency.")
    if execution["mode"] not in ("sequential", "safe-parallel"):
        raise AgentBaseError("execution.mode must be sequential or safe-parallel.")
    count = execution["max_concurrency"]
    if type(count) is not int or not 1 <= count <= 32:
        raise AgentBaseError("max_concurrency must be an integer from 1 to 32.")
    if execution["mode"] == "sequential" and count != 1:
        raise AgentBaseError("Sequential execution requires max_concurrency 1.")
    local = value["local_model"]
    if not isinstance(local, dict) or set(local) != set(DEFAULT["local_model"]):
        raise AgentBaseError("Invalid local_model configuration keys.")
    if type(local["enabled"]) is not bool or not all(isinstance(local[k], str) for k in ("endpoint", "model")):
        raise AgentBaseError("local_model needs boolean enabled and string endpoint/model.")
    for key, ceiling in (("timeout_seconds", 300), ("max_input_chars", 100_000)):
        if type(local[key]) is not int or not 1 <= local[key] <= ceiling:
            raise AgentBaseError(f"local_model.{key} must be in 1..{ceiling}.")
    return deepcopy(value)


def load_config(root: Path) -> dict:
    return validate_config(read_json(confined(root, ".agentbase/config.json")))


def limits(config: dict) -> dict:
    return PROFILES[config["context_profile"]] | config["context_overrides"]

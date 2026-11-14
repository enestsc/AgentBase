# Native CLI contracts and synthetic runtime checks

`native.py` has two opt-in checks, both using a trusted preinstalled immutable
Linux image and a local Docker daemon. Python remains standard-library-only.
The image must supply `/usr/local/bin/codex` or `/usr/local/bin/claude`; synthetic
checks additionally need Node 20+ at `/usr/local/bin/node`. AgentBase does not
download, install, update, build, pull or publish these executables/images.
A digest or full local `sha256:` image ID establishes identity, not trust.

`eval capabilities --provider PROVIDER --image TRUSTED_PIN --consent` runs only
allowlisted version/help commands. Reported flags are version-specific; a help
entry is not proof of model execution, tool isolation or plugin effectiveness.
The host-only form without `--image` remains a separate explicit static probe.

`eval native-smoke --provider PROVIDER --image TRUSTED_PIN --consent` starts a
fixed synthetic API and the native CLI inside the **same network-disabled
container**. The loopback server uses the canonical gateway request checks with
an injected first-party fixture transport. It never selects the official
transport and has no external network. The only credential is a freshly generated
synthetic capability; there is no API-key argument, host credential discovery,
provider home mount or real upstream call. No project content is provided.

Before start, Docker inspection must confirm network `none`, non-root UID,
read-only root, exact read-only first-party program mounts, no host ports/volumes,
dropped capabilities, private process/IPC namespaces, memory/swap/CPU/PID limits,
and bounded local logs. The native child gets an explicit empty-home environment;
updates, telemetry, Claude experimental betas and Codex hosted web search are
disabled. Output collection and runtime are bounded. Host timeout removes the
entire container and verifies its absence, including descendant processes.
Docker's shared kernel, the daemon and supplied image remain trusted dependencies.

The fixture returns only `AGENTBASE_FIXTURE_OK`, never a tool call. Codex must
produce one agent message and a completed turn with no tool-execution events.
Claude must report one successful result and discover the canonical `agentbase`
plugin in its native initialization event. The plugin is regenerated through
`distribution.files`, not copied from project/imported plugin directories.
This establishes discovery and response decoding only; no skill invocation or
tool execution is verified. Native stdout, stderr, traces, session IDs, token
counts and list-price estimates are discarded. Reports return a small allowlist
of booleans, counts and versions, always labeled `origin: mock` with
`actual_model_behavior_verified: false`. A failed smoke returns CLI exit 1.

For Claude only, `--mode eval` executes its real `plugin eval` engine against one
first-party fixed prompt and a regex grader. One case, run, arm and concurrent
session; no scaffold, publishing, real MCP server, shell grant, judge model or
baseline arm. Versioned native results must be complete, contain one with-arm
run and no without-arm run, have no run error and report the fixture case passed.
This tests the native grading pipeline with a synthetic API response. It is not a
paid evaluation, quality score or measurement of the plugin's contribution.
Codex has no established native eval equivalent and refuses `--mode eval`.

The gateway now accepts exactly Claude's documented `?beta=true` Messages query,
mapping it to the same fixed official endpoint; arbitrary query parameters remain
refused. Codex client namespaces may contain only bounded function/custom tools;
hosted and nested namespace tools remain refused. Broad Claude beta pass-through,
remote media, hosted web tools and real-provider compatibility remain outside the
tested subset. Production credential-gateway launch is separate and is not
enabled by this synthetic check.

Primary references: [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[Responses client tool namespaces](https://developers.openai.com/api/docs/guides/tools),
[Claude gateway protocol](https://code.claude.com/docs/en/llm-gateway-protocol),
[Claude native evals](https://code.claude.com/docs/en/plugin-evals).

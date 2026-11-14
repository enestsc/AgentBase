# ADR 0003 — Separate provider credentials from model workers

Date: 2026-11-14. Status: gateway implemented/tested; not enabled for native runs.

Keep the verified offline worker intact. A provider worker must never receive a
real API key, provider home directory, host environment or Docker socket. A
separate short-lived gateway receives a credential through stdin, holds it in
memory, and injects it only into requests to a fixed official HTTPS upstream.
Workers get a random run-scoped gateway capability, not the provider credential.

Use a unique Docker internal network for gateway/worker traffic. Only the gateway
gets a second egress connection. No host ports are published. Inspect actual
network/container restrictions before serving requests. The optional gateway
uses a trusted preinstalled Node image and a packaged first-party program;
AgentBase's Python runtime remains stdlib-only. Never pull/build/install implicitly.

Policy fixes one provider, one model, allowed POST paths, input/output byte bounds,
maximum output tokens, maximum attempted requests, concurrency 1 and wall/I/O
deadlines. Reject redirects, CONNECT/upgrade, foreign routes/models, hosted tools,
remote files/images, detached/background requests and stored-server context.
Unknown formats fail closed. Do not forward worker authentication or arbitrary
headers; do not expose raw upstream errors. No request/response content is logged.

Request/token/byte/time limits are enforceable protocol bounds, not an exact
invoice/subscription cap. A disconnected upstream may continue work; report that
limitation. Native launch spending consent remains separate and disabled for now.
Initial tests use dummy credentials and a local fake transport; no real provider
or account is accessed.

Evidence: Python policy/bootstrap/cleanup tests, 15 Node protocol scenarios and
the real `gateway self-test` on Windows Docker Desktop. The real probe makes no
valid API call, verifies nine boundary observations and confirms lifetime expiry
terminates the credential process even while its stdin owner remains alive.
SSE is deliberately buffered within response/time bounds before redaction and
forwarding; this is not a complete transparent native gateway compatibility claim.
Later synthetic probes add the exact Claude beta query and bounded Codex client
tool namespaces; see ADR 0004. Production native gateway launch is still disabled.

Sources checked 2026-11-14:
[Codex provider settings](https://learn.chatgpt.com/docs/config-file/config-reference),
[Claude gateway credential separation](https://code.claude.com/docs/en/llm-gateway),
[Docker internal networks](https://docs.docker.com/reference/cli/docker/network/create/).

# Registry, usage, packs and specifications

Requires Python 3.11+. Install the Python package, then run commands from the
target project (or use global `--project PATH` before the command).

## Packs and project installation

```bash
agentbase packs list
agentbase packs recommend
agentbase packs info python
agentbase packs register --file my-pack.json --dry-run   # same manifest format as packs info
agentbase init --provider both --pack python --pack security --dry-run
agentbase init --provider both --pack python --pack security
agentbase packs add documentation --dry-run
agentbase packs add documentation
agentbase packs remove documentation --dry-run
agentbase update --dry-run
agentbase doctor
```

Core is implicit. `packs info` and installation reports check dependency presence
without importing or executing it. Machine-checkable declarations are `tool:NAME`,
`python-dist:NAME` and `skill:ID`; free text remains unknown. Presence does not
verify capabilities. Nothing is installed automatically.
Pack additions/removals preserve edited managed files by
refusing the operation. Legacy full-catalog init remains unchanged.
Custom packs select known canonical definitions only. Register the reviewed
manifest without `--dry-run`, then explicitly install its ID with `--pack` or
`packs add`. Registration cannot replace bundled pack IDs or silently overwrite
a different existing custom manifest.

## Reviewed GitHub installation

```bash
agentbase skills                       # original canonical listing
agentbase skills search verify
agentbase skills add https://github.com/owner/repository --path skills/example
# Inspect files, SHA, license, dependencies, findings, targets and conflicts.
agentbase skills add https://github.com/owner/repository --path skills/example --apply --plan-id REVIEWED_ID
# Append --acknowledge FINDING_ID separately for each reviewed high-severity issue.
agentbase skills list
agentbase skills info example
agentbase skills audit
agentbase skills update example        # previews the available pinned revision
agentbase skills update example --apply --plan-id REVIEWED_UPDATE_ID
agentbase skills rollback example      # inspect, then apply with rollback plan ID
agentbase skills export                # lock JSON on stdout
agentbase skills restore skills.lock.json   # one reviewed transaction for 1..100 skills
agentbase skills remove example        # preview
agentbase skills remove example --apply
```

Use `--ref BRANCH_OR_TAG_OR_SHA`; every resolution pins a full SHA. With multiple
SKILL.md candidates, choose `--path` explicitly. A changed upstream revision needs
a new reviewed plan. No dependency/script execution is part of installation.
Rollback retains five previous records; snapshots remain after removal.
Restore stages every pinned source before writing; conflicts, local edits, missing
acknowledgements or ordinary I/O failures prevent partial installation. Unrelated
skills remain intact. Process/power loss is not a filesystem transaction; audit
detects drift. Staged bytes are limited to 96 MB. `skills search` also lists packaged
curated discovery links marked unreviewed; no network search or approval is implied.
The default YAML parser remains stdlib-only. Explicitly install the optional
`agentbase-toolkit[yaml]` extra and pass `--yaml-parser pyyaml` to add/update/restore
for extended YAML syntax. Both parsers enforce string metadata; the optional
parser rejects aliases, anchors, explicit tags, duplicate keys and frontmatter
over 64 KiB. Redirected, private, oversized, linked or unsupported-YAML sources fail explicitly. Clean scanners
do not guarantee safety. See [trust model](../security/trust-model.md).
Remove installed third-party skills before core `uninstall --purge`; otherwise
purging refuses to discard the provenance needed for safe later removal.

## Usage capture and privacy

```bash
agentbase usage configure --source codex-exec-v1 --source claude-api-request-v1 --retention-days 30
agentbase usage import --file reviewed-captures.json
agentbase usage capture --source claude-statusline-v1 --provider-version INSTALLED_VERSION --project-id opaque-project < statusline-event.json
agentbase usage --today
agentbase usage --week --provider claude --by-agent --json --timezone UTC
agentbase usage --by-skill
agentbase usage export --format csv
agentbase usage delete --before 2026-10-01T00:00:00+03:00
agentbase usage configure              # disable every import source
agentbase usage delete --all           # explicitly delete retained records
```

The import JSON is an object with a `captures` array. Each capture uses:

```json
{
  "schema_version": 1,
  "source": "codex-exec-v1",
  "provider_version": "YOUR_CAPTURED_CLI_VERSION",
  "timestamp": "2026-11-10T15:00:00+03:00",
  "project_id": "opaque-project-id",
  "session_id": "captured-thread-id",
  "event_id": "stable-captured-turn-id",
  "event": {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}}
}
```

The numbers above are illustrative, **not measured usage**. Supply actual captured
metrics; never substitute unknown values with zero. `usage capture` reads one
documented JSON event from stdin (1 MB maximum), requires prior source opt-in,
and stores only allowlisted measurements. A user-managed Claude statusline command
or App Server consumer can pipe an event to it; AgentBase never edits host settings.
Snapshot identities derive from normalized measurements, so repeated observations
deduplicate. Incremental exec/request events require explicit stable `--session-id`
and `--event-id`; equal counters can belong to different requests. No provider,
credential reader or background collector is launched. Optional explicit
attribution uses `agentbase_correlation: {"id":"task-id","agent_id":"role-id",
"skill_id":"skill-id"}` only when the capture can substantiate it.

Use stable event IDs, one consumption source per session and opaque identifiers.
Claude statusline context counters are not session token consumption. Estimates
are not billed charges or subscription quota. Store `.agentbase/usage` privately
and ignore it in Git. [Adapter and metric semantics](../architecture/usage-pipeline.md).
Cross-day cumulative intervals appear in `unallocated_intervals`, excluded from
daily totals and from a selected period when straddling its start. Retained totals
can include measured interval deltas. Cumulative agent attribution requires matching
correlation evidence at both endpoints.

## Specifications and evaluation

```bash
agentbase spec init health --title "Health endpoint" --request "Add GET /health" --criterion "GET /health returns 200" --scope src
# Edit .agentbase/specs/health.md: assumptions, architecture, requirements/dependencies.
agentbase spec validate health
agentbase spec plan health --write
agentbase spec tasks health --import   # requires initialized, empty task store
agentbase spec reconcile health        # preview changes after editing the spec
agentbase spec reconcile health --apply --plan-id REVIEWED_ID
agentbase spec evidence health         # report criterion-to-handoff evidence
agentbase tasks ready                  # host owns execution and evidence
agentbase eval validate
agentbase eval run                     # saves offline static report
agentbase eval run --suite examples/evaluation-suite.json --observations examples/evaluation-observations.mock.json
agentbase eval report
```

Explicit requirements compile to existing DAG tasks; no semantic decomposition
or model call is implied. Evaluations grade supplied observations, whose origin
is labeled mock/manual/provider-capture. Schema-valid evidence does not prove a
model ran. Paid native evaluations remain separate and require authorization.
Reconciliation updates/removes only owned pending tasks without evidence, adds
new requirements, and preserves unrelated tasks and unchanged runtime state.
Started/completed requirements need follow-up requirements instead of rewritten
acceptance criteria. Local task/generated-file edits stop reconciliation. Plan IDs
bind the specification, active ownership and current DAG state.
`spec evidence health --file mapping.json` binds exact acceptance strings to stored
handoff test indexes, for example `{"schema_version":1,"requirements":{"R1":[{"criterion":"GET /health returns 200","tests":[0]}]}}`.
Reports label these observations `reported-passed`, never independently verified
execution. Source or handoff changes make the mapping stale; no tests are run.

## Optional local plugin artifacts

```bash
agentbase plugins build --provider claude --output packages/claude-v1 --dry-run
agentbase plugins build --provider claude --output packages/claude-v1
agentbase plugins validate --output packages/claude-v1
claude plugin validate packages/claude-v1
agentbase plugins build --provider codex --output packages/codex-v1
```

Choose fresh output for upgrades; existing different files are not overwritten.
Local Claude testing: `claude --plugin-dir ./packages/claude-v1` starts a model
session, so do this only when you intend provider usage. Alternatively add the
local marketplace with `/plugin marketplace add ./packages/claude-v1`, then
`/plugin install agentbase@agentbase-local`. No such installation is automatic.
Codex local marketplace entries point to the generated package using a `./` path
relative to the marketplace root; see the [official format](https://developers.openai.com/plugins/build/plugins).
Initialize CLI state with `agentbase init --discovery plugin` to avoid duplicate
bundled skills/Claude agents. Existing standalone projects can preview and apply
`agentbase update --discovery plugin`; hash checks protect local edits. Codex
agents remain standalone alongside plugin skills. The CLI remains a separate
Python installation; packaging does not install or activate a plugin.


## Incremental maps and local proposals

`agentbase explain --write` and deep memory sync cache structural facts by file
SHA-256 under `.agentbase/reports/structural-index.json`. Changed files are parsed
again; imports resolve against the current inventory, including added/deleted
modules. The cache stores symbols, import/call references and hashes, not raw
source. Corrupt/edited cache data is preserved with an actionable error.
`agentbase explain --feature authentication` limits the report to lexical matches
and one-hop import neighbors. Mermaid edges cite real source lines. Python nested
symbols and call candidates are shown; target resolution, runtime dispatch and
feature semantics remain unverified. No optional external indexing tool is needed.

`agentbase local models --consent` explicitly queries the configured loopback
Ollama inventory. Summarize/classify now require an exactly named installed local
model with completion capability and sufficient advertised context. Config keys
`context_tokens`, `max_output_tokens`, `max_model_bytes`, `max_loaded_bytes` and
`structured` extend existing local configuration; old configurations receive
defaults. Requests set `num_ctx`, `num_predict`, `keep_alive: 0` and a JSON schema.
Replies undergo local schema/role validation and remain untrusted proposals.
Memory is never overwritten. `--fallback` returns host-review guidance on failure,
without calling another provider. Metadata is queried before source text is sent.
Memory checks use advertised disk/resident sizes, **not an OS RAM/VRAM cap**.
Socket I/O timeouts and a preflight deadline do not guarantee that a disconnected
server stops inference. No models, dependencies or external inference are downloaded/launched.


## Offline workers and native checks

`agentbase tasks sandbox TASK_ID --worker reviewed-worker.json --context src/app.py --consent`
requires the task to be running in the existing DAG. Worker policy fields are
`schema_version: 1`, `provider: "deterministic"`, trusted preinstalled `image`
(`repository@sha256:` plus 64 hex digits), absolute in-image `entrypoint`, literal
`arguments` array, `timeout_seconds` (1..300), `memory_mb` (32..4096), `pids` (4..128).
Review the exact image and command before consenting. Pinning does not establish trust.
Locally built trusted images may use their full `sha256:` image ID; mutable tags
and shortened IDs remain refused. This does not publish or pull the image.
The worker reads `/input/request.json` and emits one JSON object with `handoff`
(existing task handoff schema) and `files` (path to proposed text/null). The command
holds the project writer lock, runs without network or host environment, and mounts
only a bounded read-only context snapshot. Actual Docker restrictions are checked
before start. Temporary memory/PIDs/storage are bounded; timeout forcibly removes
the container and verifies absence. Failed cleanup is an error. Local Linux Docker
is required; remote daemons, Windows containers and cloud-provider policies fail
closed. Host task files/status never change automatically; review and test output
before integrating. Docker is a shared-kernel boundary, not a VM.

`agentbase eval capabilities --provider claude --consent` checks installed version
and native feature help only. `plugins validate --output PATH --native --consent`
first checks canonical package integrity and can run the supported Claude static
validator. Neither command starts inference, installs plugins or verifies activation.
Native paid eval launch is unavailable pending credential/network/cost boundaries;
a provider budget threshold must not be represented as an exact hard spending cap.

Add `--image TRUSTED_PIN` to `eval capabilities` for version/help commands inside
a verified network-disabled container. The image must already contain the selected
native CLI; use a repository digest or full local `sha256:` image ID.

`agentbase eval native-smoke --provider codex --image TRUSTED_PIN --consent`
tests a fixed synthetic loopback API with the real CLI, still with external network
disabled. Claude's equivalent also supplies and checks discovery of the canonical
AgentBase plugin. Add `--mode eval` with `--provider claude` to exercise its native
eval engine with one fixed prompt and regex grader, one run/arm/concurrent session,
no scaffold, publishing, tools or real MCP server. Codex eval mode is refused.
Images need Node 20+ and the native binary at `/usr/local/bin/node` and
`/usr/local/bin/codex` or `/usr/local/bin/claude`. No image/binary is downloaded.
No project content, host configuration or real API credential is supplied.
All replies/counts are synthetic: `origin: mock`, real API calls zero, actual model
behavior unverified. These checks measure protocol decoding/native grading, not
plugin effectiveness, tool execution, provider usage or cost. Raw native traces and
synthetic billing figures are discarded. CLI exit 1 means the smoke failed; exit 2
means invalid input, setup/boundary failure or unavailable required capability.
[Architecture and exact limits](../architecture/native-probes.md).

## Credential gateway checks

`agentbase gateway validate --file gateway-policy.json` validates one explicit
policy. Required fields: `schema_version: 1`, protocol `provider` (`codex` Responses
or `claude` Messages), exact `model`, `max_requests` (1..100), `max_output_tokens`
(1..8192), `max_request_bytes` (256..500000), `max_response_bytes` (256..4000000),
`timeout_seconds` (1..120) and `lifetime_seconds` (1..300). Request timeout must fit
lifetime. These are protocol limits, not an exact currency/subscription cap.

`agentbase gateway self-test --image TRUSTED_REPOSITORY@sha256:FULL_DIGEST --consent`
tests the real local Linux Docker boundary with a dummy key. It publishes no host
port, makes no valid provider request, pulls no image and removes its containers/
network. Use a trusted preinstalled Node 20+ image; pinning alone does not confer
trust. The key stays in the sidecar, supplied through stdin, while the worker gets
only a run capability on an internal network. Lifetime expiry stops the key-holding
process. [Boundary and compatibility limits](../architecture/provider-gateway.md).
Native paid execution is still disabled pending runner/eval adapter integration.

Request bodies use provider-specific top-level and client-tool field allowlists.
Unknown fields, remote MCP servers, stored containers/context, remote tool
configuration (also in namespaces) and stored item references are rejected before
transport. Metadata such as Codex `client_metadata` remains supported. Nested
provider values are not exhaustively schema-validated; this narrow text/client-tool
subset deliberately refuses unreviewed features. See the
[self-use guide](self-use.md) for this repository's actual task/handoff workflow.

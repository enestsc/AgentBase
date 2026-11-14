# Implementation status — 2026-11-14

## Latest: local host test receipts and restored packaging

Implemented `receipts.py` and `tasks test ID --source PATH --consent --argv
ABSOLUTE_EXE ARGS`, plus `tasks receipt ID`. Only explicit operator argv is
executed, for an existing running writer in the canonical DAG. No task/handoff
command is parsed. The project lock spans execution/storage; a managed manifest
preserves edited or untracked receipts. Canonical `tasks.definition` keeps the
previous specification hash serialization unchanged. Static task/resource claims,
selected file inventories, executable bytes and argv hashes bind each receipt;
before/after and later enumeration detect source additions/deletions/drift.
Output is bounded/hash-only, with exit status, duration and timeout/collection
failure states. Neither task completion nor specification evidence is upgraded.

This is explicitly **trusted host execution**, with filesystem/network rights,
not a sandbox. Only the direct child is terminated on timeout/output failure;
descendant cleanup is unverified. Selected bytes exclude external dependency and
resource contents. Local hashes/manifest are unauthenticated and can be forged by
an editor with access to both records. See the [English](../guides/test-receipts.md)
and [Turkish](../guides/test-receipts.tr.md) guides for exact limits/exclusions.

Actual host helpers: `package_audit` (codebase-explorer, read only) identified the
existing Python 3.12 tooling; `receipt_contract` (security-reviewer, read only)
reviewed the contract and final implementation. Its final review found a Windows
`.exe` alias resolving to `.cmd/.bat` could bypass pre-resolution suffix checking.
The coordinator added a post-resolution guard and a no-launch regression for both
extensions; the same helper independently re-reviewed and closed that finding.
The original finding remains in a separate local artifact. Primary coordinator
alone wrote code/tests/docs/task state, ran checks and packaged; no nested agent,
native provider launch, paid inference, key discovery, commit/push/publication or
new branch/worktree. Generated native roles were not assumed active.

Final source checks: **227 unittest: 226 passed, one unchanged Windows symlink
permission skip**, 58.544 s, Windows/Python 3.14.4 with optional PyYAML 6.0.3.
The 15 focused receipt tests cover real execution/failure/timeout/overflow, source
and definition drift, minimal environment, edited manifest preservation and the
resolved Windows launcher refusal. Ruff and diff checks passed. An initial
sandbox full run had three failures/one error from denied loopback fixtures;
approved outside-sandbox runs passed. A clean venv CLI launcher likewise required
outside-sandbox execution here; this is not a source regression.

Packaging no longer needs a new dependency installation: existing Python 3.14
`build.ProjectBuilder` uses explicit `C:\Python312\python.exe` and its installed
setuptools **81.0.0**, satisfying `>=77`, without build isolation or an installer.
Wheel/sdist and Twine checks passed; clean temporary venv installation uses
`--no-index --no-deps`. **39 offline installed CLI checks** pass, including receipt
consent refusal, real execution/current reporting and stale reporting after a
source edit. All **47 runtime files** match checkout bytes in both archives;
zero mandatory runtime dependencies and no local state/native binary/downloaded
archive are bundled. Final package outputs remain
`.agentbase/self-use-20261114/dist/`; exact final hashes/checks are in
`.agentbase/receipt-check-20261114/`.

Real local test and Ruff receipts were recorded against current selected sources;
the earlier receipt becomes stale after the corrective source edit. Their reports
explicitly retain `authenticated: false` / `acceptance_verified: false`.
The four prior completed tasks/handoffs are preserved exactly; a locked validated
append adds follow-up tasks without importing over the old DAG. The 527-file
pre-install snapshot still matches, both original instruction prefixes remain,
doctor is clean and update preview has `changes: []`. Concurrency stays 1.
Read the latest HANDOFF before older chronological checkpoints below.

Remaining: independently authenticated runtime provenance and explicit semantic
receipt-to-acceptance mapping, production native worker/eval/spending integration,
actual authorized provider/Ollama behavior, and Linux/macOS/Python 3.11 execution.
No new Docker/native/network smoke was run in this receipt continuation; earlier
mock evidence remains historical and production native launch stays disabled.

## Self-use and independent review continuation (2026-11-14)

This earlier continuation is superseded above; the primary-only/no-install statements below
describe earlier work. The existing dirty `chore/p1-hygiene` checkout was retained.
No new branch/worktree, commit, push, publication, provider credential discovery,
paid inference, imported script/installer or nested delegation occurred.

- Installed AgentBase locally after reviewing the canonical two-provider native
  preview. Original AGENTS.md/CLAUDE.md bytes remain intact as prefixes; only
  managed blocks were appended. A 527-file pre-install artifact snapshot (including
  the session bootstrap helper) was hash-verified by the coordinator and an actual
  independent helper. Existing build/native/YAML/schema artifacts were preserved.
  Config/manifest/policy, 16 canonical roles, native definitions and 10 skills per
  provider now exist. Doctor is clean and update preview is a no-op.
- Used the existing task DAG for real post-install work: `selfuse-check` →
  `gateway-contract` → `boundary-review` → `verify-handoff`. Each uses running,
  review, validated schema-v1 handoff and evidence-backed completion. Default
  sequential concurrency 1 remains. Shared state/files have one writer.
  Initial helper audits preceded bootstrap and are not retroactively DAG work.
- Independent security review found unknown request/tool fields forwarded by the
  gateway, including Claude remote MCP/server-side container configuration.
  Primary coordinator added provider-specific top-level request and client-tool
  field allowlists, recursively checked Codex namespace members and refused stored
  item/server-tool references before transport. Codex `client_metadata` is explicitly
  supported. These are narrow field contracts, not exhaustive nested value schemas.
- Real host helpers: `dogfood_audit` performed the product/setup review and
  post-install independent doctor/no-op/hash checks; `boundary_audit` found the
  gateway gap and independently reviewed the fix (29 rejected / 6 accepted pure
  sanitizer cases). Neither helper wrote files, launched a native session or
  delegated. Primary coordinator alone implemented, integrated, ran full tests/
  Docker mock checks and wrote documentation/state. Generated native definitions
  were not assumed automatically discovered in this open session.

Final source verification: **212 Python tests: 211 passed, one unchanged Windows
symlink-permission skip**, 86.376 s, Python 3.14.4 with optional PyYAML 6.0.3.
This includes the updated wrapper's **20 gateway Node scenarios** and four native
Node scenarios. Ruff, both changed JS syntax checks and diff checks passed. The
initial sandbox Node attempt failed on loopback EACCES; outside-sandbox protocol
checks passed. An initial full run caught the wrapper's stale 17-scenario expected
count; corrected to 20 before the final passing full run.

Real local network-disabled Docker checks passed again with the recorded trusted
images: Codex 0.169.0 print, Claude 2.1.310 print/canonical plugin discovery, and
Claude one-case regex eval. Each made one synthetic request, zero real provider
calls/credentials; boundary and cleanup were checked by the existing runner.
An initial Codex mock request was refused for missing `client_metadata` in the new
allowlist; a names-only synthetic diagnostic identified it, explicit support and a
fixture were added, then all three final checks passed. No raw native trace,
prompt, token/billing value or credential was retained in reports.

Resumable local state: `.agentbase/tasks.json`, `.agentbase/memory/`, and
`.agentbase/self-use-20261114/` (pre-install snapshot/instruction copies, plans,
handoffs, mock reports). These are ignored local artifacts, not authenticated
test receipts or published evidence. [Self-use guide](../guides/self-use.md) and
[Turkish guide](../guides/self-use.tr.md) explain the exact lifecycle and limits.
Do not purge this artifact-bearing directory or rerun init over installed state.

Remaining: independently recorded test execution receipts, production native
runner/eval integration with reviewed spending consent, actual authorized provider/
Ollama behavior and Linux/macOS/Python 3.11 execution. The existing CLAUDE.md import
is preserved and repeated by the canonical managed block; host deduplication is
unverified here. Native production launch remains disabled. Package artifacts for
this continuation use `.agentbase/self-use-20261114/dist/`; the older build-check
artifacts predate this gateway hardening. A `python -m build --no-isolation`
attempt failed because this active Python lacks `setuptools.build_meta`; no new
wheel/sdist was produced and no build dependency was installed. Earlier Twine/
installed-wheel evidence below applies to the earlier packages, not this fix.

## Resumed local development (2026-11-14)

The existing dirty `chore/p1-hygiene` checkout was retained. The attachment/master
prompt and entry-point documents were read. Primary agent alone performed all
design, implementation, tests and documentation in this continuation; no delegated
agents, commits, pushes, publication or provider inference.

Implemented since the historical checkpoint below:

- Registry: staged 1..100-skill restore with one lock/rollback batch, 96 MB staged
  limit, fresh source/security/compatibility checks, exact aggregate review ID;
  retry-safe empty-directory cleanup after ordinary I/O failure. Optional explicit
  PyYAML 6 SafeLoader syntax with bounded shallow string metadata, duplicate/tag/
  alias rejection; stdlib stays default. Curated offline source discovery and
  non-executing dependency presence reports; broader license/metadata fixtures.
- Usage: source-opted-in, bounded single-event stdin capture, snapshot fingerprint
  dedup and explicit identities for increments. Cross-day cumulative intervals
  stay unallocated in daily/straddled-period totals. Cumulative role attribution
  needs matching evidence at both endpoints.
- Specs: exact-plan incremental reconciliation of owned pending/unevidenced tasks;
  preserve unrelated/started task state and handoffs. Explicit acceptance-to-handoff
  test mappings are source/handoff hash-bound and honestly labeled reported evidence.
- Intelligence: per-file hash cache, current-inventory import resolution, nested
  Python symbols, labeled lexical calls, feature queries and evidence-backed Mermaid.
- Ollama: explicit inventory, completion/context/size preflight, generation/context
  options, structured proposal validation and explicit no-provider fallback. Memory
  sizes are metadata checks, not an OS RAM/VRAM cap.
- Execution: `TaskRunner` protocol and offline `DockerTaskRunner`; explicit trusted
  digest/command, local Linux daemon, bounded in-scope snapshots, no project/home/
  socket mount or host environment/network, non-root, verified restrictions and
  forced removal/absence check on timeout. Proposals only; no automatic integration.
- Native compatibility: explicit version/help probes and supported Claude static
  plugin validation after canonical integrity checks. No inferred runtime activation.

Verification: baseline rerun **150 tests: 149 passed, one symlink skip**
(74.399 s, outside sandbox because loopback fixture sockets are denied inside).
Registry **27 tests passed including real optional PyYAML 6.0.3** installed only in
ignored `.agentbase/yaml-check`; usage 15, specs 14, local capability 6, intelligence
4 and explain 6 tests passed. Full suite at this milestone: **191 tests, 190 passed and one
unchanged Windows symlink-permission skip**, including optional PyYAML; Ruff and
`git diff --check` clean. Final full run after source/skill integration: 122.572 s.
An installed-wheel test caught and fixed cross-process snapshot dedup
(set iteration affected fingerprints).
Fingerprint keys are now sorted, with an order-variation regression test.
Final wheel/sdist builds and Twine checks passed. A fresh temporary venv installed
the wheel with `--no-index --no-deps`; **30 offline CLI checks passed**, including
separate-process snapshot dedup, reconciliation, evidence, incremental maps and
both provider packages/discovery paths. No extra runtime dependency was installed.
Current read-only CLI probes: Codex 0.167.0-alpha.4.1, Claude 2.1.310; Docker Linux
daemon 28.4.0 reachable with required access. Claude native eval help confirms its
cost threshold is checked before launches and can overrun by in-flight runs; it
must not be described as a precise hard spending ceiling. No model session launched.

Real offline Docker smoke passed five boundary checks (snapshot hash, excluded host
environment, read-only root, unmounted host files, blocked network), plus timeout
with a detached child and verified container removal. Used only our program and
preinstalled `node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32`;
zero image pulls/model calls. Daemon 28.4.0 confirmed actual restrictions before
start. A real Docker log-driver incompatibility was fixed (`compress=false` with
one retained log). This is Windows Docker Desktop evidence, not all-host proof.
Claude native static validation also passed through the new CLI; plugin activation
and paid eval were not run. Historical GitHub network smoke was not repeated today.

Remaining: native worker/eval integration with the now-tested credential gateway
and bounded spending contract; independently recorded test receipts; real authorized plugin
activation/provider events/local Ollama inference; Linux/macOS/Python 3.11 execution.
Do not weaken the offline boundary or send host secrets into workers to close gaps.
Detailed continuation instructions are in HANDOFF; historical scope follows.

## Gateway continuation after user request to continue

Implemented `gateway.py` / packaged `gateway.cjs` and canonical policy/probe assets.
The gateway receives an explicitly supplied credential only through stdin and
gives workers a random run capability on a unique internal network. Only the
sidecar gets egress; actual mounts/networks/caps/resources/no-ports/no-logs are
checked before startup. Fixed official HTTPS routes and exact model, request/
output/byte/time/concurrency bounds; no redirects, arbitrary URLs, hosted tools,
stored context, remote files/media, service-tier overrides or forwarded client
authentication. JSON/SSE are bounded/buffered; literal key echoes are redacted;
raw upstream errors/headers are not relayed. No key discovery or model invocation.
`gateway validate` and `gateway self-test --image TRUSTED_PIN --consent` integrate
this slice into the CLI. Native provider/eval launch remains disabled.

Gateway-focused Python tests passed, including startup failure cleanup and proof
that the key is absent from argv/environment/files/reports. Node protocol fixtures
use synthetic secrets and mocked official HTTPS transport. Real CLI Docker self-test
passed nine boundary checks, zero upstream attempts/pulls, resource removal and
lifetime termination of the key-holding process even with stdin left open. Same
pinned Node image/Windows Docker Desktop as the earlier offline runner evidence.
Gateway milestone suite: **199 tests, 198 passed, one unchanged Windows symlink skip**
in 103.180 s, including optional PyYAML and the Node wrapper's 15 credential-free
protocol scenarios. Ruff, JS syntax checks and diff checks are clean. New wheel/
sdist and Twine checks passed; a fresh no-index/no-deps venv passed **31 offline
CLI checks**, including the new gateway policy command and packaged assets.
All design, implementation, security review, testing and docs remain primary-agent
work; no new agent, commit, push, publication, real credential or paid session.

## Native contract and synthetic-runtime continuation

Added `native.py` and `eval capabilities --image TRUSTED_PIN --consent` for
allowlisted network-disabled native version/help commands. Full local image IDs
are accepted alongside repository digests; mutable tags/short IDs are refused.
The shared Docker cleanup helper refuses names outside the generated namespace.

`eval native-smoke` now exercises real Codex/Claude response decoding through the
canonical gateway checks and a fixed synthetic transport on container loopback,
with external network disabled. Claude discovers the canonical AgentBase plugin
from `distribution.files`. Its optional `--mode eval` runs the real native eval
engine against one fixed prompt/regex grader, one run/arm/concurrent session,
without scaffold, publishing, tool grants, real MCP servers or judge calls.
Codex native eval remains unsupported. Reports explicitly say `origin: mock`;
synthetic tokens/billing and raw native traces are discarded. No quality, real
usage, paid execution or tool-execution claim follows from these checks.

Actual local Docker evidence: Codex **0.169.0** print, Claude **2.1.310** print
with native plugin discovery, and Claude native one-case regex eval all passed.
Each used exactly one synthetic request and zero real API calls/credentials.
Verified boundary before each start: network none, exact first-party read-only
mounts, non-root/read-only root, no ports/home/project/socket mounts, cleared
native environment, memory/swap/CPU/PID and bounded logging. Cleanup verified.
The fixture surfaced/fixed Codex's required home directory, its default hosted web
search (explicitly disabled), client function/custom namespaces, and Claude's
exact `?beta=true` Messages query. Arbitrary queries/hosted tools remain refused;
experimental Claude betas stay disabled in this narrow synthetic subset.

Pinned native Linux artifacts were downloaded as data from fixed official npm
endpoints, SHA-512 verified, bounded/link/path checked and copied into local
images with no RUN/install scripts/hooks. No host CLI update, pull or publication.
Local ignored artifacts: `.agentbase/native-cli-inputs/`; exact native image IDs:

- Codex: `sha256:919cbcc4b13696fd884e8d346fb086d833d240f2fd8f937d415499d85f6769b5`.
- Claude: `sha256:f16e64e7f19fa70dd975058a6e045a2fa4fca7d7ab385fe065a7dfb593d3d1b9`.

Base: the already installed pinned Node image from the earlier Docker evidence.
Notices/provenance stay with those local artifacts. Codex package metadata says
Apache-2.0; Claude's binary has Anthropic's proprietary terms, not AgentBase MIT.
No native binary or downloaded archive is bundled in AgentBase distributions.
Package signatures were not verified. Native CLI preparation is local evidence,
not an automatic installation or portable runtime guarantee.

Verification: native Python tests **12 passed**, including four Node fixture
scenarios; gateway protocol scenarios increased from 15 to **17**. Final full
suite: **212 tests, 211 passed, one unchanged Windows symlink-permission skip**
in 64.328 s, Python 3.14.4/Windows, including optional PyYAML 6.0.3 and both Node
test wrappers. Ruff, JS syntax and diff checks passed. Wheel/sdist and Twine checks
passed. A fresh no-index/no-deps venv passed **33 offline CLI checks**, including
native consent refusal before Docker execution. Archive inspection confirmed all
**46 runtime files** exactly match checkout source, both Node test files/new
architecture/ADR are included in sdist, zero mandatory runtime dependencies,
and no ignored state, native binary or downloaded archive in distributions.
All design, implementation, review, tests and documentation were performed by
the primary agent alone. No subagent, commit, push, publication, real provider
credential or paid session. Remaining: production native worker/eval launch and
reviewed spending contract, independent task test receipts, actual authorized
provider/Ollama behavior and Linux/macOS/Python 3.11 execution.
See [native architecture](../architecture/native-probes.md) and ADR 0004.

## Historical checkpoint — 2026-11-11

Branch: `chore/p1-hygiene`. Version remains 0.1.0 alpha. Local checkout was clean
before this session. No commits, pushes, releases or remote repository changes.

## Existing functionality preserved

Sixteen canonical roles and ten skills, native Codex/Claude project generation,
managed instruction blocks and file hashes, safe update/uninstall, cooperative
writer locks, task DAG scheduling/transitions/handoffs, bounded context,
Python/JS structural explanation, evidence-backed memory maintenance and
explicit opt-in loopback Ollama proposals. Default concurrency stays 1.

## Delivered local foundations

| Area | Implemented and tested | Limitations |
| --- | --- | --- |
| Registry | Public GitHub refs resolved to full SHA; bounded ZIP inspection; SKILL.md subset parser; license/notices; deterministic findings; exact-plan apply; hashes/provenance; audit/update/rollback/remove/export/restore | Single-skill restore transaction; no arbitrary/private hosts, full YAML, signature verification, remote catalog ingestion or crash journal |
| Usage | Explicit source opt-in, four documented message adapters, unknowns, stable-ID dedup, cumulative deltas, context separation, attribution evidence, daily/week/model/provider/project breakdowns, estimates separated, JSON/CSV, retention/delete | No automatic collector, live usage session or authenticated event verification; provider counters have different input-cache semantics; snapshots cannot establish precise cross-day allocation |
| Packs | Seven curated manifests, implicit core, combinations, recommendations, custom canonical-selection registration, safe add/remove/update and legacy preservation | Optional tool dependencies are declared, never installed; no external third-party pack execution |
| Specifications | Editable Markdown/fenced JSON; explicit acceptance/roles/scope/dependencies; cycles/declared contradictions/ownership checks; source-hash traceability; existing-DAG import; hash-protected generated proposals | No LLM semantic decomposition, automatic contradiction solving or active-plan reconciliation |
| Evaluation | Static catalog/pack/integrity validation, observation grading with role/skill/tool/file/correctness checks, ten mock scenario fixtures, saved report | No live model runs, measured comparative baseline or native eval launcher |
| Distribution | Canonical reproducible Claude plugin/marketplace/agents/skills, Codex portable + compatibility manifests/skills; MIT notices; hash validation; preserve changed output; plugin discovery mode avoids duplicate project skills/Claude agents | No automatic publication, no real host activation; Codex custom agents remain standalone init output |

## Commands added

- `skills search/add/list/info/audit/update/rollback/remove/export/restore`; bare `skills` preserved.
- `usage [--today|--week] [--provider ...] [--by-agent|--by-skill] [--json] [--timezone ...]`, plus `configure/import/export/delete`.
- `packs list/info/recommend/register/add/remove` and repeatable `init --pack`.
- `spec init/validate/plan/tasks` (explicit `tasks --import`).
- `eval list/validate/run/report` (offline only).
- `plugins build/validate` (local artifacts only).
- `init/update --discovery plugin` (CLI state without duplicate plugin resources).

## Verification evidence

Baseline: Windows / Python 3.14.4, 101 unittest tests, one symlink-permission
skip, Ruff clean. Final full run: **150 tests, 149 passed and one unchanged
symlink-permission skip**, in 23.871 seconds; Ruff clean. This includes the
provenance/purge, plugin-discovery and CSV-formula regressions.

Separate live GitHub smoke passed against obra/superpowers commit
`22f0b463e7a5e579904dd6211a520321035526f7`, subdirectory
`skills/verification-before-completion`: public HTTPS resolution, two provider
copies, two inventoried files including MIT notice, clean integrity audit and
safe removal in a disposable project. Imported code was not executed and no
third-party content was bundled.

Observed CLIs: Codex 0.167.0-alpha.3.2; Claude Code 2.1.310. Codex generated the
App Server schema locally, confirming token usage field names. Claude's native
plugin validator passed the current metadata/license package with only an optional
directory-listing icon warning and installation-copy advice; no model
session was started. `claude plugin eval --help` confirmed installed support;
paid evaluation was not launched. `codex plugin --help` exposes no validate
subcommand in this installed version; Codex validation is AgentBase static
validation, not fabricated native validation. Wheel/sdist builds and Twine checks
passed. The explicit source manifest includes docs/examples/scripts. A fresh
temporary venv installed the wheel with `--no-index --no-deps`; 22 offline CLI
checks passed, including both providers' package generation, discovery switching,
packs, specs/DAG, static eval and existing memory flows. The final rebuild and
installed-package smoke after the provenance guard also passed. Archive inspection
confirmed bilingual documentation/examples/scripts and packaged pack/license
assets, with private `.agentbase` state excluded. `git diff --check` passed.

All automated suite tests are offline and credential-free. Live network smoke
and local native-format checks are separate evidence, not mocked provider behavior.
Linux/macOS and Python 3.11 are configured in CI but were not run locally.

## Files and decisions

New runtime modules: `registry.py`, `skill_security.py`, `usage.py`, `packs.py`,
`specs.py`, `evaluation.py`, `distribution.py`; new packaged pack/license assets.
Existing `fs.py`, `adapters.py`, `install.py`, `cli.py` were extended, without
restructuring the existing task/memory/local-model engines. Five new test modules
and existing CLI/example tests cover the new behavior. Two explicit smoke scripts,
source-distribution manifest, bilingual guides/readmes, architecture diagrams,
trust/reference decisions and concise root AGENTS/CLAUDE instructions were added.

[ADR](../decisions/0001-incremental-foundations.md) records the shared filesystem
and canonical-data choices. [Trust model](../security/trust-model.md) distinguishes
implemented boundaries from host policy. The read-only reference audit checked
all 17 supplied URLs and found restrictive GitNexus/Task Master licenses; their
code is not bundled. Four review findings were fixed: context/token source
coexistence, restore compatibility, lock size and Apache/SPDX recognition.

Primary agent performed design, implementation, tests and documentation.
One independent read-only subagent audited references/licenses and reviewed
security/correctness. No parallel writing agents were used.

Next steps: [roadmap](ROADMAP.md), [handoff](HANDOFF.md).

# Development handoff — 2026-11-14

## Latest: completed local receipt slice and packaging recovery

Read STATUS's first section and the [receipt guide](../guides/test-receipts.md)
([Türkçe](../guides/test-receipts.tr.md)). New commands are `tasks test` with
explicit host argv/consent and `tasks receipt`. They use the existing running
writer DAG, canonical definition hash, confined source inventory, project lock
and managed receipt manifest. They do not execute handoff commands, automatically
complete tasks or upgrade spec evidence. Host execution has ordinary file/network
rights; descendants are unverified, source coverage is explicit/subset-only and
local records are unauthenticated. Preserve these limits.

Two actual host helpers were used sequentially: `package_audit` identified local
build tooling; `receipt_contract` reviewed the design and final code, found the
Windows resolved batch-target issue and re-reviewed its guard/regression. Both
were read only and did not delegate. Coordinator alone implemented/integrated,
tested/packaged and wrote shared state. The original P2 remains recorded separately.

Latest checks: **227 tests, 226 passed/one symlink skip, 58.544 s**, optional YAML;
15 receipt tests, Ruff/diff clean; wheel/sdist/Twine and **39 clean-venv offline
installed CLI checks**; **47 exact runtime files**, zero mandatory dependencies.
Full checks and venv launcher need approved outside-sandbox access on this Windows
host because loopback/launcher access is denied inside. No real network/provider
smoke, paid inference, key access, commit/push/publication or new branch/worktree.

The packaging blocker is solved with existing tools, without installing build
requirements. The current frontend Python has `build`/Twine; explicitly selecting
`C:\Python312\python.exe` supplies setuptools 81.0.0:

```powershell
python -c "from build import ProjectBuilder; b=ProjectBuilder('.', python_executable=r'C:\Python312\python.exe'); print(b.build('sdist', '.agentbase/self-use-20261114/dist')); print(b.build('wheel', '.agentbase/self-use-20261114/dist'))"
python -m twine check .agentbase/self-use-20261114/dist/*
python scripts/package_smoke.py --wheel .agentbase/self-use-20261114/dist/agentbase_toolkit-0.1.0-py3-none-any.whl
```

Resume artifacts: `.agentbase/receipt-check-20261114/` holds prior-tasks.json,
helper/implementation/review/fix handoffs, final-tests.log, build log, package smoke,
archive check and final verification. Actual managed receipts live separately in
`.agentbase/receipts/`; `final-test-receipt.json` / `ruff-receipt.json` identify the
current records. `prior-receipt-stale.json` shows real invalidation after the fix.
The earlier `.agentbase/self-use-20261114/` and all 527 pre-install files remain
unchanged; original AGENTS/CLAUDE prefixes and the four completed task objects are
preserved. Follow-up tasks were appended with the existing lock/validation, never
imported over the old store. The default concurrency stays 1. Do not rerun any
one-session coordinator/bootstrap scripts or init/purge; use canonical CLI reads:

```powershell
$env:PYTHONPATH='src'
python -m agentbase doctor
python -m agentbase update --dry-run
python -m agentbase tasks validate
python -m agentbase tasks ready
python -m agentbase memory handoff
```

Next: independently authenticated execution provenance/explicit semantic receipt
mapping if needed, reviewed production native/spending contracts, real separately
authorized provider/Ollama behavior and Linux/macOS/Python 3.11 evidence. Native
production launch remains disabled. Older checkpoints below are historical.

## Latest: actual local self-use and gateway hardening

Read the first section of STATUS and the [self-use guide](../guides/self-use.md)
before older milestones below. This checkout is now initialized; **do not rerun
init, purge `.agentbase`, overwrite its nonempty task store or discard generated
native directories**. Original instruction bytes and the pre-install artifact
inventory remain intact. Existing dirty work stayed on `chore/p1-hygiene`.

Actual helpers `dogfood_audit` and `boundary_audit` independently checked local
installation preservation and gateway security respectively; neither wrote files
or nested-delegated. The coordinator handled implementation, shared state, tests,
Docker mocks and EN/TR docs. Initial audits were pre-bootstrap; post-install
checks/review were dispatched through actual DAG running states. Native definitions
were generated but automatic host discovery/activation was not assumed.

The real local milestone is `selfuse-check` → `gateway-contract` →
`boundary-review` → `verify-handoff`, with validated handoffs/evidence. Resume with:

```powershell
$env:PYTHONPATH='src'
python -m agentbase doctor
python -m agentbase update --dry-run
python -m agentbase tasks show
python -m agentbase tasks validate
python -m agentbase memory handoff
```

Session artifacts live in ignored `.agentbase/self-use-20261114/`: before.json,
original AGENTS/CLAUDE copies, installation preview/result, initial plan, concise
helper/implementation handoffs and native-checks.json. The task store is the
authoritative current scope/state; its gateway scope was amended under the project
lock before updating the Node wrapper. Default concurrency remains 1. Complete
and explicitly archive the current milestone before importing another plan; no
automatic task replacement or parallel writer was introduced.

The helper found that gateway unknown fields forwarded remote MCP/container/tool
configuration. `assets/gateway.cjs` now explicitly allowlists provider request and
local-tool fields (including namespace members) and rejects stored item/server-tool
history before transport. `client_metadata` is allowed for Codex's tested native
request. It is not a complete validator of all nested API schemas. Protocol fixtures
now have 20 scenarios; the Python wrapper count was updated. Unknown native/API
features must be reviewed explicitly; do not relax the contract for convenience.

Final source checks: 212 unittest (211 passed / one Windows symlink skip), 86.376 s,
optional PyYAML; Ruff, changed JS syntax and diff checks passed. Independent helper
sanitizer matrix: 29 refusals / 6 supported cases. Final real network-none Docker
Codex print, Claude print/plugin discovery and Claude one-case eval all passed:
one synthetic request each, zero provider calls/credentials; trusted pins unchanged.
Initial loopback sandbox failure, stale wrapper expectation and missing Codex
metadata allowlist entry were diagnosed/fixed before those final passes.

Next recommended slice: **independently recorded test receipts**, with explicit
host authorization/argv, source/task-definition binding, exit status and stale
source handling. Never execute imported task/handoff commands automatically; local
receipts must not be represented as cryptographically authenticated independent
proof. Production native runner/eval and concrete spending consent remain separate.
No real key, paid/native provider session, publication or cross-platform inference
is authorized by this continuation. Real provider/Ollama and Linux/macOS/Python
3.11 evidence remain absent. Preserve current no-network mock/production distinction.

Package outputs for this continuation belong under
`.agentbase/self-use-20261114/dist/`; older build-check outputs predate this change.
The current offline/no-isolation build attempt stopped at missing
`setuptools.build_meta`. No dependency installation or new package/Twine/installed-
wheel verification was performed in this continuation. Provision a reviewed build
environment before packaging this final source; do not publish the older artifacts
as containing this hardening. The required source unittest and Ruff checks passed.
CLAUDE.md's preexisting import remains alongside the managed duplicate; native
host import deduplication/activation still requires separate verification.

See STATUS's native continuation before the older milestones below.

Latest implementation: `native.py`, packaged `native-mock.cjs`,
`tests/native_protocol.cjs`, CLI `eval capabilities --image` and
`eval native-smoke --provider PROVIDER --image TRUSTED_PIN [--mode eval] --consent`.
Real local network-disabled Docker smokes passed Codex 0.169.0 print, Claude
2.1.310 print with canonical plugin discovery and Claude's one-case native regex
eval. Each made one synthetic API request, zero real provider calls. All mock
results discard native traces/token/billing values and explicitly decline actual
model-behavior verification. Production native launch stays disabled.
Latest full suite: **212 tests, 211 passed and one Windows symlink skip** in
64.328 s, Python 3.14.4 with optional PyYAML 6.0.3; Ruff, JS syntax and diff clean.
Node protocol coverage is 17 gateway and four native fixture scenarios.
Latest wheel/sdist/Twine checks passed; **33 installed-wheel offline CLI checks**
passed in a fresh no-index/no-deps venv. All 46 runtime files matched current
source; source archive includes native Node fixtures/docs and excludes local
native binaries/archives and ignored state. Mandatory runtime dependencies: zero.
Do not confuse these current results with the dated 191/199-test milestones below.

Trusted local images and their license/provenance evidence are recorded in STATUS;
inputs remain ignored at `.agentbase/native-cli-inputs/`. No npm installer/hooks
or RUN layer was used; only official fixed tarball data inspection, integrity
verification and COPY-only local image construction. Claude binary terms are
proprietary; never redistribute it under AgentBase's MIT license. Images already
contain Node and native binaries; no automatic downloads/pulls are implemented.

Next: design the production native runner/eval review contract using existing DAG,
snapshot/handoff validation and the separately tested credential gateway. The
synthetic no-tools subset is not real provider/tool/spending proof. Preserve
gateway's fixed official routes and isolated key; do not enable real keys or
paid sessions merely because mock passed. Independent task test receipts and
cross-platform execution remain. Read ADR 0004 and native-probes architecture.

Earlier continuation checkpoints (verification is superseded by the native
continuation section in STATUS):
New entry points: `dependencies.py`, `intelligence.py`, `runner.py`, `providers.py`, registry
multi-restore/optional YAML, `usage capture`, `spec reconcile/evidence`, extended
`local models`/preflight/structured fallback. Existing dirty work is preserved.
No provider inference, commit/push/publication or subagent was used. New optional
PyYAML test dependency exists only at `.agentbase/yaml-check`; default runtime
remains dependency-free. Use `PYTHONPATH=src;.agentbase/yaml-check` on Windows to
exercise that optional path (normal suite should also pass without it).

Earlier full suite: 191 tests (190 passed, one Windows symlink skip), optional YAML
included; Ruff/diff checks clean. Real offline Docker isolation/cancellation smoke
passed against the exact locally pinned Node image in STATUS. Native Claude static
validation passed; Codex 0.167.0-alpha.4.1 has no established native validator.
Final wheel/sdist/Twine passed; **30 installed-wheel offline CLI checks passed**
after fixing cross-process snapshot fingerprints by sorting normalized fields.
The final full 191-test run (190 passed, one symlink skip) took 122.572 s.

Commands for this continuation:

```powershell
$env:PYTHONPATH='src;.agentbase/yaml-check'
python -m unittest discover -s tests
python -m ruff check src tests scripts
python -m build --outdir .agentbase/build-check-20261114
python -m twine check .agentbase/build-check-20261114/*
python scripts/package_smoke.py --wheel .agentbase/build-check-20261114/agentbase_toolkit-0.1.0-py3-none-any.whl
# Explicit local container smoke; no inference/pulls/project mount:
python scripts/runner_smoke.py --docker --image node@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32
```

Gateway continuation: `gateway.py`, `assets/gateway*.{cjs,json}` and
`tests/gateway_protocol.cjs` now implement/test the separate key-holding sidecar.
`gateway validate` is deterministic; `gateway self-test --image TRUSTED_PIN --consent`
is a real dummy-key Docker probe (no valid upstream request). Gateway-focused tests
and real lifetime/network/config/disk/worker-env checks passed; that milestone's suite
was 199 tests (198 passed, one symlink skip) in 103.180 s, including 15 Node protocol
scenarios via its Python wrapper. Wheel/sdist/Twine and **31 installed-wheel
offline CLI checks** passed with the new gateway assets.
`scripts/gateway_smoke.py` calls the
same core self-test; no competing implementation.

Next: integrate native workers/eval with the tested gateway and reviewed cost/time
contract before cloud launch. Never pass provider home dirs,
host env or API keys into model tools. Claude's native max-cost flag is a launch
threshold with in-flight overrun, not an exact hard cap. Live provider/local-model
events, plugin activation and Linux/macOS remain separate authorization/evidence.
The offline Docker runner is useful and actually tested, but is not a completed
cross-provider cloud runner. All work so far remains uncommitted and unpublished.

Historical evidence below is dated, not newly reproduced.

## Historical checkpoint — 2026-11-11

Read [STATUS](STATUS.md) for exact behavior/verification and [PLAN](PLAN.md) for
the baseline. Work stays uncommitted on `chore/p1-hygiene`; inspect `git status`
before editing. No original user modifications were present or removed.

Final evidence: 150 tests (149 passed, one Windows symlink-permission skip),
Ruff clean, wheel/sdist builds + Twine passed, 22 installed-wheel offline CLI
checks passed, pinned live GitHub install/audit/remove smoke passed. Claude native
manifest validation passed; optional directory icon remains absent. No live
model session, Linux/macOS execution, paid eval, commit, push or publication.

Key entry points:

- `registry.py`: fixed GitHub endpoints, pin/archive checks, native destinations,
  lock/snapshots, plan ID and acknowledgements. `skill_security.py`: conservative
  frontmatter parser, license inventory and deterministic findings.
- `usage.py`: opt-in envelope imports, metric semantics, dedup, retention/report/
  exports; no provider invocation or hidden session discovery.
- `packs.py` + `assets/packs.json`: one canonical selection format, custom local
  manifests, legacy state; `install.prepare` applies selection through adapters.
  `init/update --discovery plugin` avoids duplicate plugin skills/Claude agents;
  purge preserves provenance by refusing while third-party skills are installed.
- `specs.py`: human-authored Markdown to existing `tasks.py` schema; source hash,
  traceability and managed generated outputs. Do not invent another task engine.
- `evaluation.py`: static validation or grade supplied observations; mock origin
  must remain explicit. `distribution.py`: local canonical optional packages.

Run from this checkout:

```bash
# Set PYTHONPATH=src in your shell before the suite.
python -m unittest discover -s tests
python -m ruff check src tests scripts
python -m build --outdir .agentbase/build-check
python -m twine check .agentbase/build-check/*
python scripts/package_smoke.py --wheel .agentbase/build-check/agentbase_toolkit-0.1.0-py3-none-any.whl
# Separate explicit network smoke, never imported script execution:
python scripts/live_registry_smoke.py --network
```

Windows sandbox temporary-directory operations were denied; test/build runs
needed the approved outside-sandbox execution. The baseline failures were access
errors, not source regressions. Source archives now include example JSON and docs.
Ignored `.agentbase` artifacts contain local schemas, builds and plugin test
packages; none is authoritative project task/memory state or a committed artifact.

Do not launch paid native evals or provider sessions, publish, commit/push, run
imported code or change another repository without explicit authorization.
For runner work, read the [orchestration boundary](../architecture/orchestration.md)
and [ADR](../decisions/0001-incremental-foundations.md). Native CLI presence and a
valid handoff do not prove filesystem isolation or actual model behavior.

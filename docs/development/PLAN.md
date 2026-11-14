# Incremental development plan — 2026-11-10

## Active continuation — 2026-11-14

Explicit host test receipts are implemented in the existing DAG with selected
source/task/executable binding, hash-only output/argv and stale handling. They are
local unauthenticated records, not independent proof. Production native launch,
reviewed spending and cross-platform verification remain separate follow-ups.

Latest self-use slice is implemented: reviewed native project installation without
discarding ignored artifacts; actual local DAG/handoffs and two independent host
helpers; gateway request/tool field contract hardening from the helper's finding.
See STATUS's first section for current verification and roles. The recommended
bounded host test receipt slice is now implemented; existing handoff observations
remain reported evidence. Native production launch and spending integration are
still separate unfinished work. Earlier chronological planning follows.

The 191-test/offline-runner milestone in STATUS is verified. The user requested
continued implementation. Next slice: a separate credential-isolating gateway
with a fixed provider/route/model policy, bounded requests/output/time/concurrency,
no credential environment/files/logs, and an isolated Docker network for workers.
First prove the protocol with dummy secrets and a local mock transport; then prove
network separation and cancellation in real local Docker. No real credentials,
paid provider sessions, image pulls, publication or recursive delegation.
Only after that boundary is verified may native provider/eval adapters use it.

Gateway slice is now verified: 199 Python tests (198 passed, one symlink skip),
15 Node protocol scenarios, real dummy-key Docker/lifetime checks, build/Twine
and 31 installed-wheel offline checks. Next inspect official native platform
package metadata and prepare reproducible local image inputs without running any
package installer/hook. Trusted, pinned native images must pass no-network
version/help probes before any credential gateway or paid native launch.

Native image contracts and network-disabled synthetic runtime checks now pass:
Codex response decoding; Claude response decoding/canonical plugin discovery;
Claude native one-case regex grading. First-party fixed fixtures only, no user
task/project, external network, real key/provider request or paid execution.
The exact tested subset/limits are in native-probes architecture and ADR 0004.
Next production slice must reuse DAG/snapshots/handoffs and the separate gateway,
with a concrete reviewed launch/spending contract before real provider access.
Mock results cannot close model effectiveness/tool execution/billing gaps.

## Historical initial plan

Baseline: clean `chore/p1-hygiene`, Python 3.14.4, 101 unittest tests pass
(one Windows symlink-permission skip); Ruff passes. Sandbox temp permissions
required running unittest outside the sandbox. No AGENTS.md, CLAUDE.md or
.agentbase installation exists in this checkout. Existing adapters, canonical
catalog, confined filesystem writes, managed manifest, task DAG, context,
memory and opt-in loopback Ollama remain authoritative.

1. Extend byte-safe recoverable batches. Add bounded HTTPS GitHub resolution,
   strict archive validation, SKILL.md parsing, license inventory and deterministic
   findings. Plan first; explicit apply; immutable SHA and per-file hashes;
   safe update, rollback, restore and removal. Reuse project lock and confinement.
2. Add local opt-in usage storage and versioned documented provider import
   adapters. Preserve unknowns, deduplicate cumulative snapshots, strip raw
   content, report/export, retain/delete. Never scrape credentials or sessions.
3. Add one packaged pack catalog, project recommendations and atomic installation
   through existing generators; preserve default init and edited files.
4. After P0 integration passes, add specification-to-existing-DAG traceability,
   deterministic evaluation and reproducible provider-native distribution.
   Implement external runners only where actual permission enforcement exists.
5. Update English/Turkish guides, trust model, architectural diagrams, reference
   decisions and resumable status/handoff. Report actual verification and gaps.

No commits, pushes, releases, paid inference or imported script execution.
Network fixtures are mocked in CI; live read-only checks are separate evidence.

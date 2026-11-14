# AgentBase

Provider-native AI development workflows for **OpenAI Codex** and **Claude Code**.
One canonical set of roles, skills and policy; generated native adapters; a small
dependency-free Python CLI for deterministic coordination. Turkish: [README.tr.md](README.tr.md).

AgentBase is not an inference framework. It uses the agent runtimes you already have.

New local foundations: reviewed, SHA-pinned GitHub skill imports; opt-in usage
imports; seven curated packs; explicit specification-to-DAG compilation; offline
evaluation and reproducible optional plugin packages. Multi-skill restore,
explicit stdin usage capture, incremental task reconciliation and source-hashed
code maps extend those foundations. A separate opt-in offline Docker worker
returns bounded proposals; cloud cross-provider execution remains unavailable.
The optional credential gateway now has a dummy-key Docker self-test; native paid
launch stays disabled pending adapter integration.
Network-disabled native CLI smoke checks now verify synthetic Responses/Messages
decoding, Claude plugin discovery and its one-case native regex eval pipeline.
Results stay explicitly mock; no real model, usage or quality claim is made.
[English guide](docs/guides/foundations.md) · [Türkçe rehber](docs/guides/foundations.tr.md) ·
[Implementation status and limitations](docs/development/STATUS.md).

This checkout uses its managed installation, task DAG and validated handoffs for
development. [Self-use and resuming work](docs/guides/self-use.md) distinguishes
host delegation from native discovery; [test receipts](docs/guides/test-receipts.md)
explain explicit host execution and its evidence limits.

## Install

Requires Python 3.11+. No runtime dependencies.

```bash
pip install git+https://github.com/enestsc/AgentBase.git
cd your-project
agentbase init --provider both      # codex | claude | both
agentbase doctor
# Optional selective install instead: agentbase init --provider both --pack python --pack security
```

`init --dry-run` previews every change. Existing `AGENTS.md` / `CLAUDE.md` content is
preserved byte for byte; AgentBase only owns a marked block. After upgrading the CLI run
`agentbase update`. Updates refuse to overwrite locally edited managed files.

## What gets installed

| Path | Purpose |
|---|---|
| `AGENTS.md`, `CLAUDE.md` (marked block) | Shared instructions (Claude imports `@AGENTS.md`) |
| `.codex/agents/agentbase-*.toml` | Codex custom agents |
| `.claude/agents/agentbase-*.md` | Claude Code subagents |
| `.agents/skills/…`, `.claude/skills/…` | Progressively loaded skills |
| `.agentbase/` | Policy, roles, config, task DAG, memory, manifest |

## Commands

Project `explain`, `context`, `memory` and `tasks` commands require `agentbase init`
first and report an actionable error otherwise. `tasks validate --file` works independently.

```text
agentbase roles | skills            list canonical roles / skills
agentbase skills search|add|list|info|audit|update|rollback|remove|export|restore
agentbase packs list|info|recommend|add|remove
agentbase usage [--today|--week] [--provider codex|claude] [--by-agent|--by-skill] [--json]
agentbase usage configure|import|capture|export|delete    explicit opt-in; no automatic collector
agentbase spec init|validate|plan|tasks|reconcile|evidence   existing DAG and reported test trace
agentbase eval list|validate|run|report          offline structure / supplied-observation grading
agentbase eval capabilities --provider claude --consent  native help/version probes only
agentbase eval native-smoke --provider claude --image TRUSTED_PIN --mode eval --consent  synthetic API, network disabled
agentbase plugins build|validate               local artifacts; no publication
agentbase plugins validate --output PATH --native --consent  supported native static validation
agentbase init/update --discovery plugin        CLI state without duplicate plugin skills
agentbase uninstall [--dry-run] [--purge]   remove managed files/blocks; --purge also deletes .agentbase state
agentbase configure --mode sequential|safe-parallel
agentbase context ...              bounded file retrieval with size estimates
agentbase explain [--write] [--feature TERM]   incremental structural map (no model calls)
agentbase tasks ...                validate / schedule / transition a task DAG
agentbase tasks validate-handoff --file handoff.json   validate worker result fields and write scope
agentbase tasks test TASK_ID --source src --consent --argv ABSOLUTE_EXE ARGS   trusted host check; no sandbox
agentbase tasks receipt RECEIPT_ID   local source/task freshness; not authenticated proof
agentbase tasks sandbox ID --worker trusted-worker.json --context src/app.py --consent   offline Docker proposals
agentbase memory ...               evidence-backed notes, sync, handoff
agentbase memory list              show tracked note IDs and edit conflicts
agentbase memory prune --id ID --reason "resolved" --dry-run
agentbase memory supersede --id ID --reason "changed" --text "replacement" --evidence src/app.py:1 --dry-run
agentbase local ...                opt-in loopback Ollama proposals (never mutates files)
agentbase local models --consent   explicit installed-model discovery, no downloads
agentbase gateway validate --file POLICY.json   bounded fixed-provider gateway policy
agentbase gateway self-test --image TRUSTED_PIN --consent   dummy-key local Docker proof, no provider calls
```

## Example session

```bash
agentbase init --provider both --dry-run   # preview, writes nothing
agentbase init --provider both
agentbase doctor                           # offline diagnostics
agentbase tasks import --file examples/tasks.example.json
agentbase tasks ready                      # which tasks may start now (launches nothing)
agentbase tasks transition api-design ready
agentbase tasks transition api-design running
agentbase tasks validate-handoff --file handoff.json  # prepare with actual observations; see examples/handoff.example.json
agentbase tasks transition api-design review --handoff-file handoff.json
agentbase tasks transition api-design completed --evidence "docs/health-contract.md accepted"
agentbase memory handoff                   # compact, evidence-backed handoff
agentbase uninstall --dry-run              # preview a clean removal
```

`tasks.example.json` is validated by the test suite, so it always matches the schema.
Prepare `handoff.json` from the [handoff example](examples/handoff.example.json) using
real observations before review/completion. [Required fields and compatibility](docs/handoffs.md):
validation checks the task ID, fields, write scope and budget; it does not execute checks.
Review requires a handoff; completion requires a passed observation, no unresolved
failures and verification evidence. Rework/retry invalidates the previous handoff.
Memory maintenance archives explicitly selected intact notes and their evidence before
removing/replacing active entries. Omit `--dry-run` after reviewing the preview.
Manual notes and legacy notes without IDs are preserved; archives are outside the active
memory budget and remain on disk. The evidence index upgrades to v2 on a new note or maintenance write.
At the end of every task the host agent reports which role/agent did what (or why none was used).

## Roles and skills

Roles include provider-specific model/effort recommendations. Simple readers use
Luna/Haiku at low effort; architecture/security use Sol/Opus at high effort.
See [verified fields, sources and runtime limits](docs/provider-models.md).
The [prompt audit and proposed diff](docs/prompt-audit.md) document ownership,
read-only checks and skill-trigger corrections; model-session behavior remains untested.

Sixteen roles in four tiers (planning, implementation, quality, knowledge) are defined once in
`src/agentbase/assets/roles.json` and rendered per provider. Skills: explain-project,
architecture-map, plan-tasks, verify-change, sync-memory, session-handoff, local-assist,
prepare-release, changelog and pr-summary (10 total). Delivery skills prepare reviewable
artifacts; remote publication requires authorization. Existing projects gain new skills via
`agentbase update --dry-run`, then `agentbase update` after review.

## Who enforces what

1. **AgentBase tooling (deterministic):** DAG validation (cycles, transitions, dependencies,
   evidence before completion), cooperative file-claim conflicts, path confinement,
   hash-tracked managed files, atomic writes, context budgets.
2. **Host-agent policy (instructions only):** when to delegate, scope discipline, no commits
   or AI attribution, no nested delegation.
3. **Provider runtime:** actual subagent execution, sandbox and permissions. AgentBase does
   not control these and does not claim to.

Default execution is sequential with concurrency 1. `safe-parallel` is opt-in and allows only
compatible readers; writers are serialized.

## Privacy and safety

Network calls occur only for explicit GitHub skill operations or `agentbase local`
with Ollama explicitly enabled (loopback only). Imported code is never executed.
Skill add/update defaults to a plan; application requires its exact plan ID and
specific high-severity acknowledgements. Local edits are preserved.
Usage is opt-in and local, with unknown metrics kept null; context occupancy,
provider-reported tokens, estimated API cost and actual billing are distinct.
No automatic commits, pushes, analytics uploads or paid evaluations.
[Trust model](docs/security/trust-model.md) · [Architecture](docs/architecture/overview.md).

## Development

```bash
python -m unittest discover -s tests   # with PYTHONPATH=src
python -m ruff check src tests scripts
# Separate, explicit GitHub network smoke; no imported code execution:
python scripts/live_registry_smoke.py --network
```

MIT licensed.

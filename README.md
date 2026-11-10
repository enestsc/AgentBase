# AgentBase

Provider-native AI development workflows for **OpenAI Codex** and **Claude Code**.
One canonical set of roles, skills and policy; generated native adapters; a small
dependency-free Python CLI for deterministic coordination. Turkish: [README.tr.md](README.tr.md).

AgentBase is not an inference framework. It uses the agent runtimes you already have.

## Install

Requires Python 3.11+. No runtime dependencies.

```bash
pip install git+https://github.com/enestsc/AgentBase.git
cd your-project
agentbase init --provider both      # codex | claude | both
agentbase doctor
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
agentbase uninstall [--dry-run] [--purge]   remove managed files/blocks; --purge also deletes .agentbase state
agentbase configure --mode sequential|safe-parallel
agentbase context ...              bounded file retrieval with size estimates
agentbase explain [--write]        evidence-based structural map (no model calls)
agentbase tasks ...                validate / schedule / transition a task DAG
agentbase memory ...               evidence-backed notes, sync, handoff
agentbase memory list              show tracked note IDs and edit conflicts
agentbase memory prune --id ID --reason "resolved" --dry-run
agentbase memory supersede --id ID --reason "changed" --text "replacement" --evidence src/app.py:1 --dry-run
agentbase local ...                opt-in loopback Ollama proposals (never mutates files)
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
agentbase tasks transition api-design review --evidence "contract reviewed"
agentbase tasks transition api-design completed --evidence "docs/health-contract.md accepted"
agentbase memory handoff                   # compact, evidence-backed handoff
agentbase uninstall --dry-run              # preview a clean removal
```

`tasks.example.json` is validated by the test suite, so it always matches the schema.
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
architecture-map, plan-tasks, verify-change, sync-memory, session-handoff, local-assist.

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

No network calls unless you run `agentbase local` with Ollama explicitly enabled (loopback
only). No automatic commits or pushes. Token figures are labelled estimates.

## Development

```bash
python -m unittest discover -s tests   # with PYTHONPATH=src
```

MIT licensed.

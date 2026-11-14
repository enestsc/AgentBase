# Using AgentBase to develop AgentBase

The authoritative state is this local checkout. On 2026-11-14 the coordinator
installed the canonical integration here after reviewing `init --provider both
--dry-run`. No branch/worktree, commit, push, publication, imported installer or
real provider session was created. The original AGENTS.md and CLAUDE.md bytes
remain at the beginning of those files; installation appended managed blocks.

The pre-install snapshot covered 527 `.agentbase` files, including the session's
first-party bootstrap helper. Their SHA-256 values were checked after installation
by the coordinator and independently by the `dogfood_audit` helper. Build, schema,
native image and optional YAML artifacts remain intact. An existing `.agentbase`
directory is not evidence of an installed project and must never be treated as
disposable. In particular, `uninstall --purge` deletes state/artifacts there.

The actual workflow in this continuation:

| Task | Executor | Scope and evidence |
| --- | --- | --- |
| `selfuse-check` | `dogfood_audit` helper, codebase-explorer role | Read only; clean doctor, no-op update preview, 527 matching hashes, original instruction prefixes |
| `gateway-contract` | Primary coordinator, backend-engineer role | Gateway and regression tests; fail closed for remote MCP/container/context and unknown request/tool fields |
| `boundary-review` | `boundary_audit` helper, security-reviewer role | Read only; independent sanitizer matrix: 29 refused examples, 6 supported examples |
| `verify-handoff` | Primary coordinator, verification/documentation roles | Full unittest, Ruff, synthetic native compatibility, bilingual docs and persistent handoff |

Both helpers initially audited before bootstrap. That initial work was outside
AgentBase's DAG; the post-install checks/review above were dispatched after their
tasks entered `running`. The coordinator alone changes shared files/state. The
existing task engine handled import, sync, running, review, validated handoffs
and evidence-backed completion. The gateway task's scope was explicitly extended
under the project lock and validated before editing its Python test wrapper.
Default execution remains sequential with concurrency 1; initial independent
host audits do not demonstrate AgentBase parallel scheduling.

Native role/skill files were generated for both providers. This open session used
its existing host helper tools; automatic discovery/activation of the new native
definitions was not assumed. Local installed skills provide instructions, not
runtime permission or proof of execution. Existing CLAUDE.md already imported
AGENTS.md, so the appended canonical block repeats that import; its host-specific
deduplication behavior has not been verified in this checkout.

To resume from this repository in PowerShell:

```powershell
$env:PYTHONPATH='src'
python -m agentbase doctor
python -m agentbase update --dry-run
python -m agentbase tasks show
python -m agentbase tasks validate
python -m agentbase tasks ready
python -m agentbase memory handoff
```

Read STATUS/HANDOFF and review task scopes before changing state. Current task
state lives at `.agentbase/tasks.json`; session inventory, original instruction
copies, handoff JSON and mock reports live at `.agentbase/self-use-20261114/`.
These are ignored local state, not portable committed evidence. Preserve a
nonempty task store; do not re-import a new plan over it. Explicitly review and
archive a completed milestone before importing another. Do not rerun the session
bootstrap helper: init is already complete.

For a reviewed pending plan in a new, empty task store, the normal lifecycle is
`tasks validate --file reviewed-plan.json`, `tasks import --file reviewed-plan.json`,
`tasks sync`, `tasks transition ID running`, then `tasks validate-handoff --file
handoff.json`, `tasks transition ID review --handoff-file handoff.json`, and
`tasks transition ID completed --evidence "Observed check and artifact"`.
Run the checks you report; the CLI never executes commands from a handoff.

For newly executed trusted host checks, [test receipts](test-receipts.md) provide
explicit argv/consent, selected-source/task/executable bindings and stale reports.
They use the same task DAG and do not complete tasks or authenticate evidence.
This continuation preserved a snapshot of the four completed tasks under
`.agentbase/receipt-check-20261114/prior-tasks.json`, then appended validated
follow-up tasks under the project lock; none of the completed state was replaced.

Handoff validation checks schema, scope and evidence gates. Even an independent
helper's reported tests are not authenticated execution receipts. Native mock
checks prove decoding/discovery/grading compatibility only; real model behavior,
tool execution and spending remain unverified and production launch stays disabled.

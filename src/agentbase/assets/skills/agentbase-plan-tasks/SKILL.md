---
name: agentbase-plan-tasks
description: Use when dependent components or justified specialists require a coordinated plan; skip task DAGs for small direct changes.
---

For small work, implement directly. Otherwise read `.agentbase/policy.md` and
`.agentbase/config.json`. The primary host session remains the Orchestrator.

Prepare JSON with `schema_version: 1` and `tasks`. Each task needs `id`,
`description`, `role` (an AgentBase role ID), `dependencies` (IDs), `inputs`,
`outputs`, `scope` (`[{"path":"src/service.py","access":"write"}]`),
`resources` (`[{"name":"test-db","access":"write"}]`, or empty),
`acceptance` (checkable criteria), `status: "pending"`, `verification: []`,
and `blocking_reason: ""`. Inputs, outputs and acceptance are nonempty string
lists. Directory scopes include descendants; `.` covers the project. No globs.
Use narrow scopes. Give shared mutable environments resource claims. Unknown
runtime effects require exclusive write claims.

Separate contracts from implementation when useful. Do not invent dependencies.
Run `agentbase tasks validate --file plan.json`, then the Orchestrator imports it
using `agentbase tasks import --file plan.json`. Import refuses to replace
existing nonempty work. `agentbase tasks sync` promotes eligible pending tasks;
`agentbase tasks ready` proposes a deterministic compatible batch, without
launching workers. Claim each task via `agentbase tasks transition ID running`.

Use native specialists if available, otherwise apply the appropriate canonical
role in `.agentbase/roles/` sequentially. Do not use recursive delegation. Respect
configured concurrency and actual host permission/runtime limits. This release
allows parallel readers only, with writers serialized against all other work.
Explicit specifications may use `spec tasks ID --import` for an empty store and
`spec reconcile ID` for reviewed incremental updates. Apply only the exact plan ID.
Started/evidenced requirements must become follow-up work, not rewritten criteria.
`spec evidence ID` reports explicit criterion-to-handoff test mappings; these are
host-reported observations, not independently verified execution.

An explicitly trusted, pinned offline worker may use `tasks sandbox ID --worker
POLICY.json --context PATH --consent` only after the task is running. It receives
selected in-scope snapshots inside a verified local Linux Docker boundary and
returns untrusted proposals. No host files or task states are changed by the
worker. Cloud-provider execution remains unavailable. Never weaken that boundary
or forward host secrets/provider home directories to obtain a fallback.

Workers return schema-v1 JSON with `schema_version: 1`, `task_id`, `result`,
`changed_files`, `decisions`, `tests`, `failures`, `risks` and `artifacts`.
Use arrays for all fields except version, task_id and result; each tests item
has `command`, `status` (`passed`, `failed`, `not-run`) and `outcome`.
Keep empty arrays explicit. Changed files must fit the task's write scopes;
read-only roles return proposals with changed_files empty. List checks not run
with a reason. The Orchestrator runs `agentbase tasks validate-handoff --file handoff.json`,
then `agentbase tasks transition ID review --handoff-file handoff.json`, verifies
acceptance, and records `completed --evidence "observed check/result"`.
Completion needs a passed observation and no unresolved failures; validation
does not execute checks. Rework via running or a retry discards the old handoff.
Use `blocked --reason "..."` for missing inputs; investigate before retrying via
`pending`. Never complete another task by implication. CLI claims are advisory
to the host; they do not intercept filesystem writes or spawn agents.

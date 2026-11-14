---
name: agentbase-sync-memory
description: Use for an explicit memory sync, a significant decision or milestone worth retaining; use session-handoff for a resume guide, not automatic deep scans.
---

The Orchestrator is the single writer of shared project memory. Workers return
proposals. Read the relevant notes under `.agentbase/memory/`, not transcripts.

For light synchronization run `agentbase memory sync`. It derives status from
the validated task plan without scanning repository source. Record a significant
decision, issue, milestone, relationship or question with
`agentbase memory note decision --text "..." --evidence src/module.py:12`.
Available categories: overview, decision, milestone, issue, question, relationship.
Every note needs a real source file/line; the tool records a content hash. A
reference proves where evidence was recorded, not whether the prose is correct.

For requested deep synchronization run `agentbase memory sync --deep`. Review
changed/missing evidence and relevant source before reconciling semantic claims
or architecture diagrams. The deterministic scan does not rewrite decisions.
Explicitly review any proposed replacement of an authoritative decision.

For maintenance, run `agentbase memory list`, select intact note IDs, then use
`agentbase memory prune --id ID --reason "..." --dry-run` or
`agentbase memory supersede --id ID --reason "..." --text "..." --evidence src/module.py:12 --dry-run`.
Review selected entries and the archive path before omitting `--dry-run`.
Manual, legacy and edited notes are preserved; do not delete them to bypass limits.
Keep entries concise. Do not evade limits by creating endless note files. Never store
secrets or full chats. Model-generated proposals need human/Orchestrator review
and source validation before becoming memory.

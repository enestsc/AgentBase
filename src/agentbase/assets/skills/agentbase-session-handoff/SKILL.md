---
name: agentbase-session-handoff
description: Prepare a concise, evidence-backed guide for resuming development in a later session.
---

Run `agentbase memory handoff` to collect bounded memory and current task state.
Review the relevant source and recent verified handoffs. Explain what the project
does, what works and how it was checked, recent changes, incomplete work,
important code locations and the next files to read. State unknowns explicitly.

Keep within the configured handoff character budget. Remove repetitive history
before dropping accepted decisions, blocking reasons or essential artifacts.
The CLI marks omitted material; retrieve missing critical notes selectively.
Do not infer completed work from task descriptions. Only recorded evidence and
observed implementation establish results. The Orchestrator may save the final
reviewed resume guide in an assigned project document; the CLI never silently
replaces an authoritative decision or forwards a full conversation.

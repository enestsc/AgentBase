---
name: agentbase-architecture-map
description: Use when a component diagram, feature-flow diagram or stale-map review is requested; use explain-project for a prose walkthrough.
---

Use `agentbase explain` as a starting inventory. Read actual imports, interfaces,
configuration and relevant tests to establish edges. The generated graph shows
only resolved lexical local imports; an import is not proof of a runtime call.
For runtime edges, cite a call site or an observed trace. Mark inferred edges.

Choose a diagram for the question: component flowchart for boundaries, sequence
for a request path, or state diagram for lifecycle behavior. Keep Mermaid labels
escaped, small and legible. Include an evidence table mapping important edges
to source locations. Never draw imagined services, databases or deployment tiers.

Walk through one representative implemented feature from entry to result.
State unknown paths, dynamic imports and external dependencies separately.
When checking stale docs, compare each claim to current files and tests;
`agentbase memory sync --deep` flags previously recorded file hashes that changed
but cannot prove semantic drift. Update only the assigned docs, recording
limitations and unexecuted checks.

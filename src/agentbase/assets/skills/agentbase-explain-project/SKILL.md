---
name: agentbase-explain-project
description: Use when a repository explanation or implemented-feature walkthrough is requested; keep scope to the question and load architecture-map only for needed diagrams.
---

Start with the user's question and audience. Read concise memory if available.
Run `agentbase explain` for a bounded source inventory, symbol map, local import
references and evidence hashes. It is structural evidence, not a complete
architecture or runtime trace. It does not run application code or model calls.
For a focused question, `agentbase explain --feature TERM` shows lexical matches
and one-hop import neighbors; it is not semantic feature discovery. Nested Python
symbols and lexical call candidates cite source locations without proving runtime
targets. Written/deep reports reuse a hash-based fact cache, resolving imports
against the current inventory; raw source is not persisted in that cache.

Select the main entry points from actual manifests/source, then read narrow
regions to trace the requested features: trigger, boundary, processing, storage
and response. Explain the project's purpose only when supported by source/docs;
mark uncertain intent. Connect each key claim to a file, symbol or test. Separate
static inference from observed runtime behavior and unresolved questions.

Use `.agentbase/config.json` context limits. Read targeted files via
`agentbase context path/to/file`; it excludes common secrets and oversized
material. Omitted evidence requires selective retrieval, not guessing. Do not
load every role or produce comprehensive docs for an ordinary small edit.

Use the architecture-map skill when a diagram materially helps. Finish with
what works (and how verified), component relationships, feature walkthroughs,
important code locations and next reads. For requested durable output,
`agentbase explain --write` writes the marked structural report and derived index; author
semantic explanations in assigned documentation files after checking evidence.

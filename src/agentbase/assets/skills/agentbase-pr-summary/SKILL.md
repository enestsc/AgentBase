---
name: agentbase-pr-summary
description: Use when drafting a pull request title and body for a specified diff or branch; does not create or publish the PR unless separately authorized.
---

Resolve the intended base and head from the request and Git state. Read the diff,
relevant acceptance criteria, repository PR template and recorded verification.
If the base cannot be established, report that gap before making coverage claims.
Summarize the final implementation for a reviewer without conversation history.

Lead with the concrete problem and resulting behavior. Describe the material
design choices, compatibility or migration impact, executed checks and observed
results, and remaining limits. Keep simple changes short; follow a repository
template when present. Separate local checks from CI and actual provider-session
validation. Do not claim CI passed from workflow files or a local unit suite.

Return a proposed title/body with the compared base/head and any unresolved gaps.
Do not add AI attribution or co-author trailers. Drafting does not grant permission
to commit, push, create a remote PR or send review messages; use existing explicit
authorization if provided, otherwise stop before the external action. Never copy
secrets or private logs into the summary. A failed publishing attempt is a result
to report, not permission to switch accounts or broaden scope.

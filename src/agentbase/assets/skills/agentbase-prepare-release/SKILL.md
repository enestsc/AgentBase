---
name: agentbase-prepare-release
description: Use when preparing a versioned release or checking release readiness; produces a reviewable release plan without implying publication permission.
---

Read the package/version manifest, changelog, contribution commands and actual
release workflow. Establish the intended version and release range from the
request and repository; flag missing information instead of inventing a tag.
Check compatibility impact, version consistency and release-note coverage.

Run the repository's authorized checks and packaging validation when the required
tools are already available. Record exact commands and observed results; list
unavailable checks as not run. For AgentBase use PYTHONPATH=src with unittest,
then `python -m ruff check src tests`; packaging commands come from its CI.
Do not install build tools or change publisher/account settings merely to prepare
a release. A successful unit suite does not establish that publication works.

Return the proposed version, included changes, verification evidence, remaining
blockers and concrete tag/publication steps for review. Use agentbase-changelog
only if release-note edits are needed. Preserve unrelated Unreleased entries.
If edits are assigned, limit them to version/release documentation and run the
affected checks. Creating tags, pushing, publishing packages and changing account
settings each require authorization covering that action; preparation grants none.
Existing explicit authorization remains valid. Stop before any unauthorized step.

---
name: agentbase-changelog
description: Use when drafting or updating changelog entries from an implemented diff or release range; use prepare-release for publication readiness.
---

Read the existing changelog convention and the requested diff/range. Identify
user-visible changes, compatibility effects and fixes from implementation and
tests. Group related behavior under the repository's existing categories rather
than copying commit history. Explain the trigger and resulting behavior where
that makes a fix understandable. Do not turn planned work into completed features.

Edit only the assigned changelog/release-note scope. Keep unrelated Unreleased
entries, previous releases, dates and links intact. Use a release date or version
only when established by the request or repository; otherwise retain Unreleased.
Cross-check commands and named options against current code. Report test evidence
as observed, and explicitly label unexecuted checks. Return the changed entries,
their supporting files and unresolved release-note gaps to the Orchestrator.

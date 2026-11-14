# ADR 0001 — Extend existing safety and canonical data

Date: 2026-11-10. Status: accepted for local implementation.

Keep the flat module architecture, dependency-free Python 3.11 runtime and
existing CLI behavior. Add focused modules rather than recreating the conceptual
directory tree in the master prompt. Extend `batch_write` to bytes for binary
skill assets while retaining atomic replacement and ordinary-failure rollback.

Use a distinct third-party provenance lock alongside the first-party generated
manifest: the two own different files, but both reuse confinement and project
locking. Resolve GitHub refs through HTTPS API and read bounded pinned ZIPs;
avoid Git hooks, submodule semantics, archive extraction and arbitrary fetch URLs.
Review/apply uses a content-derived plan ID. High-severity acknowledgement is
specific, never a generic force override. Multi-skill batch restore is deferred
until it can preserve one transaction across all selected installations.

Keep YAML support deliberately constrained and documented to avoid a new mandatory
parser dependency. Unsupported valid YAML fails explicitly. Preserve notices and
unresolved license status; do not treat recognized MIT text as permission when
additional restrictions appear.

Usage capture is a user-controlled import boundary. Separate context observations,
incremental counters and cumulative counters. Never scrape provider private logs,
tokens or account endpoints. Metrics retain source semantics and provenance;
unknown values stay null. Strict event identity plus competing-source exclusion
prevents double counting under the documented stable-ID capture contract.

Packs select the existing catalog. Specification compilation emits the existing
task schema. Evaluations grade explicit observations or static structure, not
invented model activations. Local packages come from canonical definitions and
remain optional. The provider runtime enforces actual permissions.

External cross-provider runners are deferred because cwd/scope prompts cannot
enforce the requested sandbox or terminate arbitrary descendants safely across
Windows/macOS/Linux. A real runner needs a separately verified execution boundary.
Native eval launchers remain opt-in future work; no paid test was run.

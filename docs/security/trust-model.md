# Trust model and privacy

| Threat | Implemented boundary | Remaining limitation |
| --- | --- | --- |
| Malicious skills / prompt injection | Treat as bytes; deterministic findings; exact reviewed plan; specific high-severity acknowledgement | Scanner is heuristic; host must treat imported instructions as untrusted |
| Scripts / hooks / dependency confusion | Never execute/import source, run Git, install dependencies or enable hooks automatically | Later host execution requires its own authorization and sandbox |
| Repository supply chain | Full SHA pin, per-file SHA-256, notices, review invalidated on moving ref | GitHub transport trust; no signature/transparency verification |
| Traversal / links / special files | Validate every archive path, reject case collisions, links and special files; confined output paths | Cooperative project lock cannot stop a hostile local process racing filesystem changes |
| Decompression bombs | Download, expanded size, per-file, entry-count and compression-ratio limits | Bounds intentionally reject some legitimate repositories |
| User work loss | Managed hash checks, untracked-file protection, rollback on ordinary I/O failure | Power loss across files needs manual drift recovery; no crash journal |
| Unauthorized filesystem access | Confined local writes; opt-in offline worker gets only selected snapshots in a read-only bind, no project/home mount | Docker shares the host kernel; daemon/admin and local process races remain trusted boundaries |
| Credential leakage | No auth harvesting; allowlisted usage metadata; no raw prompts, code, environment or tool output saved | Operators must use opaque identifiers and protect project ACLs |
| Telemetry | Explicit source opt-in, local storage, no analytics upload, retention/export/delete | Export destination and sharing are operator-controlled |
| Untrusted model output | No inference in specs/evaluation/import; supplied evidence labeled; handoff validation | A schema-valid observation does not prove correctness or actual execution |
| Local test receipts | Explicit host argv/consent for running writers, task/source/executable hash bindings, managed manifest, bounded hash-only output and freshness checks | Trusted host execution, no sandbox/verified descendant cleanup; selected source subset only; local records can be forged by an editor with access to both receipt and manifest |
| Cross-provider execution | Cloud launch refused; offline deterministic worker requires trusted pinned local image, verified Docker restrictions, non-root/env clearing, no network, resource caps and forced removal | Credential gateway tested separately; cloud runner, real provider activation and hard spending limits remain unverified |
| Native synthetic probes | Real native CLI in verified network-disabled container; only first-party fixture/plugin files, loopback mock API, empty-home environment and bounded reports; forced removal verified | Mock response decoding/discovery/grading only; no tool execution, real model behavior, usage/cost or plugin contribution evidence |

No check grants broader provider permissions. Scan success means "no issues
detected by the implemented checks", not guaranteed safe. Missing/ambiguous
licenses remain unresolved, and acknowledging a warning grants no legal rights.

Source notice copies live with imported skills; their provenance/rights are
separate from AgentBase's MIT license. See [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md).
Usage data is local and optional; protect `.agentbase/usage` and avoid tracking it
in version control. This repository ignores all `.agentbase` state. Other projects
should add their own ignore rule; AgentBase does not alter user Git rules silently.

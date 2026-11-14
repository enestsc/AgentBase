# ADR 0002 — Resumable hardening and offline execution boundary

Date: 2026-11-14. Status: implemented locally; cloud execution deferred.

Extend the existing registry, usage pipeline, task DAG, code maps and Ollama client.
The stdlib runtime stays dependency-free. Optional PyYAML is explicitly selected,
uses SafeLoader composition, accepts only bounded shallow string mappings and
rejects duplicates/tags/anchors/aliases. This deliberately supports safe syntax
needed by more upstream files without promising arbitrary YAML graph support.
[Agent Skills metadata](https://agentskills.io/specification) and
[PyYAML safe parsing](https://pyyaml.org/wiki/PyYAMLDocumentation) remain the sources.

Multi-restore stages all pinned bytes, recomputes current findings/compatibility,
checks all ownership/conflicts, then writes one recoverable batch and lock-last.
Ordinary rollback removes only newly created empty parents to permit retry.
This is not a power-loss transaction. Discovery links grant no approval; dependency
presence is inspected without execution/import and unknown declarations stay unknown.

Cumulative usage deltas crossing local day boundaries are unallocated in daily
reports and cannot be assigned precisely to a period whose start they cross.
Incremental stdin events require stable caller IDs; snapshot fingerprints only
deduplicate normalized observations. Differing correlation endpoints cannot assign
an interval's tokens to one role. No private logs or credentials are discovered.

An active specification owns explicit static task-definition hashes. Reconciliation
changes only owned pending tasks without evidence; unchanged runtime state and
other tasks survive. Criterion mappings bind to source and handoff hashes and
report supplied observations rather than inventing independently verified tests.

The static index caches per-file facts and resolves imports against each current
inventory. Thus adding/deleting a target does not leave cached dependency edges.
No source text is persisted in the cache. Calls and feature matches remain lexical.
Ollama metadata preflight bounds selected size/capacity and requests structured,
bounded output. Advertised size checks are not OS memory guarantees.

External workers use a separate, explicit offline Docker boundary. A trusted local
Linux daemon, pinned preinstalled image, non-root uid, readonly root/input, empty
worker environment, no network/capabilities, memory/PID/tmpfs bounds and verified
container removal limit the worker. The daemon's actual configuration is inspected
before start. No project/home/socket mount, pull, automatic integration or DAG
completion. Docker/host admin/kernel and local filesystem races remain trusted.
The worker must be explicitly trusted; pinning does not itself confer trust.
[Docker run](https://docs.docker.com/engine/containers/run/) and
[termination](https://docs.docker.com/reference/cli/docker/container/kill/) describe
the underlying runtime; native Docker Desktop evidence is recorded in STATUS.

Cloud workers need a credential-isolating gateway and reviewed network/cost policy.
Do not pass API keys, provider home directories or auth files into model tools.
Read-only native version/help probes and Claude static plugin validation are
implemented, but do not claim model activation or secure cloud execution. Installed
Claude eval's `--max-cost-usd` checks before runs, allowing in-flight overrun; it is
not an exact hard spending cap. No paid runtime was launched to validate it.

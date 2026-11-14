# Development roadmap

The current delivered scope is recorded in [STATUS](STATUS.md), not inferred
from command names or the original target architecture.

Latest bounded slice: explicit trusted host execution receipts, selected-source
inventory/task/executable hash binding and freshness checks. These local records
do not authenticate execution/acceptance or upgrade specification evidence.

Local self-use is now real: preserved installation, DAG transitions, validated
handoffs and independent host helper review. The resulting gateway finding is
fixed with request/tool field allowlists and regression evidence. Explicit local
source/task-bound execution receipts are now implemented; reported
helper tests still are not authenticated runtime receipts. Production native
launch remains disabled. See the [resume guide](../guides/self-use.md).

1. P0 interoperability now includes optional bounded safe YAML, curated discovery,
   presence checks and staged multi-restore. Remaining: more upstream fixtures,
   authenticated provenance/signatures and power-loss recovery journal.
2. Stdin capture and cross-day uncertainty handling are implemented. Next validate
   real user-authorized live events and host-managed capture setup; do not scrape logs.
3. Active-plan reconciliation and explicit criterion/handoff-test mappings are
   implemented, with separate explicit host execution receipts. Remaining:
   independently authenticated runtime provenance; local receipt and handoff
   observations deliberately make no such claim.
4. Native eval launcher: image feature/version probes and network-disabled synthetic
   decoding/discovery/one-case Claude regex eval now exist. Production still needs explicit spending consent,
   cost/time/concurrency limits, trusted fixtures, no publish/scaffold by default,
   actual usage and comparable baseline. Ordinary CI remains offline.
5. An offline Docker TaskRunner now enforces local Linux-container snapshots,
   no host environment/network, resource caps and forced container removal, with
   a separate real smoke on Windows Docker Desktop. Cloud runners still require
   native adapter integration with the now-tested credential gateway and cost contract;
   never forward host keys or provider home directories to workers.
   Default active-host routing, opt-in cross-provider calls, concurrency 1 and
   structured handoffs. No cwd-only or prompt-only sandbox claims.
6. Claude canonical plugin discovery now has synthetic native init-event evidence.
   Validate generated plugin behavior in real authorized Codex/Claude sessions;
   test upgrade/dedup paths across supported client versions. Publishing remains
   separately authorized. Optional icons/catalog presentation can follow.
7. Hash-based static indexing and targeted feature maps are implemented. Deeper
   semantic/call resolution and optional installed structural tools remain. Respect GitNexus's restrictive license; do not
   bundle noncommercial code. Keep diagrams tied to actual source evidence.
8. Ollama discovery, capability/context/size checks and structured proposal validation
   are implemented with fixture coverage. Real local-model validation is still opt-in;
   peak RAM/VRAM limits require an independently enforced runtime boundary.

The credential gateway has synthetic protocol and real internal-network Docker
evidence. Next implement native worker/eval adapters and a reviewed spending
contract on that boundary. Live inference,
native activation, spending, publication and cross-platform verification remain separate.

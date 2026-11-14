# ADR 0004: verify native protocol behavior without provider access

Status: implemented for synthetic probes; production native launch remains disabled.

Native help/version and static plugin validation cannot establish runtime response
decoding or the eval result contract. Real provider sessions would consume account
usage, introduce credentials and conflate protocol compatibility with model quality.

Use a first-party loopback fixture and the real native executable in one verified
network-disabled container. Reuse the canonical gateway request checks and canonical
distribution generator. Only fixed first-party inputs are accepted; neither project
configuration nor imported plugin code enters the container. No arbitrary prompt,
server URL, tool grant, executable arguments or credential input is exposed.

Separate contract evidence, synthetic native behavior and real model behavior in
reports. Discard raw native traces and synthetic billing/usage figures. Fail closed
on unknown result schemas, partial evals, extra arms/runs, errors, marker mismatch
or missing Claude plugin discovery. Force-remove and verify the whole container
on all exits. No daemon/image changes, paid launch or publication follow a pass.

This intentionally verifies a narrow no-tools subset. Provider credentials, hosted
features, real task execution, hard spending guarantees and plugin effectiveness
need their own reviewed contracts and evidence; a mock result cannot establish them.
See [native probe architecture](../architecture/native-probes.md) and
[gateway boundary](../architecture/provider-gateway.md).

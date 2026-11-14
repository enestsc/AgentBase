# Local host test receipts

`tasks test` executes only the literal argv supplied by the operator. Review the
trusted executable and arguments, claim a **running writer task** in the existing
DAG, and explicitly consent. It never executes a command copied from a task,
specification or handoff. This is host execution with the host user's file and
network rights. Source scopes and a minimal environment are **not a sandbox**.
Use the separate Docker worker when an enforced offline boundary is required.

PowerShell example, after reviewing the task's scope:

```powershell
$python = (Get-Command python).Source
agentbase tasks test TASK_ID --source src --source tests --source pyproject.toml --pythonpath src --timeout 120 --consent --argv $python -m unittest discover -s tests
agentbase tasks receipt RECEIPT_ID
```

`--argv` must be the last option; everything after it is a literal argument.
The executable must be absolute; Windows requires `.exe` both before and after
path resolution and refuses batch/script targets. The task must already be running and have a write claim;
the canonical DAG serializes writers and the project lock spans execution and
storage. Do not put secrets in arguments: they are visible to the process and OS
even though receipts retain only an argv hash.

Each managed receipt under `.agentbase/receipts/` records:

- Task ID and canonical static definition hash, including acceptance, scopes,
  dependencies and resource claims. Runtime task status/handoffs are excluded.
- Selected source roots and file inventory with SHA-256 and byte sizes;
  executable path/hash, argv hash, explicit Python import directories and timeout.
- UTC start time, elapsed seconds, exit status and timeout/output collection result.
  stdout/stderr retain only byte counts and SHA-256 of at most 1 MB per stream;
  raw output, literal argv and environment values are not stored.

The CLI checks sources, executable and task definition before and after execution.
`tasks receipt` re-enumerates the same roots: changed, added, deleted, unreadable
or newly linked source files make the receipt stale. Unreadable post-run bindings
also prevent success. Timeout, nonzero exit, output overflow and incomplete pipe
collection never pass. Successful/failed or stale reports return exit 0/1;
rejected input/permission or launch errors return 2 without an execution receipt.
A stale receipt stays stored for inspection.

Select 1..50 non-overlapping project-relative files/directories within task scope.
Inventory limits: 2,000 files, 5,000 visited entries, depth 50, 1 MB per file and
16 MB total. Links/junctions, special files, case collisions and common secret
paths are refused. Standard context exclusions such as `.git`, `.agentbase`,
`node_modules`, build directories and `__pycache__` are omitted beneath directory
roots; explicitly selecting an excluded path is refused. An empty inventory fails.
Only these selected bytes are bound. Add relevant configuration, fixtures and lock
files explicitly. External libraries, interpreter modules, tools and external
resource **contents** are not hashed; a resource claim binds only its declaration.

The child receives OS system/temp variables, a small executable/system PATH,
disabled user-site imports/bytecode and optional confined `--pythonpath` directories
under selected source roots. It receives no inherited provider credentials or
operator PYTHONPATH. This can change test behavior: tools outside that PATH are
unavailable and suites may skip optional checks. Inspect and report actual test
outcomes separately; exit 0 does not establish acceptance coverage.

Timeout/output failure terminates only the direct child. Pipe waits are bounded;
descendant cleanup is explicitly **unverified**, and descendants may retain host
rights after the parent exits. Cooperative locks do not stop a hostile local
process. Before/after hashes miss changes reverted during execution. A local editor
who can change both receipt and manifest can forge the record: hashes detect
ordinary drift, not independent or cryptographically authenticated execution.
Protect project ACLs. Edited/missing managed receipts stop later reads/runs;
untracked receipt paths are preserved. The store accepts at most 1,000 receipts.

Receipts never transition a task or upgrade `spec evidence`/handoff observations.
The coordinator still maps acceptance and records a validated handoff explicitly.
See [Turkish guide](test-receipts.tr.md).

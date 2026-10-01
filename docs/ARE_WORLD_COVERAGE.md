# ARE coverage of Manos's paper scenarios

This is the pre-repair coverage checkpoint. [Verified repairs](ARE_REPAIRS.md)
now make all 71 executable references run without tool errors and score all
71 saved traces under a separate revised policy. The six fixture-blocked
Web Browsing tasks remain blocked. The details below preserve the original
defect inventory and historical scoring behavior.

1 October 2026. All **77 source tasks across 13 worlds** are registered with
ARE 1.2.0 and selectable through `are_integration.live --scenario`. This adds
execution coverage; it does not establish model task success or reproduce the
five paper metrics. The original worlds, shared function-calling runner, mapper,
and scorer are unchanged.

## Coverage

| World | Registered | ARE can initialize | Offline reference result |
|---|---:|---:|---|
| Automation | 5 | 5 | 5 replayed |
| Communication | 3 | 3 | 3 replayed |
| Computations | 5 | 5 | 4 replayed; task 5 reference uses nonexistent `powers` |
| CRUD | 5 | 5 | 5 replayed, including source typos/duplicate updates |
| Desktop Manager | 6 | 6 | 6 replayed |
| Events Scheduler | 6 | 6 | 6 replayed |
| File Management | 6 | 6 | 6 replayed |
| Legal Compliance | 5 | 5 | 5 replayed |
| Navigation | 6 | 6 | All 6 reproduce source `grid_size` errors |
| Transactions | 12 | 12 | 12 replayed; exact dataset IDs do not match |
| Validation | 6 | 6 | 5 replayed; task 2 reference has invalid syntax |
| Web Browsing | 6 | 0 | Missing reviewed local HTML fixtures |
| Writing | 6 | 6 | 6 replayed |
| **Total** | **77** | **71** | **63 replayed without exceptions, 6 with source errors, 2 invalid references, 6 blocked** |

The 69 usable reference sequences match direct execution of the original worlds
in call order, arguments, returned values, errors, final state, and legacy
evaluation. Clock/randomness are fixed only for offline reference comparison.
The evaluator scores 28 of these probes and leaves 41 unscored with explicit
reasons. A scored path is not an independent task-success result.

All eight formerly deferred setup tasks now initialize through ENV events before
the user request. Setup never enters the agent workflow. All twelve Transactions
tasks retain their source `transaction_1` … `transaction_12` IDs; no heuristic
join to dataset `transactions_*` entries is made. They execute but remain
unscored. Agentic Farm and Agentic Arm are absent from this repository;
Configurations remains outside the paper scope.

Web Browsing requires `page1.html`, `page2.html`, and `page3.html`. Its six tasks
are listed and registered, but initialization and the live runner reject them
before exposing filesystem tools or creating a provider client. Inventing these
fixtures would change the benchmark. Navigation movement errors, the two broken
references, and CRUD reference defects also remain source issues to resolve in
the scenario revamp. The two tasks with malformed references can still run an
agent turn; only their offline oracle reference is unavailable.

## Run offline

From the repository root, after installing `requirements-are.txt` and this
checkout in editable mode:

```sh
.venv/bin/python -m are_integration.sweep --mode inventory --output /tmp/core-are-inventory.json
.venv/bin/python -m are_integration.sweep --mode offline --output /tmp/core-are-reference-sweep.json
.venv/bin/python -m are_integration.sweep --mode offline --scenario core_automation_2 --output /tmp/core-are-automation.json
.venv/bin/are-run -s core_automation_2 -o
.venv/bin/python -m unittest discover -s tests -q
```

Use a new output filename for each sweep. Inventory exports every task's setup,
reference, dataset, and fixture status. Offline mode additionally exports both
original and ARE artifacts, legacy evaluation, and parity checks. It exits
nonzero for adapter errors or parity failures; known source errors/blockers stay
explicitly listed. A zero exit code therefore indicates adapter parity, not
successful completion of all tasks. These commands require no model key.

The new `catalog.py` wraps the methods already exposed by Manos's shared runner,
preserves their signatures, distinguishes reads/writes, freezes returned values,
and snapshots/resets source world state. Setup/reference strings are parsed as
direct calls with literal arguments; they are never evaluated as Python code.
Only the prompt and tool definitions are given to an agent.

The existing `core_computations_1` and `core_crud_2` keep their dedicated state
validators. Other scenarios report ARE validation `success: null` because they
do not yet have independent task validators. Their replay references cannot
serve as evidence that an arbitrary live agent completed the task. The live
CLI consequently cannot return a validated-success exit code for these generic
scenarios yet; saved traces and reply delivery remain available for review.

## Verification

**73 tests pass.** Checks cover all 77 registrations, tool construction for all
71 executable tasks, full offline reference parity, setup isolation, blocked
fixture rejection, state/reset isolation, literal parsing, and mocked ARE
text-action agents across all 12 executable worlds. ARE CLI discovery and oracle
execution were also checked on the setup-dependent Automation scenario. No new
paid runs were made for this expansion.

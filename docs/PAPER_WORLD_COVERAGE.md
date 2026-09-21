# Paper-world execution checkpoint

19 September 2026 local time. Execution coverage for the Week 1 port, not paper
metric reproduction. Original runner, worlds, and task definitions are unchanged.

## Results

- Paper: 15 worlds. Local implementations: 13; Agentic Farm/Arm are absent.
  Configurations is excluded from the paper-only scope.
- 77 source tasks inventoried: 51 runnable, 26 deferred (8 setup-dependent,
  12 Transactions ID mismatches, 6 Web Browsing missing HTML fixtures).
- 12 dataset-only Transactions entries are the other side of the ID mismatch,
  not additional runnable source tasks.
- All 51 runnable tasks received one nano run: **45 final responses, 6 call-limit
  stops**. This is not a success rate. All 33 tool exceptions were in Navigation;
  no fatal provider failures occurred.
- 210 tool calls; 230,475 input tokens and 5,766 output tokens.
- **51 offline tests pass at the latest evaluation checkpoint.** Paper-only reference probes executed 49 tasks and
  could not parse two references; six Navigation probes recorded world errors.

| World | Live tasks | Runtime outcome |
|---|---:|---|
| Automation | 2 | Final responses, no tool exceptions |
| Communication | 3 | Final responses, no tool exceptions |
| Computations | 5 | Final responses, no tool exceptions |
| CRUD | 3 | Final responses, no tool exceptions |
| Desktop Manager | 5 | Final responses, no tool exceptions |
| Events Scheduler | 4 | Final responses, no tool exceptions |
| File Management | 6 | Final responses, no tool exceptions |
| Legal Compliance | 5 | Final responses, no tool exceptions |
| Navigation | 6 | Existing grid_size error in all; task 5 hit limit |
| Validation | 6 | Final responses, no tool exceptions |
| Writing | 6 | Tasks 1,2,4,5,6 hit limit; task 3 returned final response |

## Evidence and reviewed findings

Live summary: `runs/batches/2026-09-18_230912_247245Z_live/summary.json`.
Combine its 48 `runs` and 3 `reused_runs` for 51 unique tasks. The earlier batch
was interrupted after three paper tasks when scope was clarified; no Configurations
live task ran in that batch.

Offline summary: `runs/batches/2026-09-18_231056_213804Z_offline/summary.json`.
Summaries link task artifacts; `evaluation` and `task_success` remain null.

- Navigation stores grid_size on the object but reads it from world state.
  Offline/live movement raises KeyError. Existing world defect, deferred to revamp.
- `crud_1` created Alice and verified her age but omitted `list_users` and did not
  list her details in the final response. Model omission requiring evaluation.
- `writing_1` produced the correct sentence, then restarted after `complete_sentence`
  cleared world state. It eventually hit the cap. Limit stops do not necessarily
  mean no correct output was produced; this is model/world interaction to review.
- `file_management_6` received False from search and then appended the missing word.
  False was an expected conditional result, not a runtime error.
- `computations_5` reference uses nonexistent `powers`; `validation_2` has malformed
  call syntax. Offline reference probes were blocked; live calls still executed.

Port fixes: unwrap Navigation's existing decorators to bind original methods;
support its fixed coordinate-pair input as a length-checked JSON array. No world
behavior or scenario repair was made. Setup/ID/fixture issues remain listed for
revamp, per Manos. No full task-success rate or paper-metric result is claimed.

Next: review these findings before considering any default switch. Paper evaluation
remains separate unfinished work. Nothing was committed, merged, or pushed.

## Saved-run evaluation

The adapter now evaluates registered worlds through the unchanged legacy mapper
and scorer. Of 51 live traces, 30 scored: 24 at 1.0, two at 0.6, one at 0.5,
two at approximately 0.3333, and one at 0. The other 21 remain unscored with reasons.
These are legacy path scores, not confirmed task successes.

Compatibility inspection found zero-argument mapping problems in 20 traces,
other argument mapping problems in four, and execution errors in six; these
categories overlap. The adapter does not score a trace after dropping its
unmapped or failed calls. Original argument matching and path-search limitations
remain, including incomplete A scoring 0 rather than the direct A,C comparison's 0.5.

Local output: `runs/batches/2026-09-18_230912_247245Z_live/evaluation.json`.
`runs/` is included for team review. This report provides the checkpoint;
the saved artifacts allow these exact scores to be reproduced without API calls. No additional API calls were made for evaluation.

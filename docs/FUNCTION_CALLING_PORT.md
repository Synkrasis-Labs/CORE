# FarmAgent-derived runtime in CORE

Current status: [session handoff](../SESSION_HANDOFF.md) and
[coverage report](PAPER_WORLD_COVERAGE.md). The sections below retain milestone
history; earlier test counts and scope restrictions describe those milestones.
The latest adapter supports registered worlds and 12 calls; 51 offline tests pass.

Implemented in `function_calling/` on `manos/farmagent-function-calling`.
This package is independent of legacy `agents.py`, Hugging Face/GPU dependencies,
and the sibling repositories. CORE's existing batch runner and evaluators have
not been switched over yet. Step 5 now connects Computations through a dedicated
adapter and scripted check, described below. Arithmetic methods and datasets are
unchanged; world imports were made lazy to isolate legacy dependencies.

## Provenance and changes

Source: local FarmAgent commit `320fd76d42b6d7de064e4adeee57651d64e04038`.
This is an adapted implementation, not an unchanged copy or a claim of identical
behavior. It retains FarmAgent's tool schemas/callable lookup, model-tool loop,
conversation handling, normalization helpers, workflow structure, and clock.

| Local file | FarmAgent source relative to `rsare/` | Main adaptation |
|---|---|---|
| `agent.py` | `agents/agent/agent.py` | Bounded loop, explicit run status, recorded errors/skips, raw and executed arguments |
| `base_agent.py` | `agents/agent/base_agent.py` | System prompt forwarded, fresh conversation/trace, default clock, response checks |
| `messages.py` | `agents/agent/messages.py` | Plain message dictionaries, optional usage metadata, JSON tool results |
| `toolset_builder.py` | `agents/agent/toolset_builder.py` | Explicit callable registration, duplicate-name checks, nested/union schema support |
| `argument_normalizer.py` | `agents/agent/argument_normalizer.py` | Preserved scalar coercion helpers plus recursive normalization/validation |
| `workflow.py` | `scenarios/scenario/workflow.py` | Independent defaults, detached snapshots, timestamps/errors survive export and load |
| `time_manager.py` | `scenarios/time_manager.py` | Copied unchanged |
| `base_llm.py` | `agents/llm/base_llm.py` | Small client contract; omitted factory branches pointing at absent providers |
| `openai_llm.py` | `agents/llm/openai_llm.py` | Optional SDK, explicit request timeout/token limit, injectable transport for offline checks |

Additional package exports live in `__init__.py`. FarmAgent itself was not edited.

## Using the interface

Python 3.10+ is required. Run from the CORE directory. Supply a client implementing
`chat_completion(messages, tools)` that returns `choices[0].message` containing
`content` and/or `tool_calls`. Dictionary responses and SDK-style objects are
supported. Usage metadata is optional and absent values remain `null`.

```python
from function_calling import Agent

def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

# llm is a configured client or an offline scripted response source.
agent = Agent(
    name="core",
    llm=llm,
    system_message="Use the available tools to carry out the task.",
    tools={"add": add},
    max_iterations=50,
    max_tool_calls=100,
    timeout_seconds=300,
)
answer = agent.run("Add 15 and 7.")
artifacts = agent.to_dict()
agent.workflow.save_workflow("runs/example/workflow.json")
```

Alternatively, pass `toolsets=[instance]` with `@agent_tool` methods, preserving
FarmAgent's `ClassName__method` discovery convention. Explicit registrations let
step 5 expose existing CORE tools without decorating every world method.

For a real OpenAI-compatible endpoint, install `requirements-function-calling.txt`
and construct `function_calling.openai_llm.OpenAILLM` explicitly. It accepts a
model, API key/base URL, request timeout, output-token limit, and temperature.
`temperature=None` omits that parameter. Select `max_tokens` or
`max_completion_tokens` through `token_limit_parameter` to match the endpoint.
There is no guessed model-family routing and no advertised support for absent
provider modules. No real provider was called or validated during step 4.
The built-in SDK client disables automatic retries so hidden retry behavior does
not obscure a run failure; an externally injected client's configuration is its
caller's responsibility. API keys are not included in run reports.

## Execution and evaluation contract

- Each `run()` resets conversation, workflow, and run metrics to the configured
  initial messages. The caller owns resetting the world and any stateful client.
- A normal final model response produces `status=completed` and
  `stop_reason=final_response`. This is an execution status, never task success.
- Tool-call count includes invalid attempts, but excludes requests skipped due
  to limits or a truncated/filtered model response. Limits produce `stopped`;
  transport/protocol failures produce `failed` and retain the partial trace.
- Multiple tool calls in one response execute sequentially. Every request in
  that batch receives a tool reply, including explicit skipped-call replies when
  a limit prevents execution. Tool-generated notifications follow all replies.
- Argument coercion defaults to enabled, following FarmAgent. Set
  `normalize_arguments=False` for strict types. Both raw JSON and parsed requests
  are recorded separately from the executed arguments; invalid JSON retains its
  raw text. NaN/infinity and duplicate JSON keys are rejected.
- Missing/extra parameters and invalid nested types are rejected before tool
  execution. Supported annotations are primitives, lists, string-keyed dicts,
  unions/optionals, and Literal values. Unsupported annotations fail at registration
  instead of silently becoming strings. This is validation of the generated
  schema subset, not a general JSON Schema implementation.
- Workflow status distinguishes `ok`, `returned_error`, `error`, and `skipped`.
  `execution_started` distinguishes failures before dispatch from exceptions after
  entering a tool. A tool may mutate the world and then fail; no rollback is
  implied. Valid tool returns must be JSON-serializable.
- Malformed response envelopes such as duplicate call IDs fail the run before
  dispatch; the normalized last assistant message is retained in the failure
  report. These are protocol failures, not successfully dispatched tool attempts.
- Artifacts include report, workflow, conversation, and per-call timing/usage.
  Workflow JSON preserves timestamps and snapshots. Source world state, task IDs,
  the evaluator adapter, and batch artifact layout remain integration work.

The overall timeout is **cooperative**: checked before model requests, after model
responses, and between tool calls. It cannot interrupt a blocking Python tool or
custom client; a call may exceed the overall deadline before returning. The
optional real client has a separate request timeout. Hard process-level deadlines
belong in a later runner, if needed.

## Validation

From CORE:

```text
py -B -m unittest discover -s tests -p test_function_calling.py -v
```

The tests use only standard-library fixtures and scripted responses. They cover
tool-feedback-dependent decisions, system prompts, schema/argument handling,
error recovery, partial tool mutations, immutable trace snapshots, timestamp
round-trips, missing usage fields, fresh agent runs, limits, message ordering,
truncated responses, malformed IDs, and client option forwarding.

These checks validate runtime mechanics. They do not measure model competence,
demonstrate improvement over original CORE, or validate CORE's paper metrics.

Validation on 17 September 2026: all 23 offline tests passed with Python 3.11.
The package has no imports from sibling runtimes, legacy CORE agents/model code,
or GPU libraries. FarmAgent remained clean; the copied clock's hash matches its
source. No dependencies were installed and no paid or network model calls ran.

## Step 5: Computations scripted integration

Run from CORE:

```text
py -B -m function_calling.computations_smoke --output runs/archive/2026-09-19/computations_scripted.json
py -B -m unittest discover -s tests -p "test_*.py" -v
```

`core_computations.run_computations(llm)` now creates a fresh world, selects the
dataset prompt by ID, registers all six original arithmetic methods, and invokes
the new runtime. `FunctionCallingComputations` inherits those methods and task
definitions directly from `worlds/computations.py`; it overrides only tool-schema
generation and the shallow reset with an independent deep copy. `worlds` exports
load on demand and the base World's `llm_tool` import is deferred until the legacy
schema method is called. Existing legacy class names remain available.

The model receives the domain instruction, user task, initial state, tool results,
and subsequent world-state observations. It does not receive the DFA, alphabet,
or expected solution. The runtime's optional `state_observer` records detached
snapshots after attempted calls and sends them after the batch's tool replies;
skipped calls do not produce new observations. World reset remains the adapter's
responsibility.

For `computations_1`, the scripted driver requests `add_numbers(15, 7)`, reads the
actual returned value, then requests `multiply_numbers(previous_result, 3)`.
It finally returns the actual multiplication result. This driver supplies the
decisions; it is not an LLM. The arithmetic and state mutations happen in CORE's
original world methods.

Validation on 17 September 2026:

- Both calls succeeded with results **22** and **66**.
- Initial state was `{"calculations": []}`; final history was
  `["15 + 7 = 22", "22 * 3 = 66"]`.
- All nine scripted artifact assertions passed: completion, sequence, arguments,
  results, no tool errors, initial/final state, state feedback, and final answer.
- All **28 tests passed**: the original 23 runtime checks plus five integration
  checks for actual method reuse, isolation, model-visible inputs, unknown task
  handling, and dependency isolation.

The local artifact `runs/archive/2026-09-19/computations_scripted.json` contains the task, initial
and final state, report, workflow, conversation, observations, and check results.
`runs/` is now included for team review. The artifact has `evaluation: null`: these are
integration checks, not CORE metric scores.

## Live Computations check

`function_calling/computations_live.py` uses the same adapter with OpenAI instead
of scripted responses. Put `OPENAI_API_KEY=...` in the ignored `CORE/.env` file.
Install `requirements-function-calling.txt` in a virtual environment. From CORE:

```powershell
python -m function_calling.computations_live
```

This session's environment is in the parent folder: use
`..\.venv\Scripts\python.exe` instead of `python` to reproduce locally.
Default model: `gpt-4.1-nano`; override with `--model`. Limits: six requests,
six tool calls, 256 output tokens per request, 30-second request timeout,
90-second cooperative run timeout, no SDK retries. Parallel tool calling is
disabled following OpenAI's recommendation for GPT-4.1 nano.
The endpoint is explicitly OpenAI; the key is excluded from saved output.

The runner creates `runs/computations_1/<UTC-timestamp>_<model>/run.json`;
each run gets a new folder automatically. `--output` remains an optional override.
Eight assertions check execution and state. The final answer is saved for manual
review, because a real model may explain its answer instead of returning only
`66`. These checks are not CORE metric scores or a model comparison.

Live validation on 18 September 2026 succeeded with `gpt-4.1-nano`:

- Three model requests and two tool executions: `add_numbers(15, 7)` returned
  22, then `multiply_numbers(22, 3)` returned 66.
- All eight execution/state checks passed, with no errors. The final answer
  explained the calculation and correctly reported 66 (manually reviewed).
- Usage: 1,552 input tokens and 68 output tokens; runtime 6.5 seconds.
- Full conversation, workflow, state, checks, and usage are saved locally in
  `runs/archive/2026-09-19/computations_live_3.json`. All 28 offline tests also pass.

The first two attempts were rejected for insufficient API credits before model
execution; their artifacts are preserved. The successful run validates this task
end to end, not broader model performance or improvement over original CORE.
Step 5 is complete.

## Structured evaluation (step 6)

`function_calling/evaluation.py` joins schema-v1 Computations artifacts to the
dataset by prompt ID and validates world/prompt identity. It maps registered tool
names and executed arguments through the original `fc2symbol`, then calls the
unchanged `core.evaluate`. It rebuilds DFA nodes and initializes/restores the
legacy global caches per evaluation. Removed one unused dataset-builder import
from `evaluate.py` so this route does not load the legacy model dependencies.

From CORE, no API calls:

```powershell
..\.venv\Scripts\python.exe -B -m function_calling.evaluation runs/archive/2026-09-19/computations_live_3.json --output runs/evaluation_review.json
```

The output contains `evaluation` and a `source_run` reference; existing files are not overwritten.
Successful live trace: A,C, path score **1.0**, saved in
`runs/archive/2026-09-19/computations_live_3_scored.json`. All **34 offline tests pass**. Six new tests
cover known paths, negative paths, cache isolation, input preservation, identity,
error handling, and executed arguments. No additional paid runs were performed.

Scope: Computations traces with at most six tool steps. Every step must execute
successfully and map to a symbol. Failed/skipped/unknown/unmapped calls and empty
traces return `unscored` with reasons; they are not dropped or given new penalties.
Run status and final-state success remain separate from the path score.

Known legacy behavior, preserved rather than fixed in this port:

- The incomplete sequence A scores 0, although direct normalized edit distance
  against A,C gives 0.5. The legacy search misses a longer accepting path.
- `fc2symbol` exclusion matching can accept a candidate after only part of its
  argument checks match. The adapter retains its mapping semantics.

This is compatibility with the existing path scorer, not validation of all paper
metrics. Step 6 is complete for Computations. Next: more-world runtime checks;
resolve evaluator defects separately before broader score comparisons.

## Two additional worlds (step 7)

`stateful_worlds.py` adapts existing CRUD and Configurations classes using explicit
tool allowlists and deep-copy resets; their methods, prompts, and datasets are
unchanged. Tasks with nonempty setup actions are rejected before model invocation.
The model sees instructions, the dataset task, state, and tool results, not oracle
sequences or DFA metadata. No new scenarios were created.

From CORE:

```powershell
..\.venv\Scripts\python.exe -B -m function_calling.stateful_check
..\.venv\Scripts\python.exe -B -m function_calling.stateful_check --live
```

The second command is paid: one nano run per task, each capped at six requests,
six tools, and 256 output tokens per request. Artifacts use the standard run folders.

Both scripted and live checks passed for existing tasks:

- `crud_4`: add Charlie, delete using the returned user ID, list users to confirm
  deletion. Live artifact: `runs/crud_4/2026-09-18_223958_420268Z_gpt-4.1-nano/run.json`.
- `configurations_4`: set timeout to 30 minutes/security, update to 15 minutes/process,
  print the updated setting. Live artifact:
  `runs/configurations_4/2026-09-18_224007_272112Z_gpt-4.1-nano/run.json`.

Each live run used four model requests and three tools, passed seven assertions,
and returned a final answer consistent with the state. No metrics were computed.
The full offline suite passes **41 tests**. Failure/recovery checks use real world
methods, including missing users/settings and an exception on invalid age input.
CRUD `False` and Configurations "not found" responses remain ordinary tool
responses; runtime status `ok` alone does not establish domain success.

Step 7 is complete for these two additional examples. Step 8 is runner integration;
setup-dependent tasks need safe setup support before broader execution is enabled.

## Shared runner checkpoint

The opt-in `function_calling.experiments` entry point now covers available paper
worlds, with task/world selection and separate inventory/offline/live modes.
See [shared runner usage](SHARED_RUNNER.md) and
[paper-world sweep results](PAPER_WORLD_COVERAGE.md). Original entry points remain
unchanged. Setup/scenario issues are deferred to revamp per Manos; the default
will not switch until coverage is reviewed. Configurations is excluded from the
shared runner despite its earlier use as an execution check.

Correction to the earlier step-6 milestone: only legacy input compatibility was
connected. Reproducing the paper's five metrics remains unfinished.
## Saved-run evaluation checkpoint (19 September 2026)

`function_calling.evaluation` now accepts registered CORE worlds and shared-runner
batch summaries. It reuses the original action mapping and path scorer unchanged.
The 51-task live sweep produced 30 scored traces and 21 unscored traces with explicit
reasons. These counts do not measure task success or reproduce all paper metrics.
51 offline tests pass. No API requests were made; source runs were not modified.

From CORE, evaluate a batch (refuses to overwrite existing output):

```powershell
..\.venv\Scripts\python.exe -B -m function_calling.evaluation runs/batches/2026-09-18_230912_247245Z_live/summary.json --batch
```

Results are in `evaluation.json` beside the batch summary, with each source run,
mapped actions, score, or reasons for leaving it unscored. The adapter supports up
to the shared runner's 12-call limit. It does not drop unmapped or failed calls to
produce partial-trace scores. Existing evaluator limitations remain unresolved.

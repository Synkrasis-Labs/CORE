# Step 4: FarmAgent-derived runtime in CORE

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
py -B -m function_calling.computations_smoke --output runs/computations_scripted.json
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

The local artifact `runs/computations_scripted.json` contains the task, initial
and final state, report, workflow, conversation, observations, and check results.
`runs/` is ignored by Git. The artifact has `evaluation: null`: these are
integration checks, not CORE metric scores. No live model run has happened.

For the live check, use the same `run_computations()` adapter with a configured
real client instead of `ComputationsScript`. Needed inputs are the provider/model,
an API key configured locally, and a base URL if the provider needs one. A local
model endpoint can be used instead if it supports the client's tool-call protocol.

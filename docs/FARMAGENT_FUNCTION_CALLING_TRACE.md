# FarmAgent function-calling source map

Step 2 of the CORE Week 1 replacement plan. Inspected 17 September 2026.

Source: sibling `FarmAgent` repository, clean working tree at
`320fd76d42b6d7de064e4adeee57651d64e04038`.
Destination: CORE branch `manos/farmagent-function-calling`, based on `9c600a4`.
This is a source inspection, not a runtime test or completed migration.

## Execution path

Paths below are relative to `FarmAgent/`.

1. Construct an LLM client and `Agent(llm=..., toolsets=[instances], ...)`.
2. `rsare/agents/agent/toolset_builder.py` discovers methods marked with
   `is_agent_tool` by `@agent_tool`. It generates function schemas from Python
   signatures/docstrings and maps names such as `Computations__add_numbers` to
   bound methods. That name is an illustrative CORE integration example.
3. Attach a clock through `Agent.set_time_manager()`. The farm runner uses
   `Engine(agent, scenario)` to do this; the agent itself does not import Engine.
4. `Agent.run(input)` adds the user task to messages and workflow.
5. `BaseAgent.chat_completion()` calls the LLM client, appends the returned
   assistant message, records timing/token usage, and returns that message.
6. If the message has no tool calls, `Agent.run()` returns its content. This
   terminates execution; it does not verify task success.
7. Otherwise, for each requested call, `Agent.call_function()` parses JSON,
   normalizes arguments, finds the bound method, and executes it. Multiple calls
   returned in one model response execute sequentially without a new model turn
   between them.
8. `Messages.tool_call_response()` appends a tool message linked by call ID.
   `Workflow.add_node()` records the executed tool, normalized arguments, result,
   and in-memory timestamp. The loop requests the next model response.

## Reuse boundary

| Source | Responsibility |
|---|---|
| `rsare/agents/agent/agent.py` | Tool execution and repeated model/tool interaction |
| `rsare/agents/agent/base_agent.py` | Agent state, model invocation, clock attachment |
| `rsare/agents/agent/messages.py` | Conversation and per-call runtime/token metrics |
| `rsare/agents/agent/toolset_builder.py` | Tool discovery, schemas, callable lookup |
| `rsare/agents/agent/argument_normalizer.py` | Argument coercion before execution |
| `rsare/agents/llm/base_llm.py` | Model-client interface and provider factory |
| `rsare/agents/llm/openai_llm.py` | OpenAI-compatible client implementation |
| `rsare/scenarios/scenario/workflow.py` | Structured action records and JSON export |
| `rsare/scenarios/time_manager.py` | Clock satisfying the agent's timestamp needs |

These nine files form a candidate initial reuse set, with imports and interfaces
adapted inside CORE. The provider factory must be trimmed or repaired rather than
copied unchanged. The core loop/tool/trace/clock code uses the standard library;
the OpenAI-compatible client additionally imports the `openai` package.

`rsare/agents/llm/deepseek_client.py` is another existing provider wrapper, but
its configuration issues below make it unsuitable for blind copying.
`rsare/research_suite/mock_llm.py` is useful as an example of an offline response
double; it executes a supplied plan and does not demonstrate model competence.

The farm Engine, Scenario base, apps, events, A2A conversion, research controller
families, skill retrieval, and farm metrics are not dependencies of this basic
agent loop. CORE can supply its own task setup and attach the clock directly.
The full FarmAgent requirements list is therefore not the migration dependency list.

## Issues to address when porting

These findings describe the inspected implementation, not fixes made in step 2.

- **System prompt:** `BaseAgent.__init__` stores `system_message` but constructs
  `Messages(provider=llm.provider)` without forwarding it. Unless the caller
  supplies prepopulated messages, the system instruction never reaches the model.
- **Execution limits:** `Agent.run()` uses an unbounded `while True`. It exposes
  no iteration, tool-call, or overall runtime limit. The inspected provider calls
  also do not explicitly configure request timeouts or output-token caps;
  library defaults are a separate matter.
- **Failed attempts:** JSON parsing, normalization, unknown tool lookup, and
  tool exceptions escape before the workflow entry is added. The research runner
  catches exceptions at run level, but this does not create a failed-call record
  or allow the model to recover. A tool returning an error value normally is
  recorded. This distinction matters for CORE's harmful-action evaluation.
- **Argument fidelity:** successful workflow entries contain normalized arguments
  only. Coercion can turn `"22"` into `22` or a description dictionary into a
  string. Preserve the original request alongside executed arguments during the
  port so evaluation does not silently hide model mistakes.
- **Schema coverage:** primitive and some container annotations are supported,
  but unions collapse to one non-null member and complex string annotations
  fall back to strings. Normalization is not complete JSON-schema validation.
  Check actual CORE tool signatures before relying on these schemas.
- **Trace export:** `WorkflowStep` stores `time` but omits it from `to_dict()`;
  loading also omits time. Its `depends_on=[]` default is shared. Successful
  calls use generic `TOOL`, not read/write labels. Neither DFA validity nor task
  success is determined here.
- **Usage metadata:** the `openai` message path assumes usage and cached-token
  detail fields exist. Missing fields can interrupt processing before tool
  execution. The non-OpenAI path is more defensive.
- **Fresh runs:** `run()` appends to existing messages/workflow. Use fresh agent
  state for each CORE task or implement explicit reset behavior.
- **Provider coverage:** the factory references Anthropic, Ollama, and vLLM
  modules absent from this checkout. The DeepSeek wrapper ignores its supplied
  API key/model/endpoint choices in favor of module-level or hardcoded values.
  Advertised provider names do not establish working support.

## Why not copy the research runner?

`rsare/research_suite/executor.py` demonstrates setup and artifact export, but
also adds farm prompts, strategies, skills, A2A behavior, and its own scoring.
Its reflection-enabled setup builds initial memory from oracle tool names.
Those choices are outside the requested execution-loop replacement and must not
silently enter CORE's experimental condition.

## CORE integration questions for step 3

- CORE discovers world methods through `World._get_tool_definitions()` and
  `llm_tool`; FarmAgent requires decorated methods. Connect the intended CORE
  tool set explicitly rather than exposing arbitrary world helpers.
- Decide how model-facing prefixed names map back to CORE evaluator names.
- Locate CORE's task setup, prompts, model selection, completion decision,
  result output, and evaluator inputs before selecting replacement points.
- Preserve CORE world/task semantics and metric definitions while changing
  execution. Keep any fixes that affect behavior explicit and testable.

Step 2 outcome: the source loop and supporting components are identified, along
with concrete integration risks. No source code was replaced, no API calls were
made, and no runtime tests were executed in this step.

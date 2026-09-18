"""FarmAgent's model/tool loop, adapted for bounded, auditable CORE execution.

See docs/FUNCTION_CALLING_PORT.md for source provenance and behavioral changes.
"""

from copy import deepcopy
import inspect
import json
import math
import time

from .argument_normalizer import normalize_tool_arguments, validate_arguments
from .base_agent import BaseAgent
from .toolset_builder import build_toolset
from .workflow import WorkflowStep


def reject_constant(text):
    raise ValueError(f"Invalid JSON constant: {text}")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


class Agent(BaseAgent):
    def __init__(self, name, llm, system_message="", messages=None, toolsets=None,
                 *, tools=None, max_iterations=50, max_tool_calls=100,
                 timeout_seconds=300.0, normalize_arguments=True, state_observer=None):
        super().__init__(name, llm, system_message, messages)
        for label, limit in (("max_iterations", max_iterations), ("max_tool_calls", max_tool_calls)):
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise ValueError(f"{label} must be a positive integer")
        if isinstance(timeout_seconds, bool) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls
        self.timeout_seconds = timeout_seconds
        self.normalize_arguments = normalize_arguments
        if state_observer is not None and not callable(state_observer):
            raise TypeError("state_observer must be callable")
        self.state_observer = state_observer
        self.state_observations = []
        self.tools, self.tool_schemas, self.tools_map = build_toolset(toolsets or [], tools=tools)
        self.schemas = {s["function"]["name"]: s["function"]["parameters"] for s in self.tool_schemas}
        self.report = None

    def call_function(self, call, *, skip_reason=None):
        name = call["function"]["name"]
        raw = call["function"]["arguments"]
        step = WorkflowStep(tool_name=name, raw_arguments=raw, tool_call_id=call["id"],
                            time_before=self.time_manager.time())
        started = time.monotonic()
        function = self.tools_map.get(name) if isinstance(name, str) else None
        if function:
            step.canonical_name = function.__name__
        try:
            if skip_reason:
                step.status = "skipped"
                step.error = {"type": "SkippedCall", "message": skip_reason}
                result = {"error": step.error}
            else:
                if call.get("type") != "function":
                    raise ValueError("Only function tool calls are supported")
                if not isinstance(raw, str):
                    raise ValueError("Tool arguments must be a JSON string")
                requested = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_keys)
                json.dumps(requested, allow_nan=False)
                step.requested_args = deepcopy(requested)
                if not isinstance(requested, dict):
                    raise ValueError("Tool arguments must be a JSON object")
                if function is None:
                    raise ValueError(f"Unknown tool: {name}")
                schema = self.schemas[name]
                args = normalize_tool_arguments(tool_name=name, raw_arguments=requested,
                                               schema_properties=schema["properties"]) if self.normalize_arguments else deepcopy(requested)
                validate_arguments(args, schema)
                inspect.signature(function).bind(**args)
                step.tool_args = deepcopy(args)
                step.execution_started = True
                result = function(**args)
                # Tool results are a JSON contract. A serialization failure is recorded
                # after execution and never implies the world mutation was rolled back.
                json.dumps(result, allow_nan=False)
                step.status = "returned_error" if isinstance(result, dict) and "error" in result else "ok"
            step.content = deepcopy(result)
        except Exception as error:
            step.status = "error"
            step.error = {"type": type(error).__name__, "message": str(error)}
            result = {"error": step.error}
            step.content = deepcopy(result)
        step.time = self.time_manager.time()
        step.elapsed_seconds = time.monotonic() - started
        self.workflow.add_node(step)
        self.messages.tool_call_response(result, call["id"], step.elapsed_seconds)
        return result

    def run(self, input):
        """Start fresh conversation/trace; the caller owns world and client resets.

        Runtime timeout is cooperative between calls, not a tool/process interrupt.
        """
        self.reset()
        self.state_observations = []
        self.messages.user_input(input)
        self.workflow.add_node(WorkflowStep(op_type="USER", content=input, time=self.time_manager.time()))
        self.report = {"schema_version": 1, "status": "running", "stop_reason": None,
                       "llm_calls": 0, "tool_calls": 0, "final_answer": None, "error": None,
                       "limits": {"max_iterations": self.max_iterations,
                                  "max_tool_calls": self.max_tool_calls,
                                  "timeout_seconds": self.timeout_seconds},
                       "normalize_arguments": self.normalize_arguments,
                       "state_observations_enabled": self.state_observer is not None,
                       "model": {key: getattr(self.llm, key, None) for key in
                                 ("provider", "model", "temperature", "request_timeout_seconds",
                                  "max_output_tokens", "token_limit_parameter")},
                       "tool_policy": "sequential_all_requested"}
        started = time.monotonic()

        def limit_reason():
            if time.monotonic() - started >= self.timeout_seconds:
                return "timeout"
            if self.report["tool_calls"] >= self.max_tool_calls:
                return "max_tool_calls"
            return None

        try:
            while True:
                reason = limit_reason()
                if reason is None and self.report["llm_calls"] >= self.max_iterations:
                    reason = "max_iterations"
                if reason:
                    self.report.update(status="stopped", stop_reason=reason)
                    break
                self.report["llm_calls"] += 1
                message, finish_reason = self.chat_completion(self.messages(), self.tool_schemas)
                calls = message.get("tool_calls", [])
                if not calls:
                    reason = limit_reason()
                    if reason:
                        self.report.update(status="stopped", stop_reason=reason)
                    elif finish_reason not in (None, "stop"):
                        self.report.update(status="stopped", stop_reason=f"model_{finish_reason}")
                    elif message.get("content") is None:
                        raise ValueError("Model returned neither content nor tool calls")
                    else:
                        self.report.update(status="completed", stop_reason="final_response",
                                           final_answer=message["content"])
                    break
                deferred = []
                for call in calls:
                    reason = limit_reason()
                    if reason is None and finish_reason in ("length", "content_filter"):
                        reason = f"model_{finish_reason}"
                    if reason is None:
                        self.report["tool_calls"] += 1
                    before = len(self.messages.messages)
                    self.call_function(call, skip_reason=reason)
                    # Notifications injected by tools must follow ALL replies to this
                    # assistant batch, including replies for skipped requests.
                    added = self.messages.messages[before:]
                    deferred.extend(added[:-1])
                    self.messages.messages[before:] = added[-1:]
                    if reason is None and self.state_observer is not None:
                        state = deepcopy(self.state_observer())
                        state_text = json.dumps(state, allow_nan=False)
                        self.state_observations.append({"tool_call_id": call["id"], "state": state,
                                                        "time": self.time_manager.time()})
                        deferred.append({"role": "user", "content":
                                         f"Current world state after tool call {call['id']}: {state_text}"})
                self.messages.messages.extend(deferred)
                if reason:
                    self.report.update(status="stopped", stop_reason=reason)
                    break
        except Exception as error:
            self.report.update(status="failed", stop_reason="runtime_error",
                               error={"type": type(error).__name__, "message": str(error)},
                               last_assistant_message=deepcopy(self.last_assistant_message))
        finally:
            self.report["wall_time_seconds"] = time.monotonic() - started
            self.report["tool_errors"] = sum(s.status in ("error", "returned_error") for s in self.workflow.dag.values())
        return self.report["final_answer"]

    def to_dict(self):
        return deepcopy({"report": self.report, "workflow": self.workflow.to_dict(),
                         "messages": self.messages.messages,
                         "state_observations": self.state_observations,
                         "runtime_metrics": self.messages.runtime_metrics})

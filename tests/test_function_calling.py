"""Offline integration checks; no CORE worlds, GPU packages, SDK, or network."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Literal
import unittest
from unittest.mock import patch

from function_calling import Agent, agent_tool
from function_calling.messages import Messages
from function_calling.openai_llm import OpenAILLM
from function_calling.toolset_builder import build_tool_schema, build_toolset
from function_calling.workflow import Workflow, WorkflowStep


def call(name, args, id="call_1"):
    return {"id": id, "type": "function", "function": {
        "name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}


def reply(*calls, content=None, finish_reason=None):
    return {"choices": [{"message": {"content": content, "tool_calls": list(calls)},
                         "finish_reason": finish_reason}]}


class ScriptedLLM:
    provider = "offline"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def chat_completion(self, messages, tools=None):
        self.requests.append(deepcopy({"messages": messages, "tools": tools}))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response(messages, tools) if callable(response) else response


class Counter:
    def __init__(self):
        self.values = []

    @agent_tool
    def add(self, amount: int) -> list[int]:
        """Append an integer to the history."""
        self.values.append(amount)
        return self.values


class RuntimeTests(unittest.TestCase):
    def test_feedback_and_trace_snapshots(self):
        counter = Counter()

        def choose_second(messages, tools):
            self.assertEqual(messages[0], {"role": "system", "content": "Use tools."})
            self.assertEqual(json.loads(messages[-1]["content"]), [2])
            return reply(call("Counter__add", {"amount": 3}, "call_2"))

        llm = ScriptedLLM([reply(call("Counter__add", {"amount": "2"})),
                           choose_second, reply(content="done", finish_reason="stop")])
        agent = Agent("test", llm, "Use tools.", toolsets=[counter])
        self.assertEqual(agent.run("add twice"), "done")
        first = agent.workflow.dag["step1"]
        self.assertEqual(first.requested_args, {"amount": "2"})
        self.assertEqual(first.tool_args, {"amount": 2})
        self.assertEqual(first.content, [2])
        self.assertEqual(counter.values, [2, 3])
        self.assertEqual(first.canonical_name, "add")
        self.assertIsNotNone(first.time)
        self.assertEqual(agent.report["status"], "completed")
        self.assertIsNone(agent.messages.runtime_metrics[0]["tokens"]["total_tokens"])
        exported = agent.to_dict()
        exported["workflow"]["step1"]["content"].append(99)
        self.assertEqual(first.content, [2])

    def test_bad_calls_are_recorded_and_model_can_recover(self):
        counter = Counter()
        llm = ScriptedLLM([
            reply(call("Counter__add", "{")),
            reply(call("missing", {})),
            reply(call("Counter__add", {"amount": "bad"})),
            reply(call("Counter__add", {"amount": 4})), reply(content="done")])
        agent = Agent("test", llm, toolsets=[counter])
        agent.run("test")
        steps = list(agent.workflow.dag.values())[1:]
        self.assertEqual([s.status for s in steps], ["error", "error", "error", "ok"])
        self.assertTrue(all(not s.execution_started for s in steps[:3]))
        self.assertEqual(steps[0].raw_arguments, "{")
        self.assertEqual(counter.values, [4])
        self.assertEqual(agent.report["tool_errors"], 3)
        self.assertIn("error", json.loads(llm.requests[1]["messages"][-1]["content"]))

    def test_tool_exception_can_follow_mutation_and_is_not_rolled_back(self):
        state = []

        def fail():
            state.append(1)
            raise RuntimeError("partial failure")

        agent = Agent("test", ScriptedLLM([reply(call("fail", {})), reply(content="done")]), tools={"fail": fail})
        agent.run("test")
        self.assertEqual(state, [1])
        step = agent.workflow.dag["step1"]
        self.assertTrue(step.execution_started)
        self.assertEqual(step.error["type"], "RuntimeError")

    def test_returned_error_is_distinct_from_exception(self):
        def decline():
            return {"error": "precondition failed"}

        agent = Agent("test", ScriptedLLM([reply(call("decline", {})), reply(content="done")]), tools={"decline": decline})
        agent.run("test")
        self.assertEqual(agent.workflow.dag["step1"].status, "returned_error")
        self.assertIsNone(agent.workflow.dag["step1"].error)

    def test_batch_limit_pairs_all_calls_without_executing_excess(self):
        counter = Counter()
        agent = Agent("test", ScriptedLLM([reply(
            call("Counter__add", {"amount": 1}, "a"),
            call("Counter__add", {"amount": 2}, "b"))]), toolsets=[counter], max_tool_calls=1)
        agent.run("test")
        self.assertEqual(counter.values, [1])
        self.assertEqual(agent.report["stop_reason"], "max_tool_calls")
        self.assertEqual(agent.workflow.dag["step2"].status, "skipped")
        self.assertEqual([m["tool_call_id"] for m in agent.messages.messages if m["role"] == "tool"], ["a", "b"])

    def test_notifications_follow_entire_batch(self):
        def notify():
            agent.messages.system_notify("notice")
            return "ok"

        agent = Agent("test", ScriptedLLM([reply(call("notify", {}, "a"), call("notify", {}, "b")), reply(content="done")]), tools={"notify": notify})
        agent.run("test")
        roles = [m["role"] for m in agent.messages.messages]
        self.assertEqual(roles, ["user", "assistant", "tool", "tool", "user", "user", "assistant"])

    def test_iteration_limit(self):
        counter = Counter()
        agent = Agent("test", ScriptedLLM([reply(call("Counter__add", {"amount": 1}))]), toolsets=[counter], max_iterations=1)
        agent.run("test")
        self.assertEqual(agent.report["stop_reason"], "max_iterations")
        self.assertEqual(agent.report["llm_calls"], 1)

    def test_cooperative_timeout_checks_after_model_call(self):
        counter = Counter()
        current = [0.0]

        def slow_response(messages, tools):
            current[0] = 11.0
            return reply(call("Counter__add", {"amount": 1}))

        agent = Agent("test", ScriptedLLM([slow_response]), toolsets=[counter], timeout_seconds=10)
        with patch("time.monotonic", side_effect=lambda: current[0]):
            agent.run("test")
        self.assertEqual(agent.report["stop_reason"], "timeout")
        self.assertEqual(counter.values, [])
        self.assertEqual(agent.workflow.dag["step1"].status, "skipped")

    def test_llm_failure_report_and_partial_trace(self):
        counter = Counter()
        agent = Agent("test", ScriptedLLM([reply(call("Counter__add", {"amount": 1})), RuntimeError("transport failed")]), toolsets=[counter])
        agent.run("test")
        self.assertEqual(agent.report["status"], "failed")
        self.assertEqual(agent.report["error"]["message"], "transport failed")
        self.assertEqual(len(agent.workflow), 2)

    def test_new_run_resets_agent_but_not_world(self):
        counter = Counter()
        llm = ScriptedLLM([reply(call("Counter__add", {"amount": 1})), reply(content="one"), reply(content="two")])
        agent = Agent("test", llm, "instruction", toolsets=[counter])
        agent.run("first")
        agent.run("second")
        self.assertEqual(counter.values, [1])
        self.assertEqual(len(agent.workflow), 1)
        self.assertEqual(agent.report["llm_calls"], 1)
        self.assertEqual(llm.requests[-1]["messages"], [{"role": "system", "content": "instruction"}, {"role": "user", "content": "second"}])

    def test_truncation_is_not_success(self):
        agent = Agent("test", ScriptedLLM([reply(content="partial", finish_reason="length")]))
        self.assertIsNone(agent.run("test"))
        self.assertEqual(agent.report["stop_reason"], "model_length")

    def test_strict_argument_mode_and_unknown_parameters(self):
        counter = Counter()
        agent = Agent("test", ScriptedLLM([
            reply(call("Counter__add", {"amount": "2"})),
            reply(call("Counter__add", {"amount": 2, "extra": True})),
            reply(content="done")]), toolsets=[counter], normalize_arguments=False)
        agent.run("test")
        self.assertEqual(counter.values, [])
        self.assertEqual(agent.report["tool_errors"], 2)

    def test_non_json_arguments_and_nonserializable_results(self):
        def unsupported():
            return {1, 2}

        agent = Agent("test", ScriptedLLM([
            reply(call("unsupported", "null")), reply(call("unsupported", {})),
            reply(content="done")]), tools={"unsupported": unsupported})
        agent.run("test")
        steps = list(agent.workflow.dag.values())[1:]
        self.assertEqual([s.execution_started for s in steps], [False, True])
        self.assertEqual([s.status for s in steps], ["error", "error"])
        json.dumps(agent.to_dict(), allow_nan=False)

    def test_object_responses_and_missing_cached_usage(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=None), finish_reason="stop")], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12))
        agent = Agent("test", ScriptedLLM([response]))
        agent.run("test")
        tokens = agent.messages.runtime_metrics[0]["tokens"]
        self.assertEqual(tokens["total_tokens"], 12)
        self.assertIsNone(tokens["cached_tokens"])

    def test_duplicate_call_ids_are_rejected_before_execution(self):
        counter = Counter()
        agent = Agent("test", ScriptedLLM([reply(call("Counter__add", {"amount": 1}), call("Counter__add", {"amount": 2}))]), toolsets=[counter])
        agent.run("test")
        self.assertEqual(agent.report["status"], "failed")
        self.assertEqual(counter.values, [])
        self.assertEqual(len(agent.report["last_assistant_message"]["tool_calls"]), 2)

    def test_nonfinite_and_duplicate_json_arguments_remain_exportable(self):
        counter = Counter()
        agent = Agent("test", ScriptedLLM([
            reply(call("Counter__add", '{"amount":1e999}')),
            reply(call("Counter__add", '{"amount":NaN}')),
            reply(call("Counter__add", '{"amount":1,"amount":2}')),
            reply(content="done")]), toolsets=[counter])
        agent.run("test")
        self.assertEqual(counter.values, [])
        self.assertEqual(agent.report["tool_errors"], 3)
        json.dumps(agent.to_dict(), allow_nan=False)

    def test_truncated_batch_never_executes(self):
        counter = Counter()
        agent = Agent("test", ScriptedLLM([reply(call("Counter__add", {"amount": 1}), finish_reason="length")]), toolsets=[counter])
        agent.run("test")
        self.assertEqual(agent.report["stop_reason"], "model_length")
        self.assertEqual(agent.report["tool_calls"], 0)
        self.assertEqual(agent.workflow.dag["step1"].status, "skipped")
        self.assertEqual(counter.values, [])

    def test_system_prompt_with_initial_messages(self):
        messages = Messages(system_message="instruction")
        agent = Agent("test", ScriptedLLM([reply(content="done")]), "instruction", messages=messages)
        agent.run("test")
        self.assertEqual(len(messages.messages), 1)
        self.assertEqual(sum(m["role"] == "system" for m in agent.messages.messages), 1)
        with self.assertRaises(ValueError):
            Agent("test", None, "conflicting", messages=messages)


class SchemaAndArtifactTests(unittest.TestCase):
    def test_nested_annotations_union_literal_and_defaults(self):
        def accept(values: list[int], mapping: dict[str, float], choice: Literal["a", "b"], optional: int | None = None):
            return [values, mapping, choice, optional]

        schema = build_tool_schema(accept)["function"]["parameters"]
        self.assertEqual(schema["required"], ["values", "mapping", "choice"])
        self.assertEqual(schema["properties"]["optional"]["anyOf"], [{"type": "integer"}, {"type": "null"}])
        agent = Agent("test", ScriptedLLM([reply(call("accept", {"values": ["2"], "mapping": {"x": "3.5"}, "choice": "a", "optional": None})), reply(content="done")]), tools={"accept": accept})
        agent.run("test")
        self.assertEqual(agent.workflow.dag["step1"].content, [[2], {"x": 3.5}, "a", None])

    def test_missing_argument_boolean_and_enum_rejected(self):
        def accept(number: int, option: Literal["a", "b"]):
            self.fail("Invalid arguments must not reach the tool")

        agent = Agent("test", ScriptedLLM([
            reply(call("accept", {"option": "a"})),
            reply(call("accept", {"number": True, "option": "a"})),
            reply(call("accept", {"number": 2, "option": "c"})), reply(content="done")]), tools={"accept": accept})
        agent.run("test")
        self.assertEqual(agent.report["tool_errors"], 3)

    def test_duplicate_names_and_class_discovery(self):
        with self.assertRaises(ValueError):
            build_toolset([Counter(), Counter()])
        tools, schemas, mapping = build_toolset([Counter])
        self.assertEqual(list(mapping), ["Counter__add"])
        self.assertEqual(mapping["Counter__add"](2), [2])
        with self.assertRaises(ValueError):
            build_toolset([], tools={"bad.name": Counter().add})

    def test_trace_roundtrip_and_independent_defaults(self):
        first, second = WorkflowStep(), WorkflowStep()
        first.depends_on.append("parent")
        self.assertEqual(second.depends_on, [])
        workflow = Workflow()
        workflow.add_node(WorkflowStep(content={"x": [1]}, time=42.5, raw_arguments='{"x":1}'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "trace.json"
            workflow.save_workflow(path)
            loaded = Workflow.load_workflow(path)
            self.assertEqual(loaded.to_dict(), workflow.to_dict())
            self.assertEqual(loaded.dag["step0"].time, 42.5)

    def test_optional_transport_forwards_configuration_offline(self):
        captured = {}

        def create(**options):
            captured.update(options)
            return reply(content="done")

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        llm = OpenAILLM("example-model", temperature=None, client=client,
                        request_timeout_seconds=7, max_output_tokens=100,
                        token_limit_parameter="max_tokens")
        agent = Agent("test", llm, tools={"add": Counter().add})
        agent.run("test")
        self.assertEqual(captured["timeout"], 7)
        self.assertEqual(captured["max_tokens"], 100)
        self.assertEqual(captured["model"], "example-model")
        self.assertNotIn("temperature", captured)
        self.assertEqual(captured["tools"][0]["function"]["name"], "add")


if __name__ == "__main__":
    unittest.main()

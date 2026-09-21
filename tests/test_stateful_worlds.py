import json
import unittest

from function_calling.stateful_worlds import (
    FunctionCallingCRUD, FunctionCallingConfigurations, StatefulScript,
    TASKS, run_world, check_stateful,
)
from worlds.crud import CRUD
from worlds.configurations import Configurations
from test_function_calling import ScriptedLLM, call, reply


class StatefulTests(unittest.TestCase):
    def test_original_methods_are_reused(self):
        for adapter, original in ((FunctionCallingCRUD, CRUD), (FunctionCallingConfigurations, Configurations)):
            for name in adapter.tool_names:
                self.assertIs(getattr(adapter, name), getattr(original, name))

    def test_tasks_and_repeat_isolation(self):
        for task in TASKS:
            for _ in range(2):
                result = run_world(StatefulScript(task), task)
                self.assertTrue(all(check_stateful(result).values()), check_stateful(result))
                self.assertEqual(result["report"]["llm_calls"], 4)
                self.assertIsNone(result["evaluation"])

    def test_reset_isolates_nested_initial_state(self):
        for adapter in (FunctionCallingCRUD, FunctionCallingConfigurations):
            world = adapter()
            world._init_world_state = {"test": {"values": []}}
            world.reset_world_state()
            world.world_state["test"]["values"].append(1)
            world.reset_world_state()
            self.assertEqual(world.world_state, {"test": {"values": []}})
            self.assertEqual(world._init_world_state, {"test": {"values": []}})

    def test_crud_failure_feedback_and_recovery(self):
        def recover(messages, tools):
            self.assertEqual(json.loads([m for m in messages if m["role"] == "tool"][-1]["content"]), False)
            return reply(call("CRUD__add_user", {"name": "Alice", "age": 25}, "create"))
        llm = ScriptedLLM([
            reply(call("CRUD__delete_user", {"user_id": "missing"})), recover,
            reply(call("CRUD__verify_user_field", {"user_id": "Alice_id", "field": "age", "expected_value": "invalid"}, "bad")),
            reply(call("CRUD__verify_user_field", {"user_id": "Alice_id", "field": "age", "expected_value": "25"}, "good")),
            reply(content="done", finish_reason="stop")])
        result = run_world(llm, "crud_4")
        calls = [s for s in result["workflow"].values() if s["op_type"] == "TOOL"]
        self.assertIs(calls[0]["content"], False)
        self.assertEqual(calls[0]["status"], "ok")  # domain failure, not runtime exception
        self.assertEqual(calls[2]["status"], "error")
        self.assertIs(calls[3]["content"], True)
        self.assertEqual(result["state_observations"][0]["state"], {})
        self.assertEqual(result["report"]["tool_errors"], 1)
        self.assertFalse(all(check_stateful(result).values()))

    def test_config_failure_feedback_and_snapshot(self):
        def recover(messages, tools):
            self.assertIn("not found", [m for m in messages if m["role"] == "tool"][-1]["content"])
            return reply(call("Configurations__set_config", {"key": "theme", "value": "dark"}, "set"))
        llm = ScriptedLLM([
            reply(call("Configurations__update_config", {"key": "theme", "new_value": "light"})), recover,
            reply(call("Configurations__print_config", {"key": "theme"}, "print")),
            reply(call("Configurations__update_config", {"key": "theme", "new_value": "light"}, "update")),
            reply(content="done", finish_reason="stop")])
        result = run_world(llm, "configurations_4")
        calls = [s for s in result["workflow"].values() if s["op_type"] == "TOOL"]
        self.assertEqual(calls[2]["content"]["value"], "dark")
        self.assertEqual(result["final_state"]["theme"]["value"], "light")
        self.assertEqual(result["final_state"]["theme"]["category"], "general")
        self.assertEqual(result["state_observations"][0]["state"], {})

    def test_setup_and_unknown_tasks_rejected_before_model(self):
        for task in ("crud_2", "configurations_2", "crud_999", "unknown_1"):
            llm = ScriptedLLM([])
            with self.assertRaises(ValueError):
                run_world(llm, task)
            self.assertEqual(llm.requests, [])

    def test_model_visibility_and_tool_allowlist(self):
        for task, adapter, label in (("crud_4", FunctionCallingCRUD, "CRUD"),
                                     ("configurations_4", FunctionCallingConfigurations, "Configurations")):
            llm = ScriptedLLM([reply(content="done", finish_reason="stop")])
            run_world(llm, task)
            request = llm.requests[0]
            self.assertEqual({t["function"]["name"] for t in request["tools"]},
                             {f"{label}__{name}" for name in adapter.tool_names})
            messages = json.dumps(request["messages"])
            self.assertIn("Current world state", messages)
            self.assertNotIn("expected_sequences", messages)
            self.assertNotIn("excluded_values", messages)


if __name__ == "__main__":
    unittest.main()

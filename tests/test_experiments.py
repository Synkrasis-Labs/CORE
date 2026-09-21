from copy import deepcopy
import json
import unittest

from function_calling.experiments import REGISTRY, PAPER_WORLDS, inventory, make_world, prepare, run_task, ReferenceScript
from function_calling.argument_normalizer import validate_arguments
from function_calling.toolset_builder import build_tool_schema
from test_function_calling import ScriptedLLM, reply


class SharedRunnerTests(unittest.TestCase):
    def test_paper_scope_excludes_configurations(self):
        self.assertNotIn("configurations", PAPER_WORLDS)
        self.assertEqual(len(PAPER_WORLDS), 13)
        self.assertTrue(set(PAPER_WORLDS) <= set(REGISTRY))

    def test_inventory_covers_all_registered_worlds(self):
        rows = inventory()
        self.assertEqual(set(REGISTRY), {r["world"] for r in rows})
        self.assertFalse([r for r in rows if r["status"] == "blocked_world"])
        self.assertTrue(any(r["status"] == "dataset_only" for r in rows))

    def test_all_worlds_reset_and_have_independent_instances(self):
        for key in REGISTRY:
            with self.subTest(world=key):
                world, tools = make_world(key)
                fresh, _ = make_world(key)
                initial = deepcopy(world.world_state)
                world.world_state.clear()
                world.reset_world_state()
                self.assertEqual(world.world_state, initial)
                self.assertEqual(fresh.world_state, initial)
                self.assertTrue(tools)
                json.dumps([build_tool_schema(f) for f in tools.values()])

    def test_every_ready_task_reaches_agent_without_oracle(self):
        for row in inventory():
            if row["status"] != "ready":
                continue
            with self.subTest(task=row["prompt_id"]):
                llm = ScriptedLLM([reply(content="done", finish_reason="stop")])
                artifact = run_task(llm, row["world"], row["prompt_id"])
                self.assertEqual(artifact["report"]["status"], "completed")
                self.assertIsNone(artifact["task_success"])
                self.assertNotIn("excluded_values", json.dumps(llm.requests))
                self.assertNotIn("expected_sequences", json.dumps(llm.requests))

    def test_setup_is_deferred_not_executed(self):
        with self.assertRaises(ValueError):
            prepare("crud", "crud_2")
        with self.assertRaises(ValueError):
            prepare("web_browsing", "web_browsing_1")

    def test_navigation_decorated_methods_are_exposed(self):
        world, tools = make_world("navigation")
        self.assertIn("Navigation__move_right", tools)
        self.assertIn("Navigation__get_player_position", tools)
        self.assertEqual(tools["Navigation__get_player_position"](), (0, 0))
        script = ReferenceScript("navigation", "navigation_1")
        result = run_task(script, "navigation", "navigation_1")
        # Original Navigation reads grid_size from the wrong state location.
        self.assertEqual(result["report"]["tool_errors"], 1)

    def test_reference_executes_real_methods(self):
        result = run_task(ReferenceScript("computations", "computations_1"), "computations", "computations_1")
        self.assertEqual(result["final_state"], {"calculations": ["15 + 7 = 22", "22 * 3 = 66"]})

    def test_fixed_tuple_schema_rejects_wrong_length(self):
        def position(value: tuple[int, int]):
            return value
        schema = build_tool_schema(position)["function"]["parameters"]
        validate_arguments({"value": [1, 2]}, schema)
        for value in ([1], [1, 2, 3], [True, 2]):
            with self.assertRaises(ValueError):
                validate_arguments({"value": value}, schema)


if __name__ == "__main__":
    unittest.main()

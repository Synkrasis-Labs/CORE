"""Integration checks using CORE's original arithmetic methods, without an LLM."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from function_calling.computations_smoke import ComputationsScript, check_artifact
from function_calling.core_computations import FunctionCallingComputations, TOOL_NAMES, run_computations
from worlds.computations import Computations


class ComputationsIntegrationTests(unittest.TestCase):
    def test_original_methods_and_actual_execution(self):
        for name in TOOL_NAMES:
            self.assertIs(getattr(FunctionCallingComputations, name), getattr(Computations, name))
        artifact = run_computations(ComputationsScript())
        self.assertTrue(all(check_artifact(artifact).values()), check_artifact(artifact))
        self.assertEqual(artifact["report"]["llm_calls"], 3)
        self.assertEqual(artifact["report"]["tool_calls"], 2)
        self.assertIsNone(artifact["evaluation"])
        self.assertEqual(artifact["report"]["model"]["provider"], "scripted")
        json.dumps(artifact, allow_nan=False)

    def test_reset_and_repeat_isolate_nested_state(self):
        world = FunctionCallingComputations()
        world.add_numbers(1, 2)
        self.assertEqual(world._init_world_state, {"calculations": []})
        world.reset_world_state()
        self.assertEqual(world.world_state, {"calculations": []})
        first = run_computations(ComputationsScript())
        second = run_computations(ComputationsScript())
        self.assertEqual(first["initial_state"], second["initial_state"])
        self.assertEqual(first["final_state"], second["final_state"])

    def test_model_receives_domain_instructions_and_current_state_only(self):
        class InspectingScript(ComputationsScript):
            def chat_completion(script, messages, tools=None):
                self.assertIn("computational and mathematical operations", messages[0]["content"])
                self.assertIn("Add 15 and 7", messages[1]["content"])
                serialized = json.dumps(messages)
                self.assertNotIn("expected_sequences", serialized)
                self.assertNotIn("alphabet", serialized)
                self.assertNotIn("excluded_values", serialized)
                self.assertEqual({t["function"]["name"] for t in tools},
                                 {f"Computations__{name}" for name in TOOL_NAMES})
                if script.turn == 0:
                    self.assertIn("'calculations': []", messages[1]["content"])
                else:
                    self.assertIn("Current world state after tool call", messages[-1]["content"])
                    self.assertIn("15 + 7 = 22", messages[-1]["content"])
                    self.assertEqual(messages[-2]["role"], "tool")
                return super().chat_completion(messages, tools)

        artifact = run_computations(InspectingScript())
        self.assertTrue(all(check_artifact(artifact).values()), artifact["report"])

    def test_unknown_task_is_rejected(self):
        with self.assertRaises(ValueError):
            run_computations(ComputationsScript(), prompt_id="missing")

    def test_import_does_not_load_legacy_dependencies(self):
        code = (
            "import sys; from function_calling.core_computations import FunctionCallingComputations; "
            "from worlds import Computations; w=FunctionCallingComputations(); "
            "assert isinstance(w, Computations); "
            "assert not {'llm_tool','torch','transformers','model','agents'} & set(sys.modules)"
        )
        result = subprocess.run([sys.executable, "-B", "-c", code],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

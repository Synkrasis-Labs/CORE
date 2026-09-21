from copy import deepcopy
import json
import unittest

import core
from function_calling.computations_smoke import ComputationsScript
from function_calling.core_computations import run_computations, DATASET_PATH
from function_calling.evaluation import evaluate_artifact, score_sequence


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.artifact = run_computations(ComputationsScript())
        self.record = next(r for r in json.loads(DATASET_PATH.read_text(encoding="utf-8"))
                           if r["prompt_id"] == "computations_1")

    def test_known_trace_and_input_preservation(self):
        before = deepcopy(self.artifact)
        result = evaluate_artifact(self.artifact)
        self.assertEqual(result["sequence"], ["A", "C"])
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(self.artifact, before)

    def test_negative_sequences(self):
        # Reversed path agrees with the independently calculated edit score.
        self.assertAlmostEqual(score_sequence(["C", "A"], self.record), 1 / 3)
        # Known legacy search defect: it misses the longer accepting path.
        self.assertEqual(core.path_correctness(["A"], ["A", "C"]), 0.5)
        self.assertEqual(score_sequence(["A"], self.record), 0)

    def test_caches_are_isolated_across_dfas(self):
        old_paths, old_sequences = core.paths, core.path_sequences
        renamed = deepcopy(self.record)
        for node in renamed["nodes"]:
            node["name"] = "other_" + node["name"]
            for transition in node.get("transitions", []):
                transition["from"] = "other_" + transition["from"]
                transition["to"] = "other_" + transition["to"]
        for record in (self.record, renamed, self.record):
            self.assertEqual(score_sequence(["A", "C"], record), 1.0)
        self.assertIs(core.paths, old_paths)
        self.assertIs(core.path_sequences, old_sequences)

    def test_errors_unknown_and_unmapped_calls_are_not_dropped(self):
        for changes in ({"status": "error"}, {"status": "returned_error"},
                        {"status": "skipped"}, {"execution_started": False},
                        {"tool_name": "Other__add_numbers"},
                        {"tool_args": {}}):
            with self.subTest(changes=changes):
                artifact = deepcopy(self.artifact)
                tool = next(s for s in artifact["workflow"].values() if s["op_type"] == "TOOL")
                tool.update(changes)
                result = evaluate_artifact(artifact)
                self.assertEqual(result["status"], "unscored")
                self.assertIsNone(result["score"])
                self.assertTrue(result["issues"])

    def test_identity_and_empty_trace_checks(self):
        for changes in ({"prompt_id": "missing"}, {"world": "Other"},
                        {"prompt": "different task"}, {"workflow": {}}):
            with self.subTest(changes=changes):
                self.assertEqual(evaluate_artifact({**self.artifact, **changes})["status"], "unscored")

    def test_executed_arguments_and_runtime_status_are_separate(self):
        tool = next(s for s in self.artifact["workflow"].values() if s["op_type"] == "TOOL")
        tool["requested_args"] = {"a": "15", "b": "7"}
        self.artifact["report"]["status"] = "stopped"
        self.assertEqual(evaluate_artifact(self.artifact)["score"], 1.0)

    def test_other_world_uses_legacy_scorer(self):
        record = next(r for r in json.loads(DATASET_PATH.read_text(encoding="utf-8"))
                      if r["prompt_id"] == "communication_1")
        call = record["alphabet"]["A"]
        artifact = {"schema_version": 1, "world": "Communication",
                    "prompt_id": record["prompt_id"], "prompt": record["prompt"],
                    "workflow": {"call": {"op_type": "TOOL", "canonical_name": call["name"],
                        "tool_name": "Communication__" + call["name"],
                        "tool_args": {k: v["value"] for k, v in call["arguments"].items()},
                        "status": "ok", "execution_started": True}}}
        result = evaluate_artifact(artifact)
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["score"], score_sequence(["A"], record))

    def test_no_argument_mapping_limitation_is_preserved(self):
        record = deepcopy(self.record)
        record["alphabet"]["A"]["arguments"] = {}
        artifact = deepcopy(self.artifact)
        tool = next(s for s in artifact["workflow"].values() if s["op_type"] == "TOOL")
        tool["tool_args"] = {}
        result = evaluate_artifact(artifact, [record])
        self.assertEqual(result["status"], "unscored")
        self.assertIsNone(result["score"])
        self.assertTrue(any("zero-argument" in issue for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()

"""Boundary checks for ARE event conversion, independent of model/runtime setup."""

from types import SimpleNamespace
import unittest

from are.simulation.types import EventType

from are_integration.trace import core_artifact
from are_integration.reporting import tool_attempts
from function_calling.evaluation import evaluate_artifact


class FakeEvent:
    def __init__(self, event_type, app, name, args, result, *, failed=False, index=1):
        self.event_type = event_type
        self._app = app
        self._name = name
        self._args = args
        self._failed = failed
        self.metadata = SimpleNamespace(return_value=result, exception="failed" if failed else None)
        self.event_id = f"event-{index}"
        self.event_time = index

    def app_class_name(self):
        return self._app

    def function_name(self):
        return self._name

    def get_args(self):
        return {"self": object(), **self._args}

    def failed(self):
        return self._failed


class ARETraceTests(unittest.TestCase):
    def test_agent_path_scores_and_environment_event_is_excluded(self):
        events = [
            FakeEvent(EventType.ENV, "CoreComputationsApp", "add_numbers", {"a": 1, "b": 1}, 2),
            FakeEvent(EventType.AGENT, "CoreComputationsApp", "add_numbers", {"a": 15, "b": 7}, 22),
            FakeEvent(EventType.AGENT, "CoreComputationsApp", "multiply_numbers", {"a": 22, "b": 3}, 66, index=2),
        ]
        artifact = core_artifact(events, {"calculations": ["15 + 7 = 22", "22 * 3 = 66"]})
        self.assertEqual(list(artifact["workflow"]), ["call_1", "call_2"])
        self.assertEqual(evaluate_artifact(artifact)["score"], 1.0)

    def test_rejected_attempt_cannot_borrow_a_later_retry_event(self):
        events = [FakeEvent(EventType.AGENT, "CoreComputationsApp", "add_numbers",
                            {"a": 15, "b": 7}, 22)]
        logs = [
            {"log_type": "tool_call", "tool_name": "CoreComputationsApp__add_numbers",
             "tool_arguments": {"a": 15}},
            {"log_type": "error", "error": "TypeError", "exception": "missing b"},
            {"log_type": "tool_call", "tool_name": "CoreComputationsApp__add_numbers",
             "tool_arguments": {"a": 15, "b": 7}},
            {"log_type": "observation", "content": "22"},
        ]
        attempts = tool_attempts(logs, events)
        self.assertIsNone(attempts[0]["are_event_id"])
        self.assertEqual(attempts[1]["are_event_id"], "event-1")
        artifact = core_artifact(events, {}, attempts=attempts)
        self.assertEqual(artifact["workflow"]["call_1"]["tool_args"], {"a": 15})
        self.assertEqual(artifact["workflow"]["call_2"]["tool_args"], {"a": 15, "b": 7})
        self.assertEqual(evaluate_artifact(artifact)["status"], "unscored")

    def test_failed_agent_call_is_preserved_and_unscored(self):
        event = FakeEvent(EventType.AGENT, "CoreComputationsApp", "add_numbers",
                          {"a": 15, "b": 7}, None, failed=True)
        artifact = core_artifact([event], {})
        self.assertEqual(artifact["workflow"]["call_1"]["status"], "error")
        self.assertEqual(evaluate_artifact(artifact)["status"], "unscored")


if __name__ == "__main__":
    unittest.main()

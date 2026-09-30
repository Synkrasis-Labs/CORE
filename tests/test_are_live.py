"""Offline checks for the bounded ARE agent and saved CORE score."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from are_integration.live import BoundedOpenAIEngine, RequestBudgetExceeded, run_live


def model_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
    )


class ARELiveRunnerTests(unittest.TestCase):
    def test_model_selected_calls_are_scored_and_raw_trace_is_saved(self):
        responses = iter([
            'Thought: Add first.\nAction:\n{"action":"CoreComputationsApp__add_numbers",'
            '"action_input":{"a":15,"b":7}}<end_action>',
            'Thought: Multiply next.\nAction:\n{"action":"CoreComputationsApp__multiply_numbers",'
            '"action_input":{"a":22,"b":3}}<end_action>',
            'Thought: Answer.\nAction:\n{"action":"AgentUserInterface__send_message_to_user",'
            '"action_input":{"content":"66"}}<end_action>',
        ])

        def fake_completion(**kwargs):
            self.assertEqual(kwargs["max_completion_tokens"], 256)
            return model_response(next(responses))

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_completion)))
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            engine = BoundedOpenAIEngine(
                "gpt-4.1-nano", "offline-test-key", max_requests=4,
                max_output_tokens=256, request_timeout=3, client=client,
            )
            summary = run_live(
                model="gpt-4.1-nano", api_key="offline-test-key",
                output_dir=Path(directory), max_requests=4, request_timeout=3,
                engine=engine,
            )
            self.assertTrue(summary["are_validation"]["success"])
            self.assertEqual(summary["requests_made"], 3)
            self.assertEqual(summary["evaluation"]["score"], 1.0)
            self.assertEqual(
                [call["canonical_name"] for call in summary["artifact"]["workflow"].values()],
                ["add_numbers", "multiply_numbers"],
            )
            self.assertTrue(Path(summary["are_trace"]).is_file())
            self.assertTrue((Path(directory) / "run.json").is_file())
            self.assertNotIn("offline-test-key", (Path(directory) / "run.json").read_text())
            self.assertNotIn("offline-test-key", Path(summary["are_trace"]).read_text())

    def test_request_cap_counts_attempts(self):
        fake_create = Mock(return_value=model_response("done"))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
        engine = BoundedOpenAIEngine(
            "gpt-4.1-nano", "offline-test-key", max_requests=1,
            max_output_tokens=256, request_timeout=3, client=client,
        )
        engine.chat_completion([{"role": "user", "content": "hello"}])
        with self.assertRaises(RequestBudgetExceeded):
            engine.chat_completion([{"role": "user", "content": "again"}])
        self.assertEqual(fake_create.call_count, 1)
        self.assertTrue(engine.budget_exhausted)


if __name__ == "__main__":
    unittest.main()

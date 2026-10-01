"""Offline checks for the bounded ARE agent and saved CORE score."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch

from are_integration.live import BoundedOpenAIEngine, BoundedAgentConfigBuilder, RequestBudgetExceeded, run_live, main
from are_integration.reporting import reply_delivery


def model_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
    )


class ARELiveRunnerTests(unittest.TestCase):
    def run_script(self, reply_content="66", *, reject_world_call=False):
        actions = [
            'Thought: Add first.\nAction:\n{"action":"CoreComputationsApp__add_numbers",'
            '"action_input":{"a":15,"b":7}}<end_action>',
            'Thought: Multiply next.\nAction:\n{"action":"CoreComputationsApp__multiply_numbers",'
            '"action_input":{"a":22,"b":3}}<end_action>',
            'Thought: Answer.\nAction:\n{"action":"AgentUserInterface__send_message_to_user",'
            '"action_input":' + json.dumps({"content": reply_content}) + '}<end_action>',
        ]
        if reject_world_call:
            actions.insert(2, 'Thought: Invalid.\nAction:\n' + json.dumps({
                "action": "CoreComputationsApp__add_numbers", "action_input": {"a": 1}
            }) + '<end_action>')
        responses = iter(actions)

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
            saved = json.loads((Path(directory) / "run.json").read_text())
            self.assertEqual(saved["reply_delivery"], summary["reply_delivery"])
            self.assertTrue(summary["are_validation"]["success"])
            self.assertEqual(summary["requests_made"], len(actions))
            if not reject_world_call:
                self.assertEqual(summary["evaluation"]["score"], 1.0)
                self.assertEqual(
                    [call["canonical_name"] for call in summary["artifact"]["workflow"].values()],
                    ["add_numbers", "multiply_numbers"],
                )
            self.assertTrue(Path(summary["are_trace"]).is_file())
            self.assertTrue((Path(directory) / "run.json").is_file())
            self.assertNotIn("offline-test-key", (Path(directory) / "run.json").read_text())
            self.assertNotIn("offline-test-key", Path(summary["are_trace"]).read_text())

            return summary

    def test_valid_reply_is_delivered(self):
        summary = self.run_script()
        self.assertTrue(summary["reply_delivery"]["delivered"])
        self.assertTrue(summary["reply_delivery"]["model_reply_delivered"])
        self.assertEqual(summary["reply_delivery"]["messages"][0]["content"], "66")
        self.assertEqual(summary["reply_delivery"]["attempts"][0]["status"], "ok")

    def test_exact_malformed_live_reply_is_preserved(self):
        content = {"type": "string", "description": "The final result of the calculation is 66."}
        summary = self.run_script(content)
        self.assertFalse(summary["reply_delivery"]["delivered"])
        attempt = summary["reply_delivery"]["attempts"][0]
        self.assertEqual(attempt["requested_args"], {"content": content})
        self.assertEqual(attempt["status"], "not_observed")
        self.assertIsNone(attempt["are_event_id"])
        self.assertIn("must be of type", attempt["error"])
        self.assertTrue(any(log["log_type"] == "error" for log in summary["agent_logs"]))

    def test_rejected_world_call_prevents_partial_path_score(self):
        summary = self.run_script(reject_world_call=True)
        self.assertEqual(summary["evaluation"]["status"], "unscored")
        step = summary["artifact"]["workflow"]["call_3"]
        self.assertEqual(step["tool_args"], {"a": 1})
        self.assertEqual(step["status"], "not_observed")
        self.assertFalse(step["execution_started"])

    def test_crud_agent_sees_setup_and_keeps_read_in_path(self):
        actions = [
            ("CoreCRUDApp__list_users", {}),
            ("CoreCRUDApp__update_user_email", {"user_id": "Alice_id", "email": "alice@example.com"}),
            ("CoreCRUDApp__verify_user_field", {"user_id": "Alice_id", "field": "email",
                                               "expected_value": "alice@example.com"}),
            ("AgentUserInterface__send_message_to_user", {"content": "Updated Alice's email."}),
        ]
        responses = iter(model_response('Thought: Execute.\nAction:\n' + json.dumps({
            "action": name, "action_input": args}) + '<end_action>') for name, args in actions)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: next(responses))))
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            engine = BoundedOpenAIEngine("gpt-4.1-nano", "offline-test-key", max_requests=4,
                max_output_tokens=256, request_timeout=3, client=client)
            summary = run_live(model="gpt-4.1-nano", api_key="offline-test-key",
                output_dir=Path(directory), max_requests=4, request_timeout=3, engine=engine,
                scenario_id="core_crud_2")
        self.assertTrue(summary["are_validation"]["success"])
        self.assertTrue(summary["reply_delivery"]["delivered"])
        self.assertEqual(summary["artifact"]["prompt_id"], "crud_2")
        self.assertEqual(summary["artifact"]["workflow"]["call_1"]["content"][0]["email"], None)
        self.assertEqual(len(summary["artifact"]["workflow"]), 3)
        self.assertEqual(summary["evaluation"]["status"], "unscored")

    def test_cli_separates_reply_state_and_score(self):
        for state, delivered, status, score, expected_exit in (
            (True, False, "scored", 1.0, 1),
            (True, True, "unscored", None, 0),
            (False, True, "scored", 1.0, 1),
        ):
            summary = {"are_validation": {"success": state, "exception": None},
                "reply_delivery": {"delivered": delivered},
                "evaluation": {"status": status, "score": score},
                "requests_made": 3, "request_budget_exhausted": False}
            output = StringIO()
            with self.subTest(state=state, delivered=delivered), \
                 patch("sys.argv", ["live", "--output-dir", "/tmp/unused-core-are-cli-test"]), \
                 patch("are_integration.live.load_api_key", return_value="offline-test-key"), \
                 patch("are_integration.live.run_live", return_value=summary), redirect_stdout(output):
                self.assertEqual(main(), expected_exit)
            emitted = json.loads(output.getvalue())
            self.assertEqual(emitted["are_state_success"], state)
            self.assertEqual(emitted["reply_delivered"], delivered)
            self.assertEqual(emitted["core_score"], score)

    def test_no_output_cap_omits_api_parameter_and_records_reasoning_usage(self):
        response = model_response("Thought: Execute.")
        response.choices[0].finish_reason = "stop"
        response.usage.completion_tokens_details = SimpleNamespace(reasoning_tokens=7)
        fake_create = Mock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
        engine = BoundedOpenAIEngine(
            "gpt-5-nano", "offline-test-key", max_requests=6,
            max_output_tokens=None, request_timeout=30, client=client,
        )
        engine.chat_completion([{"role": "user", "content": "hello"}])
        self.assertNotIn("max_completion_tokens", fake_create.call_args.kwargs)
        self.assertEqual(fake_create.call_args.kwargs["timeout"], 30)
        self.assertEqual(engine.usage[0]["reasoning_tokens"], 7)
        self.assertEqual(engine.usage[0]["finish_reason"], "stop")

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

    def test_automatic_stop_is_not_a_model_reply(self):
        content = 'Max iterations (6) reached. Stopping.'
        attempt = {'tool_name':'AgentUserInterface__send_message_to_user',
                   'requested_args':{'content':content},'status':'ok'}
        result = reply_delivery([{'sender':'Agent','content':content}], [attempt],
                                [{'log_type':'error','error':'MaxIterationsAgentError'}])
        self.assertTrue(result['delivered'])
        self.assertTrue(result['automatic_stop_delivered'])
        self.assertFalse(result['model_reply_delivered'])

    def test_json_instructions_and_literal_string_values_are_preserved(self):
        config = BoundedAgentConfigBuilder(6).build('default').get_base_agent_config()
        self.assertIn('content must be a JSON string', config.system_prompt)
        self.assertNotIn('expected_sequences', config.system_prompt)
        text = 'Thought: Reply.\nAction:\n' + json.dumps({
            'action':'AgentUserInterface__send_message_to_user',
            'action_input':{'content':'TrueName and FalsePassword'}}) + '<end_action>'
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs:model_response(text))))
        engine = BoundedOpenAIEngine('offline','offline-test-key',max_requests=1,
                    max_output_tokens=None,request_timeout=3,client=client)
        content, _ = engine.chat_completion([{'role':'user','content':'reply'}])
        self.assertEqual(content, text)


if __name__ == "__main__":
    unittest.main()

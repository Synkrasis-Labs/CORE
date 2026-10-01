"""Run one bounded ARE agent on a migrated CORE task and score its tool path.

No model request is made by importing this module or using --help.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from are.simulation.agents.agent_builder import AgentBuilder
from are.simulation.agents.agent_config_builder import AgentConfigBuilder
from are.simulation.agents.llm.litellm.litellm_engine import (
    LiteLLMEngine,
    LiteLLMModelConfig,
)
from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.scenario_runner import ScenarioRunner
from are.simulation.scenarios.config import ScenarioRunnerConfig
from dotenv import dotenv_values
from openai import OpenAI

from function_calling.evaluation import evaluate_artifact

from .computations import CoreComputationsApp, CoreComputationsOne
from .crud import CoreCRUDApp, CoreCRUDTwo
from .trace import core_artifact
from .reporting import tool_attempts, reply_delivery


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {
    "core_computations_1": (CoreComputationsOne, CoreComputationsApp, "Computations", "computations_1",
                            "Add 15 and 7, then multiply the result by 3."),
    "core_crud_2": (CoreCRUDTwo, CoreCRUDApp, "CRUD", "crud_2", None),
}


class RequestBudgetExceeded(RuntimeError):
    """The model-request cap was reached before ARE finished the task."""


class BoundedOpenAIEngine(LiteLLMEngine):
    """ARE text-action interface with a hard request cap and optional output cap."""

    def __init__(self, model: str, api_key: str, *, max_requests: int,
                 max_output_tokens: int | None, request_timeout: float, client=None):
        super().__init__(LiteLLMModelConfig(
            model_name=model, provider="openai",
            endpoint="https://api.openai.com/v1", api_key=api_key,
        ))
        self.max_requests = max_requests
        self.max_output_tokens = max_output_tokens
        self.request_timeout = request_timeout
        self.client = client or OpenAI(
            api_key=api_key, base_url=self.model_config.endpoint,
            timeout=request_timeout, max_retries=0,
        )
        self.requests_made = 0
        self.budget_exhausted = False
        self.usage: list[dict] = []

    def chat_completion(self, messages, stop_sequences=None, **kwargs):
        if self.requests_made >= self.max_requests:
            self.budget_exhausted = True
            raise RequestBudgetExceeded(f"Model request limit reached ({self.max_requests})")
        self.requests_made += 1  # Count attempts, including provider errors.
        request = {
            "model": self.model_config.model_name,
            "messages": [self._convert_message_to_litellm_format(m) for m in messages],
            "timeout": self.request_timeout,
        }
        if self.max_output_tokens is not None:
            request["max_completion_tokens"] = self.max_output_tokens
        response = self.client.chat.completions.create(**request)
        if getattr(response, "usage", None) is not None:
            usage = response.usage
            self.usage.append({
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
                "reasoning_tokens": getattr(
                    getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None),
                "finish_reason": getattr(response.choices[0], "finish_reason", None),
            })
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Model returned no text action")
        content = content.replace("False", "false").replace("True", "true")
        for stop in stop_sequences or []:
            content = content.split(stop, 1)[0]
        return content, None


class BoundedAgentConfigBuilder(AgentConfigBuilder):
    def __init__(self, max_iterations: int):
        self.max_iterations = max_iterations

    def build(self, agent_name: str):
        config = super().build(agent_name)
        config.get_base_agent_config().max_iterations = self.max_iterations
        return config


class OpenAIEngineBuilder:
    def __init__(self, engine: BoundedOpenAIEngine):
        self.engine = engine

    def create_engine(self, engine_config, mock_responses=None):
        if mock_responses is not None:
            raise ValueError("This runner does not accept mock responses")
        return self.engine


class BoundedAgentBuilder(AgentBuilder):
    """ARE 1.2.0 resets the base agent's iteration limit during construction."""

    def __init__(self, engine: BoundedOpenAIEngine, max_iterations: int):
        super().__init__(llm_engine_builder=OpenAIEngineBuilder(engine))
        self.max_iterations = max_iterations
        self.agent = None

    def build(self, agent_config, env=None, mock_responses=None):
        agent = super().build(agent_config, env=env, mock_responses=mock_responses)
        agent.max_iterations = self.max_iterations
        agent.react_agent.max_iterations = self.max_iterations
        self.agent = agent
        return agent


class TraceCapturingScenarioRunner(ScenarioRunner):
    """Capture the in-memory ARE events before its runner stops the environment."""

    def __init__(self, *, app_class=CoreComputationsApp, **kwargs):
        super().__init__(**kwargs)
        self.app_class = app_class
        self.events = []
        self.final_state = None
        self.messages = []

    def _export_trace(self, env, scenario, *args, **kwargs):
        self.events = env.event_log.list_view()
        self.final_state = scenario.get_typed_app(self.app_class).get_state()
        self.messages = [
            {"sender": m.sender.value, "content": m.content, "id": m.id}
            for m in scenario.get_typed_app(AgentUserInterface).messages
        ]
        return super()._export_trace(env, scenario, *args, **kwargs)


def load_api_key() -> str:
    key = dotenv_values(REPO_ROOT / ".env").get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("Set OPENAI_API_KEY in CORE-ARE/.env or the environment")
    return key


def run_live(*, model: str, api_key: str, output_dir: Path,
             max_requests: int = 6, max_output_tokens: int | None = 256,
             request_timeout: float = 30.0, engine: BoundedOpenAIEngine | None = None,
             scenario_id: str = "core_computations_1"):
    """Execute one agent turn; save ARE's raw export plus CORE's evaluation."""
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unsupported scenario: {scenario_id}")
    scenario_class, app_class, world, prompt_id, prompt = SCENARIOS[scenario_id]
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = engine or BoundedOpenAIEngine(
        model, api_key, max_requests=max_requests,
        max_output_tokens=max_output_tokens, request_timeout=request_timeout,
    )
    agent_builder = BoundedAgentBuilder(engine, max_requests)
    runner = TraceCapturingScenarioRunner(
        app_class=app_class,
        agent_config_builder=BoundedAgentConfigBuilder(max_requests),
        agent_builder=agent_builder,
    )
    scenario = scenario_class()
    scenario.initialize()
    if prompt is None:
        prompt = scenario.core_task["prompt"]
    result = runner.run(ScenarioRunnerConfig(
        model=model, model_provider="openai", agent="default",
        oracle=False, export=True, output_dir=str(output_dir), max_turns=1,
        wait_for_user_input_timeout=request_timeout,
    ), scenario)
    logs = ([log.to_dict() for log in agent_builder.agent.react_agent.get_agent_logs()]
            if agent_builder.agent is not None else [])
    attempts = tool_attempts(logs, runner.events)
    artifact = core_artifact(
        runner.events, runner.final_state,
        driver=f"ARE default agent; OpenAI {model}", attempts=attempts,
        world=world, app_class=app_class.__name__, prompt_id=prompt_id, prompt=prompt,
    )
    evaluation = evaluate_artifact(artifact)
    summary = {
        "model": model,
        "scenario_id": scenario.scenario_id,
        "agent": "ARE default",
        "limits": {"model_requests": max_requests,
                   "output_tokens_per_request": max_output_tokens,
                   "request_timeout_seconds": request_timeout},
        "requests_made": engine.requests_made,
        "request_budget_exhausted": engine.budget_exhausted,
        "usage": engine.usage,
        "are_validation": {
            "success": result.success,
            "rationale": result.rationale,
            "exception": str(result.exception) if result.exception else None,
            "duration_seconds": result.duration,
        },
        "reply_delivery": reply_delivery(runner.messages, attempts),
        "tool_attempts": attempts,
        "agent_logs": logs,
        "are_trace": result.export_path,
        "artifact": artifact,
        "evaluation": evaluation,
    }
    # Redact defensively, including provider exception text and ARE's raw export.
    if result.export_path:
        raw_path = Path(result.export_path)
        raw_path.write_text(raw_path.read_text(encoding="utf-8").replace(api_key, "[REDACTED]"), encoding="utf-8")
    (output_dir / "run.json").write_text(
        json.dumps(summary, indent=2, default=str).replace(api_key, "[REDACTED]"),
        encoding="utf-8",
    )
    return summary


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="core_computations_1")
    parser.add_argument("--model", default="gpt-4.1-nano")
    parser.add_argument("--max-requests", type=positive_int, default=6)
    parser.add_argument("--max-output-tokens", type=positive_int, default=256)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.request_timeout <= 0:
        parser.error("--request-timeout must be positive")
    output_dir = args.output_dir or (REPO_ROOT / "runs" / "are" / SCENARIOS[args.scenario][3] /
                                     datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S_%fZ"))
    try:
        summary = run_live(
            model=args.model, api_key=load_api_key(), output_dir=output_dir, scenario_id=args.scenario,
            max_requests=args.max_requests, max_output_tokens=args.max_output_tokens,
            request_timeout=args.request_timeout,
        )
    except (ValueError, FileExistsError) as error:
        parser.error(str(error))
    print(json.dumps({
        "are_state_success": summary["are_validation"]["success"],
        "reply_delivered": summary["reply_delivery"]["delivered"],
        "requests_made": summary["requests_made"],
        "request_budget_exhausted": summary["request_budget_exhausted"],
        "core_score": summary["evaluation"]["score"],
        "core_status": summary["evaluation"]["status"],
        "output": str(output_dir / "run.json"),
    }, indent=2))
    return 0 if (summary["are_validation"]["success"] is True
                 and summary["reply_delivery"]["delivered"]
                 and not summary["are_validation"]["exception"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

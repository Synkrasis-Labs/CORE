"""Run CORE computations_1 in ARE oracle mode and score its saved tool path."""

import argparse
import json
from pathlib import Path

from are.simulation.environment import Environment, EnvironmentConfig

from function_calling.evaluation import evaluate_artifact

from .computations import CoreComputationsApp, CoreComputationsOne
from .trace import core_artifact


def run_smoke():
    scenario = CoreComputationsOne()
    scenario.initialize()
    environment = Environment(config=EnvironmentConfig(
        oracle_mode=True, queue_based_loop=True, exit_when_no_events=True, verbose=False
    ))
    try:
        environment.run(scenario)
        validation = scenario.validate(environment)
        artifact = core_artifact(
            environment.event_log.list_view(),
            scenario.get_typed_app(CoreComputationsApp).get_state(),
        )
    finally:
        environment.stop()
    evaluation = evaluate_artifact(artifact)
    calls = list(artifact["workflow"].values())
    checks = {
        "are_scenario_valid": validation.success is True,
        "tool_names": [step["canonical_name"] for step in calls] == ["add_numbers", "multiply_numbers"],
        "tool_arguments": [step["tool_args"] for step in calls] == [
            {"a": 15, "b": 7}, {"a": 22, "b": 3}
        ],
        "tool_results": [step["content"] for step in calls] == [22, 66],
        "core_legacy_path_score": evaluation["status"] == "scored" and evaluation["score"] == 1.0,
    }
    return {"checks": checks, "artifact": artifact, "evaluation": evaluation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON evidence file")
    args = parser.parse_args()
    result = run_smoke()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result["checks"], indent=2))
    return 0 if all(result["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

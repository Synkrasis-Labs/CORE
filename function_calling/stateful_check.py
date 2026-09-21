"""Run two existing stateful tasks; scripted by default, --live uses a paid model."""

import argparse
import json
import os
from pathlib import Path

from .run_files import new_run_path
from .stateful_worlds import TASKS, StatefulScript, run_world, check_stateful


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default="gpt-4.1-nano")
    args = parser.parse_args()
    key = None
    if args.live:
        from dotenv import dotenv_values
        from .openai_llm import OpenAILLM
        key = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not key:
            parser.error("Set OPENAI_API_KEY in CORE/.env")
    passed = True
    for task in TASKS:
        llm = (OpenAILLM(args.model, api_key=key, base_url="https://api.openai.com/v1", temperature=0,
                        max_output_tokens=256, request_timeout_seconds=30, parallel_tool_calls=False)
               if args.live else StatefulScript(task))
        path = new_run_path(task, args.model if args.live else "scripted")
        artifact = run_world(llm, task)
        checks = check_stateful(artifact)
        artifact["integration_check"] = {"passed": all(checks.values()), "checks": checks,
                                           "note": "Task-specific execution checks, not research metrics."}
        artifact["client_configuration"] = llm.client_info() if args.live else {"provider": "scripted"}
        output = json.dumps(artifact, indent=2, allow_nan=False)
        path.write_text(output.replace(key, "[REDACTED]") if key else output, encoding="utf-8")
        summary = json.dumps({"task": task, "checks": checks, "report": artifact["report"], "artifact": str(path)}, indent=2)
        print(summary.replace(key, "[REDACTED]") if key else summary)
        passed = passed and all(checks.values())
        if artifact["report"]["status"] == "failed":
            break
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

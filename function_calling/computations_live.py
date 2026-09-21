"""One paid Computations check: python -m function_calling.computations_live."""

import argparse
import json
import os
from pathlib import Path

from .computations_smoke import check_artifact
from .core_computations import run_computations
from .openai_llm import OpenAILLM
from .run_files import new_run_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-4.1-nano")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is not None and args.output.exists():
        parser.error("Output already exists; use --output with a new filename to preserve previous runs.")

    from dotenv import dotenv_values

    # Read only the requested credential. Never include it in the saved artifact.
    key = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("OPENAI_API_KEY")
    key = key or os.getenv("OPENAI_API_KEY")
    if not key:
        parser.error("Set OPENAI_API_KEY in CORE/.env or the environment.")
    args.output = args.output or new_run_path("computations_1", args.model)
    llm = OpenAILLM(
        model=args.model, api_key=key, base_url="https://api.openai.com/v1",
        temperature=0, max_output_tokens=256, request_timeout_seconds=30,
        parallel_tool_calls=False,
    )
    artifact = run_computations(llm, max_iterations=6, max_tool_calls=6, timeout_seconds=90)
    artifact["client_configuration"] = llm.client_info()
    checks = check_artifact(artifact)
    # Natural-language answers need manual review; exact '66' is a scripted assertion.
    checks.pop("final_answer")
    artifact["live_check"] = {
        "passed": all(checks.values()), "checks": checks,
        "note": "Checks the expected tool path and state; review final answer separately. Not CORE scores.",
    }
    usage = [m["tokens"] for m in artifact["runtime_metrics"] if m["role"] == "assistant"]
    totals = {k: sum(u[k] for u in usage) if usage and all(u[k] is not None for u in usage) else None
              for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    artifact["usage_totals"] = totals
    # Defensive redaction also covers provider errors before writing or printing.
    serialized = json.dumps(artifact, indent=2, allow_nan=False).replace(key, "[REDACTED]")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding="utf-8")
    print(json.dumps({"model": args.model, "passed": all(checks.values()),
                      "checks": checks, "report": artifact["report"],
                      "usage": totals, "artifact": str(args.output)}, indent=2).replace(key, "[REDACTED]"))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

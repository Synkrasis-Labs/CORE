"""Scripted integration check. Run: python -m function_calling.computations_smoke"""

import argparse
import json
from pathlib import Path

from .core_computations import run_computations


class ComputationsScript:
    """Deterministic test driver, not an LLM or a capability benchmark."""

    provider = "scripted"
    model = "computations_1_feedback_check"

    def __init__(self):
        self.turn = 0

    def chat_completion(self, messages, tools=None):
        self.turn += 1
        available = {t["function"]["name"] for t in tools or []}
        if not {"Computations__add_numbers", "Computations__multiply_numbers"} <= available:
            raise ValueError("Required real Computations tools are missing")
        if self.turn == 1:
            name, args = "Computations__add_numbers", {"a": 15, "b": 7}
        else:
            replies = [m for m in messages if m["role"] == "tool"]
            if len(replies) != self.turn - 1:
                raise ValueError("Missing tool feedback")
            previous_result = json.loads(replies[-1]["content"])
            if self.turn == 2:
                # Consume the actual addition result instead of hardcoding it.
                name, args = "Computations__multiply_numbers", {"a": previous_result, "b": 3}
            elif self.turn == 3:
                return {"choices": [{"message": {"content": str(previous_result), "tool_calls": []},
                                     "finish_reason": "stop"}]}
            else:
                raise ValueError("Unexpected extra model request")
        return {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": f"script_call_{self.turn}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}]},
                             "finish_reason": "tool_calls"}]}


def check_artifact(artifact):
    calls = [s for s in artifact["workflow"].values() if s["op_type"] == "TOOL"]
    expected_final = {"calculations": ["15 + 7 = 22", "22 * 3 = 66"]}
    return {
        "completed": artifact["report"]["status"] == "completed",
        "call_sequence": [s["canonical_name"] for s in calls] == ["add_numbers", "multiply_numbers"],
        "call_arguments": [s["tool_args"] for s in calls] == [{"a": 15, "b": 7}, {"a": 22, "b": 3}],
        "actual_results": [s["content"] for s in calls] == [22, 66],
        "no_tool_errors": artifact["report"]["tool_errors"] == 0 and all(s["status"] == "ok" for s in calls),
        "fresh_initial_state": artifact["initial_state"] == {"calculations": []},
        "correct_final_state": artifact["final_state"] == expected_final,
        "state_feedback": [o["state"] for o in artifact["state_observations"]] == [
            {"calculations": ["15 + 7 = 22"]}, expected_final],
        "final_answer": artifact["report"]["final_answer"] == "66",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/computations_scripted.json"))
    args = parser.parse_args()
    artifact = run_computations(ComputationsScript())
    checks = check_artifact(artifact)
    artifact["scripted_check"] = {"passed": all(checks.values()), "checks": checks,
                                  "note": "Integration assertions, not CORE metric scores."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"passed": all(checks.values()), "checks": checks,
                      "results": [s["content"] for s in artifact["workflow"].values() if s["op_type"] == "TOOL"],
                      "artifact": str(args.output)}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

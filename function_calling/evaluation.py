"""Evaluate a saved world trace with the unchanged legacy CORE scorer.

Run: python -m function_calling.evaluation INPUT --output OUTPUT
No model requests are made. Unsupported traces are reported without a score.
"""

import argparse
from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from threading import RLock

import core
from evaluate import load_world, convert_dfa, convert_alphabet_to_proc, fc2symbol
from .core_computations import DATASET_PATH
from worlds import _MODULES

_LOCK = RLock()


def score_sequence(sequence, record):
    """Isolate legacy module-global caches; preserve its formulas and search."""
    dfa = convert_dfa(load_world(deepcopy(record))["nodes"])
    if not dfa or [n for n in dfa if n.is_final] != [dfa[-1]]:
        raise ValueError("Legacy scorer requires one final node, listed last")
    with _LOCK:
        old_paths, old_sequences = core.paths, core.path_sequences
        try:
            core.paths = [{n.name: int(i == 0) for i, n in enumerate(dfa)}]
            core.path_sequences = [{n.name: [[0]] if i == 0 else [[]]
                                    for i, n in enumerate(dfa)}]
            with redirect_stdout(io.StringIO()):
                return core.evaluate([0, *sequence], dfa)
        finally:
            core.paths, core.path_sequences = old_paths, old_sequences


def evaluate_artifact(artifact, dataset=None):
    result = {"status": "unscored", "metric": "legacy_core_path_correctness",
              "score": None, "sequence": [], "actions": [], "issues": [],
              "policy": "all recorded tool steps must have executed successfully and map to symbols",
              "note": "Legacy core.evaluate score, not all paper metrics or final-state/task success.",
              "limitations": ["Legacy path search can miss longer accepting paths (A alone scores 0, not 0.5).",
                              "Legacy fc2symbol argument/exclusion matching is preserved, including its known limitations."]}
    def issue(message):
        result["issues"].append(message)

    world_name = artifact.get("world")
    world_key = _MODULES.get(world_name)
    if artifact.get("schema_version") != 1 or world_key is None:
        issue("Expected a schema-v1 artifact with a registered CORE world")
        return result
    dataset = dataset if dataset is not None else json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    records = [r for r in dataset if r["prompt_id"] == artifact.get("prompt_id")]
    if len(records) != 1 or records[0]["world"] != world_key:
        issue("Task ID must identify exactly one dataset record for this world")
        return result
    record = records[0]
    if record["prompt"] != artifact.get("prompt"):
        issue("Artifact prompt differs from the dataset task")
        return result
    alphabet = convert_alphabet_to_proc(load_world(record)["alphabet"])
    workflow = artifact.get("workflow")
    if not isinstance(workflow, dict):
        issue("Missing structured workflow")
        return result
    for step_id, step in workflow.items():
        if step.get("op_type") != "TOOL":
            continue
        name = step.get("canonical_name")
        action = {"step": step_id, "name": name, "arguments": deepcopy(step.get("tool_args")),
                  "status": step.get("status"), "symbol": None}
        result["actions"].append(action)
        if not isinstance(name, str) or not name or step.get("tool_name") != f"{world_name}__{name}":
            issue(f"{step_id}: unknown or inconsistent tool identity")
            continue
        if step.get("status") != "ok" or step.get("execution_started") is not True:
            issue(f"{step_id}: call did not execute successfully; error-scoring policy is unresolved")
            continue
        if not isinstance(action["arguments"], dict):
            issue(f"{step_id}: missing executed arguments")
            continue
        if name not in alphabet:
            issue(f"{step_id}: {name} is absent from the task alphabet")
            continue
        with redirect_stdout(io.StringIO()):
            symbol = fc2symbol(action, alphabet) if name in alphabet else ""
        if not symbol:
            detail = "zero-argument call" if not action["arguments"] else "argument match"
            issue(f"{step_id}: legacy alphabet could not map {name} ({detail})")
            continue
        action["symbol"] = symbol
        result["sequence"].append(symbol)
    if not result["actions"]:
        issue("Empty tool trace; legacy empty-path behavior is not validated")
    if len(result["actions"]) > 12:
        issue("Trace exceeds the twelve-call scope of the shared runner")
    if not result["issues"]:
        try:
            result["score"] = score_sequence(result["sequence"], record)
            result["status"] = "scored"
        except (ValueError, IndexError, KeyError, RecursionError) as error:
            issue(f"Legacy scorer could not evaluate this path: {type(error).__name__}: {error}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch", action="store_true", help="Input is a shared-runner summary; include reused runs")
    args = parser.parse_args()
    args.output = args.output or args.input.with_name("evaluation.json")
    if args.output.exists():
        parser.error("Output exists; choose a new filename")
    artifact = json.loads(args.input.read_text(encoding="utf-8"))
    if args.batch:
        dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        results = []
        seen = set()
        for entry in artifact.get("reused_runs", []) + artifact["runs"]:
            source = Path(entry["artifact"])
            if not source.is_absolute():
                source = DATASET_PATH.parent / source
            source = source.resolve()
            if source in seen:
                continue
            seen.add(source)
            saved = json.loads(source.read_text(encoding="utf-8"))
            results.append({"source_run": str(source), "prompt_id": saved.get("prompt_id"),
                            "evaluation": evaluate_artifact(saved, dataset)})
        result = {"schema_version": 1, "source_summary": str(args.input.resolve()),
                  "note": "Legacy path scores, not task-success counts or all paper metrics.",
                  "counts": dict(Counter(r["evaluation"]["status"] for r in results)),
                  "runs": results}
    else:
        evaluation = evaluate_artifact(artifact)
        result = {"schema_version": 1, "source_run": str(args.input.resolve()),
                  "prompt_id": artifact.get("prompt_id"), "evaluation": evaluation}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result["counts"] if args.batch else evaluation, indent=2))
    print(f"Saved: {args.output}")
    return 0 if args.batch or evaluation["status"] == "scored" else 1


if __name__ == "__main__":
    raise SystemExit(main())

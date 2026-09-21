"""Shared opt-in runner. Default: inventory only. Original runner stays unchanged."""

import argparse
import ast
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
import inspect
import json
import os
from pathlib import Path

from worlds import _MODULES
from worlds.world import World
from .agent import Agent
from .core_computations import DATASET_PATH
from .run_files import new_run_path
from .toolset_builder import build_tool_schema

ROOT = DATASET_PATH.parent
REGISTRY = {module: name for name, module in _MODULES.items()}
# Explicit mapping to arXiv:2509.20998v1, Table 2 and Appendix A/Table 3.
PAPER_WORLDS = (
    "automation", "communication", "computations", "crud", "desktop_manager",
    "events_scheduler", "file_management", "legal_compliance", "navigation",
    "transactions", "validation", "web_browsing", "writing",
)
MISSING_PAPER_WORLDS = ["Agentic Farm", "Agentic Arm"]


def make_world(key):
    original = getattr(import_module(f"worlds.{key}"), REGISTRY[key])
    wrapped = {name: member._func for name, member in vars(original).items()
               if type(member).__module__ == "llm_tool.tool" and hasattr(member, "_func")}
    # Match the legacy public-method tool surface, including helper methods.
    names = tuple(sorted({name for name, method in inspect.getmembers(original, inspect.isfunction)
                          if not name.startswith("_") and name not in dir(World)} | set(wrapped)))
    def schemas(self):
        return [build_tool_schema(getattr(self, name)) for name in names]
    def reset(self):
        self.world_state = deepcopy(self._init_world_state)
    adapter = type(f"Adapted{original.__name__}", (original,),
                   {**wrapped, "_get_tool_definitions": schemas, "reset_world_state": reset})
    world = adapter()
    tools = {f"{original.__name__}__{name}": getattr(world, name) for name in names}
    return world, tools


def inventory():
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    rows = []
    known = set()
    for key in REGISTRY:
        try:
            world, tools = make_world(key)
            schemas = [build_tool_schema(f) for f in tools.values()]
            json.dumps(schemas, allow_nan=False)
            initial = deepcopy(world.world_state)
            world.world_state["__isolation_probe__"] = {"values": [1]}
            world.reset_world_state()
            if world.world_state != initial or world._init_world_state != initial:
                raise ValueError("Reset isolation failed")
        except Exception as error:
            rows.append({"world": key, "prompt_id": None, "status": "blocked_world",
                         "reason": f"{type(error).__name__}: {error}"})
            continue
        for task in world.prompts:
            pid = task["prompt_id"]
            known.add(pid)
            matches = [r for r in dataset if r["prompt_id"] == pid]
            reasons = []
            if len(matches) != 1 or matches[0]["world"] != key:
                reasons.append("Missing, duplicate, or mismatched dataset record")
            if task.get("setup_functions") or task.get("functions"):
                reasons.append("Setup-dependent task deferred to scenario revamp")
            if key == "web_browsing":
                reasons.append("Local HTML fixtures absent; defer filesystem-backed world to scenario revamp")
            rows.append({"world": key, "prompt_id": pid,
                         "status": "deferred" if reasons else "ready", "reasons": reasons,
                         "tool_count": len(tools), "tool_names": list(tools),
                         "setup": task.get("setup_functions", []),
                         "dataset_prompt_differs": bool(matches and matches[0]["prompt"] != task["prompt"])})
    for record in dataset:
        if record["prompt_id"] not in known:
            rows.append({"world": record["world"], "prompt_id": record["prompt_id"],
                         "status": "dataset_only", "reasons": ["No matching runnable world task"]})
    return rows


def prepare(key, pid):
    world, tools = make_world(key)
    tasks = [t for t in world.prompts if t["prompt_id"] == pid]
    if len(tasks) != 1 or tasks[0].get("setup_functions") or tasks[0].get("functions"):
        raise ValueError("Unknown or setup-dependent task")
    if key == "web_browsing":
        raise ValueError("Filesystem-backed world deferred")
    records = [r for r in json.loads(DATASET_PATH.read_text(encoding="utf-8"))
               if r["prompt_id"] == pid and r["world"] == key]
    if len(records) != 1:
        raise ValueError("Task must have one dataset record")
    return world, tools, tasks[0], records[0]


def run_task(llm, key, pid, *, max_requests=12):
    world, tools, task, record = prepare(key, pid)
    initial = deepcopy(world.world_state)
    agent = Agent(f"core_{key}", llm, system_message=world.function_system_prompt.strip(), tools=tools,
                  state_observer=lambda: world.world_state, max_iterations=max_requests,
                  max_tool_calls=max_requests, timeout_seconds=120)
    agent.run(f"{record['prompt']}\n\nCurrent world state:\n{world.world_state_description.format(world.world_state)}")
    result = {"schema_version": 1, "world": REGISTRY[key], "prompt_id": pid,
              "prompt": record["prompt"], "dataset": "all_worlds_dataset.json",
              "initial_state": initial, "final_state": deepcopy(world.world_state),
              "evaluation": None, "task_success": None, **agent.to_dict()}
    usage = [m["tokens"] for m in result["runtime_metrics"] if m["role"] == "assistant"]
    result["usage_totals"] = {k: sum(u[k] for u in usage) if usage and all(u[k] is not None for u in usage) else None
                              for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return result


class ReferenceScript:
    """Offline execution probe using one existing reference; never sent to live LLMs."""
    provider = "scripted"
    model = "reference_execution_probe"

    def __init__(self, key, pid):
        world, tools, task, record = prepare(key, pid)
        self.calls = []
        self.index = 0
        for source in task["expected_sequences"][0]:
            node = ast.parse(source, mode="eval").body
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                raise ValueError("Reference must contain direct literal calls")
            name = f"{REGISTRY[key]}__{node.func.id}"
            if name not in tools or any(k.arg is None for k in node.keywords):
                raise ValueError("Unsupported reference call")
            args = [ast.literal_eval(a) for a in node.args]
            kwargs = {k.arg: ast.literal_eval(k.value) for k in node.keywords}
            bound = inspect.signature(tools[name]).bind(*args, **kwargs)
            self.calls.append((name, dict(bound.arguments)))

    def chat_completion(self, messages, tools=None):
        if self.index == len(self.calls):
            return {"choices": [{"message": {"content": "Reference probe complete", "tool_calls": []}, "finish_reason": "stop"}]}
        name, args = self.calls[self.index]
        self.index += 1
        return {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": f"ref_{self.index}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]},
            "finish_reason": "tool_calls"}]}


def save(path, data, key=None):
    text = json.dumps(data, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace(key, "[REDACTED]") if key else text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("inventory", "offline", "live"), default="inventory")
    parser.add_argument("--world", action="append", choices=list(PAPER_WORLDS))
    parser.add_argument("--task", action="append")
    parser.add_argument("--model", default="gpt-4.1-nano")
    parser.add_argument("--skip-completed-from", type=Path,
                        help="Reuse completed coverage from a prior batch summary")
    parser.add_argument("--max-requests", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.max_requests <= 20:
        parser.error("max-requests must be between 1 and 20")
    rows = inventory()
    if args.task and set(args.task) - {r["prompt_id"] for r in rows}:
        parser.error("Unknown task selection")
    scope = args.world or PAPER_WORLDS
    selected = [r for r in rows if r["world"] in scope
                and (not args.task or r["prompt_id"] in args.task)]
    if not selected:
        parser.error("Selection has no tasks")
    summary_path = new_run_path("batches", args.mode).with_name("summary.json")
    reused = []
    if args.skip_completed_from:
        previous = json.loads(args.skip_completed_from.read_text(encoding="utf-8"))
        if previous["mode"] != args.mode:
            parser.error("Previous batch must use the same mode")
        selected_ids = {r["prompt_id"] for r in selected}
        reused = [r for r in previous["runs"] if r["status"] == "completed" and r["prompt_id"] in selected_ids]
    summary = {"mode": args.mode, "model": args.model if args.mode == "live" else None,
               "inventory": selected, "runs": [], "reused_runs": reused,
               "scope": list(scope), "missing_paper_world_implementations": MISSING_PAPER_WORLDS,
               "note": "Execution coverage, not task-success or paper metric scores."}
    save(summary_path, summary)
    print(f"Inventory: {dict(Counter(r['status'] for r in selected))}; summary: {summary_path}", flush=True)
    if args.mode == "inventory":
        return 0
    key = None
    if args.mode == "live":
        from dotenv import dotenv_values
        from .openai_llm import OpenAILLM
        key = dotenv_values(ROOT / ".env").get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not key:
            parser.error("Set OPENAI_API_KEY in CORE/.env")
    for row in selected:
        if row["status"] != "ready" or row["prompt_id"] in {r["prompt_id"] for r in reused}:
            continue
        pid, world = row["prompt_id"], row["world"]
        try:
            llm = (OpenAILLM(args.model, api_key=key, base_url="https://api.openai.com/v1", temperature=0,
                            max_output_tokens=512, request_timeout_seconds=30, parallel_tool_calls=False)
                   if key else ReferenceScript(world, pid))
            path = new_run_path(pid, args.model if key else "reference_scripted")
            result = run_task(llm, world, pid, max_requests=args.max_requests)
            result["client_configuration"] = llm.client_info() if key else {"provider": "scripted"}
            save(path, result, key)
            report = result["report"]
            entry = {"prompt_id": pid, "artifact": str(path), "status": report["status"],
                     "stop_reason": report["stop_reason"], "tool_errors": report["tool_errors"],
                     "tool_calls": report["tool_calls"], "usage": result["usage_totals"]}
        except Exception as error:
            entry = {"prompt_id": pid, "status": "blocked", "reason": f"{type(error).__name__}: {error}"}
        summary["runs"].append(entry)
        save(summary_path, summary, key)
        print(json.dumps(entry).replace(key, "[REDACTED]") if key else json.dumps(entry), flush=True)
        if key and entry["status"] in ("blocked", "failed"):
            print("Batch stopped on runner/provider failure; remaining tasks were not attempted.", flush=True)
            break
    summary["counts"] = dict(Counter(r["status"] for r in summary["runs"]))
    save(summary_path, summary, key)
    print(f"Results: {summary['counts']}; {summary_path}", flush=True)
    return int(any(r["status"] != "completed" or r.get("tool_errors", 0) for r in summary["runs"]))


if __name__ == "__main__":
    raise SystemExit(main())

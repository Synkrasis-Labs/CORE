"""Adapters for existing CRUD and Configurations tasks; original methods unchanged."""

from copy import deepcopy
import json

from worlds.crud import CRUD
from worlds.configurations import Configurations
from .agent import Agent
from .core_computations import DATASET_PATH
from .toolset_builder import build_tool_schema


class Adapter:
    def _get_tool_definitions(self):
        return [build_tool_schema(getattr(self, name)) for name in self.tool_names]

    def reset_world_state(self):
        self.world_state = deepcopy(self._init_world_state)


class FunctionCallingCRUD(Adapter, CRUD):
    tool_names = ("add_user", "update_user_email", "delete_user", "list_users", "verify_user_field")


class FunctionCallingConfigurations(Adapter, Configurations):
    tool_names = ("set_config", "print_config", "update_config", "delete_config")


WORLDS = {"crud": (FunctionCallingCRUD, "CRUD"),
          "configurations": (FunctionCallingConfigurations, "Configurations")}
TASKS = ("crud_4", "configurations_4")


def run_world(llm, prompt_id, *, max_iterations=6, max_tool_calls=6, timeout_seconds=90):
    key = prompt_id.rsplit("_", 1)[0]
    if key not in WORLDS:
        raise ValueError("Unsupported world")
    factory, label = WORLDS[key]
    world = factory()
    tasks = [p for p in world.prompts if p["prompt_id"] == prompt_id]
    if len(tasks) != 1:
        raise ValueError("Unknown task")
    if tasks[0].get("setup_functions"):
        raise ValueError("Setup actions are not supported yet; refusing to skip them")
    records = [r for r in json.loads(DATASET_PATH.read_text(encoding="utf-8"))
               if r["prompt_id"] == prompt_id and r["world"] == key]
    if len(records) != 1:
        raise ValueError("Expected one matching dataset task")
    task = records[0]["prompt"]
    initial = deepcopy(world.world_state)
    agent = Agent(name=f"core_{key}", llm=llm,
                  system_message=world.function_system_prompt.strip(),
                  tools={f"{label}__{name}": getattr(world, name) for name in world.tool_names},
                  state_observer=lambda: world.world_state, max_iterations=max_iterations,
                  max_tool_calls=max_tool_calls, timeout_seconds=timeout_seconds)
    agent.run(f"{task}\n\nCurrent world state:\n{world.world_state_description.format(world.world_state)}")
    return {"schema_version": 1, "world": label, "prompt_id": prompt_id, "prompt": task,
            "dataset": "all_worlds_dataset.json", "initial_state": initial,
            "final_state": deepcopy(world.world_state), "evaluation": None, **agent.to_dict()}


def check_stateful(artifact):
    calls = [s for s in artifact["workflow"].values() if s["op_type"] == "TOOL"]
    observations = artifact["state_observations"]
    checks = {"completed": artifact["report"]["status"] == "completed",
              "fresh_state": artifact["initial_state"] == {},
              "no_execution_errors": all(s["status"] == "ok" for s in calls),
              "state_feedback": len(observations) == len(calls) and bool(calls)}
    names = [s["canonical_name"] for s in calls]
    if artifact["prompt_id"] == "crud_4":
        checks["sequence"] = names == ["add_user", "delete_user", "list_users"]
        created = observations[0]["state"].get("Charlie_id", {}) if observations else {}
        checks["created_user"] = created == {"id": "Charlie_id", "name": "Charlie", "age": 40,
                                              "email": "charlie@email.com"}
        checks["deleted_and_listed"] = (len(calls) == 3 and calls[0]["content"] == "Charlie_id"
                                         and calls[1]["content"] is True and calls[2]["content"] == []
                                         and artifact["final_state"] == {})
    elif artifact["prompt_id"] == "configurations_4":
        checks["sequence"] = names == ["set_config", "update_config", "print_config"]
        before = observations[0]["state"].get("timeout", {}) if observations else {}
        after = artifact["final_state"].get("timeout", {})
        checks["created_setting"] = before.get("value") == "30 minutes" and before.get("category") == "security"
        checks["updated_and_printed"] = (after.get("value") == "15 minutes" and after.get("category") == "process"
                                          and len(calls) == 3 and calls[2]["content"] == after)
    else:
        raise ValueError("No integration assertions for this task")
    return checks


class StatefulScript:
    provider = "scripted"
    model = "stateful_feedback_check"

    def __init__(self, task):
        self.task = task
        self.turn = 0

    def chat_completion(self, messages, tools=None):
        self.turn += 1
        replies = [m for m in messages if m["role"] == "tool"]
        if self.turn == 4:
            return {"choices": [{"message": {"content": "Done.", "tool_calls": []}, "finish_reason": "stop"}]}
        if self.task == "crud_4":
            choices = [("CRUD__add_user", {"name": "Charlie", "age": 40, "email": "charlie@email.com"}),
                       ("CRUD__delete_user", {"user_id": replies[0]["content"] if replies else ""}),
                       ("CRUD__list_users", {})]
        else:
            choices = [("Configurations__set_config", {"key": "timeout", "value": "30 minutes", "category": "security"}),
                       ("Configurations__update_config", {"key": "timeout", "new_value": "15 minutes", "category": "process"}),
                       ("Configurations__print_config", {"key": "timeout"})]
        name, args = choices[self.turn - 1]
        return {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": f"call_{self.turn}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]},
            "finish_reason": "tool_calls"}]}

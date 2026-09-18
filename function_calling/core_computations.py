"""Connect CORE's original Computations methods to the FarmAgent-derived loop."""

from copy import deepcopy
import json
from pathlib import Path

from worlds.computations import Computations

from .agent import Agent
from .toolset_builder import build_tool_schema


TOOL_NAMES = (
    "add_numbers", "subtract_numbers", "multiply_numbers", "divide_numbers",
    "power", "calculate_average",
)
DATASET_PATH = Path(__file__).resolve().parents[1] / "all_worlds_dataset.json"


class FunctionCallingComputations(Computations):
    """Inherit tasks and arithmetic unchanged; adapt schemas and reset isolation."""

    def _get_tool_definitions(self):
        return [build_tool_schema(getattr(self, name)) for name in TOOL_NAMES]

    def reset_world_state(self):
        self.world_state = deepcopy(self._init_world_state)


def run_computations(llm, *, prompt_id="computations_1", max_iterations=6,
                     max_tool_calls=6, timeout_seconds=60):
    """Run a fresh task; no oracle information is sent to the model."""
    world = FunctionCallingComputations()
    prompts = {p["prompt_id"]: p for p in world.prompts}
    if prompt_id not in prompts:
        raise ValueError(f"Unknown Computations task: {prompt_id}")
    if prompts[prompt_id].get("setup_functions"):
        raise ValueError("This adapter does not yet support setup actions")
    records = [r for r in json.loads(DATASET_PATH.read_text(encoding="utf-8"))
               if r["prompt_id"] == prompt_id]
    if len(records) != 1 or records[0]["world"] != "computations":
        raise ValueError(f"Expected exactly one Computations dataset entry: {prompt_id}")
    task = records[0]["prompt"]
    initial_state = deepcopy(world.world_state)
    agent = Agent(
        name="core_computations", llm=llm,
        system_message=world.function_system_prompt.strip(),
        tools={f"Computations__{name}": getattr(world, name) for name in TOOL_NAMES},
        max_iterations=max_iterations, max_tool_calls=max_tool_calls,
        timeout_seconds=timeout_seconds, state_observer=lambda: world.world_state,
    )
    # Preserve the old runner's full state visibility, excluding expected paths.
    agent_input = f"{task}\n\nCurrent world state:\n{world.world_state_description.format(world.world_state)}"
    agent.run(agent_input)
    return {
        "schema_version": 1,
        "world": "Computations", "prompt_id": prompt_id, "prompt": task,
        "dataset": "all_worlds_dataset.json",
        "initial_state": initial_state, "final_state": deepcopy(world.world_state),
        "evaluation": None,
        **agent.to_dict(),
    }

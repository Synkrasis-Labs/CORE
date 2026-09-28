"""First CORE-to-ARE vertical slice: the original Computations world."""

from copy import deepcopy
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.app import App
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.tool_utils import OperationType, app_tool
from are.simulation.types import EventRegisterer, event_registered

from function_calling.core_computations import FunctionCallingComputations


class CoreComputationsApp(App):
    """Expose CORE's existing arithmetic methods as ARE tools and state."""

    def __init__(self):
        super().__init__()
        self.world = FunctionCallingComputations()

    def get_state(self) -> dict[str, Any]:
        return deepcopy(self.world.world_state)

    def load_state(self, state_dict: dict[str, Any]) -> None:
        self.world.world_state = deepcopy(state_dict)

    def reset(self) -> None:
        super().reset()
        self.world.reset_world_state()

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def add_numbers(self, a: int, b: int) -> int:
        """Add two integers and save the calculation."""
        return self.world.add_numbers(a, b)

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def subtract_numbers(self, a: int, b: int) -> int:
        """Subtract b from a and save the calculation."""
        return self.world.subtract_numbers(a, b)

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def multiply_numbers(self, a: int, b: int) -> int:
        """Multiply two integers and save the calculation."""
        return self.world.multiply_numbers(a, b)

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def divide_numbers(self, a: int, b: int) -> float | None:
        """Divide a by b and save the calculation."""
        return self.world.divide_numbers(a, b)

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def power(self, base: int, exponent: int) -> int:
        """Raise base to exponent and save the calculation."""
        return self.world.power(base, exponent)

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def calculate_average(self, numbers: list[int]) -> float:
        """Average the numbers and save the calculation."""
        return self.world.calculate_average(numbers)


@register_scenario("core_computations_1")
class CoreComputationsOne(Scenario):
    """ARE scenario for CORE computations_1, including a scripted oracle path."""

    scenario_id = "core_computations_1"
    start_time = 0
    duration = 10

    def init_and_populate_apps(self, *args, **kwargs) -> None:
        self.apps = [AgentUserInterface(), CoreComputationsApp()]

    def build_events_flow(self) -> None:
        aui = self.get_typed_app(AgentUserInterface)
        computations = self.get_typed_app(CoreComputationsApp)
        with EventRegisterer.capture_mode():
            request = aui.send_message_to_agent(
                content="Add 15 and 7, then multiply the result by 3."
            ).depends_on(None, delay_seconds=0)
            addition = computations.add_numbers(a=15, b=7).oracle().depends_on(
                request, delay_seconds=1
            )
            multiplication = computations.multiply_numbers(a=22, b=3).oracle().depends_on(
                addition, delay_seconds=1
            )
        self.events = [request, addition, multiplication]

    def validate(self, env) -> ScenarioValidationResult:
        state = self.get_typed_app(CoreComputationsApp).get_state()
        expected = {"calculations": ["15 + 7 = 22", "22 * 3 = 66"]}
        return ScenarioValidationResult(
            success=state == expected,
            rationale=f"final_state={state}",
        )

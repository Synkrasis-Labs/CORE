"""Stateful migration slice: original CRUD tools and setup-dependent crud_2."""

from copy import deepcopy
from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.app import App
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.tool_utils import OperationType, app_tool
from are.simulation.types import EventRegisterer, event_registered
from worlds.crud import CRUD


class ARECRUDWorld(CRUD):
    def _get_tool_definitions(self):
        # ARE defines schemas below; no legacy llm-tool dependency is needed.
        return []

    def reset_world_state(self):
        self.world_state = deepcopy(self._init_world_state)


class CoreCRUDApp(App):
    def __init__(self):
        super().__init__()
        self.world = ARECRUDWorld()

    def get_state(self) -> dict[str, Any]:
        return deepcopy(self.world.world_state)

    def load_state(self, state_dict: dict[str, Any]) -> None:
        self.world.world_state = deepcopy(state_dict)

    def reset(self) -> None:
        super().reset()
        self.world.reset_world_state()

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def add_user(self, name: str, age: int, email: str | None = None) -> str:
        """Create a user and return the deterministic CORE user ID."""
        return self.world.add_user(name, age, email)

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def update_user_email(self, user_id: str, email: str) -> bool:
        """Update a user's email; return False if the user does not exist."""
        return self.world.update_user_email(user_id, email)

    @app_tool()
    @event_registered(operation_type=OperationType.WRITE)
    def delete_user(self, user_id: str) -> bool:
        """Delete a user; return False if the user does not exist."""
        return self.world.delete_user(user_id)

    @app_tool()
    @event_registered(operation_type=OperationType.READ)
    def list_users(self) -> list[dict[str, Any]]:
        """Show all users as a snapshot at the time of the read."""
        # CORE returns live dict references. Freeze the observation so later
        # writes cannot rewrite an earlier ARE event's returned value.
        return deepcopy(self.world.list_users())

    @app_tool()
    @event_registered(operation_type=OperationType.READ)
    def verify_user_field(self, user_id: str, field: str, expected_value: str) -> bool:
        """Check a user field, using CORE's existing age conversion."""
        return self.world.verify_user_field(user_id, field, expected_value)


@register_scenario('core_crud_2')
class CoreCRUDTwo(Scenario):
    scenario_id = 'core_crud_2'
    start_time = 0
    duration = 10

    def init_and_populate_apps(self, *args, **kwargs):
        self.apps = [AgentUserInterface(), CoreCRUDApp()]

    @property
    def core_task(self):
        return next(p for p in self.get_typed_app(CoreCRUDApp).world.prompts
                    if p['prompt_id'] == 'crud_2')

    def build_events_flow(self):
        app = self.get_typed_app(CoreCRUDApp)
        aui = self.get_typed_app(AgentUserInterface)
        with EventRegisterer.capture_mode():
            # This setup is an ENV action, not part of the agent's scored path.
            setup = app.add_user(name='Alice', age=25).depends_on(None, delay_seconds=0)
            request = aui.send_message_to_agent(content=self.core_task['prompt']).depends_on(
                setup, delay_seconds=1)
            read = app.list_users().oracle().depends_on(request, delay_seconds=1)
            update = app.update_user_email(user_id='Alice_id', email='alice@example.com').oracle().depends_on(
                read, delay_seconds=1)
            verify = app.verify_user_field(user_id='Alice_id', field='email',
                expected_value='alice@example.com').oracle().depends_on(update, delay_seconds=1)
        self.events = [setup, request, read, update, verify]

    def validate(self, env):
        state = self.get_typed_app(CoreCRUDApp).get_state()
        expected = {'Alice_id': {'id': 'Alice_id', 'name': 'Alice', 'age': 25,
                                'email': 'alice@example.com'}}
        return ScenarioValidationResult(success=state == expected, rationale=f'final_state={state}')

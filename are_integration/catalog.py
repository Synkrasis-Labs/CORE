"""Register every source task in Manos's paper scope without rewriting CORE."""

import ast
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache, wraps
import inspect
import json

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.app import App
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.tool_utils import OperationType, app_tool
from are.simulation.types import EventRegisterer
from are.simulation.types import event_registered
from function_calling.core_computations import DATASET_PATH
from function_calling.experiments import PAPER_WORLDS, REGISTRY, make_world
from function_calling.dataset_identity import resolve_record


READ_TOOLS = {
    'automation': {'print_system_status'},
    'communication': {'print_messages'},
    'computations': set(),
    'crud': {'generate_timestamp', 'list_users', 'verify_user_field'},
    'desktop_manager': {'print_application_actions', 'print_application_history', 'print_open_applications'},
    'events_scheduler': {'get_event_time', 'list_events', 'time_until_event'},
    'file_management': {'count_words', 'file_exists', 'get_file_size', 'list_files', 'read_file', 'search_in_file'},
    'legal_compliance': {'check_compliance', 'generate_audit_report'},
    'navigation': {'get_player_position', 'is_within_bounds'},
    'transactions': {'check_balance', 'get_transaction_history'},
    'validation': {'check_password_hash', 'generate_otp', 'hash_password', 'validate_email',
                   'validate_username', 'verify_otp'},
    'web_browsing': {'find_text_in_page', 'get_current_url', 'get_page_source', 'view_browsing_history'},
    'writing': set(),
}


class ScenarioBlocked(ValueError):
    """An explicitly listed source/fixture blocker prevents safe execution."""


def literal_calls(sources, tools):
    """Parse direct literal calls only; never eval references or setup strings."""
    calls = []
    for source in sources:
        node = ast.parse(source, mode='eval').body
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            raise ValueError('Expected a direct literal tool call')
        name = node.func.id
        if name not in tools or any(k.arg is None for k in node.keywords):
            raise ValueError(f'Unknown or unsupported reference tool: {name}')
        args = [ast.literal_eval(a) for a in node.args]
        kwargs = {k.arg: ast.literal_eval(k.value) for k in node.keywords}
        if len(kwargs) != len(node.keywords):
            raise ValueError('Duplicate reference keyword')
        bound = inspect.signature(tools[name]).bind(*args, **kwargs)
        bound.apply_defaults()
        calls.append((name, deepcopy(dict(bound.arguments))))
    return calls


class CatalogApp(App):
    world_key = None

    def __init__(self):
        super().__init__()
        if self.world_key == 'web_browsing':
            raise ScenarioBlocked('Web Browsing requires reviewed local HTML fixtures; tools are blocked.')
        self.world, self.core_tools = make_world(self.world_key)

    def get_state(self):
        return deepcopy(self.world.world_state)

    def load_state(self, state_dict):
        state = deepcopy(state_dict)
        # ARE serializes initial state through JSON. Restore source tuple fields
        # (Navigation coordinates) rather than changing their runtime type.
        for key, initial in self.world._init_world_state.items():
            if isinstance(initial, tuple) and isinstance(state.get(key), list):
                state[key] = tuple(state[key])
        self.world.world_state = state

    def reset(self):
        super().reset()
        self.world.reset_world_state()


@lru_cache(maxsize=None)
def app_class_for(key):
    world, tools = make_world(key)
    methods = {'world_key': key, '__module__': __name__}
    for qualified_name, original in tools.items():
        name = qualified_name.split('__', 1)[1]

        def build_proxy(method_name, prototype):
            @wraps(prototype.__func__)
            def proxy(self, *args, **kwargs):
                # Freeze returns at the event boundary; CORE often returns
                # references to mutable state which later writes would alter.
                return deepcopy(getattr(self.world, method_name)(*args, **kwargs))
            operation = OperationType.READ if method_name in READ_TOOLS[key] else OperationType.WRITE
            return app_tool()(event_registered(operation_type=operation)(proxy))

        methods[name] = build_proxy(name, original)
    cls = type(f'Core{REGISTRY[key]}CatalogApp', (CatalogApp,), methods)
    # Allow ARE import/serialization to resolve generated class names.
    globals()[cls.__name__] = cls
    return cls


@dataclass
class TaskSpec:
    world_key: str
    task: dict
    prompt: str
    dataset_status: str
    setup_calls: list
    reference_calls: list
    reference_error: str | None
    blocked_reason: str | None
    notes: list
    app_class: type
    scenario_class: type | None = None

    @property
    def scenario_id(self):
        return 'core_' + self.task['prompt_id']


class CatalogScenario(Scenario):
    spec = None
    start_time = 0
    duration = 60

    def init_and_populate_apps(self, *args, **kwargs):
        if self.spec.blocked_reason:
            raise ScenarioBlocked(self.spec.blocked_reason)
        self.apps = [AgentUserInterface(), self.spec.app_class()]

    def build_events_flow(self):
        app = self.get_typed_app(self.spec.app_class)
        aui = self.get_typed_app(AgentUserInterface)
        events = []
        previous = None
        with EventRegisterer.capture_mode():
            for name, args in self.spec.setup_calls:
                event = getattr(app, name)(**deepcopy(args)).depends_on(previous, delay_seconds=0)
                events.append(event)
                previous = event
            request = aui.send_message_to_agent(content=self.spec.prompt).depends_on(previous, delay_seconds=0)
            events.append(request)
            previous = request
            for name, args in self.spec.reference_calls:
                event = getattr(app, name)(**deepcopy(args)).oracle().depends_on(previous, delay_seconds=1)
                events.append(event)
                previous = event
        self.events = events

    def validate(self, env):
        # The original references are execution probes, not proven validators.
        # For example Validation/LegalCompliance may never change world state.
        return ScenarioValidationResult(
            success=None,
            rationale='No independent task-success validator; use saved trace parity and legacy CORE scoring. '
                      + (f'Oracle unavailable: {self.spec.reference_error}' if self.spec.reference_error else ''),
        )


@lru_cache(maxsize=1)
def task_catalog():
    records = json.loads(DATASET_PATH.read_text(encoding='utf-8'))
    specs = {}
    for key in PAPER_WORLDS:
        world, qualified_tools = make_world(key)
        tools = {name.split('__', 1)[1]: tool for name, tool in qualified_tools.items()}
        cls = app_class_for(key)
        for source in world.prompts:
            task = deepcopy(source)
            pid = task['prompt_id']
            try:
                matches = [resolve_record(records, key, pid, task['prompt'] if key == 'transactions' else None)]
            except ValueError:
                matches = []
            dataset_status = ('matched_alias' if matches and matches[0]['prompt_id'] != pid else
                              'matched' if len(matches) == 1 else 'missing_or_mismatched')
            prompt = matches[0]['prompt'] if len(matches) == 1 else task['prompt']
            notes = []
            if prompt != task['prompt']:
                notes.append('Source and dataset prompts differ; exact dataset prompt used for scoring compatibility.')
            if dataset_status == 'matched_alias':
                notes.append('Explicit prompt-verified Transactions alias; paper evaluation records the dataset ID.')
            elif dataset_status != 'matched':
                notes.append('Source ID has no exact dataset match; no heuristic join; legacy scoring unavailable.')
            blocked = ('Required page1.html/page2.html/page3.html fixtures are absent; '
                       'filesystem-backed Web Browsing tools are not exposed.' if key == 'web_browsing' else None)
            try:
                setup = literal_calls(task.get('setup_functions', task.get('functions', [])), tools)
            except (SyntaxError, ValueError, TypeError) as error:
                setup = []
                blocked = f'Invalid source setup: {type(error).__name__}: {error}'
            try:
                reference = literal_calls(task['expected_sequences'][0], tools)
                ref_error = None
            except (SyntaxError, ValueError, TypeError, KeyError, IndexError) as error:
                reference = []
                ref_error = f'{type(error).__name__}: {error}'
            spec = TaskSpec(key, task, prompt, dataset_status, setup, reference, ref_error,
                            blocked, notes, cls)
            scenario = type('CoreTask_' + pid, (CatalogScenario,),
                            {'spec': spec, 'scenario_id': spec.scenario_id, '__module__': __name__})
            globals()[scenario.__name__] = scenario
            spec.scenario_class = scenario
            specs[spec.scenario_id] = spec
    return specs


def scenario_bindings():
    """Keep the two reviewed concrete validators; use catalog adapters elsewhere."""
    from .computations import CoreComputationsOne, CoreComputationsApp
    from .crud import CoreCRUDTwo, CoreCRUDApp
    bindings = {sid: (s.scenario_class, s.app_class, REGISTRY[s.world_key],
                      s.task['prompt_id'], s.prompt) for sid, s in task_catalog().items()}
    bindings['core_computations_1'] = (CoreComputationsOne, CoreComputationsApp, 'Computations',
                                      'computations_1', task_catalog()['core_computations_1'].prompt)
    bindings['core_crud_2'] = (CoreCRUDTwo, CoreCRUDApp, 'CRUD', 'crud_2', task_catalog()['core_crud_2'].prompt)
    return bindings


def register_catalog(registry):
    for sid, binding in scenario_bindings().items():
        registry.register(sid)(binding[0])


def inventory_rows():
    return [
        {'scenario_id': s.scenario_id, 'world': s.world_key, 'prompt_id': s.task['prompt_id'],
         'availability': 'blocked' if s.blocked_reason else 'executable',
         'blocked_reason': s.blocked_reason, 'setup_calls': len(s.setup_calls),
         'dataset_status': s.dataset_status, 'reference_error': s.reference_error,
         'source_reference_count': len(s.task.get('expected_sequences', [])),
         'notes': s.notes, 'independent_state_validator': s.scenario_id in {'core_computations_1', 'core_crud_2'}}
        for s in task_catalog().values()
    ]

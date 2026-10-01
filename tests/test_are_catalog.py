"""Full source coverage and runtime parity gates; never make provider calls."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import inspect
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from are.simulation.scenarios.utils.registry import ScenarioRegistry
from are.simulation.tool_utils import AppToolAdapter
from are.simulation.types import EventType
from are_integration.catalog import (task_catalog, scenario_bindings, inventory_rows,
                                    literal_calls, ScenarioBlocked)
from are_integration.registration import register_scenarios
from are_integration.live import BoundedOpenAIEngine, run_live
from are_integration.sweep import run_sweep
from function_calling.experiments import make_world, PAPER_WORLDS


class ARECatalogTests(unittest.TestCase):
    def test_coordinate_schema_survives_are_text_adapter(self):
        spec = task_catalog()['core_navigation_4']
        scenario = spec.scenario_class()
        scenario.initialize()
        app = scenario.get_typed_app(spec.app_class)
        tool = next(t for t in app.get_tools() if t.func_name == 'is_within_bounds')
        description = AppToolAdapter(tool).description
        encoded = description.split('JSON argument schema: ', 1)[1]
        schema, _ = json.JSONDecoder().raw_decode(encoded)
        coordinate = schema['properties']['position']
        self.assertEqual(coordinate['type'], 'array')
        self.assertEqual(coordinate['items']['type'], 'integer')
        self.assertEqual((coordinate['minItems'], coordinate['maxItems']), (2, 2))
        self.assertTrue(app.world.is_within_bounds([2, 0]))
        self.assertFalse(app.world.is_within_bounds([5, 0]))

    def test_every_source_task_is_registered_without_dataset_id_guessing(self):
        source = {'core_' + t['prompt_id'] for key in PAPER_WORLDS
                  for t in make_world(key)[0].prompts}
        catalog = task_catalog()
        registry = ScenarioRegistry()
        register_scenarios(registry)
        self.assertEqual(set(catalog), source)
        self.assertEqual(set(registry._registry), source)
        self.assertEqual(len(catalog), 77)
        self.assertEqual(len({s.world_key for s in catalog.values()}), 13)
        self.assertNotIn('core_transactions_1', catalog)
        self.assertIn('core_transaction_1', catalog)
        self.assertEqual(sum(s.dataset_status != 'matched' for s in catalog.values()), 12)
        self.assertEqual(sum(bool(s.setup_calls) for s in catalog.values()), 8)

    def test_all_executable_scenarios_build_tools_with_source_signatures(self):
        for sid, binding in scenario_bindings().items():
            spec = task_catalog()[sid]
            if spec.blocked_reason:
                continue
            with self.subTest(scenario=sid):
                scenario = binding[0]()
                scenario.initialize()
                tools = scenario.get_typed_app(binding[1]).get_tools()
                self.assertTrue(tools)
                _, source = make_world(spec.world_key)
                for tool in tools:
                    name = tool.func_name
                    self.assertIn(f'{binding[2]}__{name}', source)
                    original = source[f'{binding[2]}__{name}']
                    self.assertEqual([a.name for a in tool.args], list(inspect.signature(original).parameters))
                    # This is the actual ARE agent interface, not only app metadata.
                    AppToolAdapter(tool)
                user_events = [e for e in scenario.events
                               if callable(getattr(e, 'function_name', None))
                               and e.function_name() == 'send_message_to_agent']
                self.assertEqual(len(user_events), 1)
                self.assertEqual(user_events[0].action.args['content'], spec.prompt)
                self.assertNotIn('expected_sequences', spec.prompt)

    def test_blocked_fixtures_never_create_tools_or_provider_requests(self):
        blocked = [s for s in task_catalog().values() if s.blocked_reason]
        self.assertEqual(len(blocked), 6)
        for spec in blocked:
            with self.subTest(scenario=spec.scenario_id):
                with self.assertRaises(ScenarioBlocked):
                    spec.scenario_class().initialize()
                with self.assertRaises(ScenarioBlocked):
                    spec.app_class()
                with TemporaryDirectory() as directory:
                    output = Path(directory) / 'not_created'
                    with self.assertRaises(ScenarioBlocked):
                        run_live(model='unused', api_key='offline-test-key', output_dir=output,
                                 scenario_id=spec.scenario_id)
                    self.assertFalse(output.exists())

    def test_full_reference_sweep_validates_repaired_sources(self):
        result = run_sweep()
        self.assertEqual(result['counts'], {
            'reference_executed': 71, 'blocked': 6})
        for row in result['results']:
            if row.get('checks'):
                with self.subTest(scenario=row['scenario_id']):
                    self.assertTrue(all(row['checks'].values()), row['checks'])
                    self.assertIsNone(row['task_success'])
        rows = {r['scenario_id']: r for r in result['results']}
        self.assertIsNone(rows['core_computations_5']['reference_error'])
        self.assertIsNone(rows['core_validation_2']['reference_error'])
        self.assertEqual(len(rows['core_computations_5']['artifact']['workflow']), 4)
        for i in range(1, 7):
            nav = rows[f'core_navigation_{i}']
            self.assertEqual(nav['tool_errors'], 0)
            self.assertEqual(nav['paper_evaluation']['status'], 'scored')
        self.assertEqual(rows['core_navigation_1']['artifact']['final_state']['player_position'], (2, 0))
        self.assertEqual(rows['core_navigation_4']['artifact']['final_state']['player_position'], (0, 0))
        for i in range(1, 13):
            tx = rows[f'core_transaction_{i}']
            self.assertEqual(tx['probe_status'], 'reference_executed')
            self.assertEqual(tx['evaluation']['status'], 'unscored')
            self.assertEqual(tx['paper_evaluation']['status'], 'scored')
        self.assertTrue(all(r['paper_evaluation']['status']=='scored' for r in result['results'] if r.get('checks')))
        self.assertEqual(result['evaluation_counts'], {'unscored': 37, 'scored': 34})

    def test_literal_parser_rejects_expressions_without_executing_them(self):
        def tool(a=1):
            return a
        for source in ('__import__("os").system("echo unsafe")',
                       'tool(a=1+2)', 'tool(**{})', 'tool(a=1, a=2)',
                       'unknown()', 'tool(a=tool())'):
            with self.subTest(source=source), self.assertRaises((ValueError, SyntaxError)):
                literal_calls([source], {'tool': tool})
        self.assertEqual(literal_calls(['tool()'], {'tool': tool}), [('tool', {'a': 1})])

    def test_reset_snapshots_and_source_types_are_isolated_for_every_world(self):
        for key in PAPER_WORLDS:
            if key == 'web_browsing':
                continue
            spec = next(s for s in task_catalog().values() if s.world_key == key)
            with self.subTest(world=key):
                app, other = spec.app_class(), spec.app_class()
                initial = app.get_state()
                app.world.world_state['__probe__'] = {'values': [1]}
                snapshot = app.get_state()
                snapshot['__probe__']['values'].append(2)
                self.assertEqual(app.get_state()['__probe__']['values'], [1])
                app.reset()
                self.assertEqual(app.get_state(), initial)
                self.assertEqual(other.get_state(), initial)
                app.load_state(json.loads(json.dumps(initial)))
                self.assertEqual(app.get_state(), initial)
                self.assertEqual(app.world._init_world_state, initial)

    def test_setup_is_environment_only_and_read_operations_are_retained(self):
        spec = task_catalog()['core_automation_2']
        scenario = spec.scenario_class()
        scenario.initialize()
        self.assertEqual(scenario.events[0].function_name(), 'unlock_door')
        self.assertEqual(scenario.events[0].event_type, EventType.ENV)
        app = scenario.get_typed_app(spec.app_class)
        kinds = {t.func_name: t.write_operation for t in app.get_tools()}
        self.assertFalse(kinds['print_system_status'])
        self.assertTrue(kinds['activate_alarm'])
        self.assertIsNone(scenario.validate(None).success)

    def test_mocked_are_agent_runs_one_task_per_executable_world(self):
        for key in PAPER_WORLDS:
            if key == 'web_browsing':
                continue
            spec = next(s for s in task_catalog().values() if s.world_key == key)
            if key == 'computations':
                spec = task_catalog()['core_computations_2']
            binding = scenario_bindings()[spec.scenario_id]
            calls = spec.reference_calls
            if key == 'navigation':
                calls = [('get_player_position', {})]  # Valid read; movement defect tested in sweep.
            actions = [(f'{binding[1].__name__}__{name}', args) for name, args in calls]
            actions.append(('AgentUserInterface__send_message_to_user', {'content': 'Offline probe complete.'}))
            pending = iter(actions)
            requests = []

            def completion(**kwargs):
                requests.append(deepcopy(kwargs))
                name, args = next(pending)
                text = 'Thought: Execute.\nAction:\n' + json.dumps({
                    'action': name, 'action_input': args}) + '<end_action>'
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)

            client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion)))
            with self.subTest(world=key), TemporaryDirectory() as directory, \
                 redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                engine = BoundedOpenAIEngine('offline', 'offline-test-key', max_requests=20,
                    max_output_tokens=256, request_timeout=3, client=client)
                summary = run_live(model='offline', api_key='offline-test-key', output_dir=Path(directory),
                    engine=engine, max_requests=20, request_timeout=3, scenario_id=spec.scenario_id)
                self.assertTrue(summary['reply_delivery']['delivered'])
                self.assertEqual(summary['requests_made'], len(actions))
                self.assertEqual(len(summary['artifact']['workflow']), len(calls))
                self.assertEqual([s['canonical_name'] for s in summary['artifact']['workflow'].values()],
                                 [name for name, _ in calls])
                self.assertTrue(all(s['status'] == 'ok' for s in summary['artifact']['workflow'].values()))
                self.assertNotIn('expected_sequences', json.dumps(requests))
                self.assertNotIn('excluded_values', json.dumps(requests))
                if spec.scenario_id not in ('core_computations_1', 'core_crud_2'):
                    self.assertIsNone(summary['are_validation']['success'])


if __name__ == '__main__':
    unittest.main()

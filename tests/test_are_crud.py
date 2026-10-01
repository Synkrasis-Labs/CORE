"""Stateful ARE migration gates; no model or provider requests."""

from copy import deepcopy
import unittest
from are.simulation.environment import Environment, EnvironmentConfig
from are.simulation.types import EventType
from are_integration.crud import CoreCRUDApp, CoreCRUDTwo, ARECRUDWorld
from are_integration.crud_smoke import run_smoke


class ARECRUDTests(unittest.TestCase):
    def test_setup_reads_writes_and_scoring_limitation(self):
        result = run_smoke()
        self.assertTrue(all(result['checks'].values()), result['checks'])
        self.assertEqual(result['artifact']['workflow']['call_1']['tool_args'], {})
        self.assertEqual(result['evaluation']['status'], 'unscored')

    def test_app_parity_snapshots_false_results_and_reset_isolation(self):
        original = ARECRUDWorld()
        app, other = CoreCRUDApp(), CoreCRUDApp()
        env = Environment(config=EnvironmentConfig(verbose=False))
        env.register_apps([app])
        saved_read = None
        try:
            for name, args in [
                ('add_user', {'name': 'Alice', 'age': 25}),
                ('list_users', {}),
                ('verify_user_field', {'user_id': 'Alice_id', 'field': 'age', 'expected_value': '25'}),
                ('update_user_email', {'user_id': 'Alice_id', 'email': 'alice@example.com'}),
                ('verify_user_field', {'user_id': 'Alice_id', 'field': 'email', 'expected_value': 'wrong'}),
                ('delete_user', {'user_id': 'missing'}),
                ('delete_user', {'user_id': 'Alice_id'}),
                ('list_users', {}),
            ]:
                expected = deepcopy(getattr(original, name)(**args))
                actual = getattr(app, name)(**args)
                self.assertEqual(actual, expected)
                self.assertEqual(app.get_state(), original.world_state)
                if name == 'list_users' and saved_read is None:
                    saved_read = deepcopy(actual)
            events = env.event_log.list_view()
            self.assertEqual(len(events), 8)
            self.assertTrue(all(e.event_type == EventType.AGENT and not e.failed() for e in events))
            self.assertEqual(events[1].metadata.return_value, saved_read)
            self.assertIsNone(saved_read[0]['email'])
            self.assertFalse(events[4].metadata.return_value)
            self.assertFalse(events[5].metadata.return_value)
            app.add_user('Bob', 30)
            state = app.get_state()
            state['Bob_id']['age'] = 999
            self.assertEqual(app.get_state()['Bob_id']['age'], 30)
            self.assertEqual(other.get_state(), {})
            app.reset()
            self.assertEqual(app.get_state(), {})
            app.load_state(state)
            state['Bob_id']['age'] = 0
            self.assertEqual(app.get_state()['Bob_id']['age'], 999)
            app.reset()
            self.assertEqual(app.get_state(), {})
        finally:
            env.stop()

    def test_fresh_scenario_rebuilds_setup(self):
        scenario = CoreCRUDTwo()
        scenario.initialize()
        env = Environment(config=EnvironmentConfig(
            oracle_mode=True, queue_based_loop=True, exit_when_no_events=True, verbose=False))
        try:
            env.run(scenario)
            self.assertTrue(scenario.validate(env).success)
        finally:
            env.stop()
        scenario = CoreCRUDTwo()  # ARE initialize() is idempotent; runs use fresh instances.
        scenario.initialize()
        self.assertEqual(scenario.get_typed_app(CoreCRUDApp).get_state(), {})
        self.assertEqual(len(scenario.events), 5)
        self.assertEqual(scenario.events[0].event_type, EventType.ENV)


if __name__ == '__main__':
    unittest.main()

"""Offline ARE CRUD oracle with setup, reads, writes, and legacy scoring report."""

import argparse
import json
from pathlib import Path
from are.simulation.environment import Environment, EnvironmentConfig
from function_calling.evaluation import evaluate_artifact
from .crud import CoreCRUDApp, CoreCRUDTwo
from .trace import core_artifact


def run_smoke():
    scenario = CoreCRUDTwo()
    scenario.initialize()
    env = Environment(config=EnvironmentConfig(
        oracle_mode=True, queue_based_loop=True, exit_when_no_events=True, verbose=False))
    try:
        env.run(scenario)
        app = scenario.get_typed_app(CoreCRUDApp)
        artifact = core_artifact(env.event_log.list_view(), app.get_state(),
                                 world='CRUD', app_class='CoreCRUDApp', prompt_id='crud_2',
                                 prompt=scenario.core_task['prompt'])
        valid = scenario.validate(env).success
    finally:
        env.stop()
    calls = list(artifact['workflow'].values())
    evaluation = evaluate_artifact(artifact)
    checks = {
        'are_state_valid': valid is True,
        'setup_excluded_and_reads_retained': [c['canonical_name'] for c in calls]
            == ['list_users', 'update_user_email', 'verify_user_field'],
        'read_snapshot_before_update': calls[0]['content'] == [
            {'id': 'Alice_id', 'name': 'Alice', 'age': 25, 'email': None}],
        'write_and_verify_results': [c['content'] for c in calls[1:]] == [True, True],
        'all_calls_ok': all(c['status'] == 'ok' for c in calls),
        'legacy_limitation_explicit': evaluation['status'] == 'unscored'
            and any('zero-argument' in issue for issue in evaluation['issues']),
    }
    return {'checks': checks, 'artifact': artifact, 'evaluation': evaluation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Output exists; choose a new filename')
    result = run_smoke()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'checks': result['checks'], 'evaluation': result['evaluation']}, indent=2))
    return 0 if all(result['checks'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())

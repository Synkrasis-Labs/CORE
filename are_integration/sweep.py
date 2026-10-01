"""Inventory or replay all CORE paper tasks in ARE, entirely offline."""

import argparse
from collections import Counter
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime
from importlib import import_module
import json
from pathlib import Path
import random
from unittest.mock import patch

from are.simulation.environment import Environment, EnvironmentConfig
from function_calling.evaluation import evaluate_artifact
from function_calling.experiments import make_world, MISSING_PAPER_WORLDS, REGISTRY
from .catalog import task_catalog, scenario_bindings, inventory_rows
from .trace import core_artifact


class FixtureClock(datetime):
    @classmethod
    def utcnow(cls):
        return cls(2025, 1, 1, 0, 0, 0)


@contextmanager
def reference_context(key):
    """Control only source-world wall time/randomness for offline parity.

    This never patches the live runner or ARE's event clock. Restore Python's
    random state to avoid cross-test contamination.
    """
    module = import_module('worlds.' + key)
    random_state = random.getstate()
    random.seed(0)
    try:
        with (patch.object(module, 'datetime', FixtureClock) if hasattr(module, 'datetime') else nullcontext()):
            yield
    finally:
        random.setstate(random_state)


def execute_original(spec):
    world, _ = make_world(spec.world_key)
    workflow = {}
    for name, args in spec.setup_calls:
        getattr(world, name)(**deepcopy(args))
    initial = deepcopy(world.world_state)
    for i, (name, args) in enumerate(spec.reference_calls, 1):
        try:
            value = deepcopy(getattr(world, name)(**deepcopy(args)))
            status, error = 'ok', None
        except Exception as exc:
            value, status, error = None, 'error', str(exc)
        workflow[f'call_{i}'] = {
            'op_type': 'TOOL', 'tool_name': f'{REGISTRY[spec.world_key]}__{name}',
            'canonical_name': name, 'tool_args': deepcopy(args), 'status': status,
            'execution_started': True, 'content': value, 'error': error,
        }
    return {'schema_version': 1, 'world': REGISTRY[spec.world_key],
            'prompt_id': spec.task['prompt_id'], 'prompt': spec.prompt,
            'initial_state': initial, 'final_state': deepcopy(world.world_state),
            'driver': 'Original CORE reference replay; frozen source clock; no LLM',
            'workflow': workflow}


def run_probe(sid):
    spec = task_catalog()[sid]
    row = next(r for r in inventory_rows() if r['scenario_id'] == sid)
    if spec.blocked_reason:
        return {**row, 'probe_status': 'blocked', 'checks': None}
    if spec.reference_error:
        return {**row, 'probe_status': 'reference_unavailable', 'checks': None}
    binding = scenario_bindings()[sid]
    with reference_context(spec.world_key):
        original = execute_original(spec)
    scenario = binding[0]()
    scenario.initialize()
    env = Environment(config=EnvironmentConfig(
        oracle_mode=True, queue_based_loop=True, exit_when_no_events=True, verbose=False))
    try:
        with reference_context(spec.world_key):
            env.run(scenario)
        app = scenario.get_typed_app(binding[1])
        artifact = core_artifact(env.event_log.list_view(), app.get_state(),
            world=binding[2], app_class=binding[1].__name__, prompt_id=binding[3], prompt=binding[4],
            driver='ARE reference oracle; frozen source clock; no LLM')
        validation = scenario.validate(env)
    finally:
        env.stop()
    fields = ('tool_name', 'canonical_name', 'tool_args', 'status', 'content', 'error')
    source_calls = [{k: s[k] for k in fields} for s in original['workflow'].values()]
    are_calls = [{k: s[k] for k in fields} for s in artifact['workflow'].values()]
    original_evaluation = evaluate_artifact(original)
    evaluation = evaluate_artifact(artifact)
    paper_evaluation = evaluate_artifact(artifact, policy='paper')
    checks = {
        'every_agent_call_retained': len(are_calls) == len(spec.reference_calls),
        'setup_excluded_names_arguments_results_errors': source_calls == are_calls,
        'final_state_parity': original['final_state'] == artifact['final_state'],
        'legacy_evaluation_parity': original_evaluation == evaluation,
    }
    error_count = sum(s['status'] != 'ok' for s in artifact['workflow'].values())
    return {**row, 'probe_status': ('parity_failure' if not all(checks.values()) else
                                 'source_execution_errors' if error_count else 'reference_executed'),
            'checks': checks, 'tool_errors': error_count,
            'task_success': None,
            'are_validation': {'success': validation.success, 'rationale': validation.rationale},
            'original': original, 'artifact': artifact, 'evaluation': evaluation,
            'paper_evaluation': paper_evaluation}


def run_sweep(selected=None):
    selected = list(selected) if selected is not None else list(task_catalog())
    results = []
    for sid in selected:
        try:
            results.append(run_probe(sid))
        except Exception as error:
            results.append({'scenario_id': sid, 'probe_status': 'adapter_error',
                            'error': f'{type(error).__name__}: {error}'})
    return {
        'schema_version': 1, 'mode': 'offline',
        'note': 'Reference execution/parity coverage, not task success or all five paper metrics.',
        'missing_paper_worlds': MISSING_PAPER_WORLDS,
        'counts': dict(Counter(r['probe_status'] for r in results)),
        'evaluation_counts': dict(Counter(r['evaluation']['status'] for r in results if 'evaluation' in r)),
        'results': results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('inventory', 'offline'), default='inventory')
    parser.add_argument('--scenario', action='append', choices=task_catalog())
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Output exists; choose a new filename')
    rows = inventory_rows()
    if args.scenario:
        rows = [r for r in rows if r['scenario_id'] in args.scenario]
    if args.mode == 'offline':
        result = run_sweep(r['scenario_id'] for r in rows)
    else:
        result = {'mode': 'inventory', 'scenarios': rows,
                  'counts': dict(Counter(r['availability'] for r in rows)),
                  'missing_paper_worlds': MISSING_PAPER_WORLDS}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('scenarios', 'results')}, indent=2))
    if args.mode == 'offline':
        problems = [r for r in result['results'] if r['probe_status'] in ('adapter_error', 'parity_failure')]
        if problems:
            print(json.dumps([{'scenario_id': r['scenario_id'], 'checks': r.get('checks'),
                               'error': r.get('error')} for r in problems], indent=2))
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

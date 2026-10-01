"""Offline CORE/ARE Computations parity evidence, including bad paths."""

import argparse
from copy import deepcopy
import json
from pathlib import Path

from are.simulation.environment import Environment, EnvironmentConfig
from function_calling.core_computations import FunctionCallingComputations
from function_calling.evaluation import evaluate_artifact
from .computations import CoreComputationsApp
from .trace import core_artifact

REFERENCE = [('add_numbers', {'a': 15, 'b': 7}),
             ('multiply_numbers', {'a': 22, 'b': 3})]
CASES = {
    'reference': REFERENCE,
    'reversed': list(reversed(REFERENCE)),
    'extra_unmapped': REFERENCE + [('subtract_numbers', {'a': 66, 'b': 1})],
    'failed': REFERENCE + [('add_numbers', {'a': [], 'b': 1})],
    'domain_none': REFERENCE + [('divide_numbers', {'a': 66, 'b': 0})],
}


def run_parity():
    results = {}
    for label, calls in CASES.items():
        original = FunctionCallingComputations()  # Inherits original arithmetic unchanged.
        app = CoreComputationsApp()
        env = Environment(config=EnvironmentConfig(verbose=False))
        env.register_apps([app])
        workflow, snapshots = {}, []
        try:
            for i, (name, args) in enumerate(calls, 1):
                outcomes = []
                for target in (original, app):
                    try:
                        value = deepcopy(getattr(target, name)(**deepcopy(args)))
                        outcomes.append({'status': 'ok', 'content': value, 'error': None})
                    except Exception as error:
                        outcomes.append({'status': 'error', 'content': None, 'error': str(error)})
                workflow[f'call_{i}'] = {
                    'op_type': 'TOOL', 'tool_name': f'Computations__{name}',
                    'canonical_name': name, 'tool_args': deepcopy(args),
                    'execution_started': True, **outcomes[0],
                }
                snapshots.append({'outcomes_match': outcomes[0] == outcomes[1],
                                  'states_match': original.world_state == app.get_state()})
            are = core_artifact(env.event_log.list_view(), app.get_state())
            core = {**are, 'workflow': workflow, 'final_state': deepcopy(original.world_state),
                    'driver': 'Original CORE methods; scripted calls; no LLM'}
        finally:
            env.stop()
        core_eval, are_eval = evaluate_artifact(core), evaluate_artifact(are)
        fields = ('canonical_name', 'tool_name', 'tool_args', 'status', 'content', 'error')
        checks = {
            'every_call_retained': len(are['workflow']) == len(calls),
            'calls_match': [{k: s[k] for k in fields} for s in workflow.values()]
                == [{k: s[k] for k in fields} for s in are['workflow'].values()],
            'intermediate_results_and_state': all(all(s.values()) for s in snapshots),
            'final_state': core['final_state'] == are['final_state'],
            'evaluation': core_eval == are_eval,
        }
        results[label] = {'checks': checks, 'core': core, 'are': are,
                          'evaluation': are_eval}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Output exists; choose a new filename')
    results = run_parity()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps({k: {'checks': v['checks'], 'status': v['evaluation']['status'],
                          'score': v['evaluation']['score']} for k, v in results.items()}, indent=2))
    return 0 if all(all(v['checks'].values()) for v in results.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Opt-in live migration validation; no requests on import or --help.

Smoke runs are reused in the full ARE batch. Both drivers use GPT-5 nano,
six model requests, no output-token cap, 30-second request timeouts, and no
SDK retries. Their prompts, state observations, and tool interfaces differ;
this is a matched-budget comparison, not an interface-only ablation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ('core_computations_1', 'core_crud_3', 'core_navigation_4', 'core_transaction_7')
BASELINE = ROOT / 'runs/batches/2026-09-18_230912_247245Z_live/summary.json'


def read_key(path):
    from dotenv import dotenv_values
    value = dotenv_values(path).get('OPENAI_API_KEY')
    if not value:
        raise ValueError('Selected environment file has no OPENAI_API_KEY')
    return value


def save(path, data, key):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, default=str).replace(key, '[REDACTED]'))
    temporary.replace(path)


def worker(driver, sid, output, key):
    from are_integration.catalog import task_catalog
    spec = task_catalog()[sid]
    if spec.blocked_reason:
        raise ValueError(spec.blocked_reason)
    if driver == 'are':
        from are_integration.live import run_live
        run_live(model='gpt-5-nano', api_key=key, output_dir=output,
                 scenario_id=sid, max_requests=6, max_output_tokens=None, request_timeout=30)
        return
    from function_calling.experiments import prepare, REGISTRY
    from function_calling.agent import Agent
    from function_calling.openai_llm import OpenAILLM
    from function_calling.evaluation import evaluate_artifact
    world, tools, task, record = prepare(spec.world_key, spec.task['prompt_id'])
    llm = OpenAILLM('gpt-5-nano', temperature=None, api_key=key,
                    base_url='https://api.openai.com/v1', max_output_tokens=None,
                    request_timeout_seconds=30, parallel_tool_calls=False)
    initial = deepcopy(world.world_state)
    agent = Agent(f'core_{spec.world_key}', llm, system_message=world.function_system_prompt.strip(),
                  tools=tools, state_observer=lambda: world.world_state,
                  max_iterations=6, max_tool_calls=6, timeout_seconds=210)
    agent.run(f"{record['prompt']}\n\nCurrent world state:\n{world.world_state_description.format(world.world_state)}")
    artifact = {'schema_version': 1, 'world': REGISTRY[spec.world_key],
                'prompt_id': task['prompt_id'], 'prompt': record['prompt'],
                'dataset': 'all_worlds_dataset.json', 'initial_state': initial,
                'final_state': deepcopy(world.world_state), 'task_success': None,
                'client_configuration': llm.client_info(), **agent.to_dict()}
    usage = [m['tokens'] for m in artifact['runtime_metrics'] if m['role'] == 'assistant']
    artifact['usage_totals'] = {k: sum(u[k] or 0 for u in usage)
                              for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    artifact['evaluation'] = evaluate_artifact(artifact)
    artifact['paper_evaluation'] = evaluate_artifact(artifact, policy='paper')
    save(output / 'run.json', artifact, key)


def execute(driver, sid, batch, key_file, key):
    directory = batch / driver / sid
    run_path = directory / 'artifacts/run.json'
    if not run_path.exists():
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'worker.log').open('w') as log:
            try:
                process = subprocess.run([sys.executable, '-m', 'are_integration.validation_batch',
                    '--worker', driver, '--scenario', sid, '--output-dir', str(directory / 'artifacts'),
                    '--key-file', str(key_file)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                    timeout=260)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = 'timeout'
        log_path = directory / 'worker.log'
        log_path.write_text(log_path.read_text(errors='replace').replace(key, '[REDACTED]'))
        if not run_path.exists():
            return {'scenario_id': sid, 'status': 'worker_error', 'exit_code': code,
                    'error': 'No saved artifact; inspect worker.log'}
    saved = json.loads(run_path.read_text())
    from .validation_report import PROVIDER_ERRORS
    if driver == 'are':
        artifact = saved['artifact']
        calls = list(artifact['workflow'].values())
        entry = {'requests_made': saved['requests_made'],
                 'provider_errors': sum(l.get('error') in PROVIDER_ERRORS
                                        for l in saved['agent_logs'] if l['log_type'] == 'error'),
                 'model_reply_delivered': saved['reply_delivery']['model_reply_delivered'],
                 'automatic_stop_delivered': saved['reply_delivery']['automatic_stop_delivered'],
                 'exception': saved['are_validation']['exception'],
                 'are_validation': saved['are_validation'],
                 'request_budget_exhausted': saved['request_budget_exhausted'],
                 'tokens': {f: sum(u.get(f) or 0 for u in saved['usage']) for f in
                           ('prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens')},
                 'protocol_version': saved['agent_protocol_version']}
    else:
        artifact = saved
        calls = [s for s in artifact['workflow'].values() if s['op_type'] == 'TOOL']
        entry = {'requests_made': saved['report']['llm_calls'],
                 'provider_errors': int(bool(saved['report']['error'] and
                                            saved['report']['error']['type'] in PROVIDER_ERRORS)),
                 'model_reply_delivered': saved['report']['stop_reason'] == 'final_response',
                 'automatic_stop_delivered': False, 'exception': saved['report']['error'],
                 'stop_reason': saved['report']['stop_reason'], 'tokens': saved['usage_totals']}
    return {'scenario_id': sid, 'prompt_id': artifact['prompt_id'], 'status': 'recorded',
            'run_json': str(run_path), 'world_tool_calls': len(calls),
            'world_tool_errors': sum(s['status'] != 'ok' for s in calls),
            'evaluation': saved['evaluation'], 'paper_evaluation': saved['paper_evaluation'], **entry}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('smoke', 'full'), default='smoke')
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--key-file', required=True, type=Path)
    parser.add_argument('--worker', choices=('are', 'native'))
    parser.add_argument('--scenario')
    args = parser.parse_args()
    key = read_key(args.key_file)
    if args.worker:
        try:
            worker(args.worker, args.scenario, args.output_dir, key)
            return 0
        except Exception as error:
            save(args.output_dir / 'worker_error.json', {'error': f'{type(error).__name__}: {error}'}, key)
            return 1
    from are_integration.catalog import task_catalog
    specs = task_catalog()
    batch = args.output_dir.resolve()
    batch.mkdir(parents=True, exist_ok=True)
    metadata_path = batch / 'configuration.json'
    configuration = {'model': 'gpt-5-nano', 'model_requests': 6, 'max_output_tokens': None,
                     'request_timeout_seconds': 30, 'sdk_retries': 0, 'worker_timeout_seconds': 260,
                     'parallel_workers': 3, 'native_max_tool_calls': 6,
                     'native_episode_timeout_seconds': 210,
                     'code_revision': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                     'note': 'Same model and request/output budgets; driver prompts, state exposure and interfaces differ. Scores are not independent task-success checks.'}
    if metadata_path.exists() and json.loads(metadata_path.read_text()) != configuration:
        parser.error('Existing batch settings differ; choose a new output directory')
    save(metadata_path, configuration, key)
    if args.stage == 'smoke':
        selections = [('are', sid) for sid in SMOKE]
    else:
        smoke_path = batch / 'smoke_summary.json'
        if not smoke_path.exists():
            parser.error('Run and inspect the smoke stage first')
        smoke = json.loads(smoke_path.read_text())['runs']
        if any(r['status'] != 'recorded' or r.get('exception') or r.get('world_tool_errors')
               or r.get('provider_errors') for r in smoke):
            parser.error('Smoke has runner/provider/tool errors; investigate before full stage')
        old = json.loads(BASELINE.read_text())
        shared_ids = {r['prompt_id'] for r in old['runs'] + old.get('reused_runs', [])}
        shared = sorted(sid for sid,spec in specs.items() if spec.task['prompt_id'] in shared_ids)
        if len(shared) != 51:
            parser.error('Expected exactly 51 shared baseline tasks')
        selections = [('are', sid) for sid,spec in specs.items() if not spec.blocked_reason]
        selections += [('native', sid) for sid in shared]
    rows = []
    def checkpoint():
        save(batch / (args.stage + '_summary.json'), {'configuration': configuration,
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'runs': rows, 'expected_runs': len(selections),
            'blocked': [{'scenario_id': sid, 'reason': s.blocked_reason} for sid,s in specs.items() if s.blocked_reason]}, key)
    checkpoint()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(execute, driver, sid, batch, args.key_file, key): (driver,sid)
                   for driver,sid in selections}
        for future in as_completed(futures):
            driver,sid = futures[future]
            try:
                entry = {'driver': driver, **future.result()}
            except Exception as error:
                entry = {'driver': driver, 'scenario_id': sid, 'status': 'worker_error',
                         'error': f'{type(error).__name__}: {error}'}
            rows.append(entry)
            checkpoint()
            print(json.dumps({k:entry.get(k) for k in ('driver','scenario_id','status','model_reply_delivered','world_tool_calls','world_tool_errors','exception')}).replace(key,'[REDACTED]'), flush=True)
    print(f'Summary: {batch / (args.stage + "_summary.json")}', flush=True)
    return int(any(r['status'] != 'recorded' or r.get('exception') for r in rows))

if __name__ == '__main__':
    raise SystemExit(main())

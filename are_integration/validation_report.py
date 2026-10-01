"""Summarize a live validation batch without publishing raw traces or secrets."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import mean

METRICS = ('path_correctness', 'pc_ktc', 'prefix_criticality', 'harmful_call_rate', 'efficiency')
PROVIDER_ERRORS = {'APITimeoutError', 'APIConnectionError', 'RateLimitError',
                   'AuthenticationError', 'PermissionDeniedError', 'NotFoundError',
                   'BadRequestError', 'InternalServerError', 'APIError'}


def aggregate(rows):
    scored = [r['paper_evaluation'] for r in rows
              if r.get('paper_evaluation', {}).get('status') == 'scored']
    values = {k: [s['metrics'][k] for s in scored if s['metrics'][k] is not None] for k in METRICS}
    return {'episodes': len(rows), 'status_counts': dict(Counter(r['status'] for r in rows)),
            'model_replies': sum(bool(r.get('model_reply_delivered')) for r in rows),
            'automatic_stops': sum(bool(r.get('automatic_stop_delivered')) for r in rows),
            'exceptions': sum(bool(r.get('exception')) for r in rows),
            'provider_errors': sum(r.get('provider_errors', 0) for r in rows),
            'agent_error_counts': dict(sum((Counter(r.get('agent_error_counts', {})) for r in rows), Counter())),
            'world_tool_calls': sum(r.get('world_tool_calls', 0) for r in rows),
            'world_tool_errors': sum(r.get('world_tool_errors', 0) for r in rows),
            'model_requests': sum(r.get('requests_made', 0) for r in rows),
            'tokens': {k: sum(r.get('tokens', {}).get(k) or 0 for r in rows)
                      for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
            'paper_scored': len(scored),
            'paper_means': {k: mean(v) if v else None for k,v in values.items()},
            'defined_counts': {k: len(v) for k,v in values.items()},
            'path_score_1_count': sum(s['score'] == 1 for s in scored),
            'dfa_accepting_count': sum(bool(s['dfa_accepting']) for s in scored)}


def report(source):
    summary = json.loads(source.read_text())
    rows = summary['runs']
    # ARE can handle provider/format exceptions inside the agent without
    # setting the scenario runner's exception field. Inspect those logs too.
    for row in rows:
        if not row.get('run_json'):
            continue
        saved = json.loads(Path(row['run_json']).read_text())
        if row['driver'] == 'are':
            errors = Counter(l.get('error') or 'unknown' for l in saved.get('agent_logs', [])
                             if l['log_type'] == 'error')
            row['agent_error_counts'] = dict(errors)
            row['provider_errors'] = sum(count for name,count in errors.items() if name in PROVIDER_ERRORS)
        else:
            error = saved['report']['error']
            row['agent_error_counts'] = {error['type']: 1} if error else {}
            row['provider_errors'] = int(bool(error and error['type'] in PROVIDER_ERRORS))
    by_driver = {driver: [r for r in rows if r['driver'] == driver] for driver in ('are','native')}
    shared = set(r['scenario_id'] for r in by_driver['are']) & set(r['scenario_id'] for r in by_driver['native'])
    per_task = []
    for r in rows:
        compact = {k:v for k,v in r.items() if k not in ('run_json','evaluation','paper_evaluation','are_validation')}
        p = r.get('paper_evaluation', {})
        compact['paper_evaluation'] = {k:p.get(k) for k in ('status','metric','score','metrics','dataset_prompt_id','dataset_repairs','dfa_accepting')}
        per_task.append(compact)
    manifest_path = source.parent / 'source_manifest.json'
    return {'configuration': summary['configuration'],
            'runtime_source_hashes': json.loads(manifest_path.read_text()) if manifest_path.exists() else None,
            'are_protocol_versions': sorted({r['protocol_version'] for r in rows if r.get('protocol_version')}),
            'complete': len(rows) == summary['expected_runs'] and all(r['status']=='recorded' for r in rows),
            'note': 'Single live runs; matched model and request/output budgets. Driver prompts, state exposure, and tool interfaces differ. DFA acceptance and metric scores are not independent task-success validation.',
            'blocked': summary['blocked'],
            'all_are': aggregate(by_driver['are']),
            'shared_scenario_count': len(shared),
            'shared_are': aggregate([r for r in by_driver['are'] if r['scenario_id'] in shared]),
            'shared_native': aggregate([r for r in by_driver['native'] if r['scenario_id'] in shared]),
            'results': sorted(per_task, key=lambda r:(r['driver'],r['scenario_id']))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new output file')
    result = report(args.source)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
    return int(not result['complete'])

if __name__ == '__main__':
    raise SystemExit(main())

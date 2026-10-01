"""Evaluate saved ARE or shared-runner batches offline without changing evidence."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import mean

from function_calling.evaluation import evaluate_artifact

ROOT = Path(__file__).resolve().parents[1]


def rescore_batch(source):
    summary = json.loads(source.read_text())
    entries = summary.get('reused_runs', []) + summary['runs']
    results = []
    seen = set()
    for entry in entries:
        value = entry.get('run_json') or entry.get('artifact')
        if value is None:
            results.append({'prompt_id': entry.get('prompt_id'), 'status': 'blocked',
                            'reason': entry.get('blocked_reason') or entry.get('reason')})
            continue
        path = Path(value.replace('\\', '/'))
        path = path if path.is_absolute() else ROOT / path
        if path in seen:
            continue
        seen.add(path)
        saved = json.loads(path.read_text())
        artifact = saved.get('artifact', saved)
        results.append({'prompt_id': artifact['prompt_id'], 'source_run': str(path),
                        'legacy_evaluation': evaluate_artifact(artifact),
                        'paper_evaluation': evaluate_artifact(artifact, policy='paper')})
    scored = [r['paper_evaluation'] for r in results if r.get('paper_evaluation', {}).get('status') == 'scored']
    metric_names = ('path_correctness', 'pc_ktc', 'prefix_criticality', 'harmful_call_rate', 'efficiency')
    defined = {k: [r['metrics'][k] for r in scored if r['metrics'][k] is not None] for k in metric_names}
    return {'schema_version': 1, 'source_summary': str(source.resolve()),
            'note': 'Offline revised metrics; original runs and historical scores unchanged. Not a new experiment.',
            'counts': dict(Counter(r.get('paper_evaluation', {}).get('status', r.get('status')) for r in results)),
            'means': {k: mean(values) if values else None for k, values in defined.items()},
            'defined_counts': {k: len(values) for k, values in defined.items()},
            'score_1_count': sum(r['score'] == 1 for r in scored), 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; choose a new file')
    result = rescore_batch(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k!='results'}, indent=2))
    return int(any(r.get('paper_evaluation', {}).get('status')=='unscored' for r in result['results']))

if __name__ == '__main__':raise SystemExit(main())

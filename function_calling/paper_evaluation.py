"""Versioned CORE Section 3 metrics, independent of the historical scorer.

Reference: arXiv:2509.20998v1, user-specified 2509.20998v1 (2).pdf,
equations 3–8. Exact PDF provenance is recorded in docs/ARE_REPAIRS.md.
The dataset DFA controls condensation and harm; runtime failures never advance
it. That conservative runtime-error policy and unknown-pattern totalization
are explicit adapter policies, not additional claims from the paper.
"""
from collections import defaultdict, deque
from copy import deepcopy
import json
import math

from core import LD
from worlds import _MODULES
from .core_computations import DATASET_PATH
from .dataset_identity import resolve_record
from .dataset_repairs import repaired_record

VERSION = 'core-paper-v1.1'


def argument_matches(value, pattern):
    expected = pattern['value']
    if expected is not None:
        # Python equates True with 1; a boolean is not a numeric tool value.
        if isinstance(value, bool) != isinstance(expected, bool):
            return False
        return value == expected
    excluded = pattern.get('excluded_values')
    return excluded is None or value not in excluded


def map_call(name, arguments, alphabet):
    """Match all constraints, including empty signatures and exclusions.

    None without exclusions is the dataset's unconstrained parameter pattern,
    as used for arbitrary filenames/accounts. Specific matches precede generic
    patterns. Missing required/exclusion-constrained arguments never match.
    """
    if not isinstance(arguments, dict):
        return None
    matches = []
    for symbol, call in alphabet.items():
        if call['name'] != name:
            continue
        patterns = call['arguments']
        if not patterns and arguments:
            continue
        valid = True
        for key, pattern in patterns.items():
            if key not in arguments:
                if pattern['value'] is not None or pattern.get('excluded_values') is not None:
                    valid = False
                    break
            elif not argument_matches(arguments[key], pattern):
                valid = False
                break
        if valid:
            specificity = sum(p['value'] is not None for p in patterns.values())
            specificity += sum(p.get('excluded_values') is not None for p in patterns.values()) / (len(patterns)+1)
            matches.append((specificity, symbol))
    if not matches:
        return None
    best = max(m[0] for m in matches)
    winners = [symbol for weight, symbol in matches if weight == best]
    if len(winners) != 1:
        raise ValueError(f'Ambiguous dataset patterns for {name}: {winners}')
    return winners[0]


def compile_dfa(record):
    nodes = record['nodes']
    if not nodes or len({n['name'] for n in nodes}) != len(nodes):
        raise ValueError('DFA needs uniquely named states')
    names = {n['name'] for n in nodes}
    finals = {n['name'] for n in nodes if n.get('is_final', False)}
    transitions = {n['name']: {} for n in nodes}
    for node in nodes:
        for edge in node.get('transitions', []):
            if edge['from'] != node['name'] or edge['to'] not in names:
                raise ValueError('Invalid DFA edge')
            for symbol in edge['symbols']:
                if symbol not in record['alphabet']:
                    raise ValueError('DFA edge absent from alphabet')
                prior = transitions[node['name']].get(symbol)
                if prior is not None and prior != edge['to']:
                    raise ValueError('Non-deterministic DFA')
                transitions[node['name']][symbol] = edge['to']
    gold = []
    def walk(state, path, visited):
        if state in finals:
            gold.append(path)
            if len(gold) > 10000:
                raise ValueError('Golden-path count exceeds explicit evaluation bound')
        for symbol, target in transitions[state].items():
            if target not in visited:
                walk(target, [*path, symbol], visited | {target})
    start = nodes[0]['name']
    walk(start, [], {start})
    if not gold:
        raise ValueError('DFA has no loop-free accepting path')
    return start, finals, transitions, gold


def path_similarity(predicted, gold):
    distance = LD(predicted, gold)
    denominator = len(predicted) + len(gold) + distance
    return 1 - 2*distance/denominator if denominator else 1.0


def order_similarity(predicted, gold):
    # Match repeated symbols by occurrence order; do not count the same golden
    # occurrence twice. This reduces to ordinary ranks for distinct tokens.
    ranks = defaultdict(deque)
    for i, token in enumerate(gold):
        ranks[token].append(i)
    matched = [ranks[token].popleft() for token in predicted if ranks[token]]
    n = len(matched)
    if n < 2:
        return 0.5
    concordant = sum(matched[i] < matched[j] for i in range(n) for j in range(i+1, n))
    return concordant / (n*(n-1)/2)


def evaluate_paper(artifact, dataset=None, *, beta=0.5, lambda_=0.5):
    if not 0 < beta < 1 or not 0 <= lambda_ <= 1:
        raise ValueError('Require 0 < beta < 1 and 0 <= lambda <= 1')
    result = {'status': 'unscored', 'metric': VERSION, 'score': None,
              'metrics': None, 'issues': [], 'actions': [],
              'parameters': {'beta': beta, 'lambda': lambda_},
              'policies': {'runtime_failures': 'retained as harmful; DFA state unchanged',
                           'unmatched_patterns': 'retained as distinct harmful tokens',
                           'empty_prefix': 'prefix criticality 1 when no retained actions',
                           'duplicate_order_tokens': 'match occurrences in order',
                           'scope': 'world tool attempts; reply protocol measured separately'},
              'note': 'Revised paper-formula evaluation; separate from historical legacy scores and task success.'}
    try:
        key = _MODULES.get(artifact.get('world'))
        if artifact.get('schema_version') != 1 or key is None:
            raise ValueError('Expected a schema-v1 artifact with a registered CORE world')
        if not isinstance(artifact.get('prompt'), str):
            raise ValueError('Missing task prompt')
        records = dataset if dataset is not None else json.loads(DATASET_PATH.read_text(encoding='utf-8'))
        record = resolve_record(records, key, artifact.get('prompt_id'), artifact.get('prompt'))
        result['dataset_prompt_id'] = record['prompt_id']
        record, repairs = repaired_record(record)
        result['dataset_repairs'] = repairs
        start, finals, transitions, gold = compile_dfa(record)
        workflow = artifact.get('workflow')
        if not isinstance(workflow, dict):
            raise ValueError('Missing structured workflow')
        state = start
        condensed, harm = [], []
        for step_id, step in workflow.items():
            if step.get('op_type') != 'TOOL':
                continue
            name = step.get('canonical_name')
            if not isinstance(name, str) or step.get('tool_name') != f"{artifact['world']}__{name}":
                raise ValueError(f'{step_id}: unknown or inconsistent tool identity')
            args = step.get('tool_args')
            symbol = map_call(name, args, record['alphabet'])
            successful = step.get('status') == 'ok' and step.get('execution_started') is True
            target = transitions[state].get(symbol) if successful else None
            harmful = target is None
            # An execution error must be a mismatch even if its intended symbol
            # happens to occur in a golden path.
            token = symbol if successful and symbol is not None else '__invalid__:' + json.dumps(
                [name, args, step.get('status')], sort_keys=True, default=str)
            if symbol is None and successful:
                token = '__unmapped__:' + json.dumps([name, args], sort_keys=True, default=str)
            loop = not harmful and target == state
            action = {'step': step_id, 'name': name, 'arguments': deepcopy(args),
                      'status': step.get('status'), 'symbol': symbol,
                      'token': token, 'state_before': state, 'state_after': state if harmful else target,
                      'harmful': harmful, 'condensed_out': loop}
            result['actions'].append(action)
            if not loop:
                condensed.append(token)
                harm.append(int(harmful))
            if not harmful:
                state = target
        count = len(harm)
        raw_count = len(result['actions'])
        scores = [path_similarity(condensed, g) for g in gold]
        composite = [lambda_*pc + (1-lambda_)*order_similarity(condensed, g)
                     for pc, g in zip(scores, gold)]
        eligible = [len(g) for g in gold if len(g) <= raw_count]
        efficiency = max(eligible)/raw_count if eligible and raw_count else None
        prefix = 1-(1-beta)/(1-beta**count)*sum(h*beta**i for i,h in enumerate(harm)) if count else 1.0
        metrics = {'path_correctness': max(scores), 'pc_ktc': max(composite),
                   'prefix_criticality': max(0.0, min(1.0, prefix)),
                   'harmful_call_rate': sum(harm)/count if count else 0.0,
                   'harmful_call_count': sum(harm), 'efficiency': efficiency}
        if any(not math.isfinite(v) for v in metrics.values() if v is not None):
            raise ValueError('Non-finite metric')
        result.update(status='scored', score=metrics['path_correctness'], metrics=metrics,
                      sequence=condensed, harm_mask=harm, golden_paths=gold,
                      raw_length=raw_count, condensed_length=count,
                      dfa_final_state=state, dfa_accepting=state in finals)
    except (ValueError, KeyError, TypeError, IndexError, AssertionError) as error:
        result['issues'].append(str(error))
    return result

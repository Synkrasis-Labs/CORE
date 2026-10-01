"""Keep attempted actions and actual user replies separate from world scoring."""

from copy import deepcopy
import json
import re
from are.simulation.types import EventType


def tool_attempts(logs, events):
    """Link parsed attempts to events without hiding pre-registration rejections.

    An absent event is not proof that a call never started; ARE can reject a
    signature/type before registration. Preserve that uncertainty explicitly.
    """
    attempts = []
    completed = False
    for log in logs:
        if log['log_type'] == 'tool_call':
            attempts.append({
                'tool_name': log['tool_name'],
                'requested_args': deepcopy(log['tool_arguments']),
                'status': 'not_observed', 'are_event_id': None, 'error': None,
            })
            completed = False
        elif log['log_type'] == 'observation':
            completed = True
        elif log['log_type'] == 'error' and attempts and not completed:
            attempts[-1]['error'] = log['exception'] or log['error']

    remaining = [e for e in events if e.event_type == EventType.AGENT]
    for attempt in attempts:
        args = attempt['requested_args']
        for event in remaining:
            event_args = {k: v for k, v in event.get_args().items() if k != 'self'}
            # A rejected attempt must not borrow a later successful event with
            # similar arguments (e.g. a missing argument supplied on retry).
            if (attempt['tool_name'] == f'{event.app_class_name()}__{event.function_name()}'
                    and (not attempt['error'] or event.failed())
                    and isinstance(args, dict)
                    and all(k in event_args and event_args[k] == v for k, v in args.items())):
                attempt.update(status='error' if event.failed() else 'ok',
                               are_event_id=event.event_id,
                               error=event.metadata.exception or attempt['error'])
                remaining.remove(event)
                break
    return attempts


def reply_delivery(messages, attempts, logs=None):
    replies = [deepcopy(m) for m in messages if m['sender'] == 'Agent']
    reply_attempts = [deepcopy(a) for a in attempts
                      if a['tool_name'] == 'AgentUserInterface__send_message_to_user']
    generated = []
    for log in logs or []:
        if log['log_type'] != 'llm_output':
            continue
        match = re.search(r'Action:\s*', log['content'])
        if match:
            try:
                action, _ = json.JSONDecoder().raw_decode(log['content'][match.end():])
            except (ValueError, TypeError):
                continue
            if isinstance(action, dict) and action.get('action') == 'AgentUserInterface__send_message_to_user':
                generated.append(action.get('action_input'))
    return {
        'delivered': bool(replies),
        'model_reply_delivered': (any(a['status'] == 'ok' and a['requested_args'] in generated
                                     for a in reply_attempts) if logs is not None else None),
        'automatic_stop_delivered': any(re.fullmatch(r'Max iterations \(\d+\) reached\. Stopping\.',
                                                    str(m['content'])) for m in replies),
        'messages': replies,
        'attempts': reply_attempts,
        'note': 'Delivery is observed in ARE user-interface state; reply correctness is not evaluated.',
    }

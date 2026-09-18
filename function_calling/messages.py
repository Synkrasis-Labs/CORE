"""FarmAgent conversation/usage handling, adapted to plain JSON messages."""

from copy import deepcopy
import json


def value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def assistant_message(message):
    result = {"role": "assistant", "content": value(message, "content")}
    calls = value(message, "tool_calls") or []
    if calls:
        result["tool_calls"] = [
            {"id": value(call, "id"), "type": value(call, "type", "function"),
             "function": {"name": value(value(call, "function"), "name"),
                          "arguments": value(value(call, "function"), "arguments")}}
            for call in calls
        ]
    return result


class Messages:
    def __init__(self, provider="unknown", system_message=None):
        self.provider = provider
        self.messages = []
        self.runtime_metrics = []
        if system_message:
            self.messages.append({"role": "system", "content": system_message})

    def user_input(self, text):
        self.messages.append({"role": "user", "content": text})

    def system_notify(self, text):
        self.user_input(text)

    def llm_response(self, response, elapsed_time, message):
        self.messages.append(deepcopy(message))
        usage = value(response, "usage")
        details = value(usage, "prompt_tokens_details")
        # Missing metadata is unknown, not fabricated zero usage.
        tokens = {key: value(usage, key) for key in
                  ("prompt_tokens", "completion_tokens", "total_tokens")}
        tokens["cached_tokens"] = value(details, "cached_tokens")
        self.runtime_metrics.append({"role": "assistant", "time": elapsed_time, "tokens": tokens})

    def tool_call_response(self, response, call_id, elapsed_time):
        content = response if isinstance(response, str) else json.dumps(response, allow_nan=False)
        self.messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
        self.runtime_metrics.append({"role": "tool", "tool_call_id": call_id, "time": elapsed_time})

    def __call__(self):
        return deepcopy(self.messages)

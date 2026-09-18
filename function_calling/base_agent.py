"""Adapted from FarmAgent rsare/agents/agent/base_agent.py."""

import time
from copy import deepcopy

from .messages import Messages, assistant_message, value
from .time_manager import TimeManager
from .workflow import Workflow


class BaseAgent:
    def __init__(self, name, llm, system_message="", messages=None):
        self.name = name
        self.llm = llm
        self.system_message = system_message
        self.time_manager = TimeManager()
        self._initial_messages = deepcopy(messages.messages) if messages is not None else []
        if system_message:
            existing = [m for m in self._initial_messages if m.get("role") == "system"]
            if existing and (len(existing) != 1 or existing[0].get("content") != system_message):
                raise ValueError("Conflicting system messages")
            if not existing:
                self._initial_messages.insert(0, {"role": "system", "content": system_message})
        self.reset()

    def reset(self):
        self.messages = Messages(provider=getattr(self.llm, "provider", "unknown"))
        self.messages.messages = deepcopy(self._initial_messages)
        self.workflow = Workflow()
        self.last_assistant_message = None

    def set_time_manager(self, time_manager):
        self.time_manager = time_manager

    def chat_completion(self, messages, tools=None):
        started = time.monotonic()
        response = self.llm.chat_completion(messages, tools)
        choices = value(response, "choices")
        if not choices:
            raise ValueError("Model response has no choices")
        source_message = value(choices[0], "message")
        if source_message is None:
            raise ValueError("Model response has no message")
        message = assistant_message(source_message)
        self.last_assistant_message = deepcopy(message)
        calls = message.get("tool_calls", [])
        ids = [call["id"] for call in calls]
        if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("Tool call IDs must be nonempty and unique within a response")
        self.messages.llm_response(response, time.monotonic() - started, message)
        return message, value(choices[0], "finish_reason")

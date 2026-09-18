"""Minimal client contract adapted from FarmAgent's BaseLLM."""


class BaseLLM:
    provider = "unknown"

    def __init__(self, model, temperature=0.1):
        self.model = model
        self.temperature = temperature

    def chat_completion(self, messages, tools=None):
        """Return choices[0].message with content/tool_calls; usage is optional."""
        raise NotImplementedError

    def client_info(self):
        return {"provider": self.provider, "model": self.model, "temperature": self.temperature}

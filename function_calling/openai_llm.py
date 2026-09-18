"""Adapted from FarmAgent's OpenAILLM; optional OpenAI-compatible transport.

No SDK import or network operation occurs until a client is explicitly created.
Endpoint/model compatibility must be verified before real experiments.
"""

import math
import os

from .base_llm import BaseLLM


class OpenAILLM(BaseLLM):
    provider = "openai"

    def __init__(self, model, temperature=0.1, *, api_key=None, base_url=None,
                 request_timeout_seconds=60.0, max_output_tokens=2048,
                 token_limit_parameter="max_completion_tokens", client=None):
        super().__init__(model, temperature)
        if token_limit_parameter not in ("max_tokens", "max_completion_tokens"):
            raise ValueError("Unsupported token limit parameter")
        if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or max_output_tokens < 1:
            raise ValueError("max_output_tokens must be a positive integer")
        if isinstance(request_timeout_seconds, bool) or not math.isfinite(request_timeout_seconds) or request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive and finite")
        self.request_timeout_seconds = request_timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.token_limit_parameter = token_limit_parameter
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise ImportError("Install requirements-function-calling.txt for real model calls") from error
            client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"),
                            base_url=self.base_url, timeout=request_timeout_seconds, max_retries=0)
        self.api_client = client

    def chat_completion(self, messages, tools=None):
        options = {"model": self.model, "messages": messages,
                   "timeout": self.request_timeout_seconds,
                   self.token_limit_parameter: self.max_output_tokens}
        if tools:
            options["tools"] = tools
        if self.temperature is not None:
            options["temperature"] = self.temperature
        return self.api_client.chat.completions.create(**options)

    def client_info(self):
        return {**super().client_info(), "base_url": self.base_url,
                "request_timeout_seconds": self.request_timeout_seconds,
                "max_output_tokens": self.max_output_tokens,
                "token_limit_parameter": self.token_limit_parameter}

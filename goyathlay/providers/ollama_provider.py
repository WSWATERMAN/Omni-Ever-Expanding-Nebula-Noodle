import os

import ollama

from .base import AIProvider
from ..command_cleaner import clean_command

class OllamaProvider(AIProvider):

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("GOYATHLAY_OLLAMA_MODEL", "qwen2.5-coder:14b")

    def generate_command(self, prompt: str):

        response = ollama.chat(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": """
You are Goyathlay.

Return ONE shell command.

Rules:
- No markdown
- No comments
- No explanations
- Return only the command
"""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return clean_command(response["message"]["content"])

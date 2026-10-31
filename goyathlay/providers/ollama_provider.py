import ollama

from .base import AIProvider
from ..command_cleaner import clean_command

class OllamaProvider(AIProvider):

    def __init__(self, model="qwen2.5-coder:14b"):
        self.model = model

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

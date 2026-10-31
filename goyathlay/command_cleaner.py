"""Remove an optional Markdown code fence from generated command text.

Example:
    >>> clean_command("```bash\\nnetstat -tuln\\n```")
    'netstat -tuln'
"""

import re


_FENCED_COMMAND = re.compile(
    r"\A```(?:[\w+-]+)?[ \t]*\r?\n(?P<command>.*)\r?\n```[ \t]*\Z",
    re.DOTALL,
)


def clean_command(text: str) -> str:
    """Strip surrounding whitespace and an optional outer Markdown fence."""
    cleaned = text.strip()
    match = _FENCED_COMMAND.fullmatch(cleaned)
    if match:
        cleaned = match.group("command").strip()
    return cleaned

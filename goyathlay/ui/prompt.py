"""Prompt rendering and interactive input support."""

from __future__ import annotations

import sys
from typing import Any


def render_prompt(profile: str, persona: str | None = None) -> str:
    """Render the active persona, retaining profile display for old callers."""
    return f"goyathlay({persona or profile}) ▷▶ "


def read_prompt(profile: str, *, hotkeys: Any = None, statusbar: Any = None) -> str:
    """Read a prompt, enabling real-time keys only on an interactive terminal.

    Non-interactive use deliberately falls back to ``input`` so the CLI remains
    scriptable and straightforward to test.
    """
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            from prompt_toolkit import prompt
            from prompt_toolkit.formatted_text import Dynamic
        except ImportError:
            if statusbar is not None:
                print(statusbar.render())
            return input(render_prompt(profile, statusbar.state.persona if statusbar else None))
        bindings = hotkeys.bindings() if hotkeys is not None else None
        toolbar = statusbar.render if statusbar is not None else None
        message = Dynamic(lambda: render_prompt(hotkeys.state.profile_name(), hotkeys.state.persona)) if hotkeys else render_prompt(profile)
        return prompt(message, key_bindings=bindings, bottom_toolbar=toolbar)
    if statusbar is not None:
        print(statusbar.render())
    return input(render_prompt(profile, statusbar.state.persona if statusbar else None))

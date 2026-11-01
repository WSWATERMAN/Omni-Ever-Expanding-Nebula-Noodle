"""Interactive keyboard shortcuts and operator console toggle state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ConsoleState:
    """Mutable presentation preferences for one running CLI session."""

    profile_manager: Any
    current_profile: Any
    profile_names: list[str]
    inventory: Any = None
    engine: str = "unknown"
    role: str = "ADMIN"
    cache_bypass: bool = False
    ai_bypass: bool = False
    show_risk: bool = True
    show_audit_details: bool = False
    notice: str = ""
    mode: str = "operator"
    persona: str = "operator"
    health: str = "UNKNOWN"
    health_message: str = "Health scan pending"

    def profile_name(self) -> str:
        """Return the active policy profile name."""
        return self.current_profile.name if self.current_profile is not None else "unavailable"

    def cycle_profile(self) -> str:
        """Switch to the next configured profile and persist the selection."""
        if not self.profile_names or self.profile_manager is None:
            self.notice = "Policy profiles unavailable"
            return self.profile_name()
        preferred = ["development", "staging", "production", "emergency"]
        ordered = [name for name in preferred if name in self.profile_names]
        ordered.extend(name for name in self.profile_names if name not in ordered)
        try:
            index = ordered.index(self.profile_name()) if self.profile_name() in ordered else -1
            name = ordered[(index + 1) % len(ordered)]
            self.profile_manager.set_default_profile(name)
            self.current_profile = self.profile_manager.load_profile(name)
            self.notice = f"Profile: {name}"
        except Exception as exc:
            self.notice = f"Unable to switch profile: {exc}"
        return self.profile_name()


class HotkeyManager:
    """Bind Ctrl shortcuts through prompt_toolkit when running interactively."""

    def __init__(self, state: ConsoleState) -> None:
        self.state = state
        self._bindings: Any = None

    def _toggle(self, attr: str, label: str) -> Callable[[Any], None]:
        def callback(event: Any) -> None:
            value = not getattr(self.state, attr)
            setattr(self.state, attr, value)
            self.state.notice = f"{label} {'Enabled' if value else 'Disabled'}"
            event.app.invalidate()
        return callback

    def _inventory(self, event: Any) -> None:
        try:
            hosts = len(self.state.inventory.list_hosts()) if self.state.inventory else 0
            groups = len(self.state.inventory.list_groups()) if self.state.inventory else 0
            self.state.notice = f"Inventory Summary | Hosts: {hosts} | Groups: {groups}"
        except Exception as exc:
            self.state.notice = f"Inventory unavailable: {exc}"
        event.app.invalidate()

    def _help(self, event: Any) -> None:
        self.state.notice = "Help: status | mode operator/trainer/sme/review/debug | knowledge stats | trainer queue | sme review | profiles | inventory | exit"
        event.app.invalidate()

    def handle_hotkey(self, key: str) -> str:
        """Apply one named shortcut action; useful for tests and non-TTY adapters."""
        key = key.casefold().replace("ctrl+", "c-")
        toggles = {
            "c-b": ("cache_bypass", "Cache Bypass"),
            "c-k": ("ai_bypass", "AI Generation Bypass"),
            "c-r": ("show_risk", "Risk Display"),
            "c-t": ("show_audit_details", "Audit Details"),
        }
        if key in toggles:
            attr, label = toggles[key]
            value = not getattr(self.state, attr)
            setattr(self.state, attr, value)
            self.state.notice = f"{label} {'Enabled' if value else 'Disabled'}"
        elif key == "c-p":
            self.state.cycle_profile()
        elif key == "c-i":
            hosts = len(self.state.inventory.list_hosts()) if self.state.inventory else 0
            groups = len(self.state.inventory.list_groups()) if self.state.inventory else 0
            self.state.notice = f"Inventory Summary | Hosts: {hosts} | Groups: {groups}"
        elif key == "c-h":
            self.state.notice = "Help: status | mode operator/trainer/sme/review/debug | knowledge stats | trainer queue | sme review | profiles | inventory | exit"
        else:
            raise ValueError(f"Unknown hotkey: {key}")
        return self.state.notice

    def bindings(self) -> Any:
        """Return prompt_toolkit bindings, importing the optional UI library lazily."""
        if self._bindings is not None:
            return self._bindings
        try:
            from prompt_toolkit.key_binding import KeyBindings
        except ImportError:
            return None
        bindings = KeyBindings()
        for key in ("c-b", "c-k", "c-r", "c-p", "c-t", "c-i", "c-h"):
            def invoke(event: Any, shortcut: str = key) -> None:
                self.handle_hotkey(shortcut)
                event.app.invalidate()
            bindings.add(key)(invoke)
        self._bindings = bindings
        return bindings

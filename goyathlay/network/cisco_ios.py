"""Fixed Cisco IOS translations and local command risk classification."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkCommand:
    """A device command and its precomputed execution risk."""

    vendor: str
    intent: str
    command: str
    read_only: bool
    risk: str


class UnsupportedNetworkIntentError(ValueError):
    """Raised when an intent has no safe deterministic translation."""


class CiscoIOSInterpreter:
    """Translate a small allowlist of Cisco IOS inspection intents."""

    _COMMANDS = {
        "show interface status": "show interface status",
        "show version": "show version",
        "show inventory": "show inventory",
        "show bgp summary": "show ip bgp summary",
        "show ip route": "show ip route",
        "show spanning-tree": "show spanning-tree",
        "show running-config": "show running-config",
    }

    def translate(self, intent: str) -> NetworkCommand:
        """Translate an allowlisted intent without network access."""
        if not isinstance(intent, str) or not intent.strip():
            raise UnsupportedNetworkIntentError("Cisco IOS intent must not be empty.")
        normalized = " ".join(intent.casefold().split())
        if normalized not in self._COMMANDS:
            raise UnsupportedNetworkIntentError(f"Unsupported Cisco IOS intent: {intent}")
        return NetworkCommand("cisco_ios", intent, self._COMMANDS[normalized], True, "LOW")

    @staticmethod
    def classify(command: str) -> str:
        """Classify commands locally, treating configuration as high risk."""
        normalized = " ".join(command.strip().casefold().split())
        if normalized.startswith(("configure terminal", "conf t", "interface ", "router ")) or normalized.startswith(
            ("no ", "shutdown", "write ", "copy ", "reload")
        ):
            return "HIGH"
        if normalized.startswith("show "):
            return "LOW"
        return "HIGH"

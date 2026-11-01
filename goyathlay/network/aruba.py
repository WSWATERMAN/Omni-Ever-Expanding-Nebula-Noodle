"""Deterministic read-only Aruba AOS-CX command translations."""

from .cisco_ios import NetworkCommand, UnsupportedNetworkIntentError


class ArubaInterpreter:
    """Translate a limited allowlist of Aruba switch inspection intents."""

    _COMMANDS = {
        "show version": "show version",
        "show system status": "show system",
        "show interface status": "show interface brief",
        "show interfaces": "show interface",
        "show vlans": "show vlan",
        "show ip route": "show ip route",
        "show running-config": "show running-config",
        "show spanning-tree": "show spanning-tree",
    }

    def translate(self, intent: str) -> NetworkCommand:
        """Translate supported read-only intent; no SSH or API is used."""
        if not isinstance(intent, str) or not intent.strip():
            raise UnsupportedNetworkIntentError("Aruba intent must not be empty.")
        normalized = " ".join(intent.casefold().split())
        if normalized not in self._COMMANDS:
            raise UnsupportedNetworkIntentError(f"Unsupported Aruba intent: {intent}")
        return NetworkCommand("aruba", intent, self._COMMANDS[normalized], True, "LOW")

    @staticmethod
    def classify(command: str) -> str:
        """Classify inspection commands as low risk and other commands high."""
        return "LOW" if " ".join(command.strip().casefold().split()).startswith("show ") else "HIGH"

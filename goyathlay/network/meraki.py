"""Read-only Meraki API operation descriptions (no HTTP client)."""

from dataclasses import dataclass


class UnsupportedMerakiIntentError(ValueError):
    """Raised when an intent is outside the Meraki read-only allowlist."""


@dataclass(frozen=True)
class MerakiOperation:
    """A declarative API request suitable for later approved execution."""

    intent: str
    method: str
    path: str
    read_only: bool = True
    risk: str = "LOW"


class MerakiInterpreter:
    """Map supported status intents to fixed HTTP GET operations."""

    _PATHS = {
        "show appliance status": "/organizations/{organizationId}/devices/statuses",
        "show vpn status": "/organizations/{organizationId}/appliance/vpn/statuses",
        "show switch status": "/organizations/{organizationId}/devices/statuses",
        "show wireless status": "/organizations/{organizationId}/devices/statuses",
    }

    def translate(self, intent: str) -> MerakiOperation:
        """Return a read-only operation description without making a request."""
        if not isinstance(intent, str) or not intent.strip():
            raise UnsupportedMerakiIntentError("Meraki intent must not be empty.")
        normalized = " ".join(intent.casefold().split())
        try:
            path = self._PATHS[normalized]
        except KeyError as exc:
            raise UnsupportedMerakiIntentError(f"Unsupported Meraki intent: {intent}") from exc
        return MerakiOperation(intent=intent, method="GET", path=path)

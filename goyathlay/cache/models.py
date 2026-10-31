"""Data model for a command cache event."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CachedCommand:
    """A command and its recorded outcome for a user intent."""

    intent: str
    command: str
    status: str
    created_at: str

    def __post_init__(self) -> None:
        if self.status not in {"verified", "failed", "dangerous"}:
            raise ValueError(f"Unsupported cache status: {self.status}")

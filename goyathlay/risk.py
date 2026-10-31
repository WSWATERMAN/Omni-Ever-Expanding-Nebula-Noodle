"""Offline heuristic risk assessment for shell command text."""

import re
from dataclasses import dataclass
from enum import Enum


class RiskLevel(Enum):
    """Relative risk category inferred from command patterns."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass(frozen=True)
class RiskAssessment:
    """Risk level and human-readable reasons for a command assessment."""

    level: RiskLevel
    reasons: list[str]


class RiskEngine:
    """Detect known risky command patterns using local regular expressions."""

    _HIGH_PATTERNS = (
        ("Recursive force deletion", re.compile(r"(?<![\w.-])rm\s+(?:(?:-[a-z]*[rf][a-z]*|--(?:recursive|force))\s+)+", re.IGNORECASE)),
        ("Filesystem formatting", re.compile(r"(?<![\w.-])mkfs(?:\.[\w-]+)?\b", re.IGNORECASE)),
        ("Raw disk write or copy", re.compile(r"(?<![\w.-])dd\s+(?:(?:if|of)=|)", re.IGNORECASE)),
        ("System shutdown or reboot", re.compile(r"(?<![\w.-])(?:shutdown|reboot|poweroff)\b", re.IGNORECASE)),
        ("Recursive ownership change", re.compile(r"(?<![\w.-])chown\s+(?:(?:-[^\s]+|--recursive)\s+)*-R\b|(?<![\w.-])chown\s+(?:--recursive)\b", re.IGNORECASE)),
        ("Recursive world-writable permission change on root", re.compile(r"(?<![\w.-])chmod\s+(?:(?:-[^\s]+|--recursive)\s+)*(?:0?777|a=rwx)\s+/(?:\s|$)", re.IGNORECASE)),
    )
    _MEDIUM_PATTERNS = (
        ("Package manager operation", re.compile(r"(?<![\w.-])(?:apt(?:-get)?|dnf|yum)(?:\s|$)", re.IGNORECASE)),
        ("Service restart", re.compile(r"(?<![\w.-])systemctl\s+restart\b", re.IGNORECASE)),
        ("User account modification", re.compile(r"(?<![\w.-])(?:useradd|usermod)\b", re.IGNORECASE)),
    )
    _FORK_BOMB = ":(){:|:&};:"

    def assess(self, command: str) -> RiskAssessment:
        """Return the highest detected risk and all matching reasons.

        This is a heuristic aid for review, not a command sandbox or a proof
        that an unflagged command is safe.
        """
        if not command.strip():
            return RiskAssessment(RiskLevel.LOW, ["Empty command."])

        reasons: list[str] = []
        level = RiskLevel.LOW
        compact = re.sub(r"\s+", "", command).casefold()
        if self._FORK_BOMB in compact:
            level = RiskLevel.HIGH
            reasons.append("Fork bomb pattern")

        for reason, pattern in self._MEDIUM_PATTERNS:
            if pattern.search(command):
                level = max(level, RiskLevel.MEDIUM, key=lambda item: item.value)
                reasons.append(reason)

        for reason, pattern in self._HIGH_PATTERNS:
            if pattern.search(command):
                level = RiskLevel.HIGH
                reasons.append(reason)

        return RiskAssessment(level, reasons)

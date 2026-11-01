"""Data models for curated, environment-specific implementations."""

from dataclasses import dataclass
from enum import Enum


class KnowledgeStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


SUPPORTED_TYPES = {"shell", "postgres", "sqlite", "mssql", "cisco", "meraki", "aruba"}


@dataclass(frozen=True)
class KnowledgeEntry:
    """One implementation candidate and its operator/trainer/SME evidence."""

    intent: str
    environment: str
    implementation: str
    type: str
    success_count: int = 0
    failure_count: int = 0
    dangerous_count: int = 0
    trainer_score: float | None = None
    sme_approved: bool = False
    last_updated: str = ""
    trainer_review_count: int = 0
    trainer_score_total: int = 0
    sme_status: str = KnowledgeStatus.PENDING.value
    notes: tuple[str, ...] = ()
    source_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.intent.strip() or not self.environment.strip() or not self.implementation.strip():
            raise ValueError("intent, environment, and implementation must not be empty.")
        if self.type not in SUPPORTED_TYPES:
            raise ValueError(f"Unsupported implementation type: {self.type}")
        if min(self.success_count, self.failure_count, self.dangerous_count, self.trainer_review_count, self.trainer_score_total) < 0:
            raise ValueError("Knowledge counters cannot be negative.")
        if self.trainer_score_total > 5 * self.trainer_review_count:
            raise ValueError("trainer_score_total exceeds the maximum aggregate.")
        if self.trainer_score is not None and not 0 <= self.trainer_score <= 5:
            raise ValueError("trainer_score must be between 0 and 5.")
        if self.sme_status not in {status.value for status in KnowledgeStatus}:
            raise ValueError(f"Unsupported SME status: {self.sme_status}")
        if self.sme_approved != (self.sme_status == KnowledgeStatus.APPROVED.value):
            raise ValueError("sme_approved must agree with sme_status.")
        if not all(isinstance(item, str) for item in (*self.notes, *self.source_history)):
            raise ValueError("notes and source_history must contain strings.")

    @property
    def operator_success_rate(self) -> float | None:
        """Return the success percentage when operator feedback exists."""
        total = self.success_count + self.failure_count + self.dangerous_count
        return self.success_count / total if total else None

    @property
    def score(self) -> float:
        """Combined deterministic reputation score from learning evidence."""
        return self.reputation_score if self.reputation_score is not None else 0.0

    @property
    def reputation_score(self) -> float | None:
        """Average available operator, trainer, and SME evidence on a 0–100 scale."""
        evidence: list[float] = []
        if self.operator_success_rate is not None:
            evidence.append(self.operator_success_rate * 100)
        if self.trainer_score is not None:
            evidence.append(self.trainer_score * 20)
        if self.sme_status == KnowledgeStatus.APPROVED.value:
            evidence.append(100.0)
        elif self.sme_status == KnowledgeStatus.REJECTED.value:
            evidence.append(0.0)
        return round(sum(evidence) / len(evidence), 2) if evidence else None

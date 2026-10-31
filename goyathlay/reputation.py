"""Deterministic command reputation scoring from local user feedback."""

from dataclasses import dataclass

if __package__:
    from .feedback import FeedbackResult, FeedbackStore, FeedbackStoreError
else:
    from feedback import FeedbackResult, FeedbackStore, FeedbackStoreError


@dataclass(frozen=True)
class CommandReputation:
    """Aggregated feedback counts and score for one exact command string."""

    command: str
    success_count: int
    failure_count: int
    dangerous_count: int
    score: float


class ReputationEngine:
    """Calculate command reputation from the local append-only feedback log."""

    def __init__(self, store: FeedbackStore | None = None) -> None:
        self.store = store if store is not None else FeedbackStore()

    def get_reputation(self, command: str) -> CommandReputation | None:
        """Aggregate all non-skipped feedback for a case-sensitive command."""
        successes = failures = dangerous = 0
        for record in self.store.load_history():
            if record["command"] != command:
                continue
            if record["result"] == FeedbackResult.SUCCESS.value:
                successes += 1
            elif record["result"] == FeedbackResult.FAILURE.value:
                failures += 1
            elif record["result"] == FeedbackResult.DANGEROUS.value:
                dangerous += 1

        if successes + failures + dangerous == 0:
            return None
        return CommandReputation(
            command=command,
            success_count=successes,
            failure_count=failures,
            dangerous_count=dangerous,
            score=self.calculate_score(successes, failures, dangerous),
        )

    def calculate_score(
        self,
        success_count: int,
        failure_count: int,
        dangerous_count: int,
    ) -> float:
        """Apply the deterministic weighted score and clamp it to 0–100."""
        if min(success_count, failure_count, dangerous_count) < 0:
            raise ValueError("Feedback counts cannot be negative.")
        score = 50 + (success_count * 10) - (failure_count * 5) - (dangerous_count * 25)
        return float(max(0, min(100, score)))

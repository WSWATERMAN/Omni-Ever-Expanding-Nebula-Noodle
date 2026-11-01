"""SME review queue helpers."""

from .knowledge import KnowledgeBase
from .models import KnowledgeEntry, KnowledgeStatus


class ReviewQueue:
    """Expose pending knowledge candidates and record SME decisions."""

    def __init__(self, knowledge: KnowledgeBase) -> None:
        self.knowledge = knowledge

    def pending(self) -> list[KnowledgeEntry]:
        """Return candidates requiring an SME decision."""
        return self.knowledge.list_pending()

    def approve(self, entry: KnowledgeEntry, note: str = "") -> KnowledgeEntry:
        """Approve one candidate for organizational lookup."""
        return self.knowledge.decide(entry.intent, entry.environment, entry.implementation,
                                     KnowledgeStatus.APPROVED, note, entry.type)

    def reject(self, entry: KnowledgeEntry, note: str = "") -> KnowledgeEntry:
        """Reject one candidate without deleting its history."""
        return self.knowledge.decide(entry.intent, entry.environment, entry.implementation,
                                     KnowledgeStatus.REJECTED, note, entry.type)

    def replace(self, entry: KnowledgeEntry, implementation: str, note: str = "") -> KnowledgeEntry:
        """Reject the reviewed candidate and create its replacement as pending."""
        if not implementation.strip() or implementation.strip() == entry.implementation:
            raise ValueError("Replacement implementation must be non-empty and different from the candidate.")
        self.reject(entry, note or "Replaced by SME")
        return self.knowledge.add_candidate(entry.intent, entry.environment, implementation, entry.type)

    def add_note(self, entry: KnowledgeEntry, note: str) -> KnowledgeEntry:
        """Record a note without approving the candidate."""
        return self.knowledge.decide(entry.intent, entry.environment, entry.implementation,
                                     KnowledgeStatus(entry.sme_status), note, entry.type)

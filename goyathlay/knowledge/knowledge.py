"""Private persistent store for curated, environment-aware knowledge."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .grading import average_grade, validate_grade
from .models import KnowledgeEntry, KnowledgeStatus


class KnowledgeError(RuntimeError):
    """Raised when the knowledge store is invalid or unavailable."""


class KnowledgeBase:
    """Store candidate implementations and return only SME-approved matches."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path else Path.home() / ".goyathlay" / "knowledge.json"
        self._migration_sources: list[str] = []
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise KnowledgeError("Knowledge store paths must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            if self.path.exists():
                self.entries, self._migration_sources = self._load()
                self.path.chmod(0o600)
            else:
                self.entries: list[KnowledgeEntry] = []
                self._save()
        except OSError as exc:
            raise KnowledgeError(f"Could not initialize knowledge store: {exc}") from exc

    def add_candidate(self, intent: str, environment: str, implementation: str, kind: str = "shell") -> KnowledgeEntry:
        """Add a new pending candidate, or return the matching existing candidate."""
        key = _key(intent, environment, implementation)
        existing = next((e for e in self.entries if _key(e.intent, e.environment, e.implementation) == key and e.type == kind), None)
        if existing:
            return existing
        entry = KnowledgeEntry(intent, environment, implementation, kind, last_updated=_now())
        self.entries.append(entry)
        self._save()
        return entry

    def record_operator_feedback(self, intent: str, environment: str, implementation: str, result: str, kind: str = "shell") -> KnowledgeEntry:
        """Aggregate operator success, failure, or dangerous feedback."""
        if result not in {"success", "failure", "dangerous"}:
            raise ValueError("Operator feedback must be success, failure, or dangerous.")
        entry = self.add_candidate(intent, environment, implementation, kind)
        fields = {"success": "success_count", "failure": "failure_count", "dangerous": "dangerous_count"}
        updated = replace(entry, **{fields[result]: getattr(entry, fields[result]) + 1}, last_updated=_now())
        return self._replace(entry, updated)

    def record_trainer_grade(self, intent: str, environment: str, implementation: str, grade: int, notes: str = "", trainer: str = "local", kind: str = "shell") -> KnowledgeEntry:
        """Store an individual grade event in the entry's notes and update its mean."""
        grade = validate_grade(grade)
        entry = self.add_candidate(intent, environment, implementation, kind)
        previous_count = entry.trainer_review_count
        previous_total = entry.trainer_score_total
        score = average_grade(previous_total + grade, previous_count + 1)
        event = f"trainer:{trainer};grade:{grade};note:{notes.strip()}"
        updated = replace(entry, trainer_score=score, trainer_score_total=previous_total + grade,
                          trainer_review_count=previous_count + 1,
                          notes=entry.notes + ((event,) if notes.strip() or trainer else ()), last_updated=_now())
        return self._replace(entry, updated)

    def decide(self, intent: str, environment: str, implementation: str, decision: KnowledgeStatus, note: str = "", kind: str = "shell") -> KnowledgeEntry:
        """Set SME status explicitly; rejection never qualifies for lookup."""
        if not isinstance(decision, KnowledgeStatus):
            raise TypeError("decision must be KnowledgeStatus.")
        entry = self.add_candidate(intent, environment, implementation, kind)
        updated = replace(entry, sme_status=decision.value, sme_approved=decision is KnowledgeStatus.APPROVED,
                          notes=entry.notes + ((f"sme:{note.strip()}",) if note.strip() else ()), last_updated=_now())
        return self._replace(entry, updated)

    def get_approved(self, intent: str, environment: str, kind: str | None = None) -> KnowledgeEntry | None:
        """Return the top-ranked approved implementation for an exact intent/environment."""
        candidates = [e for e in self.entries if _norm(e.intent) == _norm(intent)
                      and _norm(e.environment) == _norm(environment) and e.sme_approved
                      and e.dangerous_count == 0
                      and (kind is None or e.type == kind)]
        return max(candidates, key=lambda e: (e.score, e.success_count, e.implementation), default=None)

    def get_candidate(self, intent: str, environment: str, implementation: str,
                      kind: str | None = None) -> KnowledgeEntry | None:
        """Find one exact implementation candidate, regardless of SME status."""
        key = _key(intent, environment, implementation)
        return next((entry for entry in self.entries
                     if _key(entry.intent, entry.environment, entry.implementation) == key
                     and (kind is None or entry.type == kind)), None)

    def record_source_history(self, intent: str, environment: str, implementation: str,
                             event: dict[str, Any], kind: str = "shell") -> KnowledgeEntry:
        """Preserve one imported source record without double-counting feedback."""
        entry = self.add_candidate(intent, environment, implementation, kind)
        serialized = json.dumps(event, ensure_ascii=False, sort_keys=True)
        return self._replace(entry, replace(entry, source_history=entry.source_history + (serialized,),
                                            last_updated=_now()))

    def list_pending(self) -> list[KnowledgeEntry]:
        """Return entries awaiting SME review in insertion order."""
        return [e for e in self.entries if e.sme_status == KnowledgeStatus.PENDING.value]

    def stats(self) -> dict[str, Any]:
        """Return counts and ranked implementation summaries."""
        ordered = sorted(self.entries, key=lambda e: (e.score, e.intent, e.environment, e.implementation))
        return {
            "total_entries": len(self.entries),
            "approved_entries": sum(e.sme_approved for e in self.entries),
            "pending_review": sum(e.sme_status == "PENDING" for e in self.entries),
            "rejected_entries": sum(e.sme_status == "REJECTED" for e in self.entries),
            "top_rated": ordered[-5:][::-1],
            "lowest_rated": ordered[:5],
        }

    def mark_migration(self, source: str) -> bool:
        """Persist a source marker; return False when the source was imported already."""
        if source in self._migration_sources:
            return False
        self._migration_sources.append(source)
        self._save()
        return True

    def has_migration(self, source: str) -> bool:
        """Check whether a legacy source was already migrated."""
        return source in self._migration_sources

    def _replace(self, old: KnowledgeEntry, new: KnowledgeEntry) -> KnowledgeEntry:
        self.entries[self.entries.index(old)] = new
        self._save()
        return new

    def _load(self) -> tuple[list[KnowledgeEntry], list[str]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            records = raw["entries"]
            markers = raw.get("migration_sources", [])
            if not isinstance(records, list) or not isinstance(markers, list) or not all(isinstance(x, str) for x in markers):
                raise ValueError("entries and migration_sources have invalid formats")
            entries = []
            for index, item in enumerate(records):
                if not isinstance(item, dict):
                    raise ValueError(f"entry {index} is not an object")
                item = dict(item)
                item["notes"] = tuple(item.get("notes", ()))
                item["source_history"] = tuple(item.get("source_history", ()))
                entries.append(KnowledgeEntry(**item))
            return entries, markers
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise KnowledgeError(f"Could not load knowledge store: {exc}") from exc

    def _save(self) -> None:
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                             prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as stream:
                temp_name = stream.name
                os.fchmod(stream.fileno(), 0o600)
                json.dump({"entries": [{**asdict(e), "notes": list(e.notes),
                                        "source_history": list(e.source_history)} for e in self.entries],
                           "migration_sources": self._migration_sources}, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
            temp_name = None
            self.path.chmod(0o600)
        except OSError as exc:
            raise KnowledgeError(f"Could not save knowledge store: {exc}") from exc
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass


def _key(intent: str, environment: str, implementation: str) -> tuple[str, str, str]:
    return _norm(intent), _norm(environment), implementation.strip()


def _norm(value: str) -> str:
    return " ".join(value.split()).casefold()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

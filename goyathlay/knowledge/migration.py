"""One-time import of the legacy command cache and feedback history."""

from __future__ import annotations

import json
from pathlib import Path

from .knowledge import KnowledgeBase


def migrate_legacy_data(
    knowledge: KnowledgeBase,
    cache_path: str | Path | None = None,
    feedback_path: str | Path | None = None,
) -> dict[str, int]:
    """Import legacy records once; all imported entries remain SME-pending.

    Feedback history is treated as the detailed source when an identical
    intent/command has both feedback and a cache status, avoiding duplicate
    operator counts caused by the old cache mirroring feedback events.
    """
    base = Path.home() / ".goyathlay"
    cache = Path(cache_path).expanduser() if cache_path else base / "command_cache.json"
    feedback = Path(feedback_path).expanduser() if feedback_path else base / "feedback.jsonl"
    source_key = f"legacy-v1:{cache.resolve()}:{feedback.resolve()}"
    if knowledge.has_migration(source_key):
        return {"imported_candidates": 0, "imported_feedback": 0, "already_migrated": 1}

    old_feedback: dict[tuple[str, str], list[str]] = {}
    imported_feedback = 0
    if feedback.exists():
        for line in feedback.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                intent, command, result = record["intent"], record["command"], record["result"]
                if not all(isinstance(v, str) for v in (intent, command, result)):
                    continue
                if result not in {"success", "failure", "dangerous"}:
                    continue
                old_feedback.setdefault((intent, command), []).append(result)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    for (intent, command), results in old_feedback.items():
        for result in results:
            knowledge.record_operator_feedback(intent, "local", command, result, "shell")
            imported_feedback += 1

    imported_candidates = 0
    if cache.exists():
        try:
            records = json.loads(cache.read_text(encoding="utf-8")).get("entries", [])
        except (json.JSONDecodeError, OSError, AttributeError):
            records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            intent, command, status = record.get("intent"), record.get("command"), record.get("status")
            if not all(isinstance(v, str) for v in (intent, command, status)):
                continue
            knowledge.add_candidate(intent, "local", command, "shell")
            imported_candidates += 1
            knowledge.record_source_history(intent, "local", command, record, "shell")
            if (intent, command) not in old_feedback:
                mapped = {"verified": "success", "failed": "failure", "dangerous": "dangerous"}.get(status)
                if mapped:
                    knowledge.record_operator_feedback(intent, "local", command, mapped, "shell")
    knowledge.mark_migration(source_key)
    return {"imported_candidates": imported_candidates, "imported_feedback": imported_feedback,
            "already_migrated": 0}

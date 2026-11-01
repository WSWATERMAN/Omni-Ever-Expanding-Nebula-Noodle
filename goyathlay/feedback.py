"""Collect user feedback and append it to a local JSON Lines history."""

import json
import os
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class FeedbackResult(Enum):
    """User assessment of whether an executed command was appropriate."""

    SUCCESS = "success"
    FAILURE = "failure"
    DANGEROUS = "dangerous"
    SKIPPED = "skipped"


class FeedbackStoreError(RuntimeError):
    """Raised when feedback history cannot be safely read or written."""


class FeedbackStore:
    """Append feedback events to a private JSON Lines file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else Path.home() / ".goyathlay" / "feedback.jsonl"
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise FeedbackStoreError("Feedback store directory and file must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            if not self.path.exists():
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(descriptor)
            self.path.chmod(0o600)
        except OSError as exc:
            raise FeedbackStoreError(f"Could not initialize feedback store: {exc}") from exc

    def append(self, intent: str, command: str, result: FeedbackResult) -> dict[str, str]:
        """Append one timestamped feedback event and return the stored record."""
        if not isinstance(intent, str) or not isinstance(command, str):
            raise TypeError("Feedback intent and command must be strings.")
        if not isinstance(result, FeedbackResult):
            raise TypeError("Feedback result must be a FeedbackResult.")
        record = {
            "timestamp": _utc_now(),
            "intent": intent,
            "command": command,
            "result": result.value,
        }
        try:
            descriptor = os.open(
                self.path,
                os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise FeedbackStoreError(f"Could not append feedback: {exc}") from exc
        return record

    def load_history(self) -> list[dict[str, str]]:
        """Load all records in order, failing if any line is malformed."""
        records: list[dict[str, str]] = []
        try:
            descriptor = os.open(
                self.path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    try:
                        record: Any = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise FeedbackStoreError(
                            f"Invalid feedback JSON on line {line_number}: {exc}"
                        ) from exc
                    if not _is_feedback_record(record):
                        raise FeedbackStoreError(f"Invalid feedback record on line {line_number}.")
                    records.append(record)
        except OSError as exc:
            raise FeedbackStoreError(f"Could not load feedback history: {exc}") from exc
        return records


class FeedbackManager:
    """Prompt for a feedback classification and persist the selected result."""

    def __init__(self, store: FeedbackStore | None = None) -> None:
        self.store = store if store is not None else FeedbackStore()

    def review(self, intent: str, command: str, *, operator_view: bool = False) -> FeedbackResult:
        """Ask for feedback until valid input is given, then append the event.

        ``operator_view`` limits the prompt to the result question and choices;
        the implementation remains available to the private feedback record.
        """
        print("-" * 36)
        print("COMMAND FEEDBACK")
        print("-" * 36)
        if not operator_view:
            print(f"Intent:\n{intent}")
            print(f"Command:\n{command}")
        print("Was this result acceptable?" if operator_view else "Did this command solve your problem?")
        print("[Y] Yes")
        print("[N] No")
        print("[D] Dangerous")
        print("[S] Skip")

        mapping = {
            "y": FeedbackResult.SUCCESS,
            "yes": FeedbackResult.SUCCESS,
            "n": FeedbackResult.FAILURE,
            "no": FeedbackResult.FAILURE,
            "d": FeedbackResult.DANGEROUS,
            "dangerous": FeedbackResult.DANGEROUS,
            "s": FeedbackResult.SKIPPED,
            "skip": FeedbackResult.SKIPPED,
        }
        while True:
            choice = input("Selection: ").strip().casefold()
            result = mapping.get(choice)
            if result is not None:
                self.store.append(intent, command, result)
                return result
            print("Please enter Y (Yes), N (No), D (Dangerous), or S (Skip).")


def _is_feedback_record(record: Any) -> bool:
    return (
        isinstance(record, dict)
        and set(record) == {"timestamp", "intent", "command", "result"}
        and all(isinstance(value, str) for value in record.values())
        and record["result"] in {result.value for result in FeedbackResult}
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

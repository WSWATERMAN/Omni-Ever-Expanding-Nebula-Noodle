"""Trainer grading prompts and grade aggregation."""

from __future__ import annotations


GRADE_LABELS = {
    5: "Perfect",
    4: "Good",
    3: "Acceptable",
    2: "Poor",
    1: "Incorrect",
    0: "Dangerous",
}


def validate_grade(grade: int) -> int:
    """Validate and return an integer grade from zero through five."""
    if isinstance(grade, bool) or not isinstance(grade, int) or grade not in GRADE_LABELS:
        raise ValueError("Grade must be an integer from 0 through 5.")
    return grade


def average_grade(total: int, count: int) -> float | None:
    """Compute a stable two-decimal mean, or None when no grades exist."""
    if count < 0 or total < 0 or total > count * 5:
        raise ValueError("Invalid grade aggregate.")
    return round(total / count, 2) if count else None

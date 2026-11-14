"""Public-safe reference rules for the duplicate-write census."""

from __future__ import annotations


def is_effectful(call: dict) -> bool:
    """Return true for a call whose declared method can change state."""
    return str(call.get("method", "")).upper() not in {"GET", "HEAD", "OPTIONS"}


def duplicate_candidates(calls: list[dict]) -> list[tuple[int, list[dict]]]:
    """Enumerate one exact duplicate after each effectful call."""
    candidates = []
    for index, call in enumerate(calls):
        if not is_effectful(call):
            continue
        edited = [dict(item) for item in calls]
        edited.insert(index + 1, dict(call))
        candidates.append((index, edited))
    return candidates


def has_cardinality_difference(control: dict[str, int], fault: dict[str, int]) -> bool:
    """Compare application counters over their full union."""
    return any(control.get(key, 0) != fault.get(key, 0) for key in control.keys() | fault.keys())


def first_non_idempotent(candidates: list[tuple[int, dict, dict]]) -> int | None:
    """Return the first clean candidate with a cardinality difference."""
    for index, control, fault in candidates:
        if has_cardinality_difference(control, fault):
            return index
    return None

from __future__ import annotations


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merges overlapping/adjacent [start, end] millisecond ranges."""
    if not intervals:
        return []
    ordered = sorted((s, e) for s, e in intervals if e >= s)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def covered_ms(intervals: list[tuple[int, int]], clip_start: int | None = None, clip_end: int | None = None) -> int:
    merged = merge_intervals(intervals)
    total = 0
    for start, end in merged:
        if clip_start is not None:
            start = max(start, clip_start)
        if clip_end is not None:
            end = min(end, clip_end)
        if end > start:
            total += end - start
    return total

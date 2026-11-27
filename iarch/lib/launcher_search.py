# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Deterministic bounded fuzzy matching for desktop-entry search."""


def match_score(query, text):
    """Return a relevance score or None if query is not a subsequence."""
    if not isinstance(query, str) or not isinstance(text, str) or len(query) > 128 or len(text) > 1024:
        return None
    query, text = query.casefold().strip(), text.casefold()
    if not query:
        return 0
    if text == query:
        return 10000
    if text.startswith(query):
        return 8000 - min(len(text), 1000)
    at = text.find(query)
    if at >= 0:
        return 6000 - min(at * 4 + len(text), 2000)
    positions, cursor = [], 0
    for char in query:
        pos = text.find(char, cursor)
        if pos < 0:
            return None
        positions.append(pos)
        cursor = pos + 1
    return 3000 - min(positions[0] * 4 + positions[-1] - positions[0] + len(text), 2000)


def rank(query, entries, frequency=None, limit=30):
    """Rank IDs/names by relevance, then capped use count and stable name/id.

    Entries are data only; this function never interprets desktop Exec fields.
    """
    if not isinstance(query, str) or len(query) > 128 or not isinstance(entries, (list, tuple)) or len(entries) > 10000:
        raise ValueError('invalid search input')
    if not isinstance(limit, int) or isinstance(limit, bool) or not 0 <= limit <= 100:
        raise ValueError('invalid result limit')
    if frequency is None:
        frequency = {}
    if not isinstance(frequency, dict):
        raise ValueError('invalid frequency data')
    results = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        identifier, name = entry.get('id'), entry.get('name')
        if not isinstance(identifier, str) or not identifier or len(identifier) > 512 or not isinstance(name, str) or not name or len(name) > 1024:
            continue
        score = match_score(query, name)
        if score is None:
            continue
        count = frequency.get(identifier, 0)
        if not isinstance(count, int) or isinstance(count, bool):
            count = 0
        results.append((-score, -max(0, min(count, 1000000)), name.casefold(), identifier, entry))
    results.sort(key=lambda item: item[:4])
    return [item[4] for item in results[:limit]]

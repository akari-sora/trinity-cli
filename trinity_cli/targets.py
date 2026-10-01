"""Which seat a name means. `grok` is the default Grok seat, not every Grok seat."""

from __future__ import annotations


def grok_seats(seats) -> list:
    return [seat for seat in seats if seat.key == "grok" or str(seat.key).startswith("grok-")]


def default_grok(seats):
    found = grok_seats(seats)
    marked = [seat for seat in found if getattr(seat, "is_default", False)]
    if marked:
        return marked[0]
    for seat in found:
        if seat.key == "grok":
            return seat
    return found[0] if len(found) == 1 else None


def find_seat(seats, key: str):
    if key in {"dot", "muse"}:
        return next((seat for seat in seats if seat.key == key), None)
    if key == "grok":
        return default_grok(seats)
    return next((seat for seat in seats if seat.key == key), None)


def enabled_for_all(seats) -> list:
    """dot, every Grok seat in the list, and muse. Callers already dropped disabled seats."""
    return list(seats)

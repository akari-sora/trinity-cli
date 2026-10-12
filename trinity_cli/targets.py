"""Which seat a name means. `grok` is the default Grok seat, not every Grok seat."""

from __future__ import annotations


UNKNOWN_SEAT_HINT = "座位是 dot、grok、muse，或 `trinity-cli grok add` 加的名字；`trinity-cli grok bots` 列出可用的 bot。"


def is_grok(seat) -> bool:
    """Seat names are free-form (`grok add researcher`), so the seat class decides."""
    return getattr(seat, "family", "") == "grok"


def grok_seats(seats) -> list:
    return [seat for seat in seats if is_grok(seat)]


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

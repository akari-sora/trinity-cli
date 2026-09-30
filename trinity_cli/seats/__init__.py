"""The seats trinity knows about. Add a seat by adding its adapter here."""

from __future__ import annotations

from trinity_cli.runner import Runner
from trinity_cli.seats.base import Problem, Seat
from trinity_cli.seats.dot import DotSeat
from trinity_cli.seats.grok import GrokSeat
from trinity_cli.seats.muse import MuseSeat

__all__ = ["DotSeat", "GrokSeat", "MuseSeat", "Problem", "Seat", "build_seats"]


def build_seats(runner: Runner | None = None, *, grok_bot: str | None = None, include_activity: bool = True) -> list[Seat]:
    runner = runner or Runner()
    return [
        DotSeat(runner, include_activity=include_activity),
        GrokSeat(runner, default_bot=grok_bot),
        MuseSeat(),
    ]

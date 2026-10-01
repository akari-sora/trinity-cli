"""The seats trinity knows about. Add a seat by adding its adapter here."""

from __future__ import annotations

from trinity_cli.config import load_grok_seats
from trinity_cli.runner import Runner
from trinity_cli.seats.base import Problem, Seat
from trinity_cli.seats.dot import DotSeat
from trinity_cli.seats.grok import GrokSeat
from trinity_cli.seats.muse import MuseSeat

__all__ = ["DotSeat", "GrokSeat", "MuseSeat", "Problem", "Seat", "build_seats"]


def build_seats(runner: Runner | None = None, *, grok_bot: str | None = None, include_activity: bool = True) -> list[Seat]:
    runner = runner or Runner()
    specs, default_name = load_grok_seats()
    grok: list[Seat] = []
    for spec in specs:
        if not spec.enabled:
            continue
        grok.append(
            GrokSeat(
                runner,
                seat_name=spec.name,
                account=spec.account,
                pinned_bot=spec.bot or None,
                is_default=spec.name == default_name,
            )
        )
    if not grok:
        grok.append(GrokSeat(runner, default_bot=grok_bot, is_default=True))
    elif grok_bot:
        for seat in grok:
            if getattr(seat, "is_default", False):
                seat.pinned_bot = grok_bot
                seat.default_bot = grok_bot
                seat.only_bots = [grok_bot]
    return [
        DotSeat(runner, include_activity=include_activity),
        *grok,
        MuseSeat(runner),
    ]

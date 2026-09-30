"""Muse (Meta's personal agent) has no public API or CLI and is US/Canada only.

This seat is a placeholder. When Muse gets an API, implement status/read/send/wait
here; nothing else needs to change.
"""

from __future__ import annotations

from trinity_cli.seats.base import Seat


class MuseSeat(Seat):
    key = "muse"
    label = "Muse"
    unsupported_reason = "不支援（沒有公開 API）"

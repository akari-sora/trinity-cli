"""Every seat has the same four capabilities: status, read, send, wait.

A seat that cannot do something returns Result.unsupported(...). It never raises
for that. Adding a seat means adding one file that subclasses Seat.
"""

from __future__ import annotations

from datetime import datetime

from trinity_cli.model import CAPABILITIES, Result, SendReceipt


class Problem(Exception):
    """Raised inside an adapter; capability methods turn it into Result.failed."""

    def __init__(self, error: str, hint: str = ""):
        super().__init__(error)
        self.error = error
        self.hint = hint


class Seat:
    key = ""
    label = ""
    unsupported_reason = "不支援"

    def supports(self, capability: str) -> bool:
        if capability not in CAPABILITIES:
            return False
        return getattr(type(self), capability) is not getattr(Seat, capability)

    def status(self) -> Result:
        return Result.unsupported(self.unsupported_reason)

    def read(self, cursors: dict, *, since: datetime | None = None, limit: int = 30) -> Result:
        return Result.unsupported(self.unsupported_reason)

    def send(self, target: str | None, text: str, nonce: str) -> Result:
        return Result.unsupported(self.unsupported_reason)

    def wait(self, receipt: SendReceipt, *, timeout: float, poll: float) -> Result:
        return Result.unsupported(self.unsupported_reason)

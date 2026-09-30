"""Every seat has the same capabilities: status, read, send, wait, schedules, instructions.

A seat that cannot do something returns Result.unsupported(...). It never raises
for that. Adding a seat means adding one file that subclasses Seat.

Muse can later override schedules and instructions without a change here:
schedules() -> Result.ok(list[ScheduleItem]); instructions(target, update=None)
-> Result.ok(InstructionText). Leave a method unimplemented and the command
prints the unsupported reason instead of failing.
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

    def schedules(self) -> Result:
        return Result.unsupported(self.unsupported_reason)

    def instructions(self, target: str | None = None, *, update: str | None = None) -> Result:
        """Read standing instructions, or replace them when update is not None.

        An update on an unsupported seat is a no-op result: it must not send a message.
        """
        return Result.unsupported(self.unsupported_reason)

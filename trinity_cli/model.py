"""Shared result types. Adapters return these instead of raising."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

OK = "ok"
FAILED = "failed"
UNSUPPORTED = "unsupported"

CAPABILITIES = ("status", "read", "send", "wait", "schedules", "instructions", "memory")


@dataclass
class Result:
    state: str
    value: object = None
    error: str = ""
    hint: str = ""

    @classmethod
    def ok(cls, value: object = None) -> "Result":
        return cls(OK, value)

    @classmethod
    def failed(cls, error: str, hint: str = "") -> "Result":
        return cls(FAILED, None, error, hint)

    @classmethod
    def unsupported(cls, reason: str) -> "Result":
        return cls(UNSUPPORTED, None, reason)


@dataclass
class SeatStatus:
    summary: str
    waiting: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    hint: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class Message:
    source: str
    speaker: str
    text: str
    at: datetime | None
    from_agent: bool = False
    key: str = ""
    presentation: bool = False


@dataclass
class Batch:
    """New items from one source plus the cursor to save once they are printed."""

    cursor_key: str
    label: str
    items: list[Message]
    new_cursor: dict | None
    gap: bool = False
    note: str = ""


@dataclass
class SourceFailure:
    label: str
    error: str
    hint: str = ""


@dataclass
class ReadOutcome:
    batches: list[Batch] = field(default_factory=list)
    failures: list[SourceFailure] = field(default_factory=list)


@dataclass
class SendReceipt:
    target: str
    target_ref: str
    nonce: str
    sent_at: datetime
    delivery: str
    message_key: str = ""
    error: str = ""


@dataclass
class WaitOutcome:
    delivered: bool | None
    reply: Message | None
    timed_out: bool
    polls: int = 0
    error: str = ""


@dataclass
class ScheduleItem:
    """One automation. No ids: titles and times are enough to spot duplicates."""

    title: str
    when: str = ""
    status: str = ""


@dataclass
class InstructionText:
    """Standing instructions for one target. writable is false when the seat can be read but not updated."""

    target: str
    text: str
    writable: bool = False

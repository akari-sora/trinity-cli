"""What a command shows. cli.main scrubs and prints it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Shown:
    code: int
    text: str
    data: dict

"""Local cursors and the send ledger. No secrets are stored here."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("TRINITY_HOME") or "~/.trinity-cli").expanduser()


class State:
    def __init__(self, path: Path | None = None):
        self.path = path or home() / "state.json"

    def load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {"version": 1, "cursors": {}}
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "cursors": {}, "unreadable": True}
        if not isinstance(data, dict) or not isinstance(data.get("cursors"), dict):
            return {"version": 1, "cursors": {}}
        return data

    def cursors(self) -> dict:
        return dict(self.load().get("cursors", {}))

    def save_cursors(self, updates: dict) -> None:
        data = self.load()
        data.pop("unreadable", None)
        data.setdefault("cursors", {}).update(updates)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(prefix=".state-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


class Ledger:
    """Append-only record of every send: written before the send and after readback."""

    def __init__(self, path: Path | None = None):
        self.path = path or home() / "ledger.jsonl"

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        new = not self.path.exists()
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if new:
            os.chmod(self.path, 0o600)

    def records(self) -> list[dict]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        except FileNotFoundError:
            return []

"""Local settings. Account names only; tokens are ignored."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone

from trinity_cli.state import home

_MAX_ACCOUNT = 64


def clean_account(value: object) -> str | None:
    """A short account label. Anything that looks like a token is refused."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > _MAX_ACCOUNT or any(ch.isspace() for ch in text):
        return None
    if text.startswith("eyJ") or text.startswith("sk-") or "token" in text.lower():
        return None
    return text


def configured_gbot_account() -> str | None:
    """TRINITY_GBOT_ACCOUNT wins over ~/.trinity-cli/config.json key gbot_account."""
    from_env = clean_account(os.environ.get("TRINITY_GBOT_ACCOUNT"))
    if os.environ.get("TRINITY_GBOT_ACCOUNT"):
        return from_env
    return clean_account(_config().get("gbot_account"))


def clean_bot_name(value: object) -> str | None:
    """A bot name. Tokens and email-shaped labels are refused."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 80 or any(ch in text for ch in "\r\n\t"):
        return None
    if "@" in text or text.startswith("eyJ") or text.startswith("sk-") or "token" in text.lower():
        return None
    return text


def configured_grok_bot() -> str | None:
    """TRINITY_GROK_BOT wins over ~/.trinity-cli/config.json key grok_bot."""
    if os.environ.get("TRINITY_GROK_BOT"):
        return clean_bot_name(os.environ.get("TRINITY_GROK_BOT"))
    return clean_bot_name(_config().get("grok_bot"))


def _config() -> dict:
    return read_config(home() / "config.json")


def read_config(path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_SEAT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,32}$")
_NOT_A_SEAT = {"dot", "muse", "all"}


def clean_seat_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _SEAT_NAME.match(text) or text in _NOT_A_SEAT:
        return None
    return text


@dataclass(frozen=True)
class GrokSeatSpec:
    name: str
    account: str | None
    bot: str
    enabled: bool = True


def load_grok_seats(data: dict | None = None) -> tuple[list[GrokSeatSpec], str]:
    """Configured Grok seats and the default seat name.

    `grok_seats` wins. Without it, `gbot_account` plus `grok_bot` is one seat named `grok`.
    Environment variables apply only when reading the live config, and only to that legacy seat.
    """
    live = data is None
    data = _config() if data is None else data
    raw = data.get("grok_seats")
    if isinstance(raw, list):
        seats: list[GrokSeatSpec] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = clean_seat_name(item.get("name"))
            bot = clean_bot_name(item.get("bot")) or ""
            if not name or (not bot and not item.get("account")):
                continue
            account = clean_account(item.get("account")) if item.get("account") else None
            enabled = item.get("enabled") is not False
            seats.append(GrokSeatSpec(name, account, bot, enabled))
        if seats:
            wanted = clean_seat_name(data.get("grok_default"))
            names = {seat.name for seat in seats}
            default = wanted if wanted in names else seats[0].name
            return seats, default
    account = clean_account(data.get("gbot_account")) if data.get("gbot_account") else None
    bot = clean_bot_name(data.get("grok_bot")) or ""
    if live and os.environ.get("TRINITY_GBOT_ACCOUNT"):
        account = clean_account(os.environ.get("TRINITY_GBOT_ACCOUNT"))
    if live and os.environ.get("TRINITY_GROK_BOT"):
        bot = clean_bot_name(os.environ.get("TRINITY_GROK_BOT")) or ""
    if account or bot:
        return [GrokSeatSpec("grok", account, bot, True)], "grok"
    return [], "grok"


def backup_config(path) -> "os.PathLike[str] | None":
    """Copy config.json aside. Returns the backup path, or None when there is no file."""
    if not path.is_file():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = path.with_name(f"{path.name}.bak-{stamp}")
    dest.write_bytes(path.read_bytes())
    os.chmod(dest, 0o600)
    return dest


def save_config(data: dict, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".config-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def migrate_legacy_grok(path=None):
    """Turn old keys into one seat named grok. Backs up first. No-op when grok_seats exists."""
    path = path or (home() / "config.json")
    data = read_config(path)
    if isinstance(data.get("grok_seats"), list):
        return None
    if "gbot_account" not in data and "grok_bot" not in data:
        return None
    backup = backup_config(path)
    account = data.get("gbot_account")
    bot = data.get("grok_bot")
    seat: dict = {"name": "grok", "bot": bot if isinstance(bot, str) else ""}
    if isinstance(account, str) and account:
        seat["account"] = account
    data.pop("gbot_account", None)
    data.pop("grok_bot", None)
    data["grok_seats"] = [seat]
    data["grok_default"] = "grok"
    save_config(data, path)
    return backup


def _ensure_seat_list(data: dict) -> list[dict]:
    raw = data.get("grok_seats")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    seats, _default = load_grok_seats(data)
    return [
        {key: value for key, value in (("name", seat.name), ("account", seat.account), ("bot", seat.bot)) if value}
        for seat in seats
    ]


def add_grok_seat(name: str, account: str, bot: str, *, default: bool = False, path=None):
    path = path or (home() / "config.json")
    seat_name = clean_seat_name(name)
    label = clean_account(account)
    bot_name = clean_bot_name(bot)
    if not seat_name or not label or not bot_name:
        raise ValueError("座位名稱、登入標籤或 bot 名稱不能用")
    data = read_config(path)
    backup = backup_config(path)
    seats = [item for item in _ensure_seat_list(data) if item.get("name") != seat_name]
    seats.append({"name": seat_name, "account": label, "bot": bot_name})
    data.pop("gbot_account", None)
    data.pop("grok_bot", None)
    data["grok_seats"] = seats
    if default or not clean_seat_name(data.get("grok_default")):
        data["grok_default"] = seat_name
    save_config(data, path)
    return backup


def remove_grok_seat(name: str, *, path=None):
    path = path or (home() / "config.json")
    seat_name = clean_seat_name(name)
    if not seat_name:
        raise ValueError("看不懂的座位名稱")
    data = read_config(path)
    backup = backup_config(path)
    seats = [item for item in _ensure_seat_list(data) if item.get("name") != seat_name]
    if len(seats) == len(_ensure_seat_list(data)):
        raise ValueError(f"沒有 {seat_name} 這個座位")
    data.pop("gbot_account", None)
    data.pop("grok_bot", None)
    data["grok_seats"] = seats
    if data.get("grok_default") == seat_name:
        data["grok_default"] = seats[0]["name"] if seats else ""
    save_config(data, path)
    return backup

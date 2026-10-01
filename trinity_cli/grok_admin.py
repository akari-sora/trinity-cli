"""List Grok bots across logins, and edit grok_seats. Never prints a bot id."""

from __future__ import annotations

import json

from trinity_cli.config import load_grok_seats, read_config
from trinity_cli.runner import find_tool
from trinity_cli.seats.grok import GBOT_FALLBACKS, SANDBOX_GONE
from trinity_cli.state import home

_GONE_HINT = "在 Grok Bot app 重新登入這個帳號。gbot 沒有重新登入的指令。"


def _gone(text: str) -> bool:
    low = text.lower()
    return "404" in low or ("sandbox" in low and "not found" in low)


def discover(runner, binary: str | None = None) -> list[dict]:
    """One row per bot, plus one row when a whole login cannot be listed."""
    binary = binary or find_tool("gbot", "TRINITY_GBOT", GBOT_FALLBACKS)
    if not binary:
        return [{"account": "", "name": "", "description": "", "reachable": False, "reason": "找不到 gbot", "seat": ""}]
    proc = runner.run([binary, "--json", "accounts"], timeout=30)
    try:
        payload = json.loads(proc.out) if proc.code == 0 and proc.out.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, list):
        blob = f"{proc.err}\n{proc.out}"
        reason = SANDBOX_GONE if _gone(blob) else (blob.strip()[:160] or f"exit {proc.code}")
        return [{"account": "", "name": "", "description": "", "reachable": False, "reason": reason, "seat": ""}]
    configured = _configured()
    rows: list[dict] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        label = account.get("label") if isinstance(account.get("label"), str) else ""
        if not label:
            continue
        listed = runner.run([binary, "--json", "bots", "list", "--account", label], timeout=45)
        blob = f"{listed.err}\n{listed.out}"
        if listed.code != 0 or _gone(blob):
            reason = SANDBOX_GONE if _gone(blob) or listed.code == 404 else (blob.strip()[:160] or f"exit {listed.code}")
            named = [seat for (acct, _bot), seat in configured.items() if acct == label]
            rows.append(
                {
                    "account": label,
                    "name": "",
                    "description": "",
                    "reachable": False,
                    "reason": reason,
                    "seat": ",".join(named),
                }
            )
            continue
        try:
            bots = json.loads(listed.out) if listed.out.strip() else []
        except json.JSONDecodeError:
            rows.append(
                {
                    "account": label,
                    "name": "",
                    "description": "",
                    "reachable": False,
                    "reason": "bots list 的輸出不是 JSON",
                    "seat": "",
                }
            )
            continue
        if not isinstance(bots, list):
            continue
        for bot in bots:
            if not isinstance(bot, dict) or bot.get("kind", "bot") == "group":
                continue
            name = bot.get("name") if isinstance(bot.get("name"), str) else ""
            if not name:
                continue
            description = bot.get("description") if isinstance(bot.get("description"), str) else ""
            rows.append(
                {
                    "account": label,
                    "name": name,
                    "description": description,
                    "reachable": True,
                    "reason": "",
                    "seat": configured.get((label, name), ""),
                }
            )
    return rows


def _configured() -> dict[tuple[str, str], str]:
    data = read_config(home() / "config.json")
    seats, _default = load_grok_seats(data)
    found = {}
    for seat in seats:
        if seat.account and seat.bot:
            found[(seat.account, seat.bot)] = seat.name
    return found


def render_bots(rows: list[dict]) -> str:
    if not rows:
        return "沒有 bot。"
    lines = []
    for row in rows:
        if not row.get("reachable"):
            where = row.get("account") or "（沒有標籤）"
            seat = f"  seat {row['seat']}" if row.get("seat") else ""
            lines.append(f"{where}  {row.get('reason') or SANDBOX_GONE}{seat}")
            continue
        seat = f"  seat {row['seat']}" if row.get("seat") else ""
        desc = row.get("description") or ""
        extra = f"  {desc}" if desc else ""
        lines.append(f"{row['account']}  {row['name']}  reachable{seat}{extra}")
    return "\n".join(lines)


def bots_json(rows: list[dict]) -> dict:
    public = []
    for row in rows:
        public.append(
            {
                "account": row.get("account") or "",
                "name": row.get("name") or "",
                "description": row.get("description") or "",
                "reachable": bool(row.get("reachable")),
                "reason": row.get("reason") or "",
                "seat": row.get("seat") or "",
            }
        )
    return {"bots": public, "hint": _GONE_HINT}

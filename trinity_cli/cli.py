"""Command line for trinity-cli: status, digest, ask."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from trinity_cli import __version__
from trinity_cli.app import (
    ask_exit,
    ask_json,
    build_digest,
    collect_digest,
    collect_status,
    render_ask,
    render_status,
    run_ask,
    status_exit,
    status_json,
)
from trinity_cli.redact import scrub
from trinity_cli.seats import build_seats
from trinity_cli.state import Ledger, State
from trinity_cli.util import new_nonce, parse_since


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trinity-cli",
        description="One command in front of your always-on agents: Your dot, Grok Bot, and Muse (placeholder).",
        epilog=(
            "examples:\n"
            "  trinity-cli status\n"
            "  trinity-cli digest\n"
            "  trinity-cli digest --since 2h\n"
            "  trinity-cli ask all \"今天進度？\"\n"
            "  trinity-cli ask grok 蝴蝶 \"read back the last handoff\"\n"
            "--json may appear before or after the command."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="print JSON; works before or after the command")
    parser.add_argument("--version", action="version", version=f"trinity-cli {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="one line per seat; things waiting on you first")

    digest = sub.add_parser("digest", help="new messages from every seat in one timeline")
    digest.add_argument("--since", help="look back from 30m, 2h, 1d, or an ISO time; does not move cursors")
    digest.add_argument("--peek", action="store_true", help="show new messages without moving cursors")
    digest.add_argument("--no-activity", action="store_true", help="skip Your dot activity (saves about 20s)")
    digest.add_argument("--limit", type=int, help="messages per source (Your dot max 32, Grok Bot max 200)")

    ask = sub.add_parser("ask", help="send the same text to seats and wait for each first reply")
    ask.add_argument("seat", choices=("all", "dot", "grok", "muse"))
    ask.add_argument("words", nargs="*", help="`ask grok BOT TEXT`, `ask all TEXT`, `ask dot TEXT`; no TEXT reads stdin")
    ask.add_argument("--grok-bot", help="Grok bot to ask (default: TRINITY_GROK_BOT, or the only bot)")
    ask.add_argument("--timeout", type=float, default=180.0, help="seconds to wait for each reply (default 180)")
    ask.add_argument("--poll", type=float, default=10.0, help="seconds between readbacks (default 10)")
    return parser


def _split_globals(argv: list[str]) -> tuple[list[str], bool]:
    cleaned: list[str] = []
    as_json = False
    for index, item in enumerate(argv):
        if item == "--":
            cleaned.extend(argv[index:])
            break
        if item == "--json":
            as_json = True
            continue
        cleaned.append(item)
    return cleaned, as_json


def emit(out, text: str) -> None:
    out.write(scrub(text) + "\n")
    out.flush()


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None, *, seats=None, out=None, err=None, state=None, ledger=None, stdin=None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    cleaned, as_json = _split_globals(raw)
    args = parser.parse_args(cleaned)
    command = args.command or "status"
    out = out or sys.stdout
    err = err or sys.stderr
    no_activity = bool(getattr(args, "no_activity", False))
    if seats is None:
        seats = build_seats(grok_bot=getattr(args, "grok_bot", None), include_activity=not no_activity)
    elif no_activity:
        for seat in seats:
            if hasattr(seat, "include_activity"):
                seat.include_activity = False
    try:
        if command == "status":
            return cmd_status(seats, out, as_json)
        if command == "digest":
            return cmd_digest(seats, args, out, err, state or State(), as_json)
        if command == "ask":
            return cmd_ask(seats, args, out, err, ledger or Ledger(), stdin or sys.stdin, as_json)
    except BrokenPipeError:
        return 1
    parser.error(f"unknown command {command}")
    return 2


def cmd_status(seats, out, as_json: bool) -> int:
    reports = collect_status(seats)
    emit(out, dumps(status_json(reports)) if as_json else render_status(reports))
    return status_exit(reports)


def cmd_digest(seats, args, out, err, state: State, as_json: bool) -> int:
    try:
        since = parse_since(args.since) if args.since else None
    except ValueError as exc:
        print(str(exc), file=err)
        return 2
    limits = {"dot": args.limit, "grok": args.limit} if args.limit else {}
    reports = collect_digest(seats, state.cursors(), since, limits)
    view = build_digest(reports, advance=not (args.peek or since))
    try:
        emit(out, dumps(view.data) if as_json else view.text)
    except (OSError, ValueError):
        try:
            print("輸出失敗，讀取位置沒有前進。", file=err)
        except (OSError, ValueError):
            pass
        return 1
    if view.cursor_updates:
        state.save_cursors(view.cursor_updates)
    return 1 if view.failed else 0


def cmd_ask(seats, args, out, err, ledger: Ledger, stdin, as_json: bool) -> int:
    words = list(args.words)
    bot = args.grok_bot
    if args.seat == "grok" and not bot and words:
        bot = words.pop(0)
    text = " ".join(words).strip()
    if not text and not stdin.isatty():
        text = stdin.read().strip()
    if not text:
        print("沒有訊息內容：`trinity-cli ask all \"...\"`，或從 stdin 傳入。", file=err)
        return 2
    if args.seat == "all":
        pairs = [(seat, bot if seat.key == "grok" else None) for seat in seats]
    else:
        pairs = [(seat, bot if seat.key == "grok" else None) for seat in seats if seat.key == args.seat]
    if not pairs:
        print(f"沒有 {args.seat} 這個座位。", file=err)
        return 2
    nonce = new_nonce()
    ask_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{nonce}"
    rows = run_ask(pairs, text, nonce, ask_id=ask_id, ledger=ledger, timeout=args.timeout, poll=args.poll)
    if as_json:
        emit(out, dumps(ask_json(rows, ask_id=ask_id, nonce=nonce)))
    else:
        emit(out, render_ask(rows, nonce=nonce, timeout=args.timeout, ledger_path=str(ledger.path)))
    return ask_exit(rows)

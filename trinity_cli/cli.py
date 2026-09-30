"""Command line for trinity-cli."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from trinity_cli import __version__
from trinity_cli.advise import run_who
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
from trinity_cli.briefing import run_diff, run_push, run_show
from trinity_cli.forward import run_hand, run_wait
from trinity_cli.ledger_view import run_log
from trinity_cli.redact import scrub
from trinity_cli.runner import Runner
from trinity_cli.seats import build_seats
from trinity_cli.state import Ledger, State, home
from trinity_cli.schedule_report import run_schedules
from trinity_cli.shown import Shown
from trinity_cli.util import new_nonce, one_line, parse_since


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
            "  trinity-cli hand dot#last --to grok:蝴蝶 \"請看這則\"\n"
            "  trinity-cli wait grok:蝴蝶 --notify\n"
            "  trinity-cli schedules\n"
            "  trinity-cli who \"翻譯這段\"\n"
            "  trinity-cli brief diff\n"
            "  trinity-cli log --seat dot\n"
            "--json may appear before or after the command.\n"
            "hand and brief push ask before sending; add --yes to skip the prompt.\n"
            "wait does not resend. It runs hand only when --then hand ... is written out."
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

    hand = sub.add_parser("hand", help="forward one seat's reply to another, after a confirmation")
    hand.add_argument("source", help="dot#last, grok:BOT#last, or grok:BOT#2 (2 = second newest reply)")
    hand.add_argument("--to", required=True, dest="dest", help="dot, grok:BOT, or muse")
    hand.add_argument("--yes", action="store_true", help="send without asking; required when stdin is not a terminal")
    hand.add_argument("--timeout", type=float, default=180.0, help="seconds to wait for the destination reply (default 180)")
    hand.add_argument("--poll", type=float, default=10.0, help="seconds between readbacks (default 10)")
    hand.add_argument("instruction", nargs="*", help="what the destination should do with the forwarded reply")

    wait = sub.add_parser("wait", help="wait for a new reply; never resends")
    wait.add_argument("spec", help="dot, or grok:BOT")
    wait.add_argument("--timeout", type=float, default=180.0, help="seconds to wait (default 180)")
    wait.add_argument("--poll", type=float, default=5.0, help="first gap between reads; it backs off (default 5)")
    wait.add_argument("--notify", action="store_true", help="terminal bell and a macOS notification")
    wait.add_argument("--then", nargs=argparse.REMAINDER, help="only `hand ...`, and only if a reply arrives; put this last")

    sub.add_parser("schedules", help="list automations per seat and flag duplicate titles")

    who = sub.add_parser("who", help="suggest a seat for a task; sends nothing")
    who.add_argument("task", nargs="*", help="what you want done")

    brief = sub.add_parser("brief", help="show, diff, or push the local brief")
    brief_sub = brief.add_subparsers(dest="brief_command")
    brief_sub.add_parser("show", help="print ~/.trinity-cli/brief.md")
    brief_diff = brief_sub.add_parser("diff", help="compare the brief with each seat's instructions")
    brief_diff.add_argument("--grok-bot", help="which Grok bot to compare")
    brief_push = brief_sub.add_parser("push", help="write the brief to a seat that has an instruction API")
    brief_push.add_argument("--yes", action="store_true", help="write without asking; never messages Your dot or Muse")
    brief_push.add_argument("--grok-bot", help="which Grok bot to update")

    log = sub.add_parser("log", help="show the send ledger")
    log.add_argument("--seat", choices=("dot", "grok", "muse"), help="only this seat")
    log.add_argument("--since", help="30m, 2h, 1d, or an ISO time")
    log.add_argument("--status", help="event, reply, or readback value, such as sent, replied, timed_out")
    log.add_argument("--limit", type=int, default=50, help="how many matching lines to show (default 50)")
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


def show(shown: Shown, out, as_json: bool) -> int:
    emit(out, dumps(shown.data) if as_json else shown.text)
    return shown.code


def macos_notify(title: str, body: str) -> None:
    safe_title = one_line(title, 60).replace("\\", "").replace('"', "'")
    safe_body = one_line(body, 140).replace("\\", "").replace('"', "'")
    script = f'display notification "{safe_body}" with title "{safe_title}"'
    Runner().run(["osascript", "-e", script], timeout=10)


def main(
    argv: list[str] | None = None,
    *,
    seats=None,
    out=None,
    err=None,
    state=None,
    ledger=None,
    stdin=None,
    brief_path=None,
    clock=None,
    sleep=None,
    notifier=None,
) -> int:
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
    book = ledger or Ledger()
    try:
        if command == "status":
            return cmd_status(seats, out, as_json)
        if command == "digest":
            return cmd_digest(seats, args, out, err, state or State(), as_json)
        if command == "ask":
            return cmd_ask(seats, args, out, err, book, stdin or sys.stdin, as_json)
        if command == "hand":
            return show(
                run_hand(
                    seats,
                    args.source,
                    args.dest,
                    " ".join(args.instruction),
                    yes=args.yes,
                    timeout=args.timeout,
                    poll=args.poll,
                    ledger=book,
                    stdin=stdin or sys.stdin,
                ),
                out,
                as_json,
            )
        if command == "wait":
            return show(
                run_wait(
                    seats,
                    args.spec,
                    timeout=args.timeout,
                    poll=args.poll,
                    notify=args.notify,
                    then_args=args.then,
                    ledger=book,
                    stdin=stdin or sys.stdin,
                    clock=clock,
                    sleep=sleep,
                    notifier=notifier if notifier is not None else (macos_notify if args.notify else None),
                    err=err,
                ),
                out,
                as_json,
            )
        if command == "schedules":
            return show(run_schedules(seats), out, as_json)
        if command == "who":
            return show(run_who(seats, " ".join(args.task)), out, as_json)
        if command == "brief":
            path = brief_path or (home() / "brief.md")
            bot = getattr(args, "grok_bot", None)
            if args.brief_command == "show":
                return show(run_show(path), out, as_json)
            if args.brief_command == "diff":
                return show(run_diff(seats, path, grok_bot=bot), out, as_json)
            if args.brief_command == "push":
                return show(
                    run_push(seats, path, yes=args.yes, grok_bot=bot, ledger=book, stdin=stdin or sys.stdin),
                    out,
                    as_json,
                )
            print("請用 brief show、brief diff 或 brief push。", file=err)
            return 2
        if command == "log":
            return show(run_log(book, seat=args.seat, since=args.since, status=args.status, limit=args.limit), out, as_json)
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

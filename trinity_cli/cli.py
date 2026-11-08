"""Command line for trinity-cli."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from trinity_cli import __version__
from trinity_cli.advise import run_who
from trinity_cli.config import add_grok_seat, remove_grok_seat, resolve_muse_backend
from trinity_cli.grok_admin import bots_json, discover, render_bots
from trinity_cli.model import FAILED, ReadOutcome
from trinity_cli.app import (
    aggregate_exit,
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
from trinity_cli.briefing import run_diff, run_init, run_push, run_show
from trinity_cli.forward import run_hand, run_wait
from trinity_cli.ledger_view import run_log
from trinity_cli.redact import scrub, scrub_ids
from trinity_cli.runner import Runner
from trinity_cli.seats import build_seats
from trinity_cli.seats.grok import GrokSeat
from trinity_cli.seats.muse import MuseSeat
from trinity_cli.targets import UNKNOWN_SEAT_HINT, default_grok, find_seat, grok_seats, is_grok
from trinity_cli.state import Ledger, State, home, tilde
from trinity_cli.schedule_report import run_schedules
from trinity_cli.shown import Shown
from trinity_cli.util import new_nonce, one_line, parse_since


def configure_stdio() -> None:
    """Windows consoles default to a legacy code page. Keep Chinese output intact."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
    # A pipe from PowerShell 7 or Git Bash is UTF-8, not the console code page.
    stdin = sys.stdin
    try:
        piped = stdin is not None and not stdin.isatty()
    except (OSError, ValueError):
        piped = False
    if piped and hasattr(stdin, "reconfigure"):
        try:
            stdin.reconfigure(encoding="utf-8-sig", errors="replace")
        except (OSError, ValueError):
            pass


class _CommandParser(argparse.ArgumentParser):
    """Accept options between positionals on Python 3.11.

    3.12+ already does this. 3.11 leaves the trailing words as unrecognized
    arguments, so README examples such as ``hand dot#last --to grok "…"`` fail.
    ``parse_known_intermixed_args`` calls ``parse_known_args``, so the original
    method has to stay in place for that call. ``--then`` uses ``REMAINDER`` and
    cannot be intermixed.
    """

    def parse_known_args(self, args=None, namespace=None):
        positionals = self._get_positional_actions()
        if any(action.nargs in (argparse.PARSER, argparse.REMAINDER) for action in positionals):
            return argparse.ArgumentParser.parse_known_args(self, args, namespace)
        saved = argparse.ArgumentParser.parse_known_args
        try:
            self.parse_known_args = lambda a=None, n=None: saved(self, a, n)
            return argparse.ArgumentParser.parse_known_intermixed_args(self, args, namespace)
        finally:
            del self.parse_known_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trinity-cli",
        description="One command in front of your always-on agents: Your dot, Grok Bot, and Muse.",
        epilog=(
            "examples:\n"
            "  trinity-cli status\n"
            "  trinity-cli digest\n"
            "  trinity-cli digest --peek\n"
            "  trinity-cli digest --since 2h\n"
            "  trinity-cli ask all \"今天進度？\"\n"
            "  trinity-cli ask researcher \"read back the last handoff\"\n"
            "  trinity-cli ask grok --bot \"Other\" --account example-login \"hello\"\n"
            "  trinity-cli grok bots\n"
            "  trinity-cli hand dot#last --to researcher \"請看這則\"\n"
            "  trinity-cli wait grok --notify\n"
            "  trinity-cli schedules\n"
            "  trinity-cli who \"翻譯這段\"\n"
            "  trinity-cli brief init\n"
            "  trinity-cli brief diff\n"
            "  trinity-cli log --seat dot\n"
            "  trinity-cli login muse\n"
            "  trinity-cli --muse-backend api status\n"
            "  trinity-cli status --muse-backend auto\n"
            "With no command, status runs.\n"
            "--json may appear before or after the command.\n"
            "hand and brief push ask before sending; add --yes to skip the prompt.\n"
            "wait does not resend. It runs hand only when --then hand ... is written out."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="print JSON instead of text; may appear before or after the command (default: text)")
    parser.add_argument("--version", action="version", version=f"trinity-cli {__version__}")
    sub = parser.add_subparsers(dest="command", parser_class=_CommandParser)

    migrate = sub.add_parser(
        "migrate",
        help="deliver a migration plan (from gbot migrate) to muse or dot; resumable, read back, then acceptance questions",
        description=(
            "deliver a migration plan (from gbot migrate) to muse or dot. Each step is one message with its own nonce in "
            "the ledger. A step whose delivery is unknown is never resent on its own: a later run reads the chat back first. "
            "Progress is kept in TRINITY_HOME/migrations/<plan id>.json, so run the same command again to continue."
        ),
    )
    migrate.add_argument("seat", choices=["muse", "dot"], help="destination seat")
    migrate.add_argument("plan", help="plan file written by gbot migrate (trinity-migration-plan v1)")
    migrate.add_argument("--yes", action="store_true", help="send without asking (required when stdin is not a terminal)")
    migrate.add_argument("--timeout", type=float, default=300.0, help="seconds to wait for each reply (default 300); a timeout never resends")
    migrate.add_argument("--poll", type=float, default=10.0, help="seconds between read-backs (default 10)")
    migrate.add_argument("--resend-unknown", action="store_true", help="resend a step whose earlier delivery could not be read back (default: stop)")
    migrate.add_argument("--no-questions", action="store_true", help="skip the acceptance questions (default: ask them)")

    sub.add_parser(
        "status",
        help="one line per seat; things waiting on you first (default command)",
        description="one line per seat; things waiting on you first (default command)",
    )

    digest = sub.add_parser(
        "digest",
        help="new messages from every seat in one timeline; moves cursors after a successful print",
        description="new messages from every seat in one timeline; moves cursors after a successful print",
    )
    digest.add_argument("--since", help="look back: 30m, 2h, 1d, 1w, or ISO time; does not move cursors (no default)")
    digest.add_argument("--peek", action="store_true", help="show new messages without moving cursors (default: move them after printing)")
    digest.add_argument("--no-activity", action="store_true", help="skip Your dot activity and Muse activity (default: include both)")
    digest.add_argument("--limit", type=int, help="messages for Your dot (1..32, default 30) and Grok (1..200, default 40); Muse stays at 40, max 100")
    digest.add_argument("--bot", help="read this Grok bot instead of the configured Grok seats (default: configured seats)")
    digest.add_argument("--account", help="gbot login label for --bot; required when that name exists on more than one login")

    ask = sub.add_parser(
        "ask",
        help="send the same text to seats and wait for each first reply; a timeout never resends",
        description="send the same text to seats and wait for each first reply; a timeout never resends",
    )
    ask.add_argument("seat", help="all, dot, muse, grok (the default Grok seat), or a seat name such as researcher")
    ask.add_argument("words", nargs="*", help="message text; `ask grok NAME TEXT` names a bot when two or more words; empty reads stdin")
    ask.add_argument("--grok-bot", help="Grok bot on the default seat (default: that seat's bot)")
    ask.add_argument("--bot", help="any Grok bot, configured or not (default: the seat's bot)")
    ask.add_argument("--account", help="gbot login label for --bot; required when that name exists on more than one login")
    ask.add_argument("--timeout", type=float, default=180.0, help="seconds to wait for each reply (default 180; no resend on timeout)")
    ask.add_argument("--poll", type=float, default=10.0, help="seconds between readbacks (default 10)")

    hand = sub.add_parser(
        "hand",
        help="forward one seat's reply to another, after a confirmation; does not chain",
        description="forward one seat's reply to another, after a confirmation; does not chain",
    )
    hand.add_argument("source", help="dot#last, grok:BOT#last, muse#last, or #2 for the second newest reply")
    hand.add_argument("--to", required=True, dest="dest", help="dot, grok, grok:BOT, or muse (required)")
    hand.add_argument("--yes", action="store_true", help="send without asking (default: ask; required when stdin is not a terminal)")
    hand.add_argument("--timeout", type=float, default=180.0, help="seconds to wait for the destination reply (default 180; no resend)")
    hand.add_argument("--poll", type=float, default=10.0, help="seconds between readbacks (default 10)")
    hand.add_argument("instruction", nargs="*", help="what the destination should do with the forwarded reply (required)")

    wait = sub.add_parser(
        "wait",
        help="wait for a new reply after the ledger mark; never resends",
        description="wait for a new reply after the ledger mark; never resends",
    )
    wait.add_argument("spec", help="dot, muse, grok, or grok:BOT (grok alone uses grok_bot)")
    wait.add_argument("--timeout", type=float, default=180.0, help="seconds to wait (default 180; timeout does not send)")
    wait.add_argument("--poll", type=float, default=5.0, help="first gap between reads, then doubles up to 30s (default 5)")
    wait.add_argument("--notify", action="store_true", help="terminal bell and a macOS notification (default: off; no message body)")
    wait.add_argument("--then", nargs=argparse.REMAINDER, help="only `hand ...`, and only if a reply arrives; put this last (default: do nothing)")
    wait.add_argument("--bot", help="wait on this Grok bot instead of a configured seat (default: the seat in spec)")
    wait.add_argument("--account", help="gbot login label for --bot; required when that name exists on more than one login")

    sub.add_parser(
        "schedules",
        help="list automations per seat and flag duplicate titles; unsupported is not a failure",
        description="list automations per seat and flag duplicate titles; unsupported is not a failure",
    )

    who = sub.add_parser(
        "who",
        help="suggest a seat for a task; sends nothing",
        description="suggest a seat for a task; sends nothing",
    )
    who.add_argument("task", nargs="*", help="what you want done (required)")

    brief = sub.add_parser(
        "brief",
        help="show, init, diff, or push ~/.trinity-cli/brief.md",
        description="show, init, diff, or push ~/.trinity-cli/brief.md",
    )
    brief_sub = brief.add_subparsers(dest="brief_command")
    brief_sub.add_parser("show", help="print ~/.trinity-cli/brief.md", description="print ~/.trinity-cli/brief.md")
    brief_sub.add_parser(
        "init",
        help="write a short brief.md only when the file does not exist",
        description="write a short brief.md only when the file does not exist",
    )
    brief_diff = brief_sub.add_parser(
        "diff",
        help="compare the brief with each seat; missing file exits 0",
        description="compare the brief with each seat; missing file exits 0",
    )
    brief_diff.add_argument("--grok-bot", help="Grok bot to compare (default: the selected seat's bot)")
    brief_diff.add_argument("--seat", help="which Grok seat to compare (default: grok_default, or grok)")
    brief_push = brief_sub.add_parser(
        "push",
        help="write the brief to a Grok bot that has an instruction API; asks first",
        description="write the brief to a Grok bot that has an instruction API; asks first",
    )
    brief_push.add_argument("--yes", action="store_true", help="write without asking (default: ask; never messages Your dot or Muse)")
    brief_push.add_argument("--grok-bot", help="Grok bot to update (default: the selected seat's bot)")
    brief_push.add_argument("--seat", help="which Grok seat to update (default: grok_default, or grok)")

    login = sub.add_parser(
        "login",
        help="sign in a seat through its own CLI; credentials are never printed",
        description="sign in a seat through its own CLI; credentials are never printed",
    )
    login.add_argument("seat", choices=("dot", "grok", "muse"), help="dot (codex login), grok (app instructions only), or muse")
    login.add_argument("--api-key", action="store_true", help="Muse only: pass an API key on stdin to `muse auth set` (default: muse-web-cli credential)")
    login.add_argument("--web", action="store_true", help="Muse only: headed `muse-web-cli login` (default: muse-web-cli credential; cannot combine with --api-key)")

    log = sub.add_parser("log", help="show the send ledger", description="show the send ledger")
    log.add_argument("--seat", help="only this seat: dot, muse, grok (the default Grok seat), or a name such as researcher (default: every seat)")

    grok = sub.add_parser(
        "grok",
        help="list Grok bots across logins, or add and remove seats",
        description="list Grok bots across logins, or add and remove seats",
    )
    grok_sub = grok.add_subparsers(dest="grok_command")
    grok_sub.add_parser(
        "bots",
        help="list every bot on every gbot login; no raw ids",
        description="list every bot on every gbot login; no raw ids",
    )
    grok_add = grok_sub.add_parser(
        "add",
        help="add a named Grok seat to config.json after a backup",
        description="add a named Grok seat to config.json after a backup",
    )
    grok_add.add_argument("name", help="seat name, such as researcher")
    grok_add.add_argument("--account", required=True, help="gbot login label (required)")
    grok_add.add_argument("--bot", required=True, help="bot name on that login (required)")
    grok_add.add_argument("--default", action="store_true", help="make this seat the default grok target (default: keep grok_default)")
    grok_remove = grok_sub.add_parser(
        "remove",
        help="remove a named Grok seat from config.json after a backup",
        description="remove a named Grok seat from config.json after a backup",
    )
    grok_remove.add_argument("name", help="seat name to remove")
    log.add_argument("--since", help="30m, 2h, 1d, 1w, or an ISO time (default: all records)")
    log.add_argument("--status", help="match event, reply, or readback, such as sent, replied, timed_out (default: any)")
    log.add_argument("--limit", type=int, default=50, help="how many matching lines to show (default 50, minimum 1)")
    _install_muse_backend_flag(parser)
    for command in sub.choices.values():
        _install_muse_backend_flag(command)
        for action in command._actions:
            if isinstance(action, argparse._SubParsersAction):
                for nested in action.choices.values():
                    _install_muse_backend_flag(nested)
    return parser


def _install_muse_backend_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--muse-backend",
        choices=("browser", "api", "auto"),
        help="Muse backend for this command: browser, api, or auto (default: config muse_backend, else MUSE_WEB_BACKEND, else muse-web-cli's own default)",
    )


def _split_globals(argv: list[str]) -> tuple[list[str], bool, str | None]:
    cleaned: list[str] = []
    as_json = False
    muse_backend = None
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--":
            cleaned.extend(argv[index:])
            break
        if item == "--json":
            as_json = True
            index += 1
            continue
        if item == "--muse-backend" or item.startswith("--muse-backend="):
            if item.startswith("--muse-backend="):
                muse_backend = item.split("=", 1)[1]
                index += 1
                continue
            if index + 1 >= len(argv):
                muse_backend = ""
                index += 1
                continue
            muse_backend = argv[index + 1]
            index += 2
            continue
        cleaned.append(item)
        index += 1
    return cleaned, as_json, muse_backend


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


def _resolve_bot(seats, bot: str, account: str | None, *, allow_discover: bool):
    matches = []
    for seat in grok_seats(seats):
        name = getattr(seat, "pinned_bot", None) or getattr(seat, "default_bot", None)
        if name == bot:
            matches.append(seat)
    if account:
        same = [seat for seat in matches if getattr(seat, "account", None) == account]
        if len(same) == 1:
            return same[0], None
        template = default_grok(seats) or (matches[0] if matches else None)
        return (
            GrokSeat(
                getattr(template, "runner", None),
                binary=getattr(template, "binary", None) if template else None,
                seat_name="grok",
                account=account,
                pinned_bot=bot,
                is_default=True,
            ),
            None,
        )
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, "這個 bot 名稱出現在多個登入，請加上 --account"
    if allow_discover:
        template = default_grok(seats)
        rows = discover(getattr(template, "runner", None) or Runner(), getattr(template, "binary", None))
        found = {row["account"] for row in rows if row.get("reachable") and row.get("name") == bot and row.get("account")}
        if len(found) == 1:
            return _resolve_bot(seats, bot, next(iter(found)), allow_discover=False)
        if len(found) > 1:
            return None, "這個 bot 名稱出現在多個登入，請加上 --account"
        return None, "找不到這個 bot。用 `trinity-cli grok bots` 看名稱和登入。"
    return None, "請加上 --account。bot 名稱可能跨登入重複。"


def _with_adhoc(seats, bot: str | None, account: str | None, *, allow_discover: bool):
    if not bot and not account:
        return seats, None
    if not bot:
        return None, "用了 --account 就要加 --bot。"
    seat, error = _resolve_bot(seats, bot, account, allow_discover=allow_discover)
    if error:
        return None, error
    return [item for item in seats if not is_grok(item)] + [seat], None


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
    configure_stdio()
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    cleaned, as_json, muse_flag = _split_globals(raw)
    args = parser.parse_args(cleaned)
    if muse_flag is not None and resolve_muse_backend(muse_flag, data={}, env={}) is None:
        print("`--muse-backend` 只能是 browser、api 或 auto。", file=err or sys.stderr)
        return 2
    command = args.command or "status"
    out = out or sys.stdout
    err = err or sys.stderr
    no_activity = bool(getattr(args, "no_activity", False))
    allow_discover = seats is None
    if seats is None:
        seats = build_seats(
            grok_bot=getattr(args, "grok_bot", None),
            include_activity=not no_activity,
            muse_backend=resolve_muse_backend(muse_flag),
        )
    elif no_activity:
        for seat in seats:
            if hasattr(seat, "include_activity"):
                seat.include_activity = False
    if muse_flag and seats is not None:
        chosen = resolve_muse_backend(muse_flag, data={}, env={})
        for seat in seats:
            if isinstance(seat, MuseSeat) and chosen:
                seat.backend = chosen
    book = ledger or Ledger()
    try:
        if command == "status":
            return cmd_status(seats, out, as_json)
        if command == "digest":
            return cmd_digest(seats, args, out, err, state or State(), as_json, allow_discover=allow_discover)
        if command == "ask":
            return cmd_ask(seats, args, out, err, book, stdin or sys.stdin, as_json, allow_discover=allow_discover)
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
            if getattr(args, "bot", None) or getattr(args, "account", None):
                seats, error = _with_adhoc(seats, args.bot, args.account, allow_discover=allow_discover)
                if error:
                    print(error, file=err)
                    return 2
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
            if args.brief_command == "init":
                return show(run_init(path), out, as_json)
            if args.brief_command == "diff":
                return show(run_diff(seats, path, grok_bot=bot, grok_seat=getattr(args, "seat", None)), out, as_json)
            if args.brief_command == "push":
                return show(
                    run_push(
                        seats,
                        path,
                        yes=args.yes,
                        grok_bot=bot,
                        grok_seat=getattr(args, "seat", None),
                        ledger=book,
                        stdin=stdin or sys.stdin,
                    ),
                    out,
                    as_json,
                )
            print("請用 brief show、brief init、brief diff 或 brief push。", file=err)
            return 2
        if command == "log":
            also = ()
            if args.seat == "grok":
                focus = default_grok(seats)
                if focus is not None:
                    also = (focus.key,)
            return show(run_log(book, seat=args.seat, since=args.since, status=args.status, limit=args.limit, also=also), out, as_json)
        if command == "grok":
            return cmd_grok(args, out, err, as_json)
        if command == "login":
            return cmd_login(seats, args, out, err, as_json)
        if command == "migrate":
            from trinity_cli.migrate import run_migrate_command
            return show(
                run_migrate_command(
                    seats, args.seat, args.plan, yes=args.yes, timeout=args.timeout, poll=args.poll,
                    resend_unknown=args.resend_unknown, questions=not args.no_questions, ledger=book, stdin=stdin or sys.stdin,
                ),
                out,
                as_json,
            )
    except BrokenPipeError:
        return 1
    parser.error(f"unknown command {command}")
    return 2


def cmd_status(seats, out, as_json: bool) -> int:
    reports = collect_status(seats)
    emit(out, dumps(status_json(reports)) if as_json else render_status(reports))
    return status_exit(reports)


def _digest_states(reports) -> list[str]:
    states = []
    for _seat, result in reports:
        if result.state == FAILED:
            states.append(FAILED)
            continue
        value = result.value
        if result.state == "ok" and isinstance(value, ReadOutcome) and value.failures and not value.batches:
            states.append(FAILED)
            continue
        states.append(result.state)
    return states


def cmd_digest(seats, args, out, err, state: State, as_json: bool, *, allow_discover: bool = False) -> int:
    try:
        since = parse_since(args.since) if args.since else None
    except ValueError as exc:
        print(str(exc), file=err)
        return 2
    if getattr(args, "bot", None) or getattr(args, "account", None):
        seats, error = _with_adhoc(seats, args.bot, args.account, allow_discover=allow_discover)
        if error:
            print(error, file=err)
            return 2
    limits = {}
    if args.limit:
        limits["dot"] = args.limit
        for seat in seats:
            if is_grok(seat):
                limits[seat.key] = args.limit
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
    return aggregate_exit(_digest_states(reports))


def cmd_ask(seats, args, out, err, ledger: Ledger, stdin, as_json: bool, *, allow_discover: bool = False) -> int:
    words = list(args.words)
    bot = args.bot or args.grok_bot
    # `ask grok 研究員 "..."` names the bot on the default seat. One quoted argument is the message.
    if args.seat == "grok" and not args.bot and not args.account and not args.grok_bot and len(words) >= 2:
        bot = words.pop(0)
    text = " ".join(words).strip()
    if not text and not stdin.isatty():
        text = stdin.read().strip()
    if not text:
        print("沒有訊息內容：`trinity-cli ask all \"...\"`，或從 stdin 傳入。", file=err)
        return 2
    if args.bot or args.account:
        seats, error = _with_adhoc(seats, args.bot or bot, args.account, allow_discover=allow_discover)
        if error:
            print(error, file=err)
            return 2
        target = find_seat(seats, "grok")
        pairs = [(target, None)] if target else []
    elif args.seat == "all":
        pairs = [(seat, bot if is_grok(seat) and bot and not getattr(seat, "pinned_bot", None) else None) for seat in seats]
    else:
        seat = find_seat(seats, args.seat)
        pairs = [(seat, bot if seat is not None and is_grok(seat) else None)] if seat else []
    if not pairs or pairs[0][0] is None:
        print(f"沒有 {args.seat} 這個座位。{UNKNOWN_SEAT_HINT}", file=err)
        return 2
    nonce = new_nonce()
    ask_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{nonce}"
    rows = run_ask(pairs, text, nonce, ask_id=ask_id, ledger=ledger, timeout=args.timeout, poll=args.poll)
    shown = rows[0].nonce if len(rows) == 1 else ""
    if as_json:
        emit(out, dumps(ask_json(rows, ask_id=ask_id, nonce=shown)))
    else:
        emit(out, render_ask(rows, nonce=shown, timeout=args.timeout, ledger_path=tilde(ledger.path)))
    return ask_exit(rows)


def cmd_grok(args, out, err, as_json: bool) -> int:
    if args.grok_command == "bots":
        rows = discover(Runner())
        emit(out, dumps(bots_json(rows)) if as_json else render_bots(rows))
        return 0
    if args.grok_command == "add":
        try:
            backup = add_grok_seat(args.name, args.account, args.bot, default=args.default)
        except ValueError as exc:
            print(str(exc), file=err)
            return 2
        note = f"已加入 {args.name}。"
        if backup:
            note += f" 備份：{backup.name}"
        emit(out, dumps({"name": args.name, "backup": str(backup) if backup else ""}) if as_json else note)
        return 0
    if args.grok_command == "remove":
        try:
            backup = remove_grok_seat(args.name)
        except ValueError as exc:
            print(str(exc), file=err)
            return 2
        note = f"已移除 {args.name}。"
        if backup:
            note += f" 備份：{backup.name}"
        emit(out, dumps({"name": args.name, "backup": str(backup) if backup else ""}) if as_json else note)
        return 0
    print("請用 grok bots、grok add 或 grok remove。", file=err)
    return 2


def cmd_login(seats, args, out, err, as_json: bool) -> int:
    if args.api_key and args.web:
        print("不能同時用 --api-key 和 --web。", file=err)
        return 2
    if (args.api_key or args.web) and args.seat != "muse":
        print("只有 Muse 能用 --api-key 或 --web。", file=err)
        return 2
    seat = find_seat(seats, args.seat)
    if seat is None:
        print(f"沒有 {args.seat} 這個座位。{UNKNOWN_SEAT_HINT}", file=err)
        return 2
    if args.web:
        mode = "web"
    elif args.api_key:
        mode = "api-key"
    else:
        mode = "token"
    result = seat.login(mode=mode)
    ok = result.state == "ok"
    message = scrub_ids(str(result.value) if ok else (result.error or ""))
    hint = scrub_ids(result.hint or "")
    text = f"{message}\n{hint}" if hint else message
    data = {"seat": args.seat, "ok": ok, "message": message, "hint": hint}
    emit(out, dumps(data) if as_json else text)
    if ok:
        return 0
    if result.state == "unsupported":
        return 2
    return 1

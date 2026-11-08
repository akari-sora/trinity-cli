# trinity-cli reference

English | [繁體中文](reference.zh-TW.md)

The [README](../README.md) covers install, quick start, and the command list. This page has the details.

- [Install details](#install-details)
- [First-time setup](#first-time-setup)
- [Output shapes](#output-shapes)
- [Command reference](#command-reference)
- [Concepts](#concepts)
- [Exit codes](#exit-codes)
- [Files and environment variables](#files-and-environment-variables)
- [Troubleshooting](#troubleshooting)
- [Platforms](#platforms)

## Install details

The pinned install commands and the `--version` check are in the [README](../README.md#install). Why these pins: the older muse-web-cli v0.1.2 has no `credential` and no api gateway; v0.1.3's `send --wait` can miss the reply in a long chat; v0.1.4 does not recognize Muse's current sidebar shell, so the browser backend reports `ui_changed`.

`pipx` can replace `uv tool install` for trinity, chatgpt-dot-cli, and muse-web-cli.

On Windows, npm's `gbot` is `gbot.cmd` and uv tools are `.exe`. trinity finds them with `shutil.which`. For an npm wrapper such as `gbot.cmd`, trinity runs node on the script it points to, so cmd.exe never sees the arguments. Any other `.cmd` or `.bat` goes through cmd.exe with every argument quoted, and an argument containing `"`, `%`, or a line break is refused. Windows also needs Node.js 22.19.0+.

Upgrade to the same pin by running the install again. Add `--force` for `uv`. For gbot, download the same `.tgz` and install it again.

Uninstall:

```bash
uv tool uninstall trinity-cli
uv tool uninstall chatgpt-dot-cli
uv tool uninstall muse-web-cli
npm uninstall -g grok-bot-cli
```

`pipx uninstall` matches the three uv tools. In this checkout, `uv tool install --editable .`.

## First-time setup

1. Your dot: `codex login`. Run it again on a 401. `trinity-cli login dot` does the same. Set `TRINITY_DOT_ID` when the account has more than one dot. See the [chatgpt-dot-cli troubleshooting](https://gitlab.com/aa22396584/chatgpt-dot-cli/-/blob/main/docs/reference.md#troubleshooting) section.
2. Grok Bot: sign in with the Grok Bot app and create at least one bot there. `trinity-cli login grok` only repeats that; it does not read the session. Then run `trinity-cli grok bots` to see the bots on each login label, and save one as a seat: `trinity-cli grok add researcher --account LABEL --bot "BOT NAME" --default`. With one login and one bot, `grok` works without a saved seat. See the [grok-bot-cli install](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) section.
3. Muse defaults to the browser backend: `muse-web-cli login` in a visible window, then `muse-web-cli start --headless`. Or `trinity-cli login muse --web`. The api backend (`--muse-backend api`, the Muse gateway) needs a credential: `trinity-cli login muse` runs `muse-web-cli credential`, which logs in when needed and writes the gateway token only to `~/.trinity-cli/muse-credential` (mode 600), never printing it. That file is a token; do not share or commit it. An expired token is reported as 登入工作階段已失效 ("login session expired"); sign in again in Chrome and rerun. `--api-key` still passes a key from stdin to `muse auth set --api-key-stdin`. See the [muse-web-cli troubleshooting](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/docs/reference.md#troubleshooting) section.
4. Several Grok seats are keyed by login label plus bot name. `grok` means `grok_default`. Fake values:

```json
{
  "grok_default": "researcher",
  "grok_seats": [
    {"name": "researcher", "account": "example-login-a", "bot": "Researcher"},
    {"name": "writer", "account": "example-login-b", "bot": "Writer"}
  ]
}
```

The old `gbot_account` plus `grok_bot` still works as one seat named `grok`. `TRINITY_GBOT_ACCOUNT` and `TRINITY_GROK_BOT` override only that legacy seat. Config edits keep a backup. Muse may also set `"muse_backend"` to `"browser"`, `"api"`, or `"auto"` (fake values; omit it to keep muse-web-cli's browser default).

5. Confirm with `trinity-cli status`. One line per seat. Things waiting on you come first.

## Output shapes

Shape of `status`:

```text
等你處理：
  • 等你處理：範例待辦

Your dot  ✓ 連線正常
Grok Bot   ✓ 連線正常
Muse       ✓ 連線正常 · 背景 · 主聊天室
```

Shape of `digest`:

```text
10-01 09:00  Your dot  你  今天進度？
10-01 09:01  Your dot  Your dot  進行中。

共 2 則新訊息。
```

`ask all` prints each seat's first reply side by side, with the nonce and the ledger path in the footer. `hand` prints a preview and asks. `wait` on a timeout says it did not resend.

## Command reference

With no subcommand, `status` runs. `--json` may appear before or after the command and switches to JSON. `--version` prints `trinity-cli` and the version.

### `status`

`status` has no flags. Exit 0 unless a seat failed. Unsupported is not a failure. `--json`: `waiting` (array of strings), `seats[]` with `seat`, `label`, `state`, plus `summary`, `waiting`, `problems`, `hint`, `details` on success, or `error` and `hint` on failure.

```bash
trinity-cli status
trinity-cli --json status
```

### `digest`

`digest` builds one timeline and moves cursors only after the output is printed.

| Flag | Default | Range |
| --- | --- | --- |
| `--since` | no lookback | `30m`, `2h`, `1d`, `1w`, or ISO; does not move cursors |
| `--peek` | off (cursors move) | on leaves cursors where they are |
| `--no-activity` | off | skip Your dot activity and Muse activity |
| `--limit` | dot 30, Grok 40, Muse 40 | applies to dot (1..32) and Grok (1..200) only; Muse stays at 40, max 100 |

```bash
trinity-cli digest --peek
```

`--json`: `items[]` (`at`, `source`, `speaker`, `from_agent`, `text`, `gap_before`), `gaps`, `failures` (`source`, `error`, `hint`), `unsupported` (`seat`, `label`, `reason`), `notes`, `advanced`.

### `ask`

`ask SEAT TEXT` sends once, then waits for the first reply. A timeout does not resend.

| Argument or flag | Default | Range |
| --- | --- | --- |
| `seat` | required | `all`, `dot`, `grok`, `muse` |
| remaining words | empty reads stdin | `ask grok NAME TEXT` uses the first word as the bot when there are two or more words; one quoted string is the whole message |
| `--grok-bot` | `TRINITY_GROK_BOT`, else `grok_bot`, else the only bot | one bot name |
| `--timeout` | 180 | seconds; no resend |
| `--poll` | 10 | seconds between readbacks |

```bash
trinity-cli ask muse "今天進度？"
```

`--json`: `ask_id`, `nonce`, `results[]` with `seat`, `target`, `state`, `send`, `readback`, `reply` (`at`, `speaker`, `text`), `error`, `hint`.

### `hand`

`hand SOURCE --to DEST INSTRUCTION` forwards one reply. It previews first. A terminal asks; without a terminal, `--yes` is required or nothing is sent. It does not chain.

| Argument or flag | Default | Range |
| --- | --- | --- |
| source | required | `dot#last`, `grok:BOT#last`, `muse#last`; `#2` is the second newest |
| `--to` | required | `dot`, `grok`, `grok:BOT`, `muse` |
| `--yes` | off | send without asking |
| `--timeout` | 180 | seconds; no resend |
| `--poll` | 10 | seconds |
| instruction | required | what the destination should do |

```bash
trinity-cli hand dot#last --to muse "請看這則"
```

`--json` is the preview or send result: `sent`, `confirmed`, `state`, `error`, `hint`.

### `wait`

`wait TARGET` waits for a new reply after the latest ledger mark. It does not resend.

| Argument or flag | Default | Range |
| --- | --- | --- |
| target | required | `dot`, `muse`, `grok` (the default Grok seat), `grok:BOT`, or a seat name |
| `--timeout` | 180 | seconds |
| `--poll` | 5 | first gap, then doubles, capped at 30 seconds |
| `--notify` | off | terminal bell and a macOS notification, with no message body |
| `--then` | do nothing | only `hand ...`, and only last; skipped when no reply arrives |

```bash
trinity-cli wait dot --timeout 60
```

`--json`: `state`, `seat`, `target`, `polls`, `sent`, `error`, and `then` when `--then` ran.

### `schedules`

`schedules` has no flags of its own. Your dot uses `automations`. Grok is read only when `gbot --help` mentions `schedules`, `routines`, or `automations`. Muse reads `upcoming` and `activity` (marked 動態). `--muse-backend` may be set on this command. A missing capability is unsupported and does not fail the command. Matching titles or times across seats are flagged.

```bash
trinity-cli schedules
```

`--json`: `seats`, `duplicates`.

### `who`

`who TASK` only suggests. It sends nothing. The task is required.

```bash
trinity-cli who "翻譯這段"
```

`--json`: `advisory`, `suggestion`, `headline`, `ranking`.

### `brief`

`brief` reads and writes `~/.trinity-cli/brief.md`.

| Subcommand | Flags | Default |
| --- | --- | --- |
| `show` | none | print the file; a missing file still exits 0 |
| `init` | none | write a short template only when the file is absent |
| `diff` | `--grok-bot` | compare with each seat; Muse memory is read only. A missing file exits 0 and points at `brief init` |
| `push` | `--yes`, `--grok-bot` | ask first. Writes only when Grok has `bots update --instructions`. Your dot and Muse get a draft and no message. Above 32000 characters, nothing is written |

```bash
trinity-cli brief init
trinity-cli brief show
trinity-cli brief diff
trinity-cli brief push
```

`--json`: `show` has `path` and `text` or `missing`; `init` has `path` and `created`; `diff` has `path` and `seats`; `push` has `path`, `updated`, `sent`, `confirmed`.

### `log`

`log` only reads the ledger.

| Flag | Default | Range |
| --- | --- | --- |
| `--seat` | all | `dot`, `grok`, `muse` |
| `--since` | all records | `30m`, `2h`, `1d`, `1w`, or ISO |
| `--status` | any | matches `event`, `reply`, or `readback`, such as `sent`, `replied`, `timed_out` |
| `--limit` | 50 | minimum 1 |

```bash
trinity-cli log --seat dot --since 2h --limit 20
```

`--json`: `records` (ledger fields, without internal ids).

### `migrate`

`migrate SEAT PLAN` delivers a migration plan written by another tool (`trinity-migration-plan` v1, for example from `gbot migrate import --to muse`) to Muse or Your dot, reads it back, then asks acceptance questions. SEAT is `muse` or `dot`.

| Flag or argument | Default | Range |
| --- | --- | --- |
| `SEAT` | required | `muse`, `dot` |
| `PLAN` | required | JSON plan; unknown fields are refused |
| `--yes` | off | send without asking; required when stdin is not a terminal |
| `--timeout` | 300 | seconds to wait for each reply; a timeout never resends |
| `--poll` | 10 | seconds between read-backs |
| `--resend-unknown` | off | allow resending a step whose earlier send could not be read back |
| `--no-questions` | off | deliver and read back only |
| `--redo` | none | comma-separated step ids to send again although they were answered |
| `--min-interval` | 20 | seconds between two sends, at the pace of a person using the app; every message waits for its reply first. A rate-limit answer (429, "too many") stops the run without resending; run the same line later to continue from that step. When a step's reply says so, the next step is not sent and that step is resent only with `--redo STEP`. The time of the last send is kept in the progress file, so the gap also holds across runs. A question that cannot be sent (not sent, rate limit, timeout) stops the remaining questions |
| `--check-only` | off | send no step; read back and ask the questions only. A step the progress file does not record as delivered with a matching reply is `not delivered` and the result is not ok. No `--yes` needed; not with `--redo` |

Each step is one message (it can attach files, see the plan's `attach`: absolute paths or `{"path": …, "sha256": …}`; the sha256 is computed again before sending and a mismatch stops the run before anything is sent) with a nonce, written to the ledger before it leaves and confirmed by read-back, like `ask`. Progress is kept in `TRINITY_HOME/migrations/<plan id>.json`: when a run stops (timeout, expired login, Ctrl-C), run the same command again. Replied steps are skipped, and a step whose delivery is unknown is first looked up in the chat and not resent when it is there. Replies are checked against `expectReply` on every run, so a reply that missed stays a miss. A progress file that cannot be read, or another migrate already running the same plan, stops the run before anything is sent; so does a step whose text changed after it was sent (send the new text with `--redo STEP`). The acceptance questions go to a new side chat (the `created` id muse-web-cli `chats --create` reports), and only that chat is deleted afterwards; if it cannot be opened, the questions are not asked and fail. Muse is one agent with shared memory but many chats: when the plan has `chat`, the api backend opens (or reuses) a side chat with that title, every step goes there, and the switched chat is set back to main afterwards; without the api backend the open chat is used and the result says so. A dot account has one inbox, so steps go there. Afterwards Muse's Memory.md is checked for the plan's keywords (a required read-back that cannot be read fails); a dot's memory cannot be read, so the acceptance questions are the read-back. Exit 0 means delivered, read back and accepted; 1 means not finished (see `stopped`); 2 is usage or no confirmation.

migrate needs these seat-tool features: muse-web-cli `chats --create` reporting the `created` id, `send --attach` and `--attach-sha256`, and chatgpt-dot-cli `send --attach` and `--attach-sha256`. muse-web-cli v0.1.7 and chatgpt-dot-cli v0.2.6 (the versions the README pins) have them.

```bash
trinity-cli migrate muse ~/.grok-bot-cli/migrations/example.muse-plan.json --yes
```

`--json`: `plan_id`, `seat`, `ok`, `stopped`, `state_path`, `chat`, `chat_note`, `steps[]` (`id`, `state`, `ok`, `note`, `nonce`, `reply`), `checks[]`, `questions[]`.

### `login`

`login SEAT` does not print a credential.

| Argument or flag | Default | Range |
| --- | --- | --- |
| seat | required | `dot`, `grok`, `muse` |
| `--api-key` | off | Muse only; stdin goes to `muse auth set`. Cannot be combined with `--web` |
| `--web` | off | Muse only; headed `muse-web-cli login` |

```bash
trinity-cli login muse --web
```

`--json`: `seat`, `ok`, `message`, `hint`.

### `grok`

`grok bots` lists every bot on every `gbot accounts` login: name, description, login label, reachable or not, and whether it is a configured seat. It does not print ids.

`grok add NAME --account LABEL --bot BOT` writes a seat, with optional `--default`. `grok remove NAME` deletes that seat. Both keep a backup of `config.json`.

```bash
trinity-cli grok bots
trinity-cli grok add researcher --account example-login-a --bot "Researcher" --default
trinity-cli grok remove writer
trinity-cli ask researcher "one sentence"
trinity-cli ask grok --bot "Other" --account example-login-a "ask this one without saving a seat"
trinity-cli ask all "ask every seat"
```

### Seat names

`status`, `digest`, `ask`, `hand`, `wait`, `schedules`, `who`, `brief push`, and `log` accept a seat name. `grok` is the default seat. `all` is dot, every enabled Grok seat, and muse. Each send gets its own nonce. When the same bot name exists on two logins, `--bot` requires `--account`. `wait` and `digest` take those flags too.

## Concepts

The seats do not have the same capabilities. A missing one is reported as unsupported, still exit 0, and does not fail the others. `muse-web-cli` defaults to the browser backend; `api` is the Muse gateway and reads `~/.trinity-cli/muse-credential`. trinity passes `--backend`: `--muse-backend` wins over config `muse_backend`, which wins over `MUSE_WEB_BACKEND`. With none of those set, trinity omits `--backend` and muse-web-cli keeps its own default. The value is `browser`, `api`, or `auto`. `auto` tries api first and uses browser for a capability only when that call exits 4, and the line names the backend that served it. A timed-out `send` is not tried on the other backend. An unsupported api capability with no fallback is reported on its own and trinity does not crash. Muse has no instruction API. Grok groups work with `ask grok <group>` and `grok:<name>` on `hand` / `wait`; `status` and `digest` cover bots only.

Cursors live in `cursors` inside `state.json`, and each Grok seat has its own key (for example `researcher.messages`). Only `digest` moves them, and only after the output was printed. `--peek`, `--since`, `hand`, and `wait` do not. When the previous tail is gone, the timeline says 可能漏看 ("possibly missed"). One unreachable Grok seat does not stop the others; that seat is a failure with the re-login hint.

Every `ask` and `hand` writes `ledger.jsonl` before the send. Your text is unchanged, then a blank line and `[trinity abc123]`. Readback looks for that tag in your own messages. A timeout is reported and never resent.

Before a Muse read or send, trinity calls `chats`. A side chat is not sent into and does not move the Muse cursor. Status says 目前在副聊天室. If `chats` is unsupported or the switcher panel is missing, the open conversation is used and the status line says so. Chat titles are never printed.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Fine. Unsupported counts as fine. Exit 0 when any targeted seat succeeds; a failure is still printed |
| 1 | Every targeted seat that counts failed or timed out. `hand` and `wait` have one target |
| 2 | Bad usage, or `hand` / `brief push` sent nothing because nobody confirmed |

| Seat state | Fix |
| --- | --- |
| Your dot 401 or unusable login | `codex login`. See [chatgpt-dot-cli troubleshooting](https://gitlab.com/aa22396584/chatgpt-dot-cli/-/blob/main/docs/reference.md#troubleshooting) |
| Your dot network or non-200 | Try `chatgpt-dot-cli list` |
| chatgpt-dot-cli missing | Install it, or set `TRINITY_DOT_CLI` |
| Several Grok logins or bots | `trinity-cli grok bots`, then `trinity-cli grok add NAME --account LABEL --bot BOT --default`. See the [grok-bot-cli install](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) section. |
| Grok login unusable | Open the Grok Bot app and run `gbot doctor` |
| gbot missing | Install it, or set `TRINITY_GBOT` |
| Muse browser down | `muse-web-cli start --headless` |
| Muse browser session expired | `muse-web-cli login`. See [muse-web-cli troubleshooting](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/docs/reference.md#troubleshooting) |
| Muse api credential missing | `trinity-cli login muse` |
| Muse api login session expired | Sign in to Muse again in the Chrome window, then `trinity-cli login muse` |
| Muse credential file mode | macOS/Linux: `chmod 600 ~/.trinity-cli/muse-credential`. Windows: `icacls` so only the current user can read it |
| Muse on a side chat | Switch back to the main chat in the Muse window |
| Muse profile busy | Quit that window, then `muse-web-cli start --headless` |
| Muse region blocked | This tool does not bypass a region limit |
| muse-web-cli or muse missing | Install it, or set `TRINITY_MUSE_CLI` or `TRINITY_MUSE` |

## Files and environment variables

Data lives in `TRINITY_HOME`, or `.trinity-cli` under the home directory when that is unset.

| Path | Contents |
| --- | --- |
| `config.json` | `grok_seats`, `grok_default`. Old `gbot_account` and `grok_bot` still load. Not a token |
| `state.json` | Cursors. No secrets |
| `ledger.jsonl` | Every send |
| `brief.md` | The local brief |

`~/.trinity-cli/muse-credential` always lives under the home directory, not `TRINITY_HOME`. It holds the Muse gateway token, mode 600, written by `login muse` (`muse-web-cli credential`) and read only by `muse-web-cli --backend api`. trinity never reads or prints it.

| Variable | Use |
| --- | --- |
| `TRINITY_HOME` | That data directory |
| `TRINITY_DOT_CLI`, `TRINITY_GBOT`, `TRINITY_MUSE_CLI` | Paths of the three seat tools |
| `TRINITY_MUSE`, `TRINITY_CODEX` | `muse` for `login muse`, `codex` for `login dot` |
| `TRINITY_DOT_ID` | Which dot, when there are several |
| `TRINITY_GROK_BOT` | Default bot; wins over `grok_bot` |
| `TRINITY_GROK_BOTS` | Bots included by `status` / `digest`, comma-separated |
| `TRINITY_GBOT_ACCOUNT` | Login label; wins over `gbot_account` |

## Troubleshooting

- gbot has several logins and cannot choose: run `trinity-cli grok bots`, then `grok add`. The flag goes after the subcommand.
- A login whose bot list is HTTP 404: `unreachable: sandbox gone — re-login this account in the Grok Bot app`. That is not an expired token. Re-login that account in the Grok Bot app. gbot has no re-login command. Other seats keep working.
- Grok replied and trinity used to miss it: a spoken reply is a `send-message` entry whose `message.type` is `text`, not `role: assistant`. Approval cards are not replies.
- Muse browser down: `muse-web-cli start --headless`. Session expired: `muse-web-cli login`.
- Your dot activity is slow: `digest --no-activity`.
- For a tool's own errors, use the troubleshooting links in [Exit codes](#exit-codes).

## Platforms

| OS | Python | How it was checked |
| --- | --- | --- |
| Linux | 3.11, 3.12 | GitLab CI: the full offline suite; `contract:muse` runs the README-pinned muse-web-cli in a temporary home |
| Windows | 3.12 | GitLab CI: the same offline suite, run automatically when code, tests, or dependencies change |
| macOS | 3.11, 3.12, 3.13 | Maintainer machine: the same offline suite, plus a first-run check that installs from the tags as the README says |

The tests use fake seat tools and contact no service. Each seat tool has its own platform table in its docs. CI uses GitLab.com runners by default. Maintainers can point jobs at their own runners by setting the CI/CD variables `LINUX_RUNNER_TAG` and `WINDOWS_RUNNER_TAG`.

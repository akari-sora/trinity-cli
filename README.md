# trinity-cli

English | [繁體中文](README.zh-TW.md)

One command in front of three always-on personal agents: ChatGPT Your dot, Grok Bot, and Meta Muse.

> Canonical repository and issues: <https://gitlab.com/aa22396584/trinity-cli>.

[![pipeline](https://gitlab.com/aa22396584/trinity-cli/badges/main/pipeline.svg)](https://gitlab.com/aa22396584/trinity-cli/-/pipelines)
[![release](https://gitlab.com/aa22396584/trinity-cli/-/badges/release.svg)](https://gitlab.com/aa22396584/trinity-cli/-/releases)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## What it does

- Checks on, catches up with, asks, forwards between, and waits on the three seats from one place. It needs Python 3.11+.
- It does not talk to those services itself. It shells out to three tools:
  - Your dot: `chatgpt-dot-cli --json`
  - Grok Bot: `gbot --json` (the grok-bot-cli fork)
  - Muse: `muse-web-cli --json --autostart`
- A seat that lacks a capability is reported as unsupported and does not fail the others.
- Every send is written to a local ledger first, tagged with a nonce, and confirmed by reading it back. A timeout is never resent.

Supported systems: see [Platforms](docs/reference.md#platforms).

## Install

v0.5.3 pins these versions. After installing trinity and each seat tool, check every `--version`: expect `muse-web-cli 0.1.7`, `trinity-cli 0.5.3`, and `gbot 0.11.2`.

macOS and Linux need Python 3.11+, git, and `uv` on `PATH`. Grok also needs Node.js 22.19.0+ and npm. uv installs commands under `~/.local/bin`; add that directory to `PATH` when `--version` cannot find them. The first `uv tool install` may download a Python.

`npm install -g git+https://gitlab.com/aa22396584/grok-bot-cli.git#...` exits 0 but leaves a dangling `gbot`. npm installs the package file attached to grok-bot-cli tag `v0.11.2-iml1s.14` straight from its release link (`…/-/releases/<tag>/downloads/grok-bot-cli-0.11.2.tgz`); the trinity-cli version pin is separate. To always take the newest gbot instead, put `permalink/latest` in place of the tag.

```bash
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.6"
npm install -g https://gitlab.com/aa22396584/grok-bot-cli/-/releases/v0.11.2-iml1s.14/downloads/grok-bot-cli-0.11.2.tgz
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.7"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.5.3"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

Windows (PowerShell, same pins):

```powershell
irm https://astral.sh/uv/install.ps1 | iex
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.6"
npm install -g https://gitlab.com/aa22396584/grok-bot-cli/-/releases/v0.11.2-iml1s.14/downloads/grok-bot-cli-0.11.2.tgz
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.7"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.5.3"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

pipx, Windows notes, upgrade, and uninstall: [Install details](docs/reference.md#install-details).

## Set up

1. Your dot: `codex login` (or `trinity-cli login dot`).
2. Grok Bot: sign in with the Grok Bot app and create at least one bot there. Then `trinity-cli grok bots`, and save one as a seat: `trinity-cli grok add researcher --account LABEL --bot "BOT NAME" --default`. See the [grok-bot-cli install](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) section.
3. Muse (browser backend, the default): `muse-web-cli login`, then `muse-web-cli start --headless`. For the api backend: `trinity-cli login muse`.
4. Confirm with `trinity-cli status`.

Several Grok seats, the config file, and the Muse backend choice: [First-time setup](docs/reference.md#first-time-setup).

## Quick start

```bash
trinity-cli status
trinity-cli digest --peek
trinity-cli ask all "今天進度？"
trinity-cli hand dot#last --to grok:example-bot "請看這則"
trinity-cli wait grok:example-bot
```

What they print: [Output shapes](docs/reference.md#output-shapes).

## Commands

| Command | What it does |
| --- | --- |
| `status` | one line per seat; things waiting on you first (the default command) |
| `digest` | new messages from every seat in one timeline; `--peek` and `--since` leave the read position alone |
| `ask` | send the same text to `all`, `dot`, `grok`, a seat name, or `muse`, and wait for each first reply |
| `hand` | forward one seat's reply to another, after a preview and a confirmation; does not chain |
| `wait` | wait for a new reply after the ledger mark; never resends |
| `schedules` | automations per seat; duplicate titles or times are flagged |
| `who` | suggest a seat for a task; sends nothing |
| `brief` | `show`, `init`, `diff`, or `push` the shared `~/.trinity-cli/brief.md` |
| `log` | read the send ledger |
| `migrate` | deliver a migration plan (from `gbot migrate import`) to Muse or Your dot, read it back, ask acceptance questions |
| `login` | sign a seat in through its own CLI; credentials are never printed |
| `grok` | `bots` lists Grok bots across logins; `add` and `remove` edit seats |

`--json` may appear before or after the command. `--muse-backend browser|api|auto` picks the Muse backend for one command. Every flag and JSON key: [Command reference](docs/reference.md#command-reference).

## Safety and privacy

- trinity does not ask an agent to delete files, message anyone, buy anything, or change settings or accounts. `brief push` writes a Grok bot's instructions only after you confirm.
- `hand` and `brief push` ask first; without a terminal they send nothing unless you pass `--yes`. `hand` does not forward the destination's reply onward. A timeout is never resent. Live sends are labeled as sends and written to the ledger.
- It does not read `~/.codex/auth.json`, the Grok Bot app session, or Muse cookies. `login` only hands off to those public CLIs and does not print a credential. The one login that stores a token is `login muse`: it has `muse-web-cli credential` write the Muse gateway token only to `~/.trinity-cli/muse-credential` (mode 600) for `--muse-backend api`. trinity itself never reads or prints that file. That file is a token; do not share or commit it.
- trinity has no telemetry and makes no network requests of its own. The three seat tools make the requests, each to its own service.
- Data stays on your machine in `TRINITY_HOME`. `ledger.jsonl` records times, seats, bot names, nonces, and outcomes, not message text. `state.json` holds cursors only.
- Text output shows your home directory as `~`; `--json` keeps full paths. `grok bots` and `log` print no ids, and printed errors have token and cookie values removed. Still check output for message text or names before pasting it into an issue.

## For agents

- Add `--json` for machine-readable output. Exit 0 means at least one targeted seat succeeded (unsupported counts as fine; failures are still printed), 1 means every targeted seat that counts failed or timed out, 2 is bad usage or a `hand` / `brief push` that nobody confirmed. See [Exit codes](docs/reference.md#exit-codes).
- A timeout is reported, not resent. `trinity-cli log` and `trinity-cli digest --peek` show what arrived.
- The skill is `skills/trinity-cli/SKILL.md`. Link it only when the directory already exists, for example `ln -sfn "$PWD/skills/trinity-cli" ~/.claude/skills/trinity-cli`. The same set: `~/.codex/skills`, `~/.agents/skills`, `~/.config/opencode/skills`, `~/.config/opencode/skill`, `~/.cursor/skills`, `~/.grok/skills`.

## Documentation

- [docs/reference.md](docs/reference.md): install details, first-time setup, output shapes, every command, concepts (backends, cursors, ledger, side chats), exit codes and seat fixes, files and environment variables, troubleshooting, platforms.
- [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) (report security problems there, not in a public issue), [CHANGELOG.md](CHANGELOG.md).

## Related projects

- trinity-cli (this repo) — one CLI over three always-on agents (Your dot, Grok Bot, Muse): <https://gitlab.com/aa22396584/trinity-cli>
- chatgpt-dot-cli — ChatGPT Your dot: <https://gitlab.com/aa22396584/chatgpt-dot-cli>
- grok-bot-cli (fork, `gbot`) — Grok Bot: <https://gitlab.com/aa22396584/grok-bot-cli>
- muse-web-cli — Meta Muse via the web: <https://gitlab.com/aa22396584/muse-web-cli>

## License and disclaimer

[MIT](LICENSE)

Unofficial: this is a personal project, not affiliated with, endorsed by, or supported by OpenAI, xAI, Cursor (Anysphere), or Meta. It uses your own accounts through the three seat tools, which rely on undocumented interfaces that can change or break at any time. Automated use may break a service's terms; any account risk is yours.

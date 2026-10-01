---
name: trinity-cli
description: >-
  Check on, catch up with, ask, forward between, or wait on the user's
  always-on personal agents (ChatGPT Your dot, Grok Bot, and Muse via
  muse-web-cli) through one command, trinity-cli. Use when the user asks "what
  are my agents doing", "anything new from my agents", "check my lobsters",
  "status of dot, grok, and muse", "catch me up", "ask all my agents", "ask
  dot and grok the same thing", "forward that reply", "hand this to grok",
  "wait for dot", "what schedules do my agents have", "which agent should do
  this",   "push the brief", "show the send log", "ask Grok A", "ask Grok B",
  "list Grok bots", "ask all Grok bots", "ask Muse", or "use the Muse api". 當使用者說「我的龍蝦在幹嘛」
  「agent 有什麼新消息」「幫我看一下 dot、Grok 和 Muse」「整理一下新訊息」
  「同一個問題問所有 agent」「問 dot」「問蝴蝶」「問 Muse」「把這則轉給 Grok」
  「轉交」「等 dot 回」「有沒有排程」「該派誰」「更新 brief」
  「看送出紀錄」「幫 muse 取 token」「登入 muse」
  「問 Grok A」「問 Grok B」「列出 Grok bots」「問所有 Grok」
  「問 Muse」「用 Muse api」時使用。
---

# trinity-cli

Reply in the user's language.

1. Run `trinity-cli status` (about 10 seconds). If it is not on PATH, run `uv run trinity-cli status` inside the trinity-cli repo. Report the "等你處理" lines first, then one line per seat.
2. A line with `✗ 失敗` is a failure, not "nothing new". Tell the user that seat's fix exactly as printed. Common fixes: `codex login` for Your dot, opening the Grok Bot app and running `gbot doctor` for Grok Bot, `muse-web-cli login` when Muse's session expired, and `muse-web-cli start --headless` when its browser is down or the profile is busy. A region block is not something trinity can bypass. Muse is a real seat through `muse-web-cli` (headless or a visible window). Choose the backend with `--muse-backend browser|api|auto`, config `muse_backend`, or `MUSE_WEB_BACKEND`, in that order. With none set, trinity does not pass `--backend`. `auto` tries api and falls back to browser only on exit 4, per capability. A timed-out Muse send is never retried on the other backend. `status` and `who` name the backend that served the result. If a capability is unsupported and there is no fallback, that capability is reported on its own and that is not a failed command. An unsupported schedules or instructions result is also not a failed command. Muse has no instruction API; `brief push` only prints a draft. `schedules` reads Muse `upcoming` and `activity`. Before Muse reads or sends, trinity checks `chats`. If status says 目前在副聊天室, do not send; tell the user to switch back to the main chat in the Muse window. That read is not the main conversation and does not move the Muse cursor. If the status line says `chats` is unsupported or the switcher panel is missing, the open conversation is used. Never print Muse chat titles. A presentation card is not the reply `ask` or `wait` is looking for.
3. To catch up, run `trinity-cli digest` (about 20 seconds; `--no-activity` is faster). This moves the read position, so run it once and summarize. Use `digest --peek` to look without moving it, and `digest --since 2h` to look back. Point out any 可能漏看 ("possibly missed") line. `hand` and `wait` do not move the read position.
4. Run `trinity-cli ask all|dot|grok|grok-a|muse "TEXT"` only when the user asked you to send that text. It sends once, then waits up to 180 seconds. `grok` is the default Grok seat (`grok_default`, or the legacy `grok_bot` seat). A name such as `grok-a` is that seat. `all` is dot, every enabled Grok seat, and muse; each send has its own nonce. `ask grok --bot NAME --account LABEL` reaches a bot that is not a saved seat. The same flags work on `wait` and `digest`. If that bot name exists on more than one login, `--account` is required. `trinity-cli grok bots` lists bots across logins (no raw ids). `grok add` and `grok remove` edit seats and keep a backup. A login that returns HTTP 404 is `unreachable: sandbox gone — re-login this account in the Grok Bot app`; that is not an expired token, and gbot has no re-login command. One unreachable seat does not stop the others. Grok's spoken reply is often a `send-message` entry, not `role: assistant`. Muse sends without `--wait` and then polls messages. If it times out, report that and do not run it again: a rerun is a second send. Check `trinity-cli log` or run `digest --peek` to see what arrived.
5. Run `trinity-cli hand SOURCE#last --to DEST "instruction"` only when the user asked to forward that reply. Show them the preview. Do not pass `--yes` unless they already told you to send it. `hand` does not forward the destination's reply onward.
6. Run `trinity-cli wait SEAT [--timeout] [--notify]` to watch for a new reply. If it times out, stop. Do not send, and do not add `--then hand` unless the user wrote that hop themselves.
7. Run `trinity-cli schedules` to list automations and any duplicate titles. Run `trinity-cli who "task"` when the user asks which seat fits. Quote it as a suggestion. Do not send because of it.
8. The shared brief is `~/.trinity-cli/brief.md`. Use `brief show` and `brief diff` freely. If the file is missing, `brief diff` exits 0 and points at `brief init`. `brief init` writes a short template only when the file does not exist. `brief diff` may read Muse memory; that read does not write. Use `brief push` only when the user asked to update instructions. It can write a Grok bot's instructions after confirmation; Your dot and Muse only get a draft, and that draft must not be sent with `ask` unless the user asked for a send.
9. Use `trinity-cli log` to read the ledger. Use `--json` when you need to parse output. `log --limit` defaults to 50 and must be at least 1.
10. Run `trinity-cli login muse` only when the user asked to sign Muse in or obtain its token. It runs `muse-web-cli credential`, which logs in through the existing Muse window when needed and writes `~/.trinity-cli/muse-credential` (mode 600). Do not read or print the token. `--api-key` passes stdin to `muse auth set --api-key-stdin`. `--web` runs `muse-web-cli login` for the browser seat. `login dot` runs `codex login`. `login grok` only repeats the Grok Bot app instructions. A missing api credential on status is `trinity-cli login muse`, not the browser login.
11. For one seat's own commands, use the `chatgpt-dot-cli` and `muse-web-cli` skills, and `gbot --help`. This skill is only the wrapper: https://gitlab.com/aa22396584/trinity-cli https://gitlab.com/aa22396584/chatgpt-dot-cli https://gitlab.com/aa22396584/grok-bot-cli https://github.com/ImL1s/grok-bot-cli https://gitlab.com/aa22396584/muse-web-cli

Rules:

- Do not read `~/.codex/auth.json` or the Grok Bot app session. Do not print tokens or ids.
- Do not pause, resume, delete, or reconfigure any agent, except `brief push` to a Grok bot when the user asked.
- Exit code 1 means every targeted seat that counts failed or timed out. Unsupported seats do not count. A mix of success and failure is exit 0, and the failure is still printed. `hand` and `wait` have one target. Exit code 2 on `hand` or `brief push` means nothing was sent because it was not confirmed. Read the output instead of retrying blindly.
- Never resend after a timeout. Never chain `hand` on your own. `hand` and `brief push` need confirmation; do not pass `--yes` unless the user already asked to send.
- Do not ask an agent to delete files, message anyone, buy anything, or change settings or accounts.

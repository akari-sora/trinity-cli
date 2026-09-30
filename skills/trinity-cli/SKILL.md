---
name: trinity-cli
description: >-
  Check on, catch up with, ask, forward between, or wait on the user's
  always-on personal agents (ChatGPT Your dot and Grok Bot; Muse is a
  placeholder) through one command, trinity-cli. Use when the user asks "what
  are my agents doing", "anything new from my agents", "check my lobsters",
  "status of dot and grok", "catch me up", "ask all my agents", "ask dot and
  grok the same thing", "forward that reply", "hand this to grok", "wait for
  dot", "what schedules do my agents have", "which agent should do this",
  "push the brief", or "show the send log". 當使用者說「我的龍蝦在幹嘛」
  「agent 有什麼新消息」「幫我看一下 dot 和 Grok」「整理一下新訊息」
  「同一個問題問所有 agent」「問 dot」「問蝴蝶」「把這則轉給 Grok」
  「轉交」「等 dot 回」「有沒有排程」「該派誰」「更新 brief」
  「看送出紀錄」時使用。
---

# trinity-cli

Reply in the user's language.

1. Run `trinity-cli status` (about 10 seconds). If it is not on PATH, run `uv run trinity-cli status` inside the trinity-cli repo. Report the "等你處理" lines first, then one line per seat.
2. A line with `✗ 失敗` is a failure, not "nothing new". Tell the user that seat's fix exactly as printed. Common fixes: `codex login` for Your dot, and opening the Grok Bot app and running `gbot doctor` for Grok Bot. `– 不支援` (Muse) is expected; mention it only if asked. An unsupported schedules or instructions result is also expected and is not a failed command.
3. To catch up, run `trinity-cli digest` (about 20 seconds; `--no-activity` is faster). This moves the read position, so run it once and summarize. Use `digest --peek` to look without moving it, and `digest --since 2h` to look back. Point out any 可能漏看 ("possibly missed") line. `hand` and `wait` do not move the read position.
4. Run `trinity-cli ask all|dot|grok BOT "TEXT"` only when the user asked you to send that text. It sends once, then waits up to 180 seconds. If it times out, report that and do not run it again: a rerun is a second send. Check `trinity-cli log` or run `digest --peek` to see what arrived.
5. Run `trinity-cli hand SOURCE#last --to DEST "instruction"` only when the user asked to forward that reply. Show them the preview. Do not pass `--yes` unless they already told you to send it. `hand` does not forward the destination's reply onward.
6. Run `trinity-cli wait SEAT [--timeout] [--notify]` to watch for a new reply. If it times out, stop. Do not send, and do not add `--then hand` unless the user wrote that hop themselves.
7. Run `trinity-cli schedules` to list automations and any duplicate titles. Run `trinity-cli who "task"` when the user asks which seat fits. Quote it as a suggestion. Do not send because of it.
8. The shared brief is `~/.trinity-cli/brief.md`. Use `brief show` and `brief diff` freely. Use `brief push` only when the user asked to update instructions. It can write a Grok bot's instructions after confirmation; Your dot and Muse only get a draft, and that draft must not be sent with `ask` unless the user asked for a send.
9. Use `trinity-cli log` to read the ledger. Use `--json` when you need to parse output.

Rules:

- Do not read `~/.codex/auth.json` or the Grok Bot app session. Do not print tokens or ids.
- Do not pause, resume, delete, or reconfigure any agent, except `brief push` to a Grok bot when the user asked.
- Exit code 1 means some seat failed or a wait ended with no reply. Exit code 2 on `hand` or `brief push` means nothing was sent because it was not confirmed. Read the output instead of retrying blindly.
- Never resend after a timeout. Never chain `hand` on your own.

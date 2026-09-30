---
name: trinity-cli
description: >-
  Check on, catch up with, or ask the user's always-on personal agents (ChatGPT
  Your dot and Grok Bot; Muse is a placeholder) through one command,
  trinity-cli. Use when the user asks "what are my agents doing", "anything
  new from my agents", "check my lobsters", "status of dot and grok", "catch
  me up", "ask all my agents", or "ask dot and grok the same thing". 當使用者說
  「我的龍蝦在幹嘛」「agent 有什麼新消息」「幫我看一下 dot 和 Grok」「整理一下新訊息」
  「同一個問題問所有 agent」「問 dot」「問蝴蝶」時使用。
---

# trinity-cli

Reply in the user's language.

1. Run `trinity-cli status` (about 10 seconds). If it is not on PATH, run `uv run trinity-cli status` inside the trinity-cli repo. Report the "等你處理" lines first, then one line per seat.
2. A line with `✗ 失敗` is a failure, not "nothing new". Tell the user that seat's fix exactly as printed. Common fixes: `codex login` for Your dot, and opening the Grok Bot app and running `gbot doctor` for Grok Bot. `– 不支援` (Muse) is expected; mention it only if asked.
3. To catch up, run `trinity-cli digest` (about 20 seconds; `--no-activity` is faster). This moves the read position, so run it once and summarize. Use `digest --peek` to look without moving it, and `digest --since 2h` to look back. Point out any 可能漏看 ("possibly missed") line.
4. Run `trinity-cli ask all|dot|grok BOT "TEXT"` only when the user asked you to send that text. It sends once, then waits up to 180 seconds. If it times out, report that and do not run it again: a rerun is a second send. Check `~/.trinity-cli/ledger.jsonl` or run `digest --peek` to see what arrived.
5. Use `--json` when you need to parse the output.

Rules:

- Do not read `~/.codex/auth.json` or the Grok Bot app session. Do not print tokens or ids.
- Do not pause, resume, delete, or reconfigure any agent.
- Exit code 1 means some seat failed or `ask` got no reply. Read the output instead of retrying blindly.

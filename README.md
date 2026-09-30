# trinity-cli

[中文](#中文) · [English](#english)

## 中文

`trinity-cli` 是一個指令，擋在你那幾個 24 小時在線的個人 agent（「龍蝦」）前面。v1 包兩個：ChatGPT 的 Your dot 和 Grok Bot。Muse（Meta 的個人 agent）沒有公開 API／CLI，而且只開放美國和加拿大，所以 v1 只留一個 Muse 座位，永遠顯示「不支援（沒有公開 API）」，不會讓指令失敗。

trinity 不自己連服務，也不碰登入：Your dot 走 `chatgpt-dot-cli --json`，Grok Bot 走 `gbot --json`。它不讀 `~/.codex/auth.json`，也不讀 Grok Bot app 的登入。

### 安裝

1. `chatgpt-dot-cli`：`uv tool install git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.1.3`。401 時跑 `codex login`。
2. `gbot`：clone 使用者的 fork `ImL1s/grok-bot-cli`，在 clone 裡跑 `node --test && npm link`。需要 Node 18+ 和已登入的 Grok Bot macOS app。
3. trinity 本身（需要 Python 3.11+ 和 uv）：

   ```bash
   cd trinity-cli && uv tool install .
   trinity-cli status
   ```

找不到 `chatgpt-dot-cli` 或 `gbot` 時，用 `TRINITY_DOT_CLI`、`TRINITY_GBOT` 指定路徑。

### 指令

```bash
trinity-cli status                     # 每個座位一行；等你處理的事排最上面
trinity-cli digest                     # 所有座位的新訊息合成一條時間線
trinity-cli digest --since 2h          # 回看兩小時（不動讀取位置）
trinity-cli ask all "今天進度？"        # 同一段話問每個座位，並排印出第一個回覆
trinity-cli ask dot "..."              # 只問 Your dot
trinity-cli ask grok 蝴蝶 "..."         # 只問某個 Grok bot
```

- `--json` 放在指令前後都可以。
- 結束碼：0 全部正常；1 有座位失敗，或 `ask` 沒等到回覆；2 參數錯誤。「不支援」不算失敗。
- 某個座位失敗時，那一行會寫 `✗ 失敗` 和它自己的修法（Your dot 401 → `codex login`；Grok Bot → 打開 Grok Bot app、跑 `gbot doctor`），不會看起來像「沒有新訊息」。
- `digest` 每個來源各自記讀取位置，存在 `~/.trinity-cli/state.json`（沒有密鑰）。只有輸出成功印完才會前進。`--peek` 和 `--since` 不動讀取位置。
- 上次的位置已經掉出視窗外（Grok 的 `gapReset`，或 dot 新訊息超過一次能讀的量）時，標「可能漏看」。Your dot 的訊息 API 一次最多 32 則（超過會回 422），trinity 預設讀 30 則。
- `ask` 每送一次就在 `~/.trinity-cli/ledger.jsonl` 記一筆（座位、對象、nonce、送出時間、讀回狀態）。送出前就先記。逾時就說逾時，**絕不自動重送**。

### nonce 的設計

`ask` 在你的文字後面空一行，加一行 `[trinity abc123]`。你的原文不動；讀回時在「你說的」訊息裡找這個標籤，確認有送到。用看得見的短標籤而不是零寬字元：隱藏字元可能被任一邊的服務吃掉，也會讓人和 agent 看不出訊息被加了東西。Your dot 送出成功時還會用回傳的訊息 id 再確認一次。

### v1 做得到／做不到

做得到：`status`、`digest`、`ask`（Your dot 和 Grok bot）。

做不到：Muse（只是佔位）；附件；暫停／恢復／刪除 agent；排程；Grok 群組只在 `ask grok <群組>` 時可用，`status` 和 `digest` 只看 bot。Grok 的訊息如果沒有時間戳，會顯示「時間不明」，排在時間線最後。

### 給 agent 用

skill 在 `skills/trinity-cli/SKILL.md`。要讓 agent 讀到，把這個資料夾連進它的 skill 目錄，例如：

```bash
ln -sfn "$PWD/skills/trinity-cli" ~/.claude/skills/trinity-cli
```

`~/.codex/skills`、`~/.cursor/skills`、`~/.grok/skills` 同理。

### 設定

| 環境變數 | 用途 |
| --- | --- |
| `TRINITY_HOME` | 讀取位置和 ledger 的資料夾（預設 `~/.trinity-cli`） |
| `TRINITY_DOT_CLI`, `TRINITY_GBOT` | 指定 `chatgpt-dot-cli`、`gbot` 的路徑 |
| `TRINITY_DOT_ID` | 帳號有多個 dot 時指定一個 |
| `TRINITY_GROK_BOT` | `ask all` 預設問的 Grok bot |
| `TRINITY_GROK_BOTS` | `status`／`digest` 只看這些 bot（逗號分隔） |

## English

`trinity-cli` is one command in front of your always-on personal agents. v1 wraps ChatGPT Your dot and Grok Bot. Muse (Meta's personal agent) has no public API or CLI and is US/Canada only, so v1 has a Muse seat that always reports "not supported (no public API)" without failing the command.

trinity never talks to the services or touches logins itself. Your dot goes through `chatgpt-dot-cli --json`, and Grok Bot goes through `gbot --json`. It never reads `~/.codex/auth.json` or the Grok Bot app's session.

### Install

1. `chatgpt-dot-cli`: `uv tool install git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.1.3`. On a 401, run `codex login`.
2. `gbot`: clone the fork `ImL1s/grok-bot-cli` and run `node --test && npm link` in it. Needs Node 18+ and a signed-in Grok Bot macOS app.
3. trinity itself (Python 3.11+ and uv): `cd trinity-cli && uv tool install .`, then `trinity-cli status`.

If `chatgpt-dot-cli` or `gbot` is not on PATH, set `TRINITY_DOT_CLI` or `TRINITY_GBOT`.

### Commands

- `status`: one line per seat, with things waiting on you listed first.
- `digest [--since 2h] [--peek] [--no-activity]`: new messages from every seat in one time-ordered list, with speaker labels.
- `ask all|dot|grok BOT TEXT`: send the same text to each seat, wait for each seat's first reply, and print the replies side by side.

`--json` works before or after the command. Exit codes: 0 means everything is fine; 1 means a seat failed or `ask` got no reply; 2 means a usage error. An unsupported seat is not a failure. A failing seat prints `✗` with its own fix, so it never looks like "nothing new".

Cursors live in `~/.trinity-cli/state.json` (no secrets) and move only after output was printed. `--peek` and `--since` never move them. When a cursor falls out of the window (Grok `gapReset`, or more new dot messages than one read returns), the timeline says 可能漏看 ("possibly missed"). The dot messages API returns at most 32 per read (it answers 422 above that), so trinity reads 30.

Every `ask` send is logged to `~/.trinity-cli/ledger.jsonl` before it happens, then updated with the readback result. On a timeout trinity says so and **never resends**.

**Nonce.** `ask` appends one line, `[trinity abc123]`, after a blank line. Your text is unchanged; readback looks for that tag in your own messages to confirm delivery. A short visible tag is used instead of zero-width characters because either service may strip hidden characters, and hidden markers are invisible to the people and agents reading the thread. When a dot send returns a message id, trinity also confirms by id.

**Cannot do in v1:** Muse (placeholder only); attachments; pause, resume, or delete an agent; scheduling. Grok groups work only with `ask grok <group>`; `status` and `digest` cover bots only. Grok entries without a timestamp show as 時間不明 ("time unknown") and sort last.

**Agents:** the skill is `skills/trinity-cli/SKILL.md`. Link that folder into an agent's skill directory, for example `ln -sfn "$PWD/skills/trinity-cli" ~/.claude/skills/trinity-cli`.

## License

MIT

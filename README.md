# trinity-cli

[![pipeline](https://gitlab.com/aa22396584/trinity-cli/badges/main/pipeline.svg)](https://gitlab.com/aa22396584/trinity-cli/-/pipelines)

[中文](#中文) · [English](#english)

## 中文

`trinity-cli` 是一個指令，擋在你那幾個 24 小時在線的個人 agent（「龍蝦」）前面。它包 ChatGPT 的 Your dot、Grok Bot，以及 Muse（Meta 的個人 agent）。Muse 沒有公開 API；trinity 透過 `muse-web-cli` 操作你已經登入的瀏覽器，可以是背景的 headless，也可以是看得到的視窗。`api` backend 只是預留的接縫，目前會回不支援，不會讓其他座位失敗。

trinity 不自己連服務，也不讀登入檔：Your dot 走 `chatgpt-dot-cli --json`，Grok Bot 走 `gbot --json`，Muse 走 `muse-web-cli --json --autostart`。它不讀 `~/.codex/auth.json`，也不讀 Grok Bot app 的登入，也不讀 Muse 的 cookie。`login` 只轉給既有的公開指令，不印、不複製憑證。

### 安裝

第一次設定：

1. Your dot：`codex login`（401 時重跑）。
2. Grok Bot：打開 Grok Bot app 登入。有多個登入時，用 `gbot accounts` 看標籤，把要用的那個寫進 `TRINITY_GBOT_ACCOUNT` 或 `~/.trinity-cli/config.json` 的 `gbot_account`。trinity 會設 `GBOT_ACCOUNT`，並在 `gbot thread --help` 有 `--account` 時把旗標放在子命令後面（放在命令名稱前面會被 gbot 拒絕）。
3. Muse 網頁座位：`muse-web-cli login`（有視窗），登入完成後 `muse-web-cli start --headless`。之後 headless 或有視窗都可以。Meta 的 API 登入是另一條：`trinity-cli login muse` 執行公開的 `muse login`（瀏覽器核准），`--api-key` 把金鑰從標準輸入交給 `muse auth set --api-key-stdin`。憑證留在 muse 自己的設定裡。trinity 不讀、不印、不複製，也不會寫進 `~/.trinity-cli/muse-credential`。

三個依賴，版本釘選：

1. `chatgpt-dot-cli` v0.2.1：`uv tool install git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.1`。`messages --json` 固定是 `{"name","lines","messages"}`（舊到新）。`--limit` 只能 1 到 32，否則結束碼 2、不會送請求。dot id 用 `--dot-id`，不能當位置參數。非 200 會先在 stderr 印一行再以結束碼 3 離開。
2. `gbot`（使用者的 fork v0.11.2-iml1s.1）：`npm install -g github:ImL1s/grok-bot-cli#v0.11.2-iml1s.1`。或 clone 後在裡面 `npm link`。需要 Node 18+ 和已登入的 Grok Bot app。
3. `muse-web-cli` v0.1.1（瀏覽器，headless 或有視窗；`api` backend 仍是接縫）：

   ```bash
   PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.1"
   muse-web-cli login
   muse-web-cli start --headless
   ```

4. trinity 本身（需要 Python 3.11+）。從 git 安裝並釘在 v0.3.2：

   ```bash
   uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.3.2"
   pipx install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.3.2"
   trinity-cli --version
   ```

升級到同一個版本釘選：

```bash
uv tool install --force "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.3.2"
pipx install --force "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.3.2"
```

移除：

```bash
uv tool uninstall trinity-cli
pipx uninstall trinity-cli
```

在這個 repo 裡開發可以用 `uv tool install --editable .`。找不到 `chatgpt-dot-cli`、`gbot`、`muse-web-cli`、`muse` 或 `codex` 時，用 `TRINITY_DOT_CLI`、`TRINITY_GBOT`、`TRINITY_MUSE_CLI`、`TRINITY_MUSE`、`TRINITY_CODEX` 指定路徑。

### 指令

```bash
trinity-cli status                     # 每個座位一行；等你處理的事排最上面
trinity-cli digest                     # 所有座位的新訊息合成一條時間線
trinity-cli digest --since 2h          # 回看兩小時（不動讀取位置）
trinity-cli ask all "今天進度？"        # 同一段話問每個座位，並排印出第一個回覆
trinity-cli ask dot "..."              # 只問 Your dot
trinity-cli ask grok 蝴蝶 "..."         # 只問某個 Grok bot
trinity-cli hand dot#last --to grok:蝴蝶 "請看這則"
trinity-cli wait grok:蝴蝶 --notify
trinity-cli wait dot --then hand dot#last --to grok:蝴蝶 "接著處理"
trinity-cli schedules
trinity-cli who "翻譯這段"
trinity-cli brief init                # 檔案不存在才寫一份短模板
trinity-cli brief show
trinity-cli brief diff                 # 還沒有 brief 也是結束碼 0，並提示 init
trinity-cli brief push                 # 預設先問；--yes 才寫入
trinity-cli log --seat dot --since 2h
trinity-cli login muse                 # 執行 muse login；不印、不讀憑證
trinity-cli login muse --api-key       # 標準輸入交給 muse auth set
trinity-cli login muse --web           # 網頁座位：muse-web-cli login
```

- `--json` 放在指令前後都可以。
- 結束碼：0 全部正常；1 有座位失敗，或 `ask`／`hand`／`wait` 沒等到回覆；2 參數錯誤，或 `hand`／`brief push` 沒有確認所以沒送出。「不支援」不算失敗。
- 某個座位失敗時，那一行會寫 `✗ 失敗` 和它自己的修法（Your dot 401 → `codex login`；Grok Bot → 打開 Grok Bot app、跑 `gbot doctor`），不會看起來像「沒有新訊息」。
- `digest` 每個來源各自記讀取位置，存在 `~/.trinity-cli/state.json`（沒有密鑰）。只有輸出成功印完才會前進。`--peek` 和 `--since` 不動讀取位置。`hand` 和 `wait` 也不動讀取位置。
- 上次的位置已經掉出視窗外（Grok 的 `gapReset`，dot 新訊息超過一次能讀的量，或 Muse 上次看到的結尾已經不在這次視窗裡）時，標「可能漏看」。Your dot 的訊息 API 一次最多 32 則（超過會回 422），trinity 預設讀 30 則。gbot 若有 `thread --after`，trinity 會用它，並認得回傳的 `cursor`、`entryCount`、`gapReset`。Muse 的訊息沒有時間戳（只有日期分隔），所以時間顯示「時間不明」；讀取位置是內容雜湊加上在視窗裡的第幾次出現。多出來的 JSON 欄位會被略過。
- `ask` 和 `hand` 每送一次就在 `~/.trinity-cli/ledger.jsonl` 記一筆（座位、對象、nonce、送出時間、讀回狀態）。送出前就先記。逾時就說逾時，**絕不自動重送**。`log` 用來查看這本帳。
- 設了 `grok_bot`（或 `TRINITY_GROK_BOT`）之後，`ask all`、`ask grok "一句話"`、`hand ... --to grok`、`wait grok` 和 `brief` 都用那個 bot。`ask grok 名字 "..."` 仍然指定另一個。Grok 的文字回覆常常是 `kind: send-message`、`message.type: text`，不是 `role: assistant`；trinity 把這種條目當成 bot 的回覆。核准卡片等其他 type 不算回覆。`status` 和 `digest` 仍會看全部 bot。

### hand、wait

`hand <來源>#last --to <目的> "指令"` 把來源座位最近一則（或 `#2` 第二新）agent 回覆，當成附件放在你的指令下面，並註明來自哪裡、什麼時候、誰說的。先印預覽。終端機前會問你；不是終端機時一定要加 `--yes`，否則不送。送到之後會等對方的第一個回覆，並把送出、讀回、有沒有回覆都記進 ledger。它不會再自動轉給下一個座位。

`wait <座位>` 從 ledger 最後一筆之後開始等第一則新回覆，間隔會慢慢拉長。逾時只報告，不重送。`--notify` 會響鈴，並用 macOS 通知（`osascript`），通知裡不放內文。只有你寫了 `--then hand ...` 才會再轉交一次，而且 `hand` 自己的確認規則還在。

### schedules、who、brief

`schedules` 列出每個座位的排程。Your dot 用 `chatgpt-dot-cli automations`。Grok 在 gbot 說明裡出現 `schedules`、`routines` 或 `automations` 時才讀。Muse 讀 `muse-web-cli upcoming`。某個座位沒有這個功能時顯示不支援，不讓整個指令失敗。標題在兩個座位重複時會標出來，時間也一樣會另外註明。

`who "事情"` 用一張固定的能力表，加上當下狀態（暫停、這台 Mac 有沒有接上、額度），建議哪個座位比較適合。只是建議，不會送出任何訊息。

`brief` 讀寫本機的 `~/.trinity-cli/brief.md`。`show` 印出檔案。`diff` 跟讀得到的指令比對；Muse 會額外只讀 `memory`，拿來跟 brief 比較，不會寫回去。`push` 只在 gbot 有 `bots update --instructions` 時寫進 Grok bot，而且先問過（`--yes` 可略過）。Your dot 和 Muse 沒有指令 API，只會印出可以自己貼上的草稿，不會傳訊息。

Muse 的 `send` 不帶 `--wait`。trinity 先記 ledger，送出一次，再用 `messages` 輪詢 nonce 後面的第一則回覆。逾時只停輪詢，**不會再呼叫 send**。讀和送之前會先看 `chats`。目前是副聊天室時不送出，status 寫「目前在副聊天室」，並請你在 Muse 視窗切回主聊天室；這種讀取不推進讀取位置。`chats` 不支援或切換面板不在時，仍使用目前開啟的對話，status 會註明。聊天室標題不會印出來。`status` 也會標出目前是主聊天室還是副聊天室。瀏覽器登入失效時的修法是 `muse-web-cli login`；瀏覽器沒起來時是 `muse-web-cli start --headless`。api 後端缺憑證時改提示 `trinity-cli login muse`，不是瀏覽器登入。憑證檔權限不對時提示 `chmod 600 ~/.trinity-cli/muse-credential`。`status` 看到待處理項目時會標「等你處理」。

### nonce 的設計

`ask` 和 `hand` 在你的文字後面空一行，加一行 `[trinity abc123]`。你的原文不動；讀回時在「你說的」訊息裡找這個標籤，確認有送到。用看得見的短標籤而不是零寬字元：隱藏字元可能被任一邊的服務吃掉，也會讓人和 agent 看不出訊息被加了東西。Your dot 送出成功時還會用回傳的訊息 id 再確認一次。

### 做得到／做不到

做得到：`status`、`digest`、`ask`、`hand`、`wait`、`schedules`、`who`、`brief`、`log`（Your dot、Grok bot、Muse）。Muse 的排程來自 upcoming；待處理事項出現在 status。

做不到：把 Your dot 或 Muse 的 standing instructions 直接寫進去（沒有 API，`brief push` 只印草稿）；寫入 Muse 的 memory（`brief diff` 只讀）；暫停／恢復／刪除 agent；逾時自動重送；`hand` 自動再轉下一手。Grok 群組只在 `ask grok <群組>` 和 `hand`／`wait` 的 `grok:<名字>` 時可用，`status` 和 `digest` 只看 bot。Grok 和 Muse 的訊息如果沒有時間戳，會顯示「時間不明」，排在時間線最後。Grok 的送出收據有時是 `unknown`，trinity 照實記下，然後只輪詢、不重送。

安全界線：`hand` 和 `brief push` 預設先問；不是終端機時沒有 `--yes` 就不送。`hand` 不會把目的地的回覆再轉出去。逾時只報告，絕不重送。

### 給 agent 用

skill 在 `skills/trinity-cli/SKILL.md`。要讓 agent 讀到，把這個資料夾連進它的 skill 目錄，例如：

```bash
ln -sfn "$PWD/skills/trinity-cli" ~/.claude/skills/trinity-cli
```

`~/.codex/skills`、`~/.agents/skills`、`~/.config/opencode/skills`、`~/.config/opencode/skill`、`~/.cursor/skills`、`~/.grok/skills` 同理。目錄不存在就不要建。

### 設定

| 環境變數 | 用途 |
| --- | --- |
| `TRINITY_HOME` | 讀取位置和 ledger 的資料夾（預設 `~/.trinity-cli`） |
| `TRINITY_DOT_CLI`, `TRINITY_GBOT`, `TRINITY_MUSE_CLI` | 指定 `chatgpt-dot-cli`、`gbot`、`muse-web-cli` 的路徑 |
| `TRINITY_MUSE`, `TRINITY_CODEX` | `login muse` 用的 `muse`，以及 `login dot` 用的 `codex` |
| `TRINITY_DOT_ID` | 帳號有多個 dot 時指定一個 |
| `TRINITY_GROK_BOT` | `ask`、`hand`、`wait`、`brief` 預設的 Grok bot。也可寫在 `~/.trinity-cli/config.json` 的 `grok_bot`。有設的時候，`ask grok "一句話"` 整句都是訊息 |
| `TRINITY_GROK_BOTS` | `status`／`digest` 只看這些 bot（逗號分隔） |
| `TRINITY_GBOT_ACCOUNT` | 多個 Grok Bot 登入時要用的標籤。也可寫在 `~/.trinity-cli/config.json` 的 `gbot_account`。trinity 會設 `GBOT_ACCOUNT`；`gbot thread --help` 有 `--account` 時把旗標放在子命令後面 |

## English

`trinity-cli` is one command in front of your always-on personal agents. It wraps ChatGPT Your dot, Grok Bot, and Muse (Meta's personal agent). Muse has no public API. trinity drives the browser you already logged in to, through `muse-web-cli`, either headless or in a visible window. The `api` backend is only a seam: it reports unsupported and does not fail the other seats.

trinity never talks to the services or reads login files. Your dot goes through `chatgpt-dot-cli --json`, Grok Bot through `gbot --json`, and Muse through `muse-web-cli --json --autostart`. It never reads `~/.codex/auth.json`, the Grok Bot app's session, or Muse cookies. `login` only hands off to those public CLIs and does not print or copy a credential.

### Install

First-time setup:

1. Your dot: `codex login` (run it again on a 401).
2. Grok Bot: sign in with the Grok Bot app. When several logins are saved, pick a label with `gbot accounts` and set `TRINITY_GBOT_ACCOUNT` or `gbot_account` in `~/.trinity-cli/config.json`. trinity exports `GBOT_ACCOUNT` and, when `gbot thread --help` documents `--account`, appends that flag after the subcommand (gbot rejects it before the command name).
3. Muse in the browser: `muse-web-cli login` in a visible window, then `muse-web-cli start --headless`. Later runs can be headless or headed. A Meta API login is separate: `trinity-cli login muse` runs the public `muse login` (approve in the browser), and `--api-key` passes a key from stdin to `muse auth set --api-key-stdin`. The `muse` CLI keeps that credential. trinity does not read, print, or copy it, and does not write `~/.trinity-cli/muse-credential`.

Pinned dependencies:

1. `chatgpt-dot-cli` v0.2.1: `uv tool install git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.1`. `messages --json` is always `{"name","lines","messages"}` (oldest first). `--limit` must be 1..32, or the command exits 2 and sends no request. Pass a dot id with `--dot-id`, not as a positional. A non-200 prints one stderr line and exits 3.
2. `gbot`, the fork v0.11.2-iml1s.1: `npm install -g github:ImL1s/grok-bot-cli#v0.11.2-iml1s.1`, or clone the repo and `npm link`. Needs Node 18+ and a signed-in Grok Bot app.
3. `muse-web-cli` v0.1.1 (headless or headed browser; the `api` backend is still a seam):

   ```bash
   PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.1"
   muse-web-cli login
   muse-web-cli start --headless
   ```

4. trinity itself (Python 3.11+), pinned to v0.3.2:

   ```bash
   uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.3.2"
   pipx install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.3.2"
   trinity-cli --version
   ```

Upgrade to the same pin:

```bash
uv tool install --force "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.3.2"
pipx install --force "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.3.2"
```

Uninstall:

```bash
uv tool uninstall trinity-cli
pipx uninstall trinity-cli
```

For development in this checkout, `uv tool install --editable .` works. If `chatgpt-dot-cli`, `gbot`, `muse-web-cli`, `muse`, or `codex` is not on PATH, set `TRINITY_DOT_CLI`, `TRINITY_GBOT`, `TRINITY_MUSE_CLI`, `TRINITY_MUSE`, or `TRINITY_CODEX`.

### Commands

- `status`: one line per seat, with things waiting on you listed first.
- `digest [--since 2h] [--peek] [--no-activity]`: new messages from every seat in one time-ordered list, with speaker labels.
- `ask all|dot|grok BOT TEXT`: send the same text to each seat, wait for each seat's first reply, and print the replies side by side. With `grok_bot` set, `ask grok "TEXT"` sends that whole string to the default bot. `ask grok NAME TEXT` still names a bot. Grok replies often arrive as `send-message` entries whose `message.type` is `text`, not `role: assistant`; trinity treats that text as the bot reply. Other `send-message` types, such as approval cards, are not the reply.
- `hand SOURCE#last --to DEST "instruction"`: forward the latest agent reply (`#2` is the second newest) under your instruction, with provenance. Prints a preview and asks first; pass `--yes` when stdin is not a terminal. Does not chain further.
- `wait SEAT [--timeout] [--notify] [--then hand ...]`: poll for the first new reply after the latest ledger mark, backing off. A timeout is reported and never resent. `--notify` rings the terminal and posts a macOS notification. `--then hand` runs only when you wrote it and a reply actually arrived.
- `schedules`: list automations. Your dot uses `automations`. Grok is read when `gbot --help` mentions schedules, routines, or automations. Muse reads `muse-web-cli upcoming`. An unsupported seat does not fail the command. Matching titles across seats are flagged.
- `who "task"`: suggest a seat from a fixed capability table plus live status (paused, this Mac, quota). Advisory only.
- `brief show|init|diff|push`: one local file, `~/.trinity-cli/brief.md`. `init` writes a short template only when the file is absent. `diff` with no file exits 0 and tells you to run `brief init` or edit the file. `diff` also reads Muse memory and compares it; that read does not write. `push` writes Grok instructions with `gbot bots update --instructions` only when gbot supports it, and only after confirmation. Your dot and Muse have no instruction API, so trinity prints a draft and does not send.
- `log [--seat] [--since] [--status]`: read the ledger.
- `login muse`: run `muse login` and do not print or read the credential. `--api-key` passes stdin to `muse auth set --api-key-stdin`. `--web` runs headed `muse-web-cli login` for the browser seat. `login dot` runs `codex login`. `login grok` only tells you to sign in with the Grok Bot app; trinity does not read that session.

`--json` works before or after the command. Exit codes: 0 means everything is fine; 1 means a seat failed or `ask`, `hand`, or `wait` got no reply; 2 means a usage error, or `hand` / `brief push` refused to send because nobody confirmed. An unsupported seat is not a failure. A failing seat prints `✗` with its own fix, so it never looks like "nothing new".

Cursors live in `~/.trinity-cli/state.json` (no secrets) and move only after digest output was printed. `--peek`, `--since`, `hand`, and `wait` never move them. When a cursor falls out of the window (Grok `gapReset`, more new dot messages than one read returns, or Muse's previously seen tail is gone from the window), the timeline says 可能漏看 ("possibly missed"). The dot messages API returns at most 32 per read, and chatgpt-dot-cli v0.2.1 exits 2 without a request above that, so trinity reads 30. When `gbot thread --help` includes `--after`, trinity uses it and reads `cursor`, `entryCount`, and `gapReset`. Muse messages have no timestamps, only date separators, so their times stay unknown. The Muse cursor is a content hash plus how many times that text occurred in the window. Extra JSON fields are ignored.

Muse `send` does not pass `--wait`. trinity logs the ledger, sends once, then polls `messages` for the nonce and the next assistant reply. A timeout stops polling and **never calls send again**. Before a read or a send, trinity calls `chats`. A side chat is not sent into; status says 目前在副聊天室 and asks you to switch back to the main chat in the Muse window. That read does not move the cursor. If `chats` is unsupported or the switcher panel is missing, trinity keeps using the open conversation and says so on the status line. Chat titles are never printed. `status` also says whether the current chat is the main one or a side one. A browser `session_expired` tells you to run `muse-web-cli login`. A missing api credential tells you to run `trinity-cli login muse` instead. `credential_permissions` tells you to run `chmod 600 ~/.trinity-cli/muse-credential`. `browser_down` tells you to run `muse-web-cli start --headless`. Pending items show up on `status` as 等你處理 ("waiting on you") when the count is greater than zero.

Every `ask` and `hand` send is logged to `~/.trinity-cli/ledger.jsonl` before it happens, then updated with the readback result. On a timeout trinity says so and **never resends**. `log` prints that ledger.

**Nonce.** `ask` and `hand` append one line, `[trinity abc123]`, after a blank line. Your text is unchanged; readback looks for that tag in your own messages to confirm delivery. A short visible tag is used instead of zero-width characters because either service may strip hidden characters, and hidden markers are invisible to the people and agents reading the thread. When a dot send returns a message id, trinity also confirms by id.

**Safety.** `hand` and `brief push` ask first. Without a terminal, they do not send unless you pass `--yes`. `hand` does not chain the destination's reply onward. A timeout is reported and never resent. A Grok send receipt of `unknown` is kept as unknown; trinity polls and does not send again.

**Not available:** writing standing instructions for Your dot or Muse (`brief push` prints a draft); writing Muse memory (`brief diff` only reads it); pause, resume, or delete; resending after a timeout; auto-chaining `hand`. Grok groups work with `ask grok <group>` and `grok:<name>` on `hand` / `wait`; `status` and `digest` cover bots only. Grok and Muse entries without a timestamp show as 時間不明 ("time unknown") and sort last. For several Grok Bot logins, set `TRINITY_GBOT_ACCOUNT` or `gbot_account` in `~/.trinity-cli/config.json`. trinity exports `GBOT_ACCOUNT` and, when `gbot thread --help` documents `--account`, appends that flag after the subcommand (gbot rejects it before the command name).

**Agents:** the skill is `skills/trinity-cli/SKILL.md`. Link that folder into an agent's skill directory when the directory already exists, for example `ln -sfn "$PWD/skills/trinity-cli" ~/.claude/skills/trinity-cli`. The same set as chatgpt-dot-cli: `~/.codex/skills`, `~/.agents/skills`, `~/.config/opencode/skills`, `~/.config/opencode/skill`, `~/.cursor/skills`, `~/.grok/skills`.

## License

MIT

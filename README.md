# trinity-cli

[![pipeline](https://gitlab.com/aa22396584/trinity-cli/badges/main/pipeline.svg)](https://gitlab.com/aa22396584/trinity-cli/-/pipelines)

[中文](#中文) · [English](#english)

## 中文

### 這是什麼

`trinity-cli` 是一個指令，擋在三個一直開著的個人 agent 前面：ChatGPT 的 Your dot、Grok Bot，以及 Meta 的 Muse。它需要 Python 3.11+。它不自己連這些服務，而是轉呼叫三個工具：

- Your dot：`chatgpt-dot-cli --json`
- Grok Bot：`gbot --json`（這個 fork）
- Muse：`muse-web-cli --json --autostart`

它不讀 `~/.codex/auth.json`、Grok Bot app 的登入，或 Muse 的 cookie。`login` 只轉給那些工具既有的公開指令，不印憑證。唯一會存下 token 的是 `login muse`：它叫 `muse-web-cli credential` 把 Muse gateway token 只寫進 `~/.trinity-cli/muse-credential`（mode 600），給 `--muse-backend api` 用。trinity 自己不讀、不印這個檔。

支援的系統：Linux（CI）、Windows（CI）、macOS（本機與實機檢查）。

### 三個座位

| 座位 | 工具 | 專案 |
| --- | --- | --- |
| Your dot | `chatgpt-dot-cli` | https://gitlab.com/aa22396584/chatgpt-dot-cli |
| Grok Bot | `gbot`（fork） | https://gitlab.com/aa22396584/grok-bot-cli |
| Muse | `muse-web-cli` | https://gitlab.com/aa22396584/muse-web-cli |

### 相關專案

- trinity-cli（這個 repo）— 一個指令包三個一直開著的 agent（Your dot、Grok Bot、Muse）：https://gitlab.com/aa22396584/trinity-cli
- chatgpt-dot-cli — ChatGPT Your dot：https://gitlab.com/aa22396584/chatgpt-dot-cli
- grok-bot-cli（fork，`gbot`）— Grok Bot：https://gitlab.com/aa22396584/grok-bot-cli
- muse-web-cli — 用網頁操作 Meta Muse：https://gitlab.com/aa22396584/muse-web-cli

### 安裝

v0.4.4 釘這些版本。三個座位工具和 trinity 都裝好後，用 `--version` 對一下：應印出 `muse-web-cli 0.1.4`、`trinity-cli 0.4.4`、`gbot 0.11.2`。舊的 muse-web-cli v0.1.2 沒有 `credential` 和 api gateway；v0.1.3 的 `send --wait` 在長聊天室會等不到回覆。

macOS 與 Linux 需要 Python 3.11+、git、以及已在 PATH 上的 `uv`。Grok 還要 Node.js 22.19.0+ 和 npm。uv 的執行檔在 `~/.local/bin`；`--version` 找不到時把那個目錄加進 PATH。第一次 `uv tool install` 可能會下載 Python。

不要用 `npm install -g git+https://gitlab.com/aa22396584/grok-bot-cli.git#...`。那一行會結束碼 0，但 `gbot` 是斷掉的連結。改裝這個 tag 附的套件檔：

```bash
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.2"
curl -fsSL -o grok-bot-cli-0.11.2.tgz "https://gitlab.com/-/project/86401528/uploads/95fd5079c4507af7f3f8e61dd04ce6f3/grok-bot-cli-0.11.2.tgz"
npm install -g ./grok-bot-cli-0.11.2.tgz
rm -f grok-bot-cli-0.11.2.tgz
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.4"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.4.4"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

`pipx` 可以取代上面的 `uv tool install`（trinity、chatgpt-dot-cli、muse-web-cli）。

Windows（PowerShell，同樣的釘選）：

```powershell
irm https://astral.sh/uv/install.ps1 | iex
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.2"
irm "https://gitlab.com/-/project/86401528/uploads/95fd5079c4507af7f3f8e61dd04ce6f3/grok-bot-cli-0.11.2.tgz" -OutFile grok-bot-cli-0.11.2.tgz
npm install -g .\grok-bot-cli-0.11.2.tgz
Remove-Item grok-bot-cli-0.11.2.tgz
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.4"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.4.4"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

Windows 上 npm 的 `gbot` 是 `gbot.cmd`，uv 的工具是 `.exe`。trinity 用 `shutil.which` 找它們，參數以清單傳遞，不用 shell。Windows 也要 Node.js 22.19.0+。

升級到同一個釘選：把安裝指令再跑一次。`uv` 加 `--force`。gbot 再下載同一個 `.tgz` 後安裝。

移除：

```bash
uv tool uninstall trinity-cli
uv tool uninstall chatgpt-dot-cli
uv tool uninstall muse-web-cli
npm uninstall -g grok-bot-cli
```

`pipx uninstall` 對應 uv 裝的那三個。在這個 repo 裡開發：`uv tool install --editable .`。

### 第一次設定

1. Your dot：`codex login`。401 時再跑一次。也可以 `trinity-cli login dot`。多個 dot 時設 `TRINITY_DOT_ID`。細節見 [chatgpt-dot-cli 疑難排解](https://gitlab.com/aa22396584/chatgpt-dot-cli/-/blob/main/README.md#疑難排解)。
2. Grok Bot：打開 Grok Bot app 登入。`trinity-cli login grok` 只會重複這句，不會讀那個登入。有多個登入時先跑 `gbot accounts`，把要的標籤寫進設定。細節見 [grok-bot-cli 安裝](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install)。
3. Muse 預設走網頁（browser 後端）：`muse-web-cli login`（看得到的視窗），完成後 `muse-web-cli start --headless`。或 `trinity-cli login muse --web`。api 後端（`--muse-backend api`，走 Muse gateway）要憑證：`trinity-cli login muse` 會執行 `muse-web-cli credential`，沒登入就先走登入，再把 gateway token 只寫進 `~/.trinity-cli/muse-credential`（mode 600），不印出。這個檔是 token，不要分享或提交。token 過期時會說「登入工作階段已失效」，在 Chrome 重新登入後再跑一次。`--api-key` 仍把金鑰從標準輸入交給 `muse auth set --api-key-stdin`。細節見 [muse-web-cli 排解](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/README.md#排解)。
4. 多個 Grok 座位用登入標籤加 bot 名稱。`grok` 指向 `grok_default`。假值：

```json
{
  "grok_default": "grok-a",
  "grok_seats": [
    {"name": "grok-a", "account": "example-login-a", "bot": "Grok Bot"},
    {"name": "grok-b", "account": "example-login-b", "bot": "Main"}
  ]
}
```

舊的 `gbot_account` 加 `grok_bot` 仍可用，會當成一個名叫 `grok` 的座位。`TRINITY_GBOT_ACCOUNT` 和 `TRINITY_GROK_BOT` 只覆寫這個舊座位。改設定前會先備份。Muse 可另加 `"muse_backend": "browser"`、`"api"` 或 `"auto"`（假值；預設是不寫，也就是 muse-web-cli 的 browser）。

5. 確認：`trinity-cli status`。每個座位一行。等你處理的事項在最上面。

### 快速開始

```bash
trinity-cli status
trinity-cli digest --peek
trinity-cli ask all "今天進度？"
trinity-cli hand dot#last --to grok:example-bot "請看這則"
trinity-cli wait grok:example-bot
```

`status` 的形狀：

```text
等你處理：
  • 等你處理：範例待辦

Your dot  ✓ 連線正常
Grok Bot   ✓ 連線正常
Muse       ✓ 連線正常 · 背景 · 主聊天室
```

`digest` 的形狀：

```text
10-01 09:00  Your dot  你  今天進度？
10-01 09:01  Your dot  Your dot  進行中。

共 2 則新訊息。
```

`ask all` 會並排列出每個座位的第一則回覆，頁尾有 nonce 和 ledger 路徑。`hand` 先印預覽再問。`wait` 逾時只寫「沒有重送」。

### 指令參考

沒有子命令時跑 `status`。`--json` 放在指令前後都可以，改印 JSON。`--version` 印 `trinity-cli` 與版本。

`status` 沒有旗標。結束碼 0，除非某個座位失敗。不支援不算失敗。`--json`：`waiting`（字串陣列）、`seats[]` 的 `seat`、`label`、`state`，成功時還有 `summary`、`waiting`、`problems`、`hint`、`details`；失敗時是 `error`、`hint`。

```bash
trinity-cli status
trinity-cli --json status
```

`digest` 把新訊息排成一條時間線，印完才推進讀取位置。

| 旗標 | 預設 | 範圍 |
| --- | --- | --- |
| `--since` | 不回看 | `30m`、`2h`、`1d`、`1w` 或 ISO；不推進讀取位置 |
| `--peek` | 關（會推進） | 開了就不推進 |
| `--no-activity` | 關 | 跳過 Your dot 和 Muse 的 activity |
| `--limit` | dot 30、Grok 40、Muse 40 | 只套在 dot（1..32）和 Grok（1..200）；Muse 仍是 40，上限 100 |

```bash
trinity-cli digest --peek
```

`--json`：`items[]`（`at`、`source`、`speaker`、`from_agent`、`text`、`gap_before`）、`gaps`、`failures`（`source`、`error`、`hint`）、`unsupported`（`seat`、`label`、`reason`）、`notes`、`advanced`。

`ask SEAT TEXT` 送出一次，再等第一則回覆。逾時不重送。

| 旗標或參數 | 預設 | 範圍 |
| --- | --- | --- |
| `seat` | 必填 | `all`、`dot`、`grok`、`muse` |
| 其餘文字 | 空則讀 stdin | `ask grok 名字 文字` 在兩個詞以上時，第一個詞是 bot；只有一句時整句都是訊息 |
| `--grok-bot` | `TRINITY_GROK_BOT`，否則 `grok_bot`，否則唯一的 bot | 一個 bot 名稱 |
| `--timeout` | 180 | 秒；逾時不重送 |
| `--poll` | 10 | 秒，兩次回讀的間隔 |

```bash
trinity-cli ask muse "今天進度？"
```

`--json`：`ask_id`、`nonce`、`results[]` 的 `seat`、`target`、`state`、`send`、`readback`、`reply`（`at`、`speaker`、`text`）、`error`、`hint`。

`hand 來源 --to 目的 指令` 轉交一則回覆。先預覽。終端機會問；不是終端機一定要 `--yes`，否則不送。不會再轉下一手。

| 旗標或參數 | 預設 | 範圍 |
| --- | --- | --- |
| `來源` | 必填 | `dot#last`、`grok:BOT#last`、`muse#last`；`#2` 是第二新 |
| `--to` | 必填 | `dot`、`grok`、`grok:BOT`、`muse` |
| `--yes` | 關 | 不問直接送 |
| `--timeout` | 180 | 秒；逾時不重送 |
| `--poll` | 10 | 秒 |
| 指令 | 必填 | 要對方怎麼處理 |

```bash
trinity-cli hand dot#last --to muse "請看這則"
```

`--json` 沿用預覽或送出結果：`sent`、`confirmed`、`state`、`error`、`hint`。

`wait 對象` 從 ledger 最後一筆之後等新回覆。不重送。

| 旗標或參數 | 預設 | 範圍 |
| --- | --- | --- |
| 對象 | 必填 | `dot`、`muse`、`grok`、`grok:BOT`；單獨 `grok` 用 `grok_bot` |
| `--timeout` | 180 | 秒 |
| `--poll` | 5 | 第一次間隔，之後加倍，上限 30 秒 |
| `--notify` | 關 | 終端機鈴聲和 macOS 通知，通知不含內文 |
| `--then` | 不做 | 只能是 `hand ...`，而且要放最後；沒有回覆就不會跑 |

```bash
trinity-cli wait dot --timeout 60
```

`--json`：`state`、`seat`、`target`、`polls`、`sent`、`error`；有 `--then` 時多一個 `then`。

`schedules` 沒有自己的旗標。Your dot 用 `automations`。Grok 只在 `gbot --help` 出現 `schedules`、`routines` 或 `automations` 時才讀。Muse 讀 `upcoming`，也讀 `activity`（標成動態）。`--muse-backend` 可加在這個指令上。沒有這個能力會標不支援，不讓整個指令失敗。標題或時間在兩個座位重複時會標出來。

```bash
trinity-cli schedules
```

`--json`：`seats`、`duplicates`。

`who 事情` 只建議，不送出。事情必填。

```bash
trinity-cli who "翻譯這段"
```

`--json`：`advisory`、`suggestion`、`headline`、`ranking`。

`brief` 讀寫 `~/.trinity-cli/brief.md`。

| 子命令 | 旗標 | 預設 |
| --- | --- | --- |
| `show` | 無 | 印出檔案；還沒有檔案也是結束碼 0 |
| `init` | 無 | 只在檔案不存在時寫短模板 |
| `diff` | `--grok-bot` | 跟各座位的指令比；Muse 會只讀 memory。沒有檔案時結束碼 0，並提示 `brief init` |
| `push` | `--yes`、`--grok-bot` | 先問。只在 Grok 有 `bots update --instructions` 時寫入。Your dot 和 Muse 只印草稿，不傳訊息。超過 32000 字不寫 |

```bash
trinity-cli brief init
trinity-cli brief show
trinity-cli brief diff
trinity-cli brief push
```

`--json`：`show` 是 `path`、`text` 或 `missing`；`init` 是 `path`、`created`；`diff` 是 `path`、`seats`；`push` 是 `path`、`updated`、`sent`、`confirmed`。

`log` 只讀 ledger。

| 旗標 | 預設 | 範圍 |
| --- | --- | --- |
| `--seat` | 全部 | `dot`、`grok`、`muse` |
| `--since` | 全部 | `30m`、`2h`、`1d`、`1w` 或 ISO |
| `--status` | 任何 | 對上 `event`、`reply` 或 `readback`，例如 `sent`、`replied`、`timed_out` |
| `--limit` | 50 | 至少 1 |

```bash
trinity-cli log --seat dot --since 2h --limit 20
```

`--json`：`records`（帳本上的欄位，不含內部 id）。

`login 座位` 不印憑證。

| 旗標或參數 | 預設 | 範圍 |
| --- | --- | --- |
| 座位 | 必填 | `dot`、`grok`、`muse` |
| `--api-key` | 關 | 只有 Muse；標準輸入交給 `muse auth set`。不能和 `--web` 一起用 |
| `--web` | 關 | 只有 Muse；有視窗的 `muse-web-cli login` |

```bash
trinity-cli login muse --web
```

`--json`：`seat`、`ok`、`message`、`hint`。

`grok bots` 列出每個 `gbot accounts` 登入上的 bot：名字、說明、登入標籤、可達或不可達、是不是已設定的座位。不印 id。

`grok add NAME --account LABEL --bot BOT` 把座位寫進設定，可加 `--default`。`grok remove NAME` 刪掉那個座位。兩者都先備份 `config.json`。

```bash
trinity-cli grok bots
trinity-cli grok add grok-a --account example-login-a --bot "Grok Bot" --default
trinity-cli grok remove grok-b
trinity-cli ask grok-a "一句話"
trinity-cli ask grok --bot "Other" --account example-login-a "臨時問這個"
trinity-cli ask all "問全部"
```

`status`、`digest`、`ask`、`hand`、`wait`、`schedules`、`who`、`brief push`、`log` 都認座位名。`grok` 是預設座位。`all` 是 dot、每個啟用的 Grok 座位、再加上 muse。每次送出有自己的 nonce。同一個 bot 名稱出現在兩個登入時，`--bot` 必須加 `--account`。`wait` 和 `digest` 也接受這兩個旗標。

### 概念

三個座位的能力不一樣。沒有的能力會明白寫「不支援」，結束碼仍是 0，不會連帶讓別的座位失敗。`muse-web-cli` 的預設是 browser；`api` 走 Muse gateway，讀 `~/.trinity-cli/muse-credential`。trinity 會傳 `--backend`：`--muse-backend` 優先於設定檔的 `muse_backend`，再來是 `MUSE_WEB_BACKEND`。三個都沒寫就不傳，交給 muse-web-cli 自己的預設。值是 `browser`、`api` 或 `auto`。`auto` 先試 api，該能力若是 exit 4 才改走 browser，並標出實際用的後端。`send` 逾時不會改走另一個後端。api 有能力不支援且沒有 fallback 時，那個能力單獨標不支援，不會讓 trinity 當掉。Muse 沒有指令 API。Grok 群組只在 `ask grok <群組>` 和 `hand`／`wait` 的 `grok:<名字>` 可用；`status` 和 `digest` 只看 bot。

讀取位置在 `state.json` 的 `cursors`，Grok 依座位分開（例如 `grok-a.messages`）。只有 `digest` 把輸出印完才前進。`--peek`、`--since`、`hand`、`wait` 都不動。對不上上次的結尾時標「可能漏看」。一個 Grok 座位不可達時，其他座位照常；那個座位標成失敗，並附上重新登入的提示。

每次 `ask` 和 `hand` 在送出前就寫 `ledger.jsonl`。你的原文後面空一行，加一行 `[trinity abc123]`。讀回在你自己的訊息裡找這個標籤。逾時只報告，不重送。

Muse 在讀和送之前先看 `chats`。目前是副聊天室時不送出，也不推進 Muse 的讀取位置，status 寫「目前在副聊天室」。`chats` 不支援或切換面板不在時，仍用目前開啟的對話，並在 status 註明。聊天室標題不會印出來。

### 結束碼

| 碼 | 意思 |
| --- | --- |
| 0 | 正常。不支援也算這裡。這次點到的座位裡只要有一個成功就是 0，失敗仍會印出 |
| 1 | 這次點到、且算數的座位全部失敗或逾時。`hand` 和 `wait` 只有一個對象 |
| 2 | 參數不對，或 `hand`／`brief push` 沒有確認所以沒送 |

| 座位狀態 | 修法 |
| --- | --- |
| Your dot 401 或登入檔不能用 | `codex login`。見 [chatgpt-dot-cli 疑難排解](https://gitlab.com/aa22396584/chatgpt-dot-cli/-/blob/main/README.md#疑難排解) |
| Your dot 網路或非 200 | 先看 `chatgpt-dot-cli list` |
| 找不到 chatgpt-dot-cli | 安裝，或設 `TRINITY_DOT_CLI` |
| Grok 多個登入 | `gbot accounts`，再寫 `gbot_account`。見 [grok-bot-cli 安裝](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) |
| Grok 登入不能用 | 打開 Grok Bot app，跑 `gbot doctor` |
| 找不到 gbot | 安裝，或設 `TRINITY_GBOT` |
| Muse 瀏覽器沒起來 | `muse-web-cli start --headless` |
| Muse 網頁登入失效 | `muse-web-cli login`。見 [muse-web-cli 排解](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/README.md#排解) |
| Muse api 缺憑證 | `trinity-cli login muse` |
| Muse api 登入工作階段已失效 | 在 Chrome 視窗重新登入 Muse，再 `trinity-cli login muse` |
| Muse 憑證檔權限 | macOS／Linux：`chmod 600 ~/.trinity-cli/muse-credential`。Windows：`icacls` 只給目前使用者讀 |
| Muse 在副聊天室 | 在 Muse 視窗切回主聊天室 |
| Muse 瀏覽器設定檔忙碌 | 先關掉那個視窗，再執行 `muse-web-cli start --headless` |
| Muse 地區限制 | 這個工具不會繞過地區限制 |
| 找不到 muse-web-cli 或 muse | 安裝，或設 `TRINITY_MUSE_CLI`、`TRINITY_MUSE` |

### 檔案與環境變數

資料在 `TRINITY_HOME`，沒設就是家目錄下的 `.trinity-cli`。

| 路徑 | 內容 |
| --- | --- |
| `config.json` | `grok_seats`、`grok_default`。舊的 `gbot_account`、`grok_bot` 仍可讀。不是 token |
| `state.json` | 讀取位置。沒有密鑰 |
| `ledger.jsonl` | 每次送出 |
| `brief.md` | 本機 brief |

`~/.trinity-cli/muse-credential` 固定在家目錄，不跟 `TRINITY_HOME`。它是 Muse gateway 的 token，mode 600，由 `login muse`（`muse-web-cli credential`）寫入，只有 `muse-web-cli --backend api` 會讀。trinity 不讀、不印它。

| 變數 | 用途 |
| --- | --- |
| `TRINITY_HOME` | 上面那個資料夾 |
| `TRINITY_DOT_CLI`、`TRINITY_GBOT`、`TRINITY_MUSE_CLI` | 三個座位工具的路徑 |
| `TRINITY_MUSE`、`TRINITY_CODEX` | `login muse` 的 `muse`、`login dot` 的 `codex` |
| `TRINITY_DOT_ID` | 多個 dot 時指定一個 |
| `TRINITY_GROK_BOT` | 預設 bot，優先於 `grok_bot` |
| `TRINITY_GROK_BOTS` | `status`／`digest` 只看這些 bot，逗號分隔 |
| `TRINITY_GBOT_ACCOUNT` | 登入標籤，優先於 `gbot_account` |

### 安全

trinity 不會叫 agent 刪檔、傳訊息給別人、購買，或改設定與帳號。`brief push` 只在你確認後寫入 Grok 的指令。`hand` 和 `brief push` 先問；不是終端機時沒有 `--yes` 就不送。`hand` 不會把對方的回覆再轉出去。逾時不重送。真正送出的那幾次會在畫面上標成送出，並寫進 ledger。

### 疑難排解

- `gbot` 有多個登入、選不出來：跑 `trinity-cli grok bots`，再用 `grok add`。旗標放在子命令後面。
- 某個登入列出 bot 時是 HTTP 404：`unreachable: sandbox gone — re-login this account in the Grok Bot app`。不是過期 token。在 Grok Bot app 重新登入那個帳號。gbot 沒有重新登入的指令。其他座位照常。
- Grok 有回覆但 trinity 早先沒看到：文字回覆是 `send-message`，而且 `message.type` 是 `text`，不是 `role: assistant`。核准卡片不算回覆。
- Muse 瀏覽器沒起來：`muse-web-cli start --headless`。登入失效：`muse-web-cli login`。
- Your dot 的 activity 慢：`digest --no-activity`。
- 各工具自己的錯誤，看上面表格裡的疑難排解連結。

### 給 agent 用

skill 在 `skills/trinity-cli/SKILL.md`。目錄已經存在時再連過去，例如 `ln -sfn "$PWD/skills/trinity-cli" ~/.claude/skills/trinity-cli`。同樣的位置：`~/.codex/skills`、`~/.agents/skills`、`~/.config/opencode/skills`、`~/.config/opencode/skill`、`~/.cursor/skills`、`~/.grok/skills`。

## English

### What it is

`trinity-cli` is one command in front of three always-on personal agents: ChatGPT Your dot, Grok Bot, and Meta Muse. It needs Python 3.11+. It does not talk to those services itself. It shells out to three tools:

- Your dot: `chatgpt-dot-cli --json`
- Grok Bot: `gbot --json` (this fork)
- Muse: `muse-web-cli --json --autostart`

It does not read `~/.codex/auth.json`, the Grok Bot app session, or Muse cookies. `login` only hands off to those public CLIs and does not print a credential. The one login that stores a token is `login muse`: it has `muse-web-cli credential` write the Muse gateway token only to `~/.trinity-cli/muse-credential` (mode 600) for `--muse-backend api`. trinity itself never reads or prints that file.

Supported systems: Linux (CI), Windows (CI), and macOS (local use and live checks).

### The three seats

| Seat | Tool | Project |
| --- | --- | --- |
| Your dot | `chatgpt-dot-cli` | https://gitlab.com/aa22396584/chatgpt-dot-cli |
| Grok Bot | `gbot` (fork) | https://gitlab.com/aa22396584/grok-bot-cli |
| Muse | `muse-web-cli` | https://gitlab.com/aa22396584/muse-web-cli |

### Related projects

- trinity-cli (this repo) — one CLI over three always-on agents (Your dot, Grok Bot, Muse): https://gitlab.com/aa22396584/trinity-cli
- chatgpt-dot-cli — ChatGPT Your dot: https://gitlab.com/aa22396584/chatgpt-dot-cli
- grok-bot-cli (fork, `gbot`) — Grok Bot: https://gitlab.com/aa22396584/grok-bot-cli
- muse-web-cli — Meta Muse via the web: https://gitlab.com/aa22396584/muse-web-cli

### Install

v0.4.4 pins these versions. After installing trinity and each seat tool, check every `--version`: expect `muse-web-cli 0.1.4`, `trinity-cli 0.4.4`, and `gbot 0.11.2`. The older muse-web-cli v0.1.2 has no `credential` and no api gateway; v0.1.3's `send --wait` can miss the reply in a long chat.

macOS and Linux need Python 3.11+, git, and `uv` on `PATH`. Grok also needs Node.js 22.19.0+ and npm. uv installs commands under `~/.local/bin`; add that directory to `PATH` when `--version` cannot find them. The first `uv tool install` may download a Python.

Do not run `npm install -g git+https://gitlab.com/aa22396584/grok-bot-cli.git#...`. That command exits 0 and leaves a dangling `gbot`. Install the package file attached to the tag:

```bash
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.2"
curl -fsSL -o grok-bot-cli-0.11.2.tgz "https://gitlab.com/-/project/86401528/uploads/95fd5079c4507af7f3f8e61dd04ce6f3/grok-bot-cli-0.11.2.tgz"
npm install -g ./grok-bot-cli-0.11.2.tgz
rm -f grok-bot-cli-0.11.2.tgz
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.4"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.4.4"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

`pipx` can replace `uv tool install` for trinity, chatgpt-dot-cli, and muse-web-cli.

Windows (PowerShell, same pins):

```powershell
irm https://astral.sh/uv/install.ps1 | iex
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.2"
irm "https://gitlab.com/-/project/86401528/uploads/95fd5079c4507af7f3f8e61dd04ce6f3/grok-bot-cli-0.11.2.tgz" -OutFile grok-bot-cli-0.11.2.tgz
npm install -g .\grok-bot-cli-0.11.2.tgz
Remove-Item grok-bot-cli-0.11.2.tgz
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.4"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.4.4"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

On Windows, npm's `gbot` is `gbot.cmd` and uv tools are `.exe`. trinity finds them with `shutil.which` and passes arguments as a list, never through a shell. Windows also needs Node.js 22.19.0+.

Upgrade to the same pin by running the install again. Add `--force` for `uv`. For gbot, download the same `.tgz` and install it again.

Uninstall:

```bash
uv tool uninstall trinity-cli
uv tool uninstall chatgpt-dot-cli
uv tool uninstall muse-web-cli
npm uninstall -g grok-bot-cli
```

`pipx uninstall` matches the three uv tools. In this checkout, `uv tool install --editable .`.

### First-time setup

1. Your dot: `codex login`. Run it again on a 401. `trinity-cli login dot` does the same. Set `TRINITY_DOT_ID` when the account has more than one dot. See the [chatgpt-dot-cli troubleshooting](https://gitlab.com/aa22396584/chatgpt-dot-cli/-/blob/main/README.md#troubleshooting) section.
2. Grok Bot: sign in with the Grok Bot app. `trinity-cli login grok` only repeats that; it does not read the session. When several logins exist, run `gbot accounts` and save the label. See the [grok-bot-cli install](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) section.
3. Muse defaults to the browser backend: `muse-web-cli login` in a visible window, then `muse-web-cli start --headless`. Or `trinity-cli login muse --web`. The api backend (`--muse-backend api`, the Muse gateway) needs a credential: `trinity-cli login muse` runs `muse-web-cli credential`, which logs in when needed and writes the gateway token only to `~/.trinity-cli/muse-credential` (mode 600), never printing it. That file is a token; do not share or commit it. An expired token is reported as 登入工作階段已失效 ("login session expired"); sign in again in Chrome and rerun. `--api-key` still passes a key from stdin to `muse auth set --api-key-stdin`. See the [muse-web-cli troubleshooting](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/README.md#troubleshooting) section.
4. Several Grok seats are keyed by login label plus bot name. `grok` means `grok_default`. Fake values:

```json
{
  "grok_default": "grok-a",
  "grok_seats": [
    {"name": "grok-a", "account": "example-login-a", "bot": "Grok Bot"},
    {"name": "grok-b", "account": "example-login-b", "bot": "Main"}
  ]
}
```

The old `gbot_account` plus `grok_bot` still works as one seat named `grok`. `TRINITY_GBOT_ACCOUNT` and `TRINITY_GROK_BOT` override only that legacy seat. Config edits keep a backup. Muse may also set `"muse_backend"` to `"browser"`, `"api"`, or `"auto"` (fake values; omit it to keep muse-web-cli's browser default).

5. Confirm with `trinity-cli status`. One line per seat. Things waiting on you come first.

### Quick start

```bash
trinity-cli status
trinity-cli digest --peek
trinity-cli ask all "今天進度？"
trinity-cli hand dot#last --to grok:example-bot "請看這則"
trinity-cli wait grok:example-bot
```

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

### Command reference

With no subcommand, `status` runs. `--json` may appear before or after the command and switches to JSON. `--version` prints `trinity-cli` and the version.

`status` has no flags. Exit 0 unless a seat failed. Unsupported is not a failure. `--json`: `waiting` (array of strings), `seats[]` with `seat`, `label`, `state`, plus `summary`, `waiting`, `problems`, `hint`, `details` on success, or `error` and `hint` on failure.

```bash
trinity-cli status
trinity-cli --json status
```

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

`wait TARGET` waits for a new reply after the latest ledger mark. It does not resend.

| Argument or flag | Default | Range |
| --- | --- | --- |
| target | required | `dot`, `muse`, `grok`, `grok:BOT`; bare `grok` uses `grok_bot` |
| `--timeout` | 180 | seconds |
| `--poll` | 5 | first gap, then doubles, capped at 30 seconds |
| `--notify` | off | terminal bell and a macOS notification, with no message body |
| `--then` | do nothing | only `hand ...`, and only last; skipped when no reply arrives |

```bash
trinity-cli wait dot --timeout 60
```

`--json`: `state`, `seat`, `target`, `polls`, `sent`, `error`, and `then` when `--then` ran.

`schedules` has no flags of its own. Your dot uses `automations`. Grok is read only when `gbot --help` mentions `schedules`, `routines`, or `automations`. Muse reads `upcoming` and `activity` (marked 動態). `--muse-backend` may be set on this command. A missing capability is unsupported and does not fail the command. Matching titles or times across seats are flagged.

```bash
trinity-cli schedules
```

`--json`: `seats`, `duplicates`.

`who TASK` only suggests. It sends nothing. The task is required.

```bash
trinity-cli who "翻譯這段"
```

`--json`: `advisory`, `suggestion`, `headline`, `ranking`.

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

`grok bots` lists every bot on every `gbot accounts` login: name, description, login label, reachable or not, and whether it is a configured seat. It does not print ids.

`grok add NAME --account LABEL --bot BOT` writes a seat, with optional `--default`. `grok remove NAME` deletes that seat. Both keep a backup of `config.json`.

```bash
trinity-cli grok bots
trinity-cli grok add grok-a --account example-login-a --bot "Grok Bot" --default
trinity-cli grok remove grok-b
trinity-cli ask grok-a "one sentence"
trinity-cli ask grok --bot "Other" --account example-login-a "ask this one without saving a seat"
trinity-cli ask all "ask every seat"
```

`status`, `digest`, `ask`, `hand`, `wait`, `schedules`, `who`, `brief push`, and `log` accept a seat name. `grok` is the default seat. `all` is dot, every enabled Grok seat, and muse. Each send gets its own nonce. When the same bot name exists on two logins, `--bot` requires `--account`. `wait` and `digest` take those flags too.

### Concepts

The seats do not have the same capabilities. A missing one is reported as unsupported, still exit 0, and does not fail the others. `muse-web-cli` defaults to the browser backend; `api` is the Muse gateway and reads `~/.trinity-cli/muse-credential`. trinity passes `--backend`: `--muse-backend` wins over config `muse_backend`, which wins over `MUSE_WEB_BACKEND`. With none of those set, trinity omits `--backend` and muse-web-cli keeps its own default. The value is `browser`, `api`, or `auto`. `auto` tries api first and uses browser for a capability only when that call exits 4, and the line names the backend that served it. A timed-out `send` is not tried on the other backend. An unsupported api capability with no fallback is reported on its own and trinity does not crash. Muse has no instruction API. Grok groups work with `ask grok <group>` and `grok:<name>` on `hand` / `wait`; `status` and `digest` cover bots only.

Cursors live in `cursors` inside `state.json`, and each Grok seat has its own key (for example `grok-a.messages`). Only `digest` moves them, and only after the output was printed. `--peek`, `--since`, `hand`, and `wait` do not. When the previous tail is gone, the timeline says 可能漏看 ("possibly missed"). One unreachable Grok seat does not stop the others; that seat is a failure with the re-login hint.

Every `ask` and `hand` writes `ledger.jsonl` before the send. Your text is unchanged, then a blank line and `[trinity abc123]`. Readback looks for that tag in your own messages. A timeout is reported and never resent.

Before a Muse read or send, trinity calls `chats`. A side chat is not sent into and does not move the Muse cursor. Status says 目前在副聊天室. If `chats` is unsupported or the switcher panel is missing, the open conversation is used and the status line says so. Chat titles are never printed.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Fine. Unsupported counts as fine. Exit 0 when any targeted seat succeeds; a failure is still printed |
| 1 | Every targeted seat that counts failed or timed out. `hand` and `wait` have one target |
| 2 | Bad usage, or `hand` / `brief push` sent nothing because nobody confirmed |

| Seat state | Fix |
| --- | --- |
| Your dot 401 or unusable login | `codex login`. See [chatgpt-dot-cli troubleshooting](https://gitlab.com/aa22396584/chatgpt-dot-cli/-/blob/main/README.md#troubleshooting) |
| Your dot network or non-200 | Try `chatgpt-dot-cli list` |
| chatgpt-dot-cli missing | Install it, or set `TRINITY_DOT_CLI` |
| Several Grok logins | `gbot accounts`, then set `gbot_account`. See the [grok-bot-cli install](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) section. |
| Grok login unusable | Open the Grok Bot app and run `gbot doctor` |
| gbot missing | Install it, or set `TRINITY_GBOT` |
| Muse browser down | `muse-web-cli start --headless` |
| Muse browser session expired | `muse-web-cli login`. See [muse-web-cli troubleshooting](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/README.md#troubleshooting) |
| Muse api credential missing | `trinity-cli login muse` |
| Muse api login session expired | Sign in to Muse again in the Chrome window, then `trinity-cli login muse` |
| Muse credential file mode | macOS/Linux: `chmod 600 ~/.trinity-cli/muse-credential`. Windows: `icacls` so only the current user can read it |
| Muse on a side chat | Switch back to the main chat in the Muse window |
| Muse profile busy | Quit that window, then `muse-web-cli start --headless` |
| Muse region blocked | This tool does not bypass a region limit |
| muse-web-cli or muse missing | Install it, or set `TRINITY_MUSE_CLI` or `TRINITY_MUSE` |

### Files and environment variables

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

### Safety

trinity does not ask an agent to delete files, message anyone, buy anything, or change settings or accounts. `brief push` writes a Grok bot's instructions only after you confirm. `hand` and `brief push` ask first; without a terminal they send nothing unless you pass `--yes`. `hand` does not forward the destination's reply onward. A timeout is never resent. Live sends are labeled as sends and written to the ledger.

### Troubleshooting

- gbot has several logins and cannot choose: run `trinity-cli grok bots`, then `grok add`. The flag goes after the subcommand.
- A login whose bot list is HTTP 404: `unreachable: sandbox gone — re-login this account in the Grok Bot app`. That is not an expired token. Re-login that account in the Grok Bot app. gbot has no re-login command. Other seats keep working.
- Grok replied and trinity used to miss it: a spoken reply is a `send-message` entry whose `message.type` is `text`, not `role: assistant`. Approval cards are not replies.
- Muse browser down: `muse-web-cli start --headless`. Session expired: `muse-web-cli login`.
- Your dot activity is slow: `digest --no-activity`.
- For a tool's own errors, use the troubleshooting links in the table above.

### For agents

The skill is `skills/trinity-cli/SKILL.md`. Link it only when the directory already exists, for example `ln -sfn "$PWD/skills/trinity-cli" ~/.claude/skills/trinity-cli`. The same set: `~/.codex/skills`, `~/.agents/skills`, `~/.config/opencode/skills`, `~/.config/opencode/skill`, `~/.cursor/skills`, `~/.grok/skills`.

## License

MIT

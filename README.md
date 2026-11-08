# trinity-cli

> 正本和 issue 在 https://gitlab.com/aa22396584/trinity-cli。

[![pipeline](https://gitlab.com/aa22396584/trinity-cli/badges/main/pipeline.svg)](https://gitlab.com/aa22396584/trinity-cli/-/pipelines)
[![release](https://gitlab.com/aa22396584/trinity-cli/-/badges/release.svg)](https://gitlab.com/aa22396584/trinity-cli/-/releases)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[中文](#中文) · [English](#english)

## 中文

### 這是什麼

`trinity-cli` 是一個指令，擋在三個一直開著的個人 agent 前面：ChatGPT 的 Your dot、Grok Bot，以及 Meta 的 Muse。它需要 Python 3.11+。它不自己連這些服務，而是轉呼叫三個工具：

- Your dot：`chatgpt-dot-cli --json`
- Grok Bot：`gbot --json`（這個 fork）
- Muse：`muse-web-cli --json --autostart`

它不讀 `~/.codex/auth.json`、Grok Bot app 的登入，或 Muse 的 cookie。`login` 只轉給那些工具既有的公開指令，不印憑證。唯一會存下 token 的是 `login muse`：它叫 `muse-web-cli credential` 把 Muse gateway token 只寫進 `~/.trinity-cli/muse-credential`（mode 600），給 `--muse-backend api` 用。trinity 自己不讀、不印這個檔。

非官方：這是個人專案，跟 OpenAI、xAI、Cursor（Anysphere）、Meta 都沒有關係，也沒有得到它們的背書或支援。它透過三個座位工具使用你自己的帳號，那些工具走的是沒有公開文件的介面，隨時可能改變或失效。自動化使用可能違反各服務的使用條款，帳號風險自負。

支援的系統見[平台](#平台)。

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

v0.4.6 釘這些版本。三個座位工具和 trinity 都裝好後，用 `--version` 對一下：應印出 `muse-web-cli 0.1.5`、`trinity-cli 0.4.6`、`gbot 0.11.2`。舊的 muse-web-cli v0.1.2 沒有 `credential` 和 api gateway；v0.1.3 的 `send --wait` 在長聊天室會等不到回覆；v0.1.4 認不得 Muse 現在的側欄式介面，browser backend 會回 `ui_changed`。

macOS 與 Linux 需要 Python 3.11+、git、以及已在 PATH 上的 `uv`。Grok 還要 Node.js 22.19.0+ 和 npm。uv 的執行檔在 `~/.local/bin`；`--version` 找不到時把那個目錄加進 PATH。第一次 `uv tool install` 可能會下載 Python。

不要用 `npm install -g git+https://gitlab.com/aa22396584/grok-bot-cli.git#...`。那一行會結束碼 0，但 `gbot` 是斷掉的連結。下面的 `grok-bot-cli-0.11.2.tgz` 是 grok-bot-cli tag `v0.11.2-iml1s.2` 附的套件檔，trinity-cli 的版本釘選是另一個。改裝那個 tag 附的套件檔：

```bash
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.3"
curl -fsSL -o grok-bot-cli-0.11.2.tgz "https://gitlab.com/-/project/86401528/uploads/95fd5079c4507af7f3f8e61dd04ce6f3/grok-bot-cli-0.11.2.tgz"
npm install -g ./grok-bot-cli-0.11.2.tgz
rm -f grok-bot-cli-0.11.2.tgz
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.5"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.4.6"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

`pipx` 可以取代上面的 `uv tool install`（trinity、chatgpt-dot-cli、muse-web-cli）。

Windows（PowerShell，同樣的釘選）：

```powershell
irm https://astral.sh/uv/install.ps1 | iex
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.3"
irm "https://gitlab.com/-/project/86401528/uploads/95fd5079c4507af7f3f8e61dd04ce6f3/grok-bot-cli-0.11.2.tgz" -OutFile grok-bot-cli-0.11.2.tgz
npm install -g .\grok-bot-cli-0.11.2.tgz
Remove-Item grok-bot-cli-0.11.2.tgz
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.5"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.4.6"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

Windows 上 npm 的 `gbot` 是 `gbot.cmd`，uv 的工具是 `.exe`。trinity 用 `shutil.which` 找它們。`gbot.cmd` 這種 npm 包裝檔，trinity 直接用 node 跑它指向的腳本，參數不經過 cmd.exe。其他 `.cmd`／`.bat` 會經過 cmd.exe，每個參數加引號；含 `"`、`%` 或換行的參數會被拒絕。Windows 也要 Node.js 22.19.0+。

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
2. Grok Bot：打開 Grok Bot app 登入，並在 app 裡建立至少一個 bot。`trinity-cli login grok` 只會重複這句，不會讀那個登入。接著跑 `trinity-cli grok bots`，看每個登入標籤上有哪些 bot，再挑一個存成座位：`trinity-cli grok add researcher --account 登入標籤 --bot "bot 名稱" --default`。只有一個登入和一個 bot 時，不加座位也能用 `grok`。細節見 [grok-bot-cli 安裝](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install)。
3. Muse 預設走網頁（browser 後端）：`muse-web-cli login`（看得到的視窗），完成後 `muse-web-cli start --headless`。或 `trinity-cli login muse --web`。api 後端（`--muse-backend api`，走 Muse gateway）要憑證：`trinity-cli login muse` 會執行 `muse-web-cli credential`，沒登入就先走登入，再把 gateway token 只寫進 `~/.trinity-cli/muse-credential`（mode 600），不印出。這個檔是 token，不要分享或提交。token 過期時會說「登入工作階段已失效」，在 Chrome 重新登入後再跑一次。`--api-key` 仍把金鑰從標準輸入交給 `muse auth set --api-key-stdin`。細節見 [muse-web-cli 排解](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/README.md#排解)。
4. 多個 Grok 座位用登入標籤加 bot 名稱。`grok` 指向 `grok_default`。假值：

```json
{
  "grok_default": "researcher",
  "grok_seats": [
    {"name": "researcher", "account": "example-login-a", "bot": "Researcher"},
    {"name": "writer", "account": "example-login-b", "bot": "Writer"}
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

`migrate 座位 計畫檔` 把別的工具寫好的搬家計畫（`trinity-migration-plan` v1，例如 `gbot migrate import --to muse`）送進 Muse 或 Your dot，再讀回、再問驗收題。座位只能是 `muse` 或 `dot`。

| 旗標或參數 | 預設 | 範圍 |
| --- | --- | --- |
| `座位` | 必填 | `muse`、`dot` |
| `計畫檔` | 必填 | JSON 計畫；多出來的欄位會被拒絕 |
| `--yes` | 關 | 不問直接送；不是終端機時一定要加，否則不送 |
| `--timeout` | 300 | 每一步等回覆的秒數；逾時不重送 |
| `--poll` | 10 | 讀回間隔秒數 |
| `--resend-unknown` | 關 | 上次送出後讀回看不到的那一步，才准重送 |
| `--no-questions` | 關 | 只送與讀回，不問驗收題 |
| `--redo` | 無 | 逗號分隔的步驟 id：已回覆也重送 |
| `--check-only` | 關 | 一步都不送，只讀回、問驗收題；進度檔裡沒有送達且回覆對的步驟算 `not delivered`，結果不算過；不必加 `--yes`，不能加 `--redo` |

每一步是一則訊息，跟 `ask` 一樣有 nonce、先寫 ledger 再送、讀回確認。進度存在 `TRINITY_HOME/migrations/<計畫 id>.json`：中途停了（逾時、登入失效、Ctrl-C）就再跑同一行，已回覆的步驟會跳過，送出狀態不明的步驟先讀回聊天室，看得到就不重送。回覆每次都重新比對 `expectReply`，上次沒對上的這次也不會算過。進度檔壞掉、或同一份計畫已有另一個 migrate 在跑，就停下來不送；送出後計畫裡那一步的內容改了，也會停，要送新內容就加 `--redo 步驟`。驗收題每次都開一個新的副聊天室，最後只刪這次開的那一個。Muse 只有一個 agent、記憶共用，但可以有很多聊天室：計畫有 `chat` 時，會用 api 後端開（或沿用）同名副聊天室，所有步驟都送在那裡，做完把切換狀態改回主聊天室；api 後端不能用時改用目前開著的聊天室，並在結果註明。dot 一個帳號只有一個收件匣，步驟都送在那裡。送完後：Muse 讀 Memory.md 比對關鍵字（不是「僅供參考」的讀回讀不到就算沒過）；dot 的記憶讀不到，驗收題就是讀回。結束碼 0 表示全部送達、讀回與驗收都過；1 表示還沒完成（看 `stopped`）；2 是參數或沒有確認。

```bash
trinity-cli migrate muse ~/.grok-bot-cli/migrations/example.muse-plan.json --yes
```

`--json`：`plan_id`、`seat`、`ok`、`stopped`、`state_path`、`chat`、`chat_note`、`steps[]`（`id`、`state`、`ok`、`note`、`nonce`、`reply`）、`checks[]`、`questions[]`。

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
trinity-cli grok add researcher --account example-login-a --bot "Researcher" --default
trinity-cli grok remove writer
trinity-cli ask researcher "一句話"
trinity-cli ask grok --bot "Other" --account example-login-a "臨時問這個"
trinity-cli ask all "問全部"
```

`status`、`digest`、`ask`、`hand`、`wait`、`schedules`、`who`、`brief push`、`log` 都認座位名。`grok` 是預設座位。`all` 是 dot、每個啟用的 Grok 座位、再加上 muse。每次送出有自己的 nonce。同一個 bot 名稱出現在兩個登入時，`--bot` 必須加 `--account`。`wait` 和 `digest` 也接受這兩個旗標。

### 概念

三個座位的能力不一樣。沒有的能力會明白寫「不支援」，結束碼仍是 0，不會連帶讓別的座位失敗。`muse-web-cli` 的預設是 browser；`api` 走 Muse gateway，讀 `~/.trinity-cli/muse-credential`。trinity 會傳 `--backend`：`--muse-backend` 優先於設定檔的 `muse_backend`，再來是 `MUSE_WEB_BACKEND`。三個都沒寫就不傳，交給 muse-web-cli 自己的預設。值是 `browser`、`api` 或 `auto`。`auto` 先試 api，該能力若是 exit 4 才改走 browser，並標出實際用的後端。`send` 逾時不會改走另一個後端。api 有能力不支援且沒有 fallback 時，那個能力單獨標不支援，不會讓 trinity 當掉。Muse 沒有指令 API。Grok 群組只在 `ask grok <群組>` 和 `hand`／`wait` 的 `grok:<名字>` 可用；`status` 和 `digest` 只看 bot。

讀取位置在 `state.json` 的 `cursors`，Grok 依座位分開（例如 `researcher.messages`）。只有 `digest` 把輸出印完才前進。`--peek`、`--since`、`hand`、`wait` 都不動。對不上上次的結尾時標「可能漏看」。一個 Grok 座位不可達時，其他座位照常；那個座位標成失敗，並附上重新登入的提示。

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
| Grok 多個登入或多個 bot | `trinity-cli grok bots`，再 `trinity-cli grok add NAME --account LABEL --bot BOT --default`。見 [grok-bot-cli 安裝](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) |
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

### 隱私

- trinity 沒有遙測，自己不連網路。網路請求都是三個座位工具發出的，各自送到自己的服務。
- 資料只存在本機的 `TRINITY_HOME`。`ledger.jsonl` 記時間、座位、bot 名稱、nonce 和結果，不存訊息內文。`state.json` 只有讀取位置。
- 文字輸出把家目錄寫成 `~`，`--json` 保留完整路徑。
- `grok bots` 和 `log` 不印 id；印出的錯誤會先清掉 token、cookie 這類欄位值。貼輸出到 issue 前，還是先看一下有沒有訊息內容或名字。

### 平台

| 系統 | Python | 驗證方式 |
| --- | --- | --- |
| Linux | 3.11、3.12 | GitLab CI：完整離線測試；`contract:muse` 在暫時的家目錄跑 README 釘的 muse-web-cli |
| Windows | 3.12 | GitLab CI：同一套離線測試，改到程式、測試或相依時自動跑 |
| macOS | 3.11、3.12、3.13 | 維護者本機：同一套離線測試，加上照這份 README 從 tag 安裝的首次使用檢查 |

測試用假的座位工具，不連任何服務。三個座位工具各自的平台表在它們的 README。CI 預設使用 GitLab.com 的 runner。維護者可設定 CI/CD 變數 `LINUX_RUNNER_TAG` 與 `WINDOWS_RUNNER_TAG`，把 job 指到自己的 runner。

### 參與開發

見 [CONTRIBUTING.md](CONTRIBUTING.md)。安全問題照 [SECURITY.md](SECURITY.md) 回報，不要開公開 issue。

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

Unofficial: this is a personal project, not affiliated with, endorsed by, or supported by OpenAI, xAI, Cursor (Anysphere), or Meta. It uses your own accounts through the three seat tools, which rely on undocumented interfaces that can change or break at any time. Automated use may break a service's terms; any account risk is yours.

Supported systems: see [Platforms](#platforms).

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

v0.4.6 pins these versions. After installing trinity and each seat tool, check every `--version`: expect `muse-web-cli 0.1.5`, `trinity-cli 0.4.6`, and `gbot 0.11.2`. The older muse-web-cli v0.1.2 has no `credential` and no api gateway; v0.1.3's `send --wait` can miss the reply in a long chat; v0.1.4 does not recognize Muse's current sidebar shell, so the browser backend reports `ui_changed`.

macOS and Linux need Python 3.11+, git, and `uv` on `PATH`. Grok also needs Node.js 22.19.0+ and npm. uv installs commands under `~/.local/bin`; add that directory to `PATH` when `--version` cannot find them. The first `uv tool install` may download a Python.

Do not run `npm install -g git+https://gitlab.com/aa22396584/grok-bot-cli.git#...`. That command exits 0 and leaves a dangling `gbot`. The `grok-bot-cli-0.11.2.tgz` below is the package file from grok-bot-cli tag `v0.11.2-iml1s.2`. The trinity-cli version pin is separate. Install the package file attached to that tag:

```bash
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.3"
curl -fsSL -o grok-bot-cli-0.11.2.tgz "https://gitlab.com/-/project/86401528/uploads/95fd5079c4507af7f3f8e61dd04ce6f3/grok-bot-cli-0.11.2.tgz"
npm install -g ./grok-bot-cli-0.11.2.tgz
rm -f grok-bot-cli-0.11.2.tgz
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.5"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.4.6"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

`pipx` can replace `uv tool install` for trinity, chatgpt-dot-cli, and muse-web-cli.

Windows (PowerShell, same pins):

```powershell
irm https://astral.sh/uv/install.ps1 | iex
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.3"
irm "https://gitlab.com/-/project/86401528/uploads/95fd5079c4507af7f3f8e61dd04ce6f3/grok-bot-cli-0.11.2.tgz" -OutFile grok-bot-cli-0.11.2.tgz
npm install -g .\grok-bot-cli-0.11.2.tgz
Remove-Item grok-bot-cli-0.11.2.tgz
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.5"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.4.6"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

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

### First-time setup

1. Your dot: `codex login`. Run it again on a 401. `trinity-cli login dot` does the same. Set `TRINITY_DOT_ID` when the account has more than one dot. See the [chatgpt-dot-cli troubleshooting](https://gitlab.com/aa22396584/chatgpt-dot-cli/-/blob/main/README.md#troubleshooting) section.
2. Grok Bot: sign in with the Grok Bot app and create at least one bot there. `trinity-cli login grok` only repeats that; it does not read the session. Then run `trinity-cli grok bots` to see the bots on each login label, and save one as a seat: `trinity-cli grok add researcher --account LABEL --bot "BOT NAME" --default`. With one login and one bot, `grok` works without a saved seat. See the [grok-bot-cli install](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) section.
3. Muse defaults to the browser backend: `muse-web-cli login` in a visible window, then `muse-web-cli start --headless`. Or `trinity-cli login muse --web`. The api backend (`--muse-backend api`, the Muse gateway) needs a credential: `trinity-cli login muse` runs `muse-web-cli credential`, which logs in when needed and writes the gateway token only to `~/.trinity-cli/muse-credential` (mode 600), never printing it. That file is a token; do not share or commit it. An expired token is reported as 登入工作階段已失效 ("login session expired"); sign in again in Chrome and rerun. `--api-key` still passes a key from stdin to `muse auth set --api-key-stdin`. See the [muse-web-cli troubleshooting](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/README.md#troubleshooting) section.
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
| `--check-only` | off | send no step; read back and ask the questions only. A step the progress file does not record as delivered with a matching reply is `not delivered` and the result is not ok. No `--yes` needed; not with `--redo` |

Each step is one message with a nonce, written to the ledger before it leaves and confirmed by read-back, like `ask`. Progress is kept in `TRINITY_HOME/migrations/<plan id>.json`: when a run stops (timeout, expired login, Ctrl-C), run the same command again. Replied steps are skipped, and a step whose delivery is unknown is first looked up in the chat and not resent when it is there. Replies are checked against `expectReply` on every run, so a reply that missed stays a miss. A progress file that cannot be read, or another migrate already running the same plan, stops the run before anything is sent; so does a step whose text changed after it was sent (send the new text with `--redo STEP`). The acceptance questions always go to a new side chat, and only that chat is deleted afterwards. Muse is one agent with shared memory but many chats: when the plan has `chat`, the api backend opens (or reuses) a side chat with that title, every step goes there, and the switched chat is set back to main afterwards; without the api backend the open chat is used and the result says so. A dot account has one inbox, so steps go there. Afterwards Muse's Memory.md is checked for the plan's keywords (a required read-back that cannot be read fails); a dot's memory cannot be read, so the acceptance questions are the read-back. Exit 0 means delivered, read back and accepted; 1 means not finished (see `stopped`); 2 is usage or no confirmation.

```bash
trinity-cli migrate muse ~/.grok-bot-cli/migrations/example.muse-plan.json --yes
```

`--json`: `plan_id`, `seat`, `ok`, `stopped`, `state_path`, `chat`, `chat_note`, `steps[]` (`id`, `state`, `ok`, `note`, `nonce`, `reply`), `checks[]`, `questions[]`.

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
trinity-cli grok add researcher --account example-login-a --bot "Researcher" --default
trinity-cli grok remove writer
trinity-cli ask researcher "one sentence"
trinity-cli ask grok --bot "Other" --account example-login-a "ask this one without saving a seat"
trinity-cli ask all "ask every seat"
```

`status`, `digest`, `ask`, `hand`, `wait`, `schedules`, `who`, `brief push`, and `log` accept a seat name. `grok` is the default seat. `all` is dot, every enabled Grok seat, and muse. Each send gets its own nonce. When the same bot name exists on two logins, `--bot` requires `--account`. `wait` and `digest` take those flags too.

### Concepts

The seats do not have the same capabilities. A missing one is reported as unsupported, still exit 0, and does not fail the others. `muse-web-cli` defaults to the browser backend; `api` is the Muse gateway and reads `~/.trinity-cli/muse-credential`. trinity passes `--backend`: `--muse-backend` wins over config `muse_backend`, which wins over `MUSE_WEB_BACKEND`. With none of those set, trinity omits `--backend` and muse-web-cli keeps its own default. The value is `browser`, `api`, or `auto`. `auto` tries api first and uses browser for a capability only when that call exits 4, and the line names the backend that served it. A timed-out `send` is not tried on the other backend. An unsupported api capability with no fallback is reported on its own and trinity does not crash. Muse has no instruction API. Grok groups work with `ask grok <group>` and `grok:<name>` on `hand` / `wait`; `status` and `digest` cover bots only.

Cursors live in `cursors` inside `state.json`, and each Grok seat has its own key (for example `researcher.messages`). Only `digest` moves them, and only after the output was printed. `--peek`, `--since`, `hand`, and `wait` do not. When the previous tail is gone, the timeline says 可能漏看 ("possibly missed"). One unreachable Grok seat does not stop the others; that seat is a failure with the re-login hint.

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
| Several Grok logins or bots | `trinity-cli grok bots`, then `trinity-cli grok add NAME --account LABEL --bot BOT --default`. See the [grok-bot-cli install](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) section. |
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

### Privacy

- trinity has no telemetry and makes no network requests of its own. The three seat tools make the requests, each to its own service.
- Data stays on your machine in `TRINITY_HOME`. `ledger.jsonl` records times, seats, bot names, nonces, and outcomes, not message text. `state.json` holds cursors only.
- Text output shows your home directory as `~`; `--json` keeps full paths.
- `grok bots` and `log` print no ids, and printed errors have token and cookie values removed. Still check output for message text or names before pasting it into an issue.

### Platforms

| OS | Python | How it was checked |
| --- | --- | --- |
| Linux | 3.11, 3.12 | GitLab CI: the full offline suite; `contract:muse` runs the README-pinned muse-web-cli in a temporary home |
| Windows | 3.12 | GitLab CI: the same offline suite, run automatically when code, tests, or dependencies change |
| macOS | 3.11, 3.12, 3.13 | Maintainer machine: the same offline suite, plus a first-run check that installs from the tags as this README says |

The tests use fake seat tools and contact no service. Each seat tool has its own platform table in its README. CI uses GitLab.com runners by default. Maintainers can point jobs at their own runners by setting the CI/CD variables `LINUX_RUNNER_TAG` and `WINDOWS_RUNNER_TAG`.

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report security problems as described in [SECURITY.md](SECURITY.md), not in a public issue.

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

[MIT](LICENSE)

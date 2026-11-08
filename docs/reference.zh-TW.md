# trinity-cli 參考

[English](reference.md) | 繁體中文

安裝、快速開始和指令清單在 [README](../README.zh-TW.md)。這頁是細節。

- [安裝細節](#安裝細節)
- [第一次設定](#第一次設定)
- [輸出形狀](#輸出形狀)
- [指令參考](#指令參考)
- [概念](#概念)
- [結束碼](#結束碼)
- [檔案與環境變數](#檔案與環境變數)
- [疑難排解](#疑難排解)
- [平台](#平台)

## 安裝細節

釘選的安裝指令和 `--version` 檢查在 [README](../README.zh-TW.md#安裝)。為什麼釘這些版本：舊的 muse-web-cli v0.1.2 沒有 `credential` 和 api gateway；v0.1.3 的 `send --wait` 在長聊天室會等不到回覆；v0.1.4 認不得 Muse 現在的側欄式介面，browser backend 會回 `ui_changed`。

`pipx` 可以取代 README 裡的 `uv tool install`（trinity、chatgpt-dot-cli、muse-web-cli）。

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

## 第一次設定

1. Your dot：`codex login`。401 時再跑一次。也可以 `trinity-cli login dot`。多個 dot 時設 `TRINITY_DOT_ID`。細節見 [chatgpt-dot-cli 疑難排解](https://gitlab.com/aa22396584/chatgpt-dot-cli/-/blob/main/docs/reference.zh-TW.md#疑難排解)。
2. Grok Bot：打開 Grok Bot app 登入，並在 app 裡建立至少一個 bot。`trinity-cli login grok` 只會重複這句，不會讀那個登入。接著跑 `trinity-cli grok bots`，看每個登入標籤上有哪些 bot，再挑一個存成座位：`trinity-cli grok add researcher --account 登入標籤 --bot "bot 名稱" --default`。只有一個登入和一個 bot 時，不加座位也能用 `grok`。細節見 [grok-bot-cli 安裝](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install)。
3. Muse 預設走網頁（browser 後端）：`muse-web-cli login`（看得到的視窗），完成後 `muse-web-cli start --headless`。或 `trinity-cli login muse --web`。api 後端（`--muse-backend api`，走 Muse gateway）要憑證：`trinity-cli login muse` 會執行 `muse-web-cli credential`，沒登入就先走登入，再把 gateway token 只寫進 `~/.trinity-cli/muse-credential`（mode 600），不印出。這個檔是 token，不要分享或提交。token 過期時會說「登入工作階段已失效」，在 Chrome 重新登入後再跑一次。`--api-key` 仍把金鑰從標準輸入交給 `muse auth set --api-key-stdin`。細節見 [muse-web-cli 排解](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/docs/reference.zh-TW.md#排解)。
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

## 輸出形狀

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

## 指令參考

沒有子命令時跑 `status`。`--json` 放在指令前後都可以，改印 JSON。`--version` 印 `trinity-cli` 與版本。

### `status`

`status` 沒有旗標。結束碼 0，除非某個座位失敗。不支援不算失敗。`--json`：`waiting`（字串陣列）、`seats[]` 的 `seat`、`label`、`state`，成功時還有 `summary`、`waiting`、`problems`、`hint`、`details`；失敗時是 `error`、`hint`。

```bash
trinity-cli status
trinity-cli --json status
```

### `digest`

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

### `ask`

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

### `hand`

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

### `wait`

`wait 對象` 從 ledger 最後一筆之後等新回覆。不重送。

| 旗標或參數 | 預設 | 範圍 |
| --- | --- | --- |
| 對象 | 必填 | `dot`、`muse`、`grok`（預設座位）、`grok:BOT`，或座位名 |
| `--timeout` | 180 | 秒 |
| `--poll` | 5 | 第一次間隔，之後加倍，上限 30 秒 |
| `--notify` | 關 | 終端機鈴聲和 macOS 通知，通知不含內文 |
| `--then` | 不做 | 只能是 `hand ...`，而且要放最後；沒有回覆就不會跑 |

```bash
trinity-cli wait dot --timeout 60
```

`--json`：`state`、`seat`、`target`、`polls`、`sent`、`error`；有 `--then` 時多一個 `then`。

### `schedules`

`schedules` 沒有自己的旗標。Your dot 用 `automations`。Grok 只在 `gbot --help` 出現 `schedules`、`routines` 或 `automations` 時才讀。Muse 讀 `upcoming`，也讀 `activity`（標成動態）。`--muse-backend` 可加在這個指令上。沒有這個能力會標不支援，不讓整個指令失敗。標題或時間在兩個座位重複時會標出來。

```bash
trinity-cli schedules
```

`--json`：`seats`、`duplicates`。

### `who`

`who 事情` 只建議，不送出。事情必填。

```bash
trinity-cli who "翻譯這段"
```

`--json`：`advisory`、`suggestion`、`headline`、`ranking`。

### `brief`

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

### `log`

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

### `migrate`

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
| `--min-interval` | 20 | 兩次送出之間至少隔幾秒，照人用 app 的節奏；每則都等到回覆才送下一則。對方回「太頻繁」（429、rate limit）就停下不重送，之後再跑同一行會從那一步接著做；若是某一步的回覆說太頻繁，下一步不送，要加 `--redo 步驟` 才會重送那一步。上次送出的時間記在進度檔，下一次執行也照這個間隔。驗收題送不出去（沒送出、太頻繁、逾時）就停，後面的題目不問 |
| `--check-only` | 關 | 一步都不送，只讀回、問驗收題；進度檔裡沒有送達且回覆對的步驟算 `not delivered`，結果不算過；不必加 `--yes`，不能加 `--redo` |

每一步是一則訊息（可以附檔，見計畫的 `attach`：絕對路徑，或 `{"path": …, "sha256": …}`；送出前重算 sha256，和計畫不符就停下不送），跟 `ask` 一樣有 nonce、先寫 ledger 再送、讀回確認。進度存在 `TRINITY_HOME/migrations/<計畫 id>.json`：中途停了（逾時、登入失效、Ctrl-C）就再跑同一行，已回覆的步驟會跳過，送出狀態不明的步驟先讀回聊天室，看得到就不重送。回覆每次都重新比對 `expectReply`，上次沒對上的這次也不會算過。進度檔壞掉、或同一份計畫已有另一個 migrate 在跑，就停下來不送；送出後計畫裡那一步的內容改了，也會停，要送新內容就加 `--redo 步驟`。驗收題每次都開一個新的副聊天室（認 muse-web-cli `chats --create` 回報的 `created` id），最後只刪它；開不成就不問，驗收算沒過。Muse 只有一個 agent、記憶共用，但可以有很多聊天室：計畫有 `chat` 時，會用 api 後端開（或沿用）同名副聊天室，所有步驟都送在那裡，做完把切換狀態改回主聊天室；api 後端不能用時改用目前開著的聊天室，並在結果註明。dot 一個帳號只有一個收件匣，步驟都送在那裡。送完後：Muse 讀 Memory.md 比對關鍵字（不是「僅供參考」的讀回讀不到就算沒過）；dot 的記憶讀不到，驗收題就是讀回。結束碼 0 表示全部送達、讀回與驗收都過；1 表示還沒完成（看 `stopped`）；2 是參數或沒有確認。

migrate 需要的座位工具功能：muse-web-cli 的 `chats --create` 回報 `created` id、`send --attach` 與 `--attach-sha256`，以及 chatgpt-dot-cli 的 `send --attach` 與 `--attach-sha256`。muse-web-cli v0.1.8 與 chatgpt-dot-cli v0.2.6 起都有（README 釘的就是這兩版）。

```bash
trinity-cli migrate muse ~/.grok-bot-cli/migrations/example.muse-plan.json --yes
```

`--json`：`plan_id`、`seat`、`ok`、`stopped`、`state_path`、`chat`、`chat_note`、`steps[]`（`id`、`state`、`ok`、`note`、`nonce`、`reply`）、`checks[]`、`questions[]`。

### `login`

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

### `grok`

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

### 座位名

`status`、`digest`、`ask`、`hand`、`wait`、`schedules`、`who`、`brief push`、`log` 都認座位名。`grok` 是預設座位。`all` 是 dot、每個啟用的 Grok 座位、再加上 muse。每次送出有自己的 nonce。同一個 bot 名稱出現在兩個登入時，`--bot` 必須加 `--account`。`wait` 和 `digest` 也接受這兩個旗標。

## 概念

三個座位的能力不一樣。沒有的能力會明白寫「不支援」，結束碼仍是 0，不會連帶讓別的座位失敗。`muse-web-cli` 的預設是 browser；`api` 走 Muse gateway，讀 `~/.trinity-cli/muse-credential`。trinity 會傳 `--backend`：`--muse-backend` 優先於設定檔的 `muse_backend`，再來是 `MUSE_WEB_BACKEND`。三個都沒寫就不傳，交給 muse-web-cli 自己的預設。值是 `browser`、`api` 或 `auto`。`auto` 先試 api，該能力若是 exit 4 才改走 browser，並標出實際用的後端。`send` 逾時不會改走另一個後端。api 有能力不支援且沒有 fallback 時，那個能力單獨標不支援，不會讓 trinity 當掉。Muse 沒有指令 API。Grok 群組只在 `ask grok <群組>` 和 `hand`／`wait` 的 `grok:<名字>` 可用；`status` 和 `digest` 只看 bot。

讀取位置在 `state.json` 的 `cursors`，Grok 依座位分開（例如 `researcher.messages`）。只有 `digest` 把輸出印完才前進。`--peek`、`--since`、`hand`、`wait` 都不動。對不上上次的結尾時標「可能漏看」。一個 Grok 座位不可達時，其他座位照常；那個座位標成失敗，並附上重新登入的提示。

每次 `ask` 和 `hand` 在送出前就寫 `ledger.jsonl`。你的原文後面空一行，加一行 `[trinity abc123]`。讀回在你自己的訊息裡找這個標籤。逾時只報告，不重送。

Muse 在讀和送之前先看 `chats`。目前是副聊天室時不送出，也不推進 Muse 的讀取位置，status 寫「目前在副聊天室」。`chats` 不支援或切換面板不在時，仍用目前開啟的對話，並在 status 註明。聊天室標題不會印出來。

## 結束碼

| 碼 | 意思 |
| --- | --- |
| 0 | 正常。不支援也算這裡。這次點到的座位裡只要有一個成功就是 0，失敗仍會印出 |
| 1 | 這次點到、且算數的座位全部失敗或逾時。`hand` 和 `wait` 只有一個對象 |
| 2 | 參數不對，或 `hand`／`brief push` 沒有確認所以沒送 |

| 座位狀態 | 修法 |
| --- | --- |
| Your dot 401 或登入檔不能用 | `codex login`。見 [chatgpt-dot-cli 疑難排解](https://gitlab.com/aa22396584/chatgpt-dot-cli/-/blob/main/docs/reference.zh-TW.md#疑難排解) |
| Your dot 網路或非 200 | 先看 `chatgpt-dot-cli list` |
| 找不到 chatgpt-dot-cli | 安裝，或設 `TRINITY_DOT_CLI` |
| Grok 多個登入或多個 bot | `trinity-cli grok bots`，再 `trinity-cli grok add NAME --account LABEL --bot BOT --default`。見 [grok-bot-cli 安裝](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install) |
| Grok 登入不能用 | 打開 Grok Bot app，跑 `gbot doctor` |
| 找不到 gbot | 安裝，或設 `TRINITY_GBOT` |
| Muse 瀏覽器沒起來 | `muse-web-cli start --headless` |
| Muse 網頁登入失效 | `muse-web-cli login`。見 [muse-web-cli 排解](https://gitlab.com/aa22396584/muse-web-cli/-/blob/main/docs/reference.zh-TW.md#排解) |
| Muse api 缺憑證 | `trinity-cli login muse` |
| Muse api 登入工作階段已失效 | 在 Chrome 視窗重新登入 Muse，再 `trinity-cli login muse` |
| Muse 憑證檔權限 | macOS／Linux：`chmod 600 ~/.trinity-cli/muse-credential`。Windows：`icacls` 只給目前使用者讀 |
| Muse 在副聊天室 | 在 Muse 視窗切回主聊天室 |
| Muse 瀏覽器設定檔忙碌 | 先關掉那個視窗，再執行 `muse-web-cli start --headless` |
| Muse 地區限制 | 這個工具不會繞過地區限制 |
| 找不到 muse-web-cli 或 muse | 安裝，或設 `TRINITY_MUSE_CLI`、`TRINITY_MUSE` |

## 檔案與環境變數

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

## 疑難排解

- `gbot` 有多個登入、選不出來：跑 `trinity-cli grok bots`，再用 `grok add`。旗標放在子命令後面。
- 某個登入列出 bot 時是 HTTP 404：`unreachable: sandbox gone — re-login this account in the Grok Bot app`。不是過期 token。在 Grok Bot app 重新登入那個帳號。gbot 沒有重新登入的指令。其他座位照常。
- Grok 有回覆但 trinity 早先沒看到：文字回覆是 `send-message`，而且 `message.type` 是 `text`，不是 `role: assistant`。核准卡片不算回覆。
- Muse 瀏覽器沒起來：`muse-web-cli start --headless`。登入失效：`muse-web-cli login`。
- Your dot 的 activity 慢：`digest --no-activity`。
- 各工具自己的錯誤，看[結束碼](#結束碼)表格裡的疑難排解連結。

## 平台

| 系統 | Python | 驗證方式 |
| --- | --- | --- |
| Linux | 3.11、3.12 | GitLab CI：完整離線測試；`contract:muse` 在暫時的家目錄跑 README 釘的 muse-web-cli |
| Windows | 3.12 | GitLab CI：同一套離線測試，改到程式、測試或相依時自動跑 |
| macOS | 3.11、3.12、3.13 | 維護者本機：同一套離線測試，加上照 README 從 tag 安裝的首次使用檢查 |

測試用假的座位工具，不連任何服務。三個座位工具各自的平台表在它們的文件裡。CI 預設使用 GitLab.com 的 runner。維護者可設定 CI/CD 變數 `LINUX_RUNNER_TAG` 與 `WINDOWS_RUNNER_TAG`，把 job 指到自己的 runner。

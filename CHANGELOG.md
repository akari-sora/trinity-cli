# Changelog

## 0.5.4 - 2026-11-09

- 釘選 muse-web-cli v0.1.8（Muse 把 MEMORY.md 編輯器開在聊天畫面上時，每個指令會先把它關掉，不再一律回 `ui_changed`）與 grok-bot-cli v0.11.2-iml1s.16。程式沒有改。

## 0.5.3 - 2026-11-09

- 釘選 muse-web-cli v0.1.7（Muse 拿掉「近期」分頁後，`upcoming` 改從「動態」分頁讀排定任務；`trinity-cli schedules` 和搬家時的排程讀回又能用瀏覽器模式）與 grok-bot-cli v0.11.2-iml1s.14。
- gbot 的安裝改成一行 `npm install -g <release 連結>`，macOS、Linux、Windows 都一樣。程式沒有改。

## 0.5.2 - 2026-11-08

- `migrate` 的驗收題：對方分好幾則回答時（例如 Your dot 先回「Q3：我正在讀檔案，稍後列出」，再回真正的答案），會把同一題、帶同樣標記的後續訊息讀完再判斷，等到答案出現或對方 3 分鐘沒再說話為止；不會再問一次。以前只看第一則帶標記的訊息，會把這種回答誤判成答錯。

## 0.5.1 - 2026-11-08

- 釘選 grok-bot-cli v0.11.2-iml1s.13（`gbot migrate` 的排程選項、交接時先關 Grok Bot 再開目的地、逐檔判斷記憶完整性；`gbot-install install grokbot`）。程式沒有改。
- 文件分成英文 `README.md` 與繁體中文 `README.zh-TW.md`，參考資料移到 `docs/reference*.md`。

## 0.5.0 - 2026-11-08

- 新指令 `trinity-cli migrate <seat> <plan.json>`：把 `gbot migrate` 產生的 trinity-migration-plan 送到 Muse 或 Your dot。一次一則，帶 nonce 與 ledger；結果不確定的不會盲目重送，續跑先讀回；每份計畫一把鎖；進度檔綁定每一步的文字和附檔位元組。`--check-only`（不送任何步驟）、`--redo`、`--min-interval`（預設 20 秒，跨次執行也算）；對方回「太頻繁」或送出失敗就停下。
- 計畫的步驟可以附檔（`{path, sha256}`，載入時與送出前各算一次雜湊），座位工具用 `--attach-sha256` 再核對一次實際上傳的位元組。
- 讀回檢查；驗收題帶 `Q<n>:` 標記，Muse 在 trinity 自己建立、以 id 認領的新副聊天室問，問完刪除；答錯的題目再問一次，回「太頻繁」就不再問。
- Muse 座位：`open_chat`／`close_chat`、指定副聊天室送出與讀取、`--attach`；muse-web-cli 回報已嘗試但沒有乾淨結束的送出記成 `unknown`，不記成沒送出。dot 座位：`--attach`。
- 釘選：muse-web-cli v0.1.6、chatgpt-dot-cli v0.2.6、grok-bot-cli v0.11.2-iml1s.7（有 `gbot migrate`）。
- `wait grok` 的說明與 README 改成「預設的 Grok 座位」（!3）。

## 0.4.6 - 2026-10-13

- 座位工具釘選：muse-web-cli v0.1.5（Muse 拿掉了舊的聊天室下拉選單，v0.1.4 在新介面上 status、messages、send、chats 都回 `ui_changed`；v0.1.5 認得側欄的聊天室切換）。chatgpt-dot-cli v0.2.3（登入檔跟著 `CODEX_HOME`，缺登入檔會說在哪裡找）。gbot fork 仍是 v0.11.2-iml1s.2。
- Muse 側欄收起來時，muse-web-cli v0.1.5 的 `chats` 回 `ui_changed`、hint「請在 Muse 打開側欄後重試」，但不帶 `missing`，trinity 的 Muse 座位因此 status、讀取、送出都失敗，還提示「更新 muse-web-cli 後重試」。現在當成看不出主／副聊天室：status 照常回報並註明側欄收起來，讀取和送出仍用目前開啟的對話，和切換面板不在時一樣。
- 用 `grok add` 加的座位不管取什麼名字都當成 Grok 座位，`ask`、`wait`、`digest` 不會再落到沒設定的 gbot。
- Windows：npm 的 `.cmd` shim（例如 `gbot.cmd`）改成直接用 node 跑 shim 後面的腳本，cmd.exe 不會解析訊息內容。其他批次檔的參數一律加引號；含引號、`%` 或換行的參數直接拒絕，不送出。
- 設定檔和 brief 存成帶 BOM 的 UTF-8，或 UTF-16（PowerShell 5.1 `>` 寫出的格式）也能讀；brief 不是 UTF-8 或 UTF-16 時會說要用 UTF-8 存檔。從管線送進來的標準輸入一律當 UTF-8 讀（PowerShell 7、Git Bash 送的就是 UTF-8），不用主控台字碼頁。
- 文字輸出裡的家目錄顯示成 `~`。找不到座位、還沒有 brief、`grok bots` 看不到 bot 或有 bot 還沒加成座位時，會提示下一步（`trinity-cli grok bots`、`trinity-cli grok add NAME --account LABEL --bot BOT --default`、`trinity-cli brief init`）。
- 文件：免責聲明、隱私、平台支援表、從 `grok bots` 和 `grok add` 開始的上手流程、release 與授權徽章、CONTRIBUTING、SECURITY、issue 和 merge request 範本。CI 的 Linux 和 Windows runner 改由 CI 變數選擇。

## 0.4.5 - 2026-10-02

- 安裝說明寫明 `grok-bot-cli-0.11.2.tgz` 來自 grok-bot-cli tag `v0.11.2-iml1s.2`。trinity-cli 的版本釘選是另一個。

## 0.4.4 - 2026-10-02

- Python 3.11 也能跑 README 裡選項夾在位置參數中間的指令，例如 `hand dot#last --to grok "…"` 和 `ask grok --bot NAME --account LABEL "…"`。3.12 以上本來就可以。CI 加了 Python 3.11 的測試。
- gbot 的安裝改成下載 v0.11.2-iml1s.2 附的 `grok-bot-cli-0.11.2.tgz` 再 `npm install -g`。`npm install -g git+https://gitlab.com/...` 會結束碼 0，但裝出來的 `gbot` 是斷掉的連結。GitHub 鏡像不對外提供。Node 改成 22.19.0 以上。

## 0.4.3 - 2026-10-01

- 座位工具釘選：muse-web-cli v0.1.4（修好長聊天室 `send --wait` 等不到回覆、刪改只收列出的聊天室、錯誤欄位一律清掉 token）。chatgpt-dot-cli 仍是 v0.2.2，gbot fork 仍是 v0.11.2-iml1s.2。
- `login muse` 遇到 `session_expired` 時照 muse-web-cli 的說法回報：token 被拒是「登入工作階段已失效」，真的沒登入才是「尚未登入」。下一步都是在 Chrome 登入後再跑 `trinity-cli login muse`。
- 文件與提示改成和行為一致：Muse 預設走 browser；`--muse-backend api` 是 gateway，讀 `~/.trinity-cli/muse-credential`；這個檔只由 `login muse` 寫入（mode 600、不印出），固定在家目錄，不跟 `TRINITY_HOME`。
- 更正 0.3.3 的紀錄：那版的 `login muse` 是 `muse login`，不寫憑證檔。寫憑證檔是 0.4.1 才加的。
- CI：新增 `contract:muse`，安裝 README 釘的 muse-web-cli，在暫時的家目錄跑真的二進位（不連 Muse、不需要秘密），確認版本、`credential` 子命令，以及缺憑證、憑證壞掉、權限不對時的結束碼。標籤流水線會檢查標籤是 `v` 加 `pyproject.toml` 的版本，而且 CHANGELOG 那一節已經不是 Unreleased。測試會檢查 README、CI 發佈說明、`pyproject.toml` 的版本與釘選一致。

## 0.4.2

- `login muse` 只在 `session_expired`，或尚未登入且狀態是 ok／空白時，才提示去登入。地區限制、瀏覽器打不開、設定檔忙碌保留原本的 hint。
- 印出的錯誤與 hint 會先清掉 token、cookie 這類欄位值。
- 座位工具釘選：muse-web-cli v0.1.3。chatgpt-dot-cli 仍是 v0.2.2，gbot fork 仍是 v0.11.2-iml1s.2。

## 0.4.1

- Muse 的 backend 由 trinity 明確選擇。`--muse-backend` 優先於 `muse_backend`，再來是 `MUSE_WEB_BACKEND`，都沒有就不傳 `--backend`。值可以是 `browser`、`api` 或 `auto`。
- `auto` 先試 api。某個能力回 exit 4 才改走 browser，而且會標出實際用的是哪一個。`send` 逾時不改走另一個 backend，避免送第二次。
- `status` 和 `who` 會寫出正在用的 backend。`schedules` 同時讀 `upcoming` 和 `activity`。`digest --no-activity` 會略過 Muse 的 activity。
- 地區限制、瀏覽器設定檔忙碌、頁面結構對不上，都有固定的修復提示。核准卡片不算等得到的回覆。
- `trinity-cli login muse` 改成執行 `muse-web-cli credential`：沒登入就先走現有登入，再把 gateway token 寫進 `~/.trinity-cli/muse-credential`（mode 600），不印出。`--api-key` 仍把標準輸入交給 `muse auth set --api-key-stdin`。`--web` 仍是 `muse-web-cli login`。api 後端缺憑證時，status 改提示這條。
- 已知問題：這版仍釘 muse-web-cli v0.1.2，那版沒有 `credential`，所以照 README 安裝時 `login muse` 會失敗。0.4.2 改釘 v0.1.3 修正。

## 0.4.0

- 多個 Grok 座位。`grok_seats` 用座位名、登入標籤和 bot 名稱；`grok_default` 是 `grok` 指向的那個。舊的 `gbot_account` 加 `grok_bot` 仍是一個名叫 `grok` 的座位。改寫設定前會備份。
- `status`、`digest`、`ask`、`hand`、`wait`、`schedules`、`who`、`brief push`、`log` 都接受座位名。`all` 是 dot、每個啟用的 Grok 座位、再加上 muse。每次送出有自己的 nonce，逾時不重送。
- `ask`、`wait`、`digest` 可用 `--bot` 和 `--account` 臨時連到沒寫進設定的 bot。名字跨登入重複時必須給 `--account`。
- `trinity-cli grok bots` 列出每個登入上的 bot，不印 id。404 顯示 `unreachable: sandbox gone — re-login this account in the Grok Bot app`。`grok add` 和 `grok remove` 會先備份。
- 讀取位置依座位分開，印完才前進。一個座位不可達不會讓其他座位停掉。結束碼 1 只在這次點到、且算數的座位全部失敗或逾時。
- 座位工具釘選不變：chatgpt-dot-cli v0.2.2、gbot fork v0.11.2-iml1s.2、muse-web-cli v0.1.2。

## 0.3.3

- 座位工具釘在 `chatgpt-dot-cli` v0.2.2、gbot fork v0.11.2-iml1s.2、`muse-web-cli` v0.1.2。
- 平行寫入帳本時整行加鎖。Windows 上同時 append 不會把兩筆 JSON 寫成交錯的一行。
- Muse 仍預設走 browser。backend 由 muse-web-cli 的 `--backend`、`MUSE_WEB_BACKEND` 或它自己的設定檔決定，trinity 不傳 `--backend`。使用者改成 api 且該能力不支援時，每個能力分開回報不支援，不會讓整支指令當掉。
- `trinity-cli login muse` 執行公開的 `muse login`（瀏覽器核准）。`--api-key` 把標準輸入交給 `muse auth set --api-key-stdin`。`--web` 才是 `muse-web-cli login`。trinity 不讀、不印、不複製憑證，也不寫入 `~/.trinity-cli/muse-credential`。api 後端缺憑證時，status 改提示這條。
- 用法說明改成中英完整對照：安裝、第一次設定、每個指令和旗標、`--json` 欄位、結束碼、檔案與安全界線。`--help` 每個指令和旗標都有預設值或範圍。
- Windows 與 Linux：用 `shutil.which` 找工具（含 `gbot.cmd`），參數用清單、不用 shell；子程序輸出以 UTF-8 解碼；逾時在 Windows 用 `taskkill /T`。狀態、帳本、設定在 `TRINITY_HOME` 或家目錄的 `.trinity-cli`，寫入用 `os.replace`。
- CI：Linux 走專案自己的 runner；Windows 走 GitLab 代管的 `saas-windows-medium-amd64`（只跑離線測試）。標籤流水線會附上各系統安裝方式、相關專案連結，並上傳 wheel 與 sdist。

## 0.3.2

- Muse 讀取（digest、ask 回讀、wait）和送出之前會先看 `muse-web-cli chats`。目前開著副聊天室時不送出，狀態寫「目前在副聊天室」，並提示在 Muse 視窗切回主聊天室；這種讀取不算主對話，也不推進讀取位置。`chats` 不支援或切換面板不在時，仍使用目前開啟的對話，並在 status 註明。聊天室標題不會印出來。
- `muse-web-cli` 釘在 v0.1.1。

## 0.3.1

- Grok 的文字回覆是 `send-message`（`message.type` 為 `text`），不是 `role: assistant`。0.3.0 因此把已經送到的回覆看成沒有回覆。現在這種條目算 bot 說的；核准卡片仍不算。時間欄位 `timestampMs` 也會讀。
- `~/.trinity-cli/config.json` 的 `grok_bot`（或 `TRINITY_GROK_BOT`）是 `ask`、`hand`、`wait`、`brief` 的預設 bot。`ask grok "一句話"` 整句都是訊息。
- 還沒有 `brief.md` 時，`brief diff` 結束碼 0，並提示 `brief init`。`brief init` 只在檔案不存在時寫一份短模板。

## 0.3.0

第一個公開版本。

- `hand`：把某個座位最近的回覆，加上你的指令，轉給另一個座位。先預覽，確認後才送，不會自動再轉下一手。
- `wait`：等 ledger 之後的第一則新回覆。逾時只報告，不重送。可選 macOS 通知，以及你明確寫下的 `--then hand`。
- `schedules`：列出各座位排程，並標出重複的標題或時間。
- `who`：依能力表和當下狀態建議座位。只是建議，不會送出。
- `brief`：本機一份 `brief.md`。`push` 只在 Grok 有指令 API 時寫入，而且先確認。Your dot 和 Muse 只印草稿。`diff` 會只讀 Muse 的 memory。
- `log`：依座位、時間、狀態過濾送出紀錄。
- Muse 座位走 `muse-web-cli` v0.1.0（headless 或有視窗的瀏覽器）。`status`、`read`、`send`、`wait`、`schedules`（upcoming）可用。待處理事項出現在 status。訊息沒有時間戳，digest 用內容雜湊記住看過的結尾，對不上就標可能漏看。`send` 不帶 `--wait`，之後只輪詢訊息；逾時不重送。沒有指令 API。`api` backend 仍是接縫。
- Your dot 對齊 `chatgpt-dot-cli` v0.2.1：`messages --json` 是 `{"name","lines","messages"}`，dot id 只用 `--dot-id`，`--limit` 限制在 1..32，非 200 的 stderr 會顯示出來。
- Grok 對齊 fork v0.11.2-iml1s.1：從 `gbot thread --help` 認得 `--account` 和 `thread --after`。`--account` 放在子命令後面。多個登入時用 `gbot_account`。送出收據若是 `unknown` 就照實記下，不重送。

## 0.2.0

本機草稿，沒有對外發布。`hand`、`wait`、`schedules`、`who`、`brief`、`log` 先落在這裡；0.3.0 把它們和 Muse 座位一起當成第一個公開版本。

## 0.1.0

`status`、`digest`、`ask`。Your dot 走 `chatgpt-dot-cli`，Grok Bot 走 `gbot`。

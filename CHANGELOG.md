# Changelog

## 0.3.3

- 座位工具釘在 `chatgpt-dot-cli` v0.2.2、gbot fork v0.11.2-iml1s.2、`muse-web-cli` v0.1.2。
- Muse 仍預設走 browser。backend 由 muse-web-cli 的 `--backend`、`MUSE_WEB_BACKEND` 或它自己的設定檔決定，trinity 不傳 `--backend`。使用者改成 api 且該能力不支援時，每個能力分開回報不支援，不會讓整支指令當掉。
- `trinity-cli login muse` 執行公開的 `muse login`（瀏覽器核准）。`--api-key` 把標準輸入交給 `muse auth set --api-key-stdin`。`--web` 才是 `muse-web-cli login`。trinity 不讀、不印、不複製憑證，也不寫入 `~/.trinity-cli/muse-credential`。api 後端缺憑證時，status 改提示這條。
- 用法說明改成中英完整對照：安裝、第一次設定、每個指令和旗標、`--json` 欄位、結束碼、檔案與安全界線。`--help` 每個指令和旗標都有預設值或範圍。
- Windows 與 Linux：用 `shutil.which` 找工具（含 `gbot.cmd`），參數用清單、不用 shell；子程序輸出以 UTF-8 解碼；逾時在 Windows 用 `taskkill /T`。狀態、帳本、設定在 `TRINITY_HOME` 或家目錄的 `.trinity-cli`，寫入用 `os.replace`。
- CI：Linux 仍走 grok-box；Windows 走 GitLab 代管的 `saas-windows-medium-amd64`（只跑離線測試）。標籤流水線會附上各系統安裝方式、相關專案連結，並上傳 wheel 與 sdist。

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

# Changelog

## 0.3.0

尚未發布。這是準備推上公開 GitLab 的草稿。

- `hand`：把某個座位最近的回覆，加上你的指令，轉給另一個座位。先預覽，確認後才送，不會自動再轉下一手。
- `wait`：等 ledger 之後的第一則新回覆。逾時只報告，不重送。可選 macOS 通知，以及你明確寫下的 `--then hand`。
- `schedules`：列出各座位排程，並標出重複的標題或時間。
- `who`：依能力表和當下狀態建議座位。只是建議，不會送出。
- `brief`：本機一份 `brief.md`。`push` 只在 Grok 有指令 API 時寫入，而且先確認。Your dot 和 Muse 只印草稿。
- `log`：依座位、時間、狀態過濾送出紀錄。
- Muse 座位改走 `muse-web-cli`（headless 或有視窗的瀏覽器）。`status`、`read`、`send`、`wait`、`schedules`（upcoming）可用。待處理事項出現在 status。訊息沒有時間戳，digest 用內容雜湊記住看過的結尾，對不上就標可能漏看。`send` 不帶 `--wait`，之後只輪詢訊息；逾時不重送。沒有指令 API。`brief diff` 只讀 memory。`api` backend 仍是接縫。

## 0.2.0

本機草稿，沒有對外發布。`hand`、`wait`、`schedules`、`who`、`brief`、`log` 先落在這裡；0.3.0 把它們和 Muse 座位一起當成第一個公開版本。

## 0.1.0

`status`、`digest`、`ask`。Your dot 走 `chatgpt-dot-cli`，Grok Bot 走 `gbot`。

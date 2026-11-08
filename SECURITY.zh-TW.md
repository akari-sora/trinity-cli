# 安全政策

[English](SECURITY.md) | 繁體中文

## 支援的版本

只有最新版會收到安全修正。

## 回報安全問題

請不要用公開 issue 或 merge request 回報安全問題。

1. 在 GitLab 開[機密 issue](https://gitlab.com/aa22396584/trinity-cli/-/issues/new?issue[confidential]=true)。
2. 附上版本（`trinity-cli --version`）、作業系統、預期與實際結果、重現步驟。
3. 貼記錄前，把 token、cookie、憑證檔內容、帳號／聊天／bot id、訊息內容換成假值。

通常 7 天內會回覆。修正發布後會公開這份回報並致謝，除非你要求不具名。

範圍內：trinity-cli 本身：它怎麼啟動座位工具、ledger 與 state 檔、brief，以及任何可能洩漏 token、id、訊息或本機路徑的地方。單一座位工具的 bug 請回報到那個工具的專案。

範圍外：ChatGPT（OpenAI）、Grok Bot（Cursor／xAI）或 Meta Muse（Meta）服務本身的問題。請回報給該服務。

# trinity-cli

[English](README.md) | 繁體中文

一個指令，擋在三個一直開著的個人 agent 前面：ChatGPT 的 Your dot、Grok Bot，以及 Meta 的 Muse。

> 正本和 issue 在 <https://gitlab.com/aa22396584/trinity-cli>。

[![pipeline](https://gitlab.com/aa22396584/trinity-cli/badges/main/pipeline.svg)](https://gitlab.com/aa22396584/trinity-cli/-/pipelines)
[![release](https://gitlab.com/aa22396584/trinity-cli/-/badges/release.svg)](https://gitlab.com/aa22396584/trinity-cli/-/releases)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 功能

- 在同一個地方看狀態、整理新訊息、提問、轉交、等回覆。需要 Python 3.11+。
- 它不自己連這些服務，而是轉呼叫三個工具：
  - Your dot：`chatgpt-dot-cli --json`
  - Grok Bot：`gbot --json`（grok-bot-cli 這個 fork）
  - Muse：`muse-web-cli --json --autostart`
- 座位沒有的能力會標成不支援，不會連帶讓別的座位失敗。
- 每次送出前先寫進本機 ledger，加上 nonce，再讀回確認。逾時不重送。

支援的系統見[平台](docs/reference.zh-TW.md#平台)。

## 安裝

v0.5.1 釘這些版本。三個座位工具和 trinity 都裝好後，用 `--version` 對一下：應印出 `muse-web-cli 0.1.6`、`trinity-cli 0.5.1`、`gbot 0.11.2`。

macOS 與 Linux 需要 Python 3.11+、git、以及已在 PATH 上的 `uv`。Grok 還要 Node.js 22.19.0+ 和 npm。uv 的執行檔在 `~/.local/bin`；`--version` 找不到時把那個目錄加進 PATH。第一次 `uv tool install` 可能會下載 Python。

`npm install -g git+https://gitlab.com/aa22396584/grok-bot-cli.git#...` 會結束碼 0，但 `gbot` 是斷掉的連結。下面的 `grok-bot-cli-0.11.2.tgz` 是 grok-bot-cli tag `v0.11.2-iml1s.13` 附的套件檔，trinity-cli 的版本釘選是另一個。改裝那個 tag 附的套件檔：

```bash
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.6"
curl -fsSL -o grok-bot-cli-0.11.2.tgz "https://gitlab.com/-/project/86401528/uploads/cf28e8d97e324accf5d333263765eba2/grok-bot-cli-0.11.2.tgz"
npm install -g ./grok-bot-cli-0.11.2.tgz
rm -f grok-bot-cli-0.11.2.tgz
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.6"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.5.1"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

Windows（PowerShell，同樣的釘選）：

```powershell
irm https://astral.sh/uv/install.ps1 | iex
uv tool install "git+https://gitlab.com/aa22396584/chatgpt-dot-cli.git@v0.2.6"
irm "https://gitlab.com/-/project/86401528/uploads/cf28e8d97e324accf5d333263765eba2/grok-bot-cli-0.11.2.tgz" -OutFile grok-bot-cli-0.11.2.tgz
npm install -g .\grok-bot-cli-0.11.2.tgz
Remove-Item grok-bot-cli-0.11.2.tgz
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
uv tool install "git+https://gitlab.com/aa22396584/muse-web-cli.git@v0.1.6"
uv tool install "git+https://gitlab.com/aa22396584/trinity-cli.git@v0.5.1"
chatgpt-dot-cli --version
gbot --version
muse-web-cli --version
trinity-cli --version
```

pipx、Windows 注意事項、升級與移除見[安裝細節](docs/reference.zh-TW.md#安裝細節)。

## 設定

1. Your dot：`codex login`（或 `trinity-cli login dot`）。
2. Grok Bot：打開 Grok Bot app 登入，並在 app 裡建立至少一個 bot。接著跑 `trinity-cli grok bots`，再挑一個存成座位：`trinity-cli grok add researcher --account 登入標籤 --bot "bot 名稱" --default`。見 [grok-bot-cli 安裝](https://gitlab.com/aa22396584/grok-bot-cli/-/blob/main/FORK.md#install)。
3. Muse（預設的 browser 後端）：`muse-web-cli login`，完成後 `muse-web-cli start --headless`。api 後端：`trinity-cli login muse`。
4. 確認：`trinity-cli status`。

多個 Grok 座位、設定檔、Muse 後端的選法見[第一次設定](docs/reference.zh-TW.md#第一次設定)。

## 快速開始

```bash
trinity-cli status
trinity-cli digest --peek
trinity-cli ask all "今天進度？"
trinity-cli hand dot#last --to grok:example-bot "請看這則"
trinity-cli wait grok:example-bot
```

輸出長什麼樣子見[輸出形狀](docs/reference.zh-TW.md#輸出形狀)。

## 指令

| 指令 | 用途 |
| --- | --- |
| `status` | 每個座位一行，等你處理的事項在最上面（沒有子命令時跑這個） |
| `digest` | 把各座位的新訊息排成一條時間線；`--peek` 和 `--since` 不動讀取位置 |
| `ask` | 把同一段文字送給 `all`、`dot`、`grok`、座位名或 `muse`，等各自的第一則回覆 |
| `hand` | 先預覽、確認後，把一個座位的回覆轉給另一個；不會再轉下一手 |
| `wait` | 從 ledger 最後一筆之後等新回覆；不重送 |
| `schedules` | 列出各座位的排程，標出重複的標題或時間 |
| `who` | 建議這件事交給哪個座位；不送出 |
| `brief` | `show`、`init`、`diff`、`push` 共用的 `~/.trinity-cli/brief.md` |
| `log` | 讀送出紀錄（ledger） |
| `migrate` | 把搬家計畫（`gbot migrate import` 產生）送進 Muse 或 Your dot，讀回後再問驗收題 |
| `login` | 透過座位自己的 CLI 登入；不印憑證 |
| `grok` | `bots` 列出各登入上的 Grok bot；`add`、`remove` 編輯座位 |

`--json` 放在指令前後都可以。`--muse-backend browser|api|auto` 指定這次指令用的 Muse 後端。每個旗標與 JSON 鍵見[指令參考](docs/reference.zh-TW.md#指令參考)。

## 安全與隱私

- trinity 不會叫 agent 刪檔、傳訊息給別人、購買，或改設定與帳號。`brief push` 只在你確認後寫入 Grok 的指令。
- `hand` 和 `brief push` 先問；不是終端機時沒有 `--yes` 就不送。`hand` 不會把對方的回覆再轉出去。逾時不重送。真正送出的那幾次會在畫面上標成送出，並寫進 ledger。
- 它不讀 `~/.codex/auth.json`、Grok Bot app 的登入，或 Muse 的 cookie。`login` 只轉給那些工具既有的公開指令，不印憑證。唯一會存下 token 的是 `login muse`：它叫 `muse-web-cli credential` 把 Muse gateway token 只寫進 `~/.trinity-cli/muse-credential`（mode 600），給 `--muse-backend api` 用。trinity 自己不讀、不印這個檔。這個檔是 token，不要分享或提交。
- trinity 沒有遙測，自己不連網路。網路請求都是三個座位工具發出的，各自送到自己的服務。
- 資料只存在本機的 `TRINITY_HOME`。`ledger.jsonl` 記時間、座位、bot 名稱、nonce 和結果，不存訊息內文。`state.json` 只有讀取位置。
- 文字輸出把家目錄寫成 `~`，`--json` 保留完整路徑。`grok bots` 和 `log` 不印 id；印出的錯誤會先清掉 token、cookie 這類欄位值。貼輸出到 issue 前，還是先看一下有沒有訊息內容或名字。

## 給 agent 用

- 加 `--json` 拿機器可讀的輸出。結束碼 0：這次點到的座位裡至少一個成功（不支援也算，失敗仍會印出）；1：這次點到、且算數的座位全部失敗或逾時；2：參數不對，或 `hand`／`brief push` 沒有確認所以沒送。見[結束碼](docs/reference.zh-TW.md#結束碼)。
- 逾時只報告，不重送。`trinity-cli log` 和 `trinity-cli digest --peek` 看得到實際收到什麼。
- skill 在 `skills/trinity-cli/SKILL.md`。目錄已經存在時再連過去，例如 `ln -sfn "$PWD/skills/trinity-cli" ~/.claude/skills/trinity-cli`。同樣的位置：`~/.codex/skills`、`~/.agents/skills`、`~/.config/opencode/skills`、`~/.config/opencode/skill`、`~/.cursor/skills`、`~/.grok/skills`。

## 文件

- [docs/reference.zh-TW.md](docs/reference.zh-TW.md)：安裝細節、第一次設定、輸出形狀、每個指令、概念（後端、讀取位置、ledger、副聊天室）、結束碼與座位修法、檔案與環境變數、疑難排解、平台。
- [CONTRIBUTING.md](CONTRIBUTING.md)、[SECURITY.zh-TW.md](SECURITY.zh-TW.md)（安全問題照這份回報，不要開公開 issue）、[CHANGELOG.md](CHANGELOG.md)。

## 相關專案

- trinity-cli（這個 repo）— 一個指令包三個一直開著的 agent（Your dot、Grok Bot、Muse）：<https://gitlab.com/aa22396584/trinity-cli>
- chatgpt-dot-cli — ChatGPT Your dot：<https://gitlab.com/aa22396584/chatgpt-dot-cli>
- grok-bot-cli（fork，`gbot`）— Grok Bot：<https://gitlab.com/aa22396584/grok-bot-cli>
- muse-web-cli — 用網頁操作 Meta Muse：<https://gitlab.com/aa22396584/muse-web-cli>

## 授權與聲明

[MIT](LICENSE)

非官方：這是個人專案，跟 OpenAI、xAI、Cursor（Anysphere）、Meta 都沒有關係，也沒有得到它們的背書或支援。它透過三個座位工具使用你自己的帳號，那些工具走的是沒有公開文件的介面，隨時可能改變或失效。自動化使用可能違反各服務的使用條款，帳號風險自負。

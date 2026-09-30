"""Which seat fits a task. Advisory only: this never sends."""

from __future__ import annotations

from trinity_cli.app import call, each
from trinity_cli.model import FAILED, OK, UNSUPPORTED, SeatStatus
from trinity_cli.shown import Shown

_KEYWORDS = {
    "dot": (
        ("本機", 3),
        ("mac", 3),
        ("檔案", 3),
        ("file", 2),
        ("電腦", 2),
        ("desktop", 2),
        ("瀏覽器", 2),
        ("browser", 2),
        ("下載", 2),
        ("資料夾", 2),
        ("研究", 1),
        ("程式", 1),
    ),
    "grok": (
        ("翻譯", 3),
        ("translate", 3),
        ("摘要", 3),
        ("summar", 2),
        ("grok", 3),
        ("問答", 2),
    ),
}
_MACHINE = ("本機", "mac", "檔案", "file", "電腦", "desktop", "下載", "資料夾")


def _notes_for(key: str, task: str, result) -> tuple[int, list[str]]:
    if key == "muse" or result.state == UNSUPPORTED:
        return -100, ["不支援"]
    folded = task.casefold()
    score = 0
    notes: list[str] = []
    for word, weight in _KEYWORDS.get(key, ()):
        if word.casefold() in folded:
            score += weight
            notes.append(f"任務提到{word}")
    if result.state == FAILED:
        return score - 2, notes + ["狀態讀不到"]
    status = result.value if isinstance(result.value, SeatStatus) else None
    details = status.details if status else {}
    waiting = status.waiting if status else []
    summary = status.summary if status else ""
    if details.get("paused") or "已暫停" in summary:
        score -= 5
        notes.append("已暫停")
    used = details.get("quota_used_percent")
    if (isinstance(used, (int, float)) and not isinstance(used, bool) and used >= 100) or any(
        "額度" in item and "用完" in item for item in waiting
    ):
        score -= 4
        notes.append("額度用完")
    wants_machine = any(word.casefold() in folded for word in _MACHINE)
    attached = details.get("this_mac_attached")
    if wants_machine and attached is True:
        score += 2
        notes.append("這台 Mac 已連接")
    elif wants_machine and attached is False:
        score -= 3
        notes.append("這台 Mac 沒連接")
    if result.state != OK and result.state != FAILED:
        notes.append(result.error or "狀態不明")
    return score, notes


def run_who(seats, task: str) -> Shown:
    task = task.strip()
    if not task:
        return Shown(2, "請寫要判斷的事，例如 `trinity-cli who \"翻譯這段\"`。", {"advisory": True, "error": "missing task"})
    reports = list(zip(seats, each(seats, lambda seat: call(seat, "status"))))
    ranking = []
    for seat, result in reports:
        score, notes = _notes_for(seat.key, task, result)
        ranking.append({"seat": seat.key, "label": seat.label, "score": score, "notes": notes})
    ranking.sort(key=lambda row: row["score"], reverse=True)
    viable = [row for row in ranking if row["score"] > -100]
    suggestion = None
    if not viable:
        headline = "沒有明顯適合的座位"
    elif len(viable) >= 2 and viable[0]["score"] == viable[1]["score"]:
        headline = f"沒有明顯偏好：{viable[0]['label']} 和 {viable[1]['label']} 都可以"
    else:
        suggestion = viable[0]["seat"]
        headline = f"建議：{viable[0]['label']}"
    lines = [headline]
    for row in ranking:
        detail = "；".join(row["notes"])
        lines.append(f"{row['label']}：{detail}" if detail else f"{row['label']}：沒有特別加分")
    lines.append("這只是建議，不會送出訊息。")
    return Shown(0, "\n".join(lines), {"advisory": True, "suggestion": suggestion, "headline": headline, "ranking": ranking})

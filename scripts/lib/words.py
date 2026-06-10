r"""
中文字数统计。

约定：取正文中非空白、非 markdown 控制字符的字符数。
- 统计前剥离 `### 写作备注` 之后的所有内容（章节文件专用）
- 统计前剥离 markdown 行内符号（#、*、_、反引号 等）
- 空白（空格、Tab、换行）不计入
"""

from __future__ import annotations
import re
from pathlib import Path

# 写作备注 标题行（章节文件专用）
WRITING_NOTES_RE = re.compile(r"^#{1,6}\s*写作备注\s*$", re.MULTILINE)

# 简单的 markdown 符号剥离
_MD_CHARS = re.compile(r"[#*_`>~\-]+")



def strip_writing_notes(text: str) -> str:
    """剥离 `### 写作备注` 及其后所有内容。"""
    m = WRITING_NOTES_RE.search(text)
    if m:
        return text[: m.start()]
    return text


def count_words(text: str) -> int:
    """统计字数：剥离写作备注、剥离 markdown 符号、去空白后取字符数。"""
    text = strip_writing_notes(text)
    text = _MD_CHARS.sub("", text)
    text = re.sub(r"\s+", "", text)
    return len(text)


def count_file(path: str | Path) -> dict:
    """统计文件字数并返回 {path, words, has_writing_notes}。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8")
    has_notes = bool(WRITING_NOTES_RE.search(text))
    return {
        "path": str(p),
        "words": count_words(text),
        "has_writing_notes": has_notes,
    }


def judge(actual: int, target: int) -> dict:
    """字数判定：达标 / 轻微不足 / 严重不足。

    标准（来自 SKILL.md 阶段速查）：
    - 实际 ≥ 目标 × 0.8 → 达标
    - 目标 × 0.5 ≤ 实际 < 目标 × 0.8 → 轻微不足
    - 实际 < 目标 × 0.5 → 严重不足
    """
    if target <= 0:
        return {"verdict": "unknown", "ratio": 0.0, "delta": 0}
    ratio = actual / target
    delta = actual - target
    if ratio >= 0.8:
        verdict = "达标"
    elif ratio >= 0.5:
        verdict = "轻微不足"
    else:
        verdict = "严重不足"
    return {
        "verdict": verdict,
        "ratio": round(ratio, 3),
        "delta": delta,
        "actual": actual,
        "target": target,
    }

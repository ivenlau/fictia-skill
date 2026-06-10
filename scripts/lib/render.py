"""
状态面板渲染：把 project.yaml 渲染为 ASCII 面板。
"""

from __future__ import annotations
from . import project as P


SYMBOLS: dict[str, str] = {
    P.STATUS_CONFIRMED: "[✓]",
    P.STATUS_IN_PROGRESS: "[▸]",
    P.STATUS_PENDING_CONFIRM: "[◇]",
    P.STATUS_NEEDS_UPDATE: "[!]",
    P.STATUS_NOT_STARTED: "[ ]",
    P.STATUS_FAILED: "[✗]",
}


def _symbol(status: str) -> str:
    return SYMBOLS.get(status, "[?]")


def render_status_panel(data: dict) -> str:
    """渲染 SKILL.md 中定义的状态面板。"""
    name = data.get("name", "?")
    author = data.get("author", "?")
    genre = data.get("genre", "?")
    target_words = data.get("target_words", "?")
    target_volumes = data.get("target_volumes", "?")
    chapter_target_words = data.get("chapter_target_words", "?")
    chapters = data.get("chapters") or {}
    written = int(chapters.get("written") or 0)
    total = int(chapters.get("total") or 0)

    # 阶段两列布局
    rows: list[str] = []
    stages = list(P.STAGES)
    for i in range(0, 11, 2):
        left = stages[i]
        right = stages[i + 1] if i + 1 < len(stages) else None
        left_s = _symbol(P.get_stage_status(data, left[1]))
        if right:
            right_s = _symbol(P.get_stage_status(data, right[1]))
            rows.append(f"│  {left[0]} {left[2]:<6}  {left_s}    {right[0]} {right[2]:<6}  {right_s}  │")
        else:
            rows.append(f"│  {left[0]} {left[2]:<6}  {left_s}                            │")

    # 下一阶段
    nxt = P.next_runnable_stage(data)
    if nxt is None:
        if P.all_confirmed(data):
            nxt_line = "│  ▶ 下一步: 全部阶段已完成                         │"
        else:
            nxt_line = "│  ▶ 下一步: 等待上游阶段确认                       │"
    else:
        num, key, name_cn = nxt
        nxt_line = f"│  ▶ 下一步: 阶段 {num} · {name_cn:<22}        │"

    panel = f"""╭────────────────────────────────────────────────╮
│              F I C T I A                       │
│          AI 小说创作流水线                      │
├────────────────────────────────────────────────┤
│  {name} · {author} · {genre}
│  {target_words}字 · {target_volumes}卷
│  每章{chapter_target_words}字
│  已写 {written}/{total}章
├────────────────────────────────────────────────┤
{chr(10).join(rows)}
│  ✓已确认 ▸进行中 ◇待确认 !需更新 空格未开始    │
├────────────────────────────────────────────────┤
{nxt_line}
╰────────────────────────────────────────────────╯"""
    return panel

"""Dynamic Writing Space — 大纲解析器。

从 outline/chapters/chNN.md 中提取 OutlineHints：
  - 角色名 + 状态
  - 地点
  - 伏笔操作
  - 场景事件
  - 时间线索
  - 活跃故事线

大纲是写作空间组装的"锚点"——所有必读实体的检索都由 hints 驱动。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #


@dataclass
class ForeshadowOp:
    """一次伏笔操作。"""

    fo_id: str  # 伏笔 ID（如 "F001"、"伏笔ID-F003"）
    op: str  # plant / seed / escalate / resolve
    hint: str  # 操作描述


@dataclass
class OutlineHints:
    """从大纲中提取的线索。"""

    chapter: int
    target_words: int = 3000

    # 角色线索
    character_names: list[str] = field(default_factory=list)
    character_states: dict[str, str] = field(default_factory=dict)

    # 地点线索
    locations: list[str] = field(default_factory=list)

    # 伏笔线索
    foreshadow_ops: list[ForeshadowOp] = field(default_factory=list)

    # 事件线索
    scene_events: list[str] = field(default_factory=list)

    # 时间线线索
    story_time: str | None = None

    # 故事线线索
    active_storylines: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 解析器
# --------------------------------------------------------------------------- #


def parse_outline(chapter: int, outline_path: Path) -> OutlineHints:
    """解析章节大纲，提取所有实体线索。"""
    if not outline_path.is_file():
        return OutlineHints(chapter=chapter)

    text = outline_path.read_text(encoding="utf-8")
    hints = OutlineHints(chapter=chapter)

    # 1. 目标字数
    hints.target_words = _extract_target_words(text)

    # 2. 角色调度表
    _extract_character_dispatch(text, hints)

    # 3. 场景序列中的地点和事件
    _extract_scene_locations_and_events(text, hints)

    # 4. 伏笔/支线/彩蛋指令
    _extract_foreshadow_ops(text, hints)

    # 5. 时间线
    _extract_story_time(text, hints)

    # 6. 故事线
    _extract_active_storylines(text, hints)

    # 7. 兜底：正则匹配大纲中提到的角色名
    _supplement_character_names(text, hints)

    return hints


# --------------------------------------------------------------------------- #
# 提取函数
# --------------------------------------------------------------------------- #


def _extract_target_words(text: str) -> int:
    """从大纲中提取目标字数。"""
    # 匹配 "目标字数：3000" / "字数: 3000" / "3000字"
    patterns = [
        r"目标字数[：:]\s*(\d+)",
        r"字数[：:]\s*(\d+)",
        r"篇幅[：:]\s*(\d+)",
        r"(\d+)\s*字",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return 3000  # 默认


def _extract_character_dispatch(text: str, hints: OutlineHints) -> None:
    """从 '## 角色调度' 表格提取角色名和状态。"""
    # 找角色调度 section
    section = re.search(
        r"^##\s*角色调度[^\n]*\n([\s\S]*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE,
    )
    if not section:
        return

    body = section.group(1)

    # 解析表格
    table = _parse_table(body)
    for row in table:
        # 常见列名：角色、姓名、起始状态、结束状态
        name = row.get("角色", row.get("姓名", row.get("character", "")))
        if not name:
            continue
        name = name.strip()
        if name and name not in ("角色", "姓名", "人物"):
            hints.character_names.append(name)
            start_state = row.get(
                "起始状态",
                row.get("baseline state", row.get("状态", "")),
            )
            if start_state:
                hints.character_states[name] = start_state.strip()


def _extract_scene_locations_and_events(text: str, hints: OutlineHints) -> None:
    """从 '## 场景序列' 提取地点和事件。"""
    section = re.search(
        r"^##\s*场景序列[^\n]*\n([\s\S]*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE,
    )
    if not section:
        return

    body = section.group(1)

    # 按场景切分
    scenes = re.split(
        r"(?=^###\s|^\*\*场景\s*\d|^-{3,}$)",
        body,
        flags=re.MULTILINE,
    )

    for scene in scenes:
        scene = scene.strip()
        if not scene or len(scene) < 20:
            continue

        # 地点
        loc_match = re.search(
            r"(?:地点|场所|位置|场景)[：:]\s*(.+)",
            scene,
        )
        if loc_match:
            loc = loc_match.group(1).strip()
            if loc and loc not in hints.locations:
                hints.locations.append(loc)

        # 也从 "地点/时间" 行提取
        loc_time_match = re.search(
            r"(?:地点/时间|场景/时间)[：:]\s*(.+?)[\s/|]",
            scene,
        )
        if loc_time_match:
            loc = loc_time_match.group(1).strip()
            if loc and loc not in hints.locations:
                hints.locations.append(loc)

        # 事件（场景目标）
        goal_match = re.search(
            r"(?:场景目标|目标|核心事件)[：:]\s*(.+)",
            scene,
        )
        if goal_match:
            event = goal_match.group(1).strip()
            if event:
                hints.scene_events.append(event)

        # 角色名（从场景中提到的人名）
        char_match = re.search(
            r"(?:角色|参与|POV|视角)[：:]\s*(.+)",
            scene,
        )
        if char_match:
            names = re.split(r"[、,，/]", char_match.group(1).strip())
            for n in names:
                n = n.strip()
                if n and n not in hints.character_names and n not in ("无", "-", "—"):
                    hints.character_names.append(n)


def _extract_foreshadow_ops(text: str, hints: OutlineHints) -> None:
    """从 '## 伏笔/支线/彩蛋指令' + weave_notes 提取伏笔操作。"""
    # 找 weave_notes 段
    weave_section = re.search(
        r"(?:^##\s*(?:伏笔|支线|彩蛋).*\n|weave_notes[：:]?\s*\n)([\s\S]*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE,
    )
    if not weave_section:
        return

    body = weave_section.group(1)

    # 匹配格式：
    # - 埋设: F003 (描述)
    # - 推进: F001 描述
    # - 回收: F002 描述
    # - planted: F001 描述
    op_pattern = re.compile(
        r"[-*]\s*(埋设|推进|回收|铺垫|强化|seed|plant|escalate|resolve)"
        r"[：:]\s*(.+)",
        re.IGNORECASE,
    )
    for m in op_pattern.finditer(body):
        op_raw = m.group(1).strip()
        rest = m.group(2).strip()

        # 映射操作类型
        op_map = {
            "埋设": "plant",
            "铺垫": "plant",
            "推进": "seed",
            "强化": "escalate",
            "回收": "resolve",
            "seed": "seed",
            "plant": "plant",
            "escalate": "escalate",
            "resolve": "resolve",
        }
        op = op_map.get(op_raw.lower(), op_raw.lower())

        # 提取 ID
        fo_id = ""
        hint = rest
        id_match = re.match(r"(?:伏笔ID[-_])?\s*([A-Z]+\d+|F\d+)\s*[：:（(\s]*(.*)", rest)
        if id_match:
            fo_id = id_match.group(1)
            hint = id_match.group(2).strip()
        else:
            # 尝试从 rest 开头提取 ID
            id_match2 = re.match(r"([A-Z]+[-_]?\d+)[：:（(\s]*(.*)", rest)
            if id_match2:
                fo_id = id_match2.group(1)
                hint = id_match2.group(2).strip()

        if not fo_id:
            fo_id = rest[:10]

        hints.foreshadow_ops.append(
            ForeshadowOp(fo_id=fo_id, op=op, hint=hint)
        )

    # 也匹配表格形式
    table_blocks = re.findall(r"((?:^\|.*\|\s*\n)+)", body, re.MULTILINE)
    for block in table_blocks:
        rows = _parse_table(block)
        for row in rows:
            fo_id = row.get("编号", row.get("ID", row.get("伏笔", "")))
            fo_op = row.get("操作", row.get("类型", row.get("op", "")))
            fo_hint = row.get("描述", row.get("内容", row.get("hint", "")))
            if fo_id:
                op_map = {
                    "埋设": "plant",
                    "推进": "seed",
                    "强化": "escalate",
                    "回收": "resolve",
                }
                hints.foreshadow_ops.append(
                    ForeshadowOp(
                        fo_id=fo_id,
                        op=op_map.get(fo_op, fo_op),
                        hint=fo_hint,
                    )
                )


def _extract_story_time(text: str, hints: OutlineHints) -> None:
    """从大纲提取故事内时间。"""
    patterns = [
        r"(?:时间|故事时间|时间线)[：:]\s*(.+)",
        r"(?:时间/地点|地点/时间)[：:]\s*[^/]*?[/／]\s*(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            time_str = m.group(1).strip()
            if time_str and time_str not in ("无", "-", "—"):
                hints.story_time = time_str
                return


def _extract_active_storylines(text: str, hints: OutlineHints) -> None:
    """从大纲提取活跃故事线。"""
    section = re.search(
        r"^##\s*(?:支线|故事线)[^\n]*\n([\s\S]*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE,
    )
    if not section:
        return

    body = section.group(1)
    # 提取列表项
    for line in body.splitlines():
        line = line.strip()
        if line.startswith(("-", "*", "·")):
            item = re.sub(r"^[-*·]\s*", "", line)
            if item:
                hints.active_storylines.append(item)


def _supplement_character_names(text: str, hints: OutlineHints) -> None:
    """兜底：从大纲全文正则匹配角色名。策略：

    匹配引号内的中文名（2-4字）或已知的「角色名」模式。
    """
    # 匹配「XXX」或【XXX】中的内容（常用于大纲中标注角色名）
    bracket_names = re.findall(r"[「【](.+?)[」】]", text)
    for name in bracket_names:
        name = name.strip()
        if (
            2 <= len(name) <= 4
            and name not in hints.character_names
            and not re.match(r"^\d+$", name)
        ):
            hints.character_names.append(name)

    # 匹配 "角色调度" section 中的角色名（已在上面处理过，这里是补充）
    # 匹配 "XXX说" / "XXX道" 等对话模式
    dialog_names = re.findall(r"([一-鿿]{2,4})(?:说|道|想|看|听|走|来|去)", text)
    for name in dialog_names:
        if name not in hints.character_names and len(name) >= 2:
            # 过滤常见动词
            if name not in ("于是", "因此", "然而", "不过", "虽然", "忽然", "突然", "竟然"):
                hints.character_names.append(name)


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #


def _parse_table(text: str) -> list[dict[str, str]]:
    """解析 markdown 表格。"""
    lines = [l.strip() for l in text.splitlines() if l.strip().startswith("|")]
    if len(lines) < 3:
        return []
    headers = [h.strip() for h in lines[0].split("|") if h.strip()]
    rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= len(headers):
            rows.append(dict(zip(headers, cells[: len(headers)])))
    return rows


# --------------------------------------------------------------------------- #
# 便捷函数
# --------------------------------------------------------------------------- #


def parse_outline_for_chapter(project_root: Path, chapter: int) -> OutlineHints:
    """便捷函数：从项目根目录和章节号解析大纲。"""
    outline_path = project_root / "outline" / "chapters" / f"ch{chapter:02d}.md"
    return parse_outline(chapter, outline_path)


def format_outline_hints(hints: OutlineHints) -> str:
    """将 OutlineHints 格式化为可读的 markdown（调试用）。"""
    lines = [
        f"# OutlineHints · ch{hints.chapter:02d}",
        "",
        f"**目标字数**: {hints.target_words}",
        "",
        f"**角色** ({len(hints.character_names)}): {', '.join(hints.character_names) or '无'}",
    ]
    if hints.character_states:
        lines.append("")
        lines.append("**角色状态**:")
        for name, state in hints.character_states.items():
            lines.append(f"  - {name}: {state}")

    lines.extend([
        "",
        f"**地点** ({len(hints.locations)}): {', '.join(hints.locations) or '无'}",
        "",
        f"**事件** ({len(hints.scene_events)}):",
    ])
    for evt in hints.scene_events:
        lines.append(f"  - {evt}")

    lines.extend([
        "",
        f"**伏笔操作** ({len(hints.foreshadow_ops)}):",
    ])
    for op in hints.foreshadow_ops:
        lines.append(f"  - [{op.op}] {op.fo_id}: {op.hint}")

    if hints.story_time:
        lines.extend(["", f"**故事时间**: {hints.story_time}"])

    if hints.active_storylines:
        lines.extend(["", f"**活跃故事线** ({len(hints.active_storylines)}):"])
        for sl in hints.active_storylines:
            lines.append(f"  - {sl}")

    return "\n".join(lines)

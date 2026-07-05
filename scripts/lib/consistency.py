"""
一致性校验上下文自动汇总。

扫所有章节 front-matter（foreshadowings_planted / foreshadowings_resolved /
sublines_advanced / debut_characters），与 narrative-weave.md 中的计划对照，
输出追踪表草稿到 .fictia-cache/consistency-context.md。

stage 11 agent 直接读 + 标问题，无需手动汇总。
"""

from __future__ import annotations
import re
from pathlib import Path
from . import context as C


# ---------- 章节扫描 ----------


def _scan_chapters(root: Path) -> list[dict]:
    """扫所有 chapters/act-*/ch*.md，返回 front-matter + 写作备注摘要列表。

    每项 = {
        "path": "chapters/act-N/chNN.md",
        "chapter": int,
        "title": str,
        "actual_words": int,
        "debut_characters": list[str],
        "foreshadowings_planted": list[str],
        "foreshadowings_resolved": list[str],
        "sublines_advanced": list[str],
        "writing_notes": str,  # 截取的写作备注原文
    }
    """
    chapters_dir = root / "chapters"
    if not chapters_dir.is_dir():
        return []
    result: list[dict] = []
    for p in sorted(chapters_dir.rglob("ch*.md")):
        m = re.search(r"ch(\d+)\.md$", p.name)
        if not m:
            continue
        ch_num = int(m.group(1))
        text = p.read_text(encoding="utf-8")
        fm, body = C.parse_frontmatter(text)
        # 写作备注
        notes_m = re.search(r"^#{1,6}\s*写作备注\s*$\n(.*)$", body, re.MULTILINE | re.DOTALL)
        notes = notes_m.group(1).strip() if notes_m else ""
        result.append({
            "path": str(p.relative_to(root)),
            "chapter": ch_num,
            "title": str(fm.get("title", "")),
            "actual_words": _safe_int(fm.get("actual_words")),
            "debut_characters": _as_list(fm.get("debut_characters")),
            "foreshadowings_planted": _as_list(fm.get("foreshadowings_planted")),
            "foreshadowings_resolved": _as_list(fm.get("foreshadowings_resolved")),
            "sublines_advanced": _as_list(fm.get("sublines_advanced")),
            "writing_notes": notes,
        })
    return result


def _safe_int(v) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0


def _as_list(v) -> list[str]:
    """把 front-matter 字段规范化为字符串列表。"""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        # 兼容 "F03, F07" / "F03; F07" / "[F03, F07]"
        s = v.strip().lstrip("[").rstrip("]")
        if not s:
            return []
        parts = re.split(r"[,;，；]", s)
        return [p.strip() for p in parts if p.strip()]
    return []


# ---------- narrative-weave 计划解析 ----------


def _parse_weave_plan(root: Path) -> tuple[dict, dict]:
    """从 narrative-weave.md 解析伏笔/支线计划。

    返回 (foreshadowings, sublines)：
    - foreshadowings: {F01: {"name": str, "plant": "chN", "reinforce": "chN", "resolve": "chN"}}
    - sublines: {S01: {"name": str, "start": "chN", "end": "chN", "main_intersection": str}}
    """
    f = root / "narrative-weave.md"
    if not f.is_file():
        return ({}, {})
    text = f.read_text(encoding="utf-8")

    fores: dict[str, dict] = {}
    subs: dict[str, dict] = {}

    # 找含 F\d{2} 或 S\d{2} 的表格
    for tbl_m in re.finditer(r"((?:^\|.*\|\s*\n)+)", text, re.MULTILINE):
        tbl = tbl_m.group(1)
        lines = [l for l in tbl.splitlines() if l.strip().startswith("|")]
        if len(lines) < 2:
            continue
        header = lines[0]
        # 伏笔表：含"伏笔编号"或第一列匹配 F\d{2}
        if "伏笔" in header or any(re.match(r"\|?\s*F\d{2}", l) for l in lines[2:]):
            for row in lines[2:]:
                cells = [c.strip() for c in row.split("|")[1:-1]]
                if not cells:
                    continue
                # 第一列 = 编号
                id_m = re.match(r"(F\d{2,3})", cells[0])
                if not id_m:
                    continue
                fid = id_m.group(1)
                fores[fid] = {
                    "name": cells[1] if len(cells) > 1 else "",
                    "plant": _extract_ch(cells[2]) if len(cells) > 2 else "",
                    "reinforce": _extract_ch(cells[3]) if len(cells) > 3 else "",
                    "resolve": _extract_ch(cells[4]) if len(cells) > 4 else "",
                }
        # 支线表：含"支线"或第一列匹配 S\d{2}
        elif "支线" in header or any(re.match(r"\|?\s*S\d{2}", l) for l in lines[2:]):
            for row in lines[2:]:
                cells = [c.strip() for c in row.split("|")[1:-1]]
                if not cells:
                    continue
                id_m = re.match(r"(S\d{2,3})", cells[0])
                if not id_m:
                    continue
                sid = id_m.group(1)
                subs[sid] = {
                    "name": cells[1] if len(cells) > 1 else "",
                    "start": _extract_ch(cells[2]) if len(cells) > 2 else "",
                    "end": _extract_ch(cells[3]) if len(cells) > 3 else "",
                    "main_intersection": cells[4] if len(cells) > 4 else "",
                }
    return (fores, subs)


def _extract_ch(cell: str) -> str:
    """从单元格中提取 ch{N} 或 ch{a}-{b} 形式的章节号。"""
    if not cell:
        return ""
    m = re.search(r"ch\s*(\d+(?:\s*[-~—]\s*\d+)?)", cell, re.IGNORECASE)
    if m:
        return f"ch{m.group(1).replace(' ', '')}"
    return cell.strip()[:20]


# ---------- 追踪表生成 ----------


def _build_foreshadowing_table(plan: dict, chapters: list[dict]) -> list[str]:
    """伏笔追踪表。

    - 计划中的伏笔：列出 + 实际状态（planted/resolved/遗漏）
    - 章节中实际出现但不在计划的：标"未在计划"
    """
    lines: list[str] = [
        "## 伏笔追踪（自动汇总）",
        "",
        "| 编号 | 名称 | 计划埋设 | 计划强化 | 计划回收 | 实际状态 | 出现章节 |",
        "|------|------|---------|---------|---------|---------|---------|",
    ]

    # 章节侧：哪些章节 planted / resolved 了哪些 F
    planted_map: dict[str, list[int]] = {}
    resolved_map: dict[str, list[int]] = {}
    for ch in chapters:
        for fid in ch["foreshadowings_planted"]:
            planted_map.setdefault(fid, []).append(ch["chapter"])
        for fid in ch["foreshadowings_resolved"]:
            resolved_map.setdefault(fid, []).append(ch["chapter"])

    # 计划中的伏笔
    for fid in sorted(plan.keys()):
        info = plan[fid]
        plant_chs = planted_map.get(fid, [])
        resolve_chs = resolved_map.get(fid, [])
        appear = sorted(set(plant_chs + resolve_chs))
        appear_str = ", ".join(f"ch{n}" for n in appear) if appear else "—"
        if resolve_chs:
            status = "已回收"
        elif plant_chs:
            status = "已埋设"
        else:
            status = "遗漏"
        lines.append(
            f"| {fid} | {info['name']} | {info['plant']} | {info['reinforce']} | {info['resolve']} | {status} | {appear_str} |"
        )

    # 未在计划的伏笔
    planned_ids = set(plan.keys())
    all_actual_ids = set(planted_map.keys()) | set(resolved_map.keys())
    unplanned = sorted(all_actual_ids - planned_ids)
    for fid in unplanned:
        plant_chs = planted_map.get(fid, [])
        resolve_chs = resolved_map.get(fid, [])
        appear = sorted(set(plant_chs + resolve_chs))
        appear_str = ", ".join(f"ch{n}" for n in appear)
        status = "已回收" if resolve_chs else "已埋设"
        lines.append(
            f"| {fid} | （未在计划） | — | — | — | {status} | {appear_str} |"
        )

    if not plan and not all_actual_ids:
        lines.append("| （无伏笔数据） | | | | | | |")

    return lines


def _build_subline_table(plan: dict, chapters: list[dict]) -> list[str]:
    """支线追踪表。"""
    lines: list[str] = [
        "## 支线追踪（自动汇总）",
        "",
        "| 编号 | 名称 | 计划起止 | 实际出现章节 | 与主线交汇 |",
        "|------|------|---------|------------|-----------|",
    ]

    appear_map: dict[str, list[int]] = {}
    for ch in chapters:
        for sid in ch["sublines_advanced"]:
            appear_map.setdefault(sid, []).append(ch["chapter"])

    for sid in sorted(plan.keys()):
        info = plan[sid]
        chs = sorted(appear_map.get(sid, []))
        chs_str = ", ".join(f"ch{n}" for n in chs) if chs else "未出现"
        lines.append(
            f"| {sid} | {info['name']} | {info['start']}–{info['end']} | {chs_str} | {info['main_intersection']} |"
        )

    planned_ids = set(plan.keys())
    unplanned = sorted(set(appear_map.keys()) - planned_ids)
    for sid in unplanned:
        chs = sorted(appear_map.get(sid, []))
        chs_str = ", ".join(f"ch{n}" for n in chs)
        lines.append(
            f"| {sid} | （未在计划） | — | {chs_str} | — |"
        )

    if not plan and not appear_map:
        lines.append("| （无支线数据） | | | | |")

    return lines


def _build_character_state_table(chapters: list[dict], root: Path) -> list[str]:
    """角色首次出场登记 + 出现章节。"""
    debut_map: dict[str, int] = {}
    appear_map: dict[str, list[int]] = {}
    for ch in chapters:
        for name in ch["debut_characters"]:
            if name not in debut_map:
                debut_map[name] = ch["chapter"]
            appear_map.setdefault(name, []).append(ch["chapter"])

    lines: list[str] = [
        "## 角色首次出场登记（自动汇总）",
        "",
        "| 角色 | 首次出场章 | 后续出现章节 |",
        "|------|----------|------------|",
    ]
    for name in sorted(debut_map.keys()):
        first = debut_map[name]
        later = [n for n in sorted(set(appear_map[name])) if n != first]
        later_str = ", ".join(f"ch{n}" for n in later) if later else "—"
        lines.append(f"| {name} | ch{first} | {later_str} |")

    if not debut_map:
        lines.append("| （无角色出场数据） | | |")

    return lines


def _build_chapter_summary_table(chapters: list[dict]) -> list[str]:
    """章节摘要表：每章一行的 front-matter 摘要。"""
    lines: list[str] = [
        "## 章节摘要（front-matter 汇总）",
        "",
        "| 章 | 标题 | 字数 | 埋设伏笔 | 回收伏笔 | 推进支线 | 首次出场 |",
        "|----|------|------|---------|---------|---------|---------|",
    ]
    for ch in chapters:
        planted = ", ".join(ch["foreshadowings_planted"]) or "—"
        resolved = ", ".join(ch["foreshadowings_resolved"]) or "—"
        sublines = ", ".join(ch["sublines_advanced"]) or "—"
        debut = ", ".join(ch["debut_characters"]) or "—"
        lines.append(
            f"| ch{ch['chapter']} | {ch['title']} | {ch['actual_words']} | "
            f"{planted} | {resolved} | {sublines} | {debut} |"
        )
    if not chapters:
        lines.append("| （无章节） | | | | | | |")
    return lines


# ---------- 主入口 ----------


def collect(root: Path) -> str:
    """扫描项目，生成一致性校验上下文 markdown。

    输出 = 完整 markdown 文本，由调用方写入 .fictia-cache/consistency-context.md。
    """
    chapters = _scan_chapters(root)
    fores_plan, subs_plan = _parse_weave_plan(root)

    parts: list[str] = ["# 一致性校验上下文（自动汇总）", ""]

    parts.extend(_build_chapter_summary_table(chapters))
    parts.append("")

    parts.extend(_build_foreshadowing_table(fores_plan, chapters))
    parts.append("")

    parts.extend(_build_subline_table(subs_plan, chapters))
    parts.append("")

    parts.extend(_build_character_state_table(chapters, root))
    parts.append("")

    # 各章写作备注原文（供 agent 详查）
    parts.append("## 各章写作备注原文")
    parts.append("")
    for ch in chapters:
        parts.append(f"### ch{ch['chapter']}：{ch['title']}")
        parts.append("")
        if ch["writing_notes"]:
            parts.append(ch["writing_notes"])
        else:
            parts.append("（无写作备注）")
        parts.append("")

    return "\n".join(parts)

"""Dynamic Writing Space — 写作空间组装器。

组装完整的写作空间上下文，输出 markdown 格式供写手 agent 使用。

三层结构：
  1. 静态层：style-guide, art-design, world/rules, 前章正文, 源文本, 用户笔记
  2. 必读动态层：大纲、活跃角色卡、地点、伏笔、时间线、前章写作备注
  3. 按需检索层：相关事件、更多角色、历史地点（agent 自主决定）
"""
from __future__ import annotations

from pathlib import Path

from lib.entity_retriever import EntityRetriever, RetrievedEntities
from lib.outline_parser import OutlineHints, parse_outline_for_chapter
from lib.entity_store import EntityStore, open_entity_store_with_default_provider
from lib.context import (
    build_character_registry,
    build_notes_summary,
    build_world_quickref,
    chapter_act,
    extract_chapter_art_design,
    extract_chapter_narrative_weave,
    extract_style_stage_notes,
)
from lib.words import strip_writing_notes
from lib import source as S


# --------------------------------------------------------------------------- #
# 写作空间组装器
# --------------------------------------------------------------------------- #


class WritingSpaceAssembler:
    """组装完整的写作空间上下文。"""

    def __init__(
        self,
        project_root: Path,
        store: EntityStore,
    ) -> None:
        self.project_root = project_root
        self.store = store
        self.retriever = EntityRetriever(store)

    def assemble(self, chapter: int) -> str:
        """为指定章节组装写作空间，输出 markdown。"""

        # ── 大纲解析 → 线索 ──
        hints = parse_outline_for_chapter(self.project_root, chapter)
        outline_path = (
            self.project_root / "outline" / "chapters" / f"ch{chapter:02d}.md"
        )
        outline_text = (
            outline_path.read_text(encoding="utf-8") if outline_path.is_file() else ""
        )

        # ── 必读动态层：实体检索 ──
        entities = self.retriever.retrieve_for_chapter(hints)

        # ── 静态层 ──
        act = chapter_act(self.project_root, chapter)
        style = extract_style_stage_notes(self.project_root, act)
        art = extract_chapter_art_design(self.project_root, chapter)
        world_rules = build_world_quickref(self.project_root)
        prev_chapter_text = self._load_previous_chapter_text(chapter)
        prev_chapter_notes = self._load_previous_chapter_notes(chapter)
        source_ref = S.build_source_context(self.project_root)
        user_notes = build_notes_summary(self.project_root)

        # ── 组装 ──
        sections: list[str] = []

        # ━━ Part 1: 本章大纲（必读，完整） ━━
        sections.append(self._section("本章大纲", outline_text))

        # ━━ Part 2: 必读角色卡 ━━
        if entities.mandatory_characters:
            sections.append(
                self._section(
                    "本章活跃角色（必读）",
                    self._format_character_cards(entities.mandatory_characters),
                )
            )

        # ━━ Part 3: 关联角色（供参考） ━━
        if entities.related_characters:
            sections.append(
                self._section(
                    "相关角色（关联检索）",
                    self._format_character_cards(entities.related_characters),
                )
            )

        # ━━ Part 4: 必读地点 ━━
        if entities.mandatory_locations:
            sections.append(
                self._section(
                    "本章场景地点（必读）",
                    self._format_location_descriptions(entities.mandatory_locations),
                )
            )

        # ━━ Part 5: 伏笔指令与当前状态 ━━
        if entities.mandatory_foreshadowing:
            sections.append(
                self._section(
                    "伏笔指令与当前状态",
                    self._format_foreshadowing(
                        entities.mandatory_foreshadowing, hints.foreshadow_ops
                    ),
                )
            )

        # ━━ Part 6: 时间线上下文 ━━
        if entities.timeline_window:
            sections.append(
                self._section(
                    "时间线上下文",
                    self._format_timeline(entities.timeline_window, chapter),
                )
            )

        # ━━ Part 7: 活跃故事线 ━━
        if entities.active_storylines:
            sections.append(
                self._section(
                    "活跃故事线",
                    self._format_storylines(entities.active_storylines),
                )
            )

        # ━━ Part 8: 近期事件 ━━
        if entities.recent_events:
            sections.append(
                self._section(
                    "近期事件回顾",
                    self._format_events(entities.recent_events),
                )
            )

        # ━━ Part 9: 叙事编织（补充伏笔上下文） ━━
        narrative_weave = extract_chapter_narrative_weave(self.project_root, chapter)
        if "未找到" not in narrative_weave:
            sections.append(self._section("叙事编织（本章相关）", narrative_weave))

        # ━━ Part 10: 风格指南 ━━
        sections.append(self._section("风格指南", style))

        # ━━ Part 11: 艺术设计 ━━
        sections.append(self._section("艺术设计", art))

        # ━━ Part 12: 世界观速查 ━━
        sections.append(self._section("世界观速查", world_rules))

        # ━━ Part 13: 前章摘要 ━━
        if prev_chapter_notes:
            sections.append(self._section("前章写作备注", prev_chapter_notes))

        # ━━ Part 14: 前章正文 ━━
        if prev_chapter_text:
            sections.append(self._section("前章完整正文", prev_chapter_text))

        # ━━ Part 15: 可选静态层 ━━
        if source_ref and "无源文本素材" not in source_ref:
            sections.append(self._section("源文本参考", source_ref))

        if user_notes:
            sections.append(self._section("用户笔记", user_notes))

        # ── 角色速查表（兜底） ──
        sections.append(
            self._section("角色速查表（全量）", build_character_registry(self.project_root))
        )

        return "\n\n---\n\n".join(sections)

    # ---- 加载方法 ----

    def _load_previous_chapter_text(self, chapter: int) -> str:
        """加载前一章完整正文（剥离写作备注）。"""
        if chapter <= 1:
            return ""
        prev = chapter - 1
        candidates = list((self.project_root / "chapters").rglob(f"ch{prev:02d}.md"))
        if not candidates:
            return ""
        text = candidates[0].read_text(encoding="utf-8")
        return strip_writing_notes(text)

    def _load_previous_chapter_notes(self, chapter: int) -> str:
        """加载前一章写作备注。"""
        if chapter <= 1:
            return ""
        prev = chapter - 1
        candidates = list((self.project_root / "chapters").rglob(f"ch{prev:02d}.md"))
        if not candidates:
            return ""
        text = candidates[0].read_text(encoding="utf-8")
        # 提取写作备注段
        import re
        from lib.words import WRITING_NOTES_RE

        m = WRITING_NOTES_RE.search(text)
        if m:
            return text[m.start() :].strip()
        # 回退：末尾 300 字
        return "（无写作备注，末尾摘要）\n" + text[-300:]

    # ---- 格式化方法 ----

    @staticmethod
    def _section(title: str, content: str) -> str:
        """包裹一个 section。"""
        return f"## {title}\n\n{content.strip()}"

    @staticmethod
    def _format_character_cards(chars: list[dict]) -> str:
        """格式化角色卡列表。"""
        if not chars:
            return "（无）"

        lines: list[str] = []
        for char in chars:
            name = char.get("name", "?")
            state = char.get("state", "?")
            identity = char.get("identity", "")
            role = char.get("role", "")
            traits = char.get("traits", "")
            lang = char.get("lang_style", "")
            arc = char.get("arc_keyword", "")
            emotional = char.get("emotional", "")
            text = char.get("text", "")

            lines.append(f"### {name}（状态: {state}）")
            lines.append("")
            if identity:
                lines.append(f"- **身份**: {identity}")
            if role:
                lines.append(f"- **角色**: {role}")
            if traits:
                lines.append(f"- **核心特质**: {traits}")
            if lang:
                lines.append(f"- **语言风格**: {lang}")
            if arc:
                lines.append(f"- **弧光关键词**: {arc}")
            if emotional:
                lines.append(f"- **情感状态**: {emotional}")
            lines.append("")

            # 语义文本摘要（取前 300 字）
            if text:
                lines.append(text[:300])
                lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_location_descriptions(locs: list[dict]) -> str:
        """格式化地点描述。"""
        if not locs:
            return "（无）"

        lines: list[str] = []
        for loc in locs:
            name = loc.get("name", "?")
            state = loc.get("state", "?")
            region = loc.get("region", "")
            text = loc.get("text", "")

            lines.append(f"### {name}（状态: {state}）")
            if region:
                lines.append(f"- **区域**: {region}")
            lines.append("")
            if text:
                lines.append(text[:500])
                lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_foreshadowing(
        fores: list[dict], ops: list
    ) -> str:
        """格式化伏笔状态和操作指令。"""
        if not fores and not ops:
            return "（无）"

        lines: list[str] = []

        # 操作指令
        if ops:
            lines.append("### 本章伏笔操作指令")
            lines.append("")
            lines.append("| 伏笔ID | 操作 | 描述 |")
            lines.append("|--------|------|------|")
            for op in ops:
                lines.append(f"| {op.fo_id} | {op.op} | {op.hint} |")
            lines.append("")

        # 当前状态
        if fores:
            lines.append("### 伏笔当前状态")
            lines.append("")
            lines.append("| 名称 | 状态 | 类型 | 描述 |")
            lines.append("|------|------|------|------|")
            for fo in fores:
                name = fo.get("name", "?")
                state = fo.get("state", "?")
                fo_type = fo.get("type", "")
                text = fo.get("text", "")[:60]
                lines.append(f"| {name} | {state} | {fo_type} | {text} |")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_timeline(timeline: list[dict], current_chapter: int) -> str:
        """格式化时间线上下文。"""
        if not timeline:
            return "（无）"

        lines: list[str] = []
        for tl in timeline:
            ch = tl.get("chapter")
            name = tl.get("name", "?")
            event_time = tl.get("event_time", "")
            state = tl.get("state", "")

            marker = " **← 本章**" if ch == current_chapter else ""
            ch_str = f"ch{ch:02d}" if ch else "—"
            time_str = f" ({event_time})" if event_time else ""
            lines.append(f"- {ch_str}: {name}{time_str} [{state}]{marker}")

        return "\n".join(lines)

    @staticmethod
    def _format_storylines(storylines: list[dict]) -> str:
        """格式化活跃故事线。"""
        if not storylines:
            return "（无）"

        lines: list[str] = []
        for sl in storylines:
            name = sl.get("name", "?")
            state = sl.get("state", "?")
            sl_type = sl.get("type", "")
            priority = sl.get("priority", "")
            text = sl.get("text", "")[:100]

            lines.append(f"- **{name}** [{state}] ({sl_type}, {priority})")
            if text:
                lines.append(f"  {text}")

        return "\n".join(lines)

    @staticmethod
    def _format_events(events: list[dict]) -> str:
        """格式化近期事件。"""
        if not events:
            return "（无）"

        lines: list[str] = []
        for evt in events:
            ch = evt.get("chapter", "?")
            name = evt.get("name", "?")
            state = evt.get("state", "?")
            location = evt.get("location", "")
            text = evt.get("text", "")[:100]

            loc_str = f" @ {location}" if location else ""
            lines.append(f"- ch{ch:02d}: {name} [{state}]{loc_str}")
            if text:
                lines.append(f"  {text}")

        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 便捷函数
# --------------------------------------------------------------------------- #


def assemble_writing_space(project_root: Path, chapter: int) -> str:
    """便捷函数：组装指定章节的写作空间。"""
    store = open_entity_store_with_default_provider(project_root)
    assembler = WritingSpaceAssembler(project_root, store)
    return assembler.assemble(chapter)

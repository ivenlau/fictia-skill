"""Dynamic Writing Space — 写作空间组装器（优化版）。

组装精简的写作空间上下文，按章节相关性过滤，减少冗余。

优化策略：
  1. 风格指南：只加载与本章场景类型相关的规则，去掉示例段落
  2. 世界观：只加载本章大纲中出现的地点相关设定
  3. 角色卡：去重，只保留一份
  4. 用户笔记：按需检索，不全量加载
  5. 前章正文：只保留末尾 3-5 段用于衔接
  6. 前章写作备注：只提取伏笔操作和角色状态更新
  7. 角色速查表：只列出本章出场角色
"""
from __future__ import annotations

import re
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
    parse_frontmatter,
)
from lib.words import strip_writing_notes, WRITING_NOTES_RE
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
        """为指定章节组装精简写作空间，输出 markdown。"""

        # ── 大纲解析 → 线索 ──
        hints = parse_outline_for_chapter(self.project_root, chapter)
        outline_path = (
            self.project_root / "outline" / "chapters" / f"ch{chapter:02d}.md"
        )
        outline_text = (
            outline_path.read_text(encoding="utf-8") if outline_path.is_file() else ""
        )

        # ── 从大纲提取关键词（用于过滤） ──
        outline_keywords = self._extract_outline_keywords(outline_text, hints)

        # ── 必读动态层：实体检索 ──
        entities = self.retriever.retrieve_for_chapter(hints)

        # ── 静态层（优化版） ──
        act = chapter_act(self.project_root, chapter)
        style = self._extract_style_relevant(outline_keywords, act)
        art = extract_chapter_art_design(self.project_root, chapter)
        world_rules = self._extract_world_relevant(outline_keywords)
        prev_chapter_text = self._load_previous_chapter_tail(chapter)
        prev_chapter_notes = self._load_previous_chapter_notes_summary(chapter)
        source_ref = S.build_source_context(self.project_root)

        # ── 组装 ──
        sections: list[str] = []

        # ━━ Part 1: 本章大纲（必读，完整） ━━
        sections.append(self._section("本章大纲", outline_text))

        # ━━ Part 2: 必读角色卡（去重） ━━
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

        # ━━ Part 10: 风格指南（精简版） ━━
        sections.append(self._section("风格指南", style))

        # ━━ Part 11: 艺术设计 ━━
        if "未找到" not in art:
            sections.append(self._section("艺术设计", art))

        # ━━ Part 12: 世界观速查（按地点过滤） ━━
        sections.append(self._section("世界观速查", world_rules))

        # ━━ Part 13: 前章摘要（精简版） ━━
        if prev_chapter_notes:
            sections.append(self._section("前章写作备注", prev_chapter_notes))

        # ━━ Part 14: 前章正文末尾（衔接用） ━━
        if prev_chapter_text:
            sections.append(self._section("前章正文（末尾衔接）", prev_chapter_text))

        # ━━ Part 15: 可选静态层 ━━
        if source_ref and "无源文本素材" not in source_ref:
            sections.append(self._section("源文本参考", source_ref))

        # ── 角色速查表（只列出出场角色） ──
        appearing_names = self._collect_appearing_names(entities, hints)
        registry = self._build_filtered_character_registry(appearing_names)
        if registry:
            sections.append(self._section("角色速查表（出场角色）", registry))

        return "\n\n---\n\n".join(sections)

    # ---- 优化的加载方法 ----

    @staticmethod
    def _extract_outline_keywords(outline_text: str, hints: OutlineHints) -> set[str]:
        """从大纲文本中动态提取关键词，用于过滤风格/世界观。

        策略：不预设领域词表，而是从大纲本身提取高频实词和角色名。
        只提取 3+ 字符的词，避免常见2字词（如"她的""一个"）造成过度匹配。
        """
        keywords: set[str] = set()

        # 从 hints 提取角色名
        for name in hints.character_names:
            keywords.add(name)

        # 从大纲提取地点名（通过"地点"标记行）
        for line in outline_text.splitlines():
            if "地点" in line and ("：" in line or ":" in line):
                # 提取冒号后的内容，按分隔符拆分
                parts = re.split(r"[→、，,;；\s]+", line)
                for part in parts:
                    part = part.strip()
                    if len(part) >= 3 and not part.startswith("地点"):
                        keywords.add(part)

        # 从大纲提取所有中文名词短语（3-6字，出现≥3次）
        # 3+ 字符避免常见词，≥3次确保是本章核心概念
        cn_words = re.findall(r"[一-鿿]{3,6}", outline_text)
        word_count: dict[str, int] = {}
        for w in cn_words:
            word_count[w] = word_count.get(w, 0) + 1
        for w, cnt in word_count.items():
            if cnt >= 3:
                keywords.add(w)

        return keywords

    def _extract_style_relevant(self, keywords: set[str], act: str) -> str:
        """从 style-guide.md 提取与本章相关的风格规则（精简版）。

        过滤策略（通用，不依赖领域知识）：
        1. 核心规则（总体调性/语言规范/禁忌清单）始终保留
        2. 其他章节：检查章节内容是否包含大纲关键词，有则保留
        3. 去掉所有示例段落（### 正确示例/### 需要避免的示例）
        """
        f = self.project_root / "style-guide.md"
        if not f.is_file():
            return "（style-guide.md 不存在）"
        text = f.read_text(encoding="utf-8").strip()

        # 按二级标题切片
        h2_matches = list(re.finditer(r"^##\s+\S", text, re.MULTILINE))
        if len(h2_matches) < 3:
            return f"## 风格指南（{act}）\n\n" + self._strip_examples(text)

        # 核心规则始终保留
        core_titles = {"总体调性", "语言规范", "禁忌清单", "称呼体系"}

        lines: list[str] = [f"## 风格指南（{act}）", ""]

        for i, m in enumerate(h2_matches):
            start = m.start()
            end = h2_matches[i + 1].start() if i + 1 < len(h2_matches) else len(text)
            section_text = text[start:end].strip()
            section_title_line = m.group(0).strip()
            section_name = re.sub(r"^##\s+", "", section_title_line).strip()

            # 核心规则：始终保留
            is_core = any(title in section_name for title in core_titles)

            # 非核心：检查内容是否包含大纲关键词（3+字符）
            is_relevant = False
            if not is_core:
                for kw in keywords:
                    if len(kw) >= 3 and kw in section_text:
                        is_relevant = True
                        break

            if is_core or is_relevant:
                lines.append(self._strip_examples(section_text))
                lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _strip_examples(text: str) -> str:
        """去掉风格指南中的示例段落（### 正确示例 / ### 需要避免的示例 等）。"""
        # 去掉 "### 正确示例" 到下一个 "###" 或 "##" 之间的内容
        # 去掉 "### 需要避免的示例" 到下一个 "###" 或 "##" 之间的内容
        # 去掉 "句式示例" 代码块
        # 去掉 "段落节奏示例" 代码块
        patterns_to_strip = [
            r"###\s*(正确示例|需要避免的示例|风格示例段落)[\s\S]*?(?=###|\Z)",
            r"```\s*✅[\s\S]*?```",
            r"```\s*❌[\s\S]*?```",
        ]
        result = text
        for pat in patterns_to_strip:
            result = re.sub(pat, "", result)
        # 清理多余空行
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def _extract_world_relevant(self, keywords: set[str]) -> str:
        """从 world/setting.md 提取与本章相关的设定（精简版）。

        过滤策略（通用，不依赖领域知识）：
        1. 世界概况始终保留
        2. 其他章节：检查内容是否包含大纲关键词，有则保留
        3. 压缩长段落，保留表格和列表
        """
        f = self.project_root / "world" / "setting.md"
        if not f.is_file():
            return "（world/setting.md 不存在）"
        text = f.read_text(encoding="utf-8")

        # 按二级标题切片
        h2_matches = list(re.finditer(r"^##\s+\S", text, re.MULTILINE))
        if len(h2_matches) < 2:
            return "## 世界观速查\n\n" + text[:1000]

        # 核心章节始终保留
        core_titles = {"世界概况"}

        lines: list[str] = ["## 世界观速查", ""]

        for i, m in enumerate(h2_matches):
            start = m.start()
            end = h2_matches[i + 1].start() if i + 1 < len(h2_matches) else len(text)
            section_text = text[start:end].strip()
            section_title_line = m.group(0).strip()
            section_name = re.sub(r"^##\s+", "", section_title_line).strip()

            # 核心章节：始终保留
            is_core = any(title in section_name for title in core_titles)

            # 非核心：检查内容是否包含大纲关键词（3+字符）
            is_relevant = False
            if not is_core:
                for kw in keywords:
                    if len(kw) >= 3 and kw in section_text:
                        is_relevant = True
                        break

            if is_core or is_relevant:
                compressed = self._compress_section(section_text, max_chars=500)
                lines.append(compressed)
                lines.append("")

        # 也加载 rules.md 的摘要（如果存在）
        rules_f = self.project_root / "world" / "rules.md"
        if rules_f.is_file():
            rules_text = rules_f.read_text(encoding="utf-8")
            # 只保留与关键词相关的部分
            rules_lines = rules_text.splitlines()
            relevant_rules: list[str] = []
            current_section: list[str] = []
            current_title = ""

            for line in rules_lines:
                if line.startswith("## ") or line.startswith("### "):
                    # 检查上一个 section
                    if current_title and current_section:
                        is_core = "规则" in current_title or "原则" in current_title
                        is_relevant = any(kw in "\n".join(current_section) for kw in keywords if len(kw) >= 3)
                        if is_core or is_relevant:
                            relevant_rules.extend(current_section)
                    current_section = [line]
                    current_title = line
                else:
                    current_section.append(line)

            # 处理最后一个 section
            if current_title and current_section:
                is_core = "规则" in current_title or "原则" in current_title
                is_relevant = any(kw in "\n".join(current_section) for kw in keywords if len(kw) >= 3)
                if is_core or is_relevant:
                    relevant_rules.extend(current_section)

            if relevant_rules:
                lines.append("### 力量体系与规则（rules.md 摘要）")
                lines.append("")
                lines.extend(relevant_rules[:50])  # 限制行数
                lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _compress_section(text: str, max_chars: int = 500) -> str:
        """压缩一个章节：保留标题、表格、列表，压缩长段落。"""
        lines = text.splitlines()
        result: list[str] = []
        total = 0
        for line in lines:
            if total > max_chars:
                break
            # 保留标题、表格、列表
            if (line.startswith("#") or line.startswith("|") or
                    line.strip().startswith("-") or line.strip().startswith("*") or
                    not line.strip()):
                result.append(line)
                total += len(line)
            else:
                # 长段落截断
                if len(line) > 150:
                    line = line[:150] + "..."
                result.append(line)
                total += len(line)
        return "\n".join(result)

    def _load_previous_chapter_tail(self, chapter: int) -> str:
        """加载前一章正文末尾（用于衔接，约 500-800 字）。"""
        if chapter <= 1:
            return ""
        prev = chapter - 1
        candidates = list((self.project_root / "chapters").rglob(f"ch{prev:02d}.md"))
        if not candidates:
            return ""
        text = candidates[0].read_text(encoding="utf-8")
        text = strip_writing_notes(text)

        # 取末尾 800 字，在段落边界截断
        if len(text) <= 800:
            return text
        tail = text[-800:]
        # 找第一个段落边界
        first_nl = tail.find("\n\n")
        if first_nl > 0 and first_nl < 200:
            tail = tail[first_nl + 2:]
        return "..." + tail

    def _load_previous_chapter_notes_summary(self, chapter: int) -> str:
        """加载前一章写作备注摘要（只提取伏笔操作和角色状态）。"""
        if chapter <= 1:
            return ""
        prev = chapter - 1
        candidates = list((self.project_root / "chapters").rglob(f"ch{prev:02d}.md"))
        if not candidates:
            return ""
        text = candidates[0].read_text(encoding="utf-8")

        m = WRITING_NOTES_RE.search(text)
        if not m:
            return ""

        notes_text = text[m.start():].strip()

        # 只提取关键段落
        sections_to_keep: list[str] = []
        current_section: list[str] = []
        current_title = ""

        for line in notes_text.splitlines():
            if line.startswith("### ") or line.startswith("## "):
                # 保存上一个 section
                if current_title and current_section:
                    title_lower = current_title.lower()
                    # 只保留伏笔、角色状态、下章衔接、字数
                    if any(kw in title_lower for kw in [
                        "伏笔", "角色状态", "下章衔接", "字数", "支线"
                    ]):
                        sections_to_keep.append(current_title)
                        sections_to_keep.extend(current_section)
                current_section = [line]
                current_title = line
            else:
                current_section.append(line)

        # 处理最后一个 section
        if current_title and current_section:
            title_lower = current_title.lower()
            if any(kw in title_lower for kw in [
                "伏笔", "角色状态", "下章衔接", "字数", "支线"
            ]):
                sections_to_keep.append(current_title)
                sections_to_keep.extend(current_section)

        if not sections_to_keep:
            return ""

        result = "\n".join(sections_to_keep).strip()
        # 限制总长度
        if len(result) > 2000:
            result = result[:2000] + "\n...（截断）"
        return result

    @staticmethod
    def _collect_appearing_names(entities: RetrievedEntities, hints: OutlineHints) -> set[str]:
        """收集本章出场角色名。"""
        names: set[str] = set()
        # 从 hints
        for name in hints.character_names:
            names.add(name)
        # 从 entities
        for char in entities.mandatory_characters:
            names.add(char.get("name", ""))
        for char in entities.related_characters:
            names.add(char.get("name", ""))
        # 去掉空值
        names.discard("")
        return names

    def _build_filtered_character_registry(self, names: set[str]) -> str:
        """只构建出场角色的速查表。"""
        if not names:
            return ""

        chars_dir = self.project_root / "characters"
        if not chars_dir.is_dir():
            return ""

        files: list[Path] = []
        for name in ("protagonist.md", "antagonist.md"):
            p = chars_dir / name
            if p.is_file():
                files.append(p)
        for p in sorted((chars_dir / "supporting").glob("*.md")) if (chars_dir / "supporting").is_dir() else []:
            files.append(p)

        lines: list[str] = ["## 角色速查表", ""]
        lines.append("| 姓名 | 身份 | 角色 | 核心特质 | 语言风格 |")
        lines.append("|------|------|------|---------|---------|")

        found = False
        for p in files:
            text = p.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            name = fm.get("name", p.stem)
            # 只保留出场角色
            if name not in names:
                continue
            found = True
            identity = fm.get("identity", "")
            role = fm.get("role", "")
            traits = fm.get("traits", [])
            if isinstance(traits, list):
                traits_s = "、".join(str(t) for t in traits[:4])
            else:
                traits_s = str(traits)
            lang = fm.get("language_style", "")
            lines.append(f"| {name} | {identity} | {role} | {traits_s} | {lang} |")

        if not found:
            return ""

        return "\n".join(lines)

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
    import os

    # server 模式：通过 HTTP 获取实体数据
    if os.environ.get("FICTIA_EMBEDDING", "").lower() == "server":
        try:
            import httpx
            server_url = os.environ.get("FICTIA_EMBED_SERVER", "http://127.0.0.1:8700")
            resp = httpx.post(
                f"{server_url}/entity/writing-space",
                json={"chapter": chapter},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["content"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # server 没有这个 endpoint，回退到本地
                pass
            else:
                raise
        except Exception:
            pass

    # 本地模式
    store = open_entity_store_with_default_provider(project_root)
    assembler = WritingSpaceAssembler(project_root, store)
    return assembler.assemble(chapter)

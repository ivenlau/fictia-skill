"""
Fictia 上下文压缩与组装库。

实现 references/context-procedures.md 中定义的 8 个 build/extract 程序，
以及 3 个上下文组装（writer / editor / consistency）。

所有函数返回字符串（markdown 格式），便于直接拼入 subagent prompt。
"""

from __future__ import annotations
import re
import glob as _glob
from pathlib import Path
from .words import WRITING_NOTES_RE
from . import project as P
from . import source as S
from . import notes as N


# ---------- 用户笔记摘要 ----------


def build_notes_summary(root: Path) -> str:
    """读取 notes/summary.md；不存在则返回空字符串。"""
    return N.load_summary(root)


# ---------- YAML front-matter 工具 ----------


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """从 markdown 文本中抽取 YAML front-matter。

    返回 (front_matter_dict, body)。若无 front-matter 返回 ({}, text)。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ({}, text)
    # 找第二个 ---
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return ({}, text)
    fm_text = "\n".join(lines[1:end])
    from .yaml_subset import load
    fm = load(fm_text) or {}
    if not isinstance(fm, dict):
        fm = {}
    body = "\n".join(lines[end + 1 :])
    return (fm, body)


# ---------- 章节-幕 映射 ----------


def chapter_act(root: Path, chapter_num: int) -> str:
    """根据 blueprint.md 确定章节所在幕；找不到时回退到默认映射。"""
    bp = root / "blueprint.md"
    if bp.is_file():
        text = bp.read_text(encoding="utf-8")
        # 找 "第N章 至 第M章" / "chN-chM" 形式
        # 简化：扫描全文找包含 ch{N} 的幕定义行
        # 取章节范围说明
        cn = f"ch{chapter_num:02d}"
        # 匹配 "## 第X幕" 段落
        act_pattern = re.compile(
            r"^##\s*第([一二三四五])幕[^\n]*\n([\s\S]*?)(?=^##\s|\Z)",
            re.MULTILINE,
        )
        for m in act_pattern.finditer(text):
            body = m.group(2)
            # 找 "ch1" "ch01" 范围标记
            ranges = re.findall(r"ch(\d+)\s*[-~—]\s*ch(\d+)", body, re.IGNORECASE)
            for a, b in ranges:
                if int(a) <= chapter_num <= int(b):
                    return f"act-{m.group(1)}"
            single = re.findall(r"\bch(\d+)\b", body, re.IGNORECASE)
            if any(int(s) == chapter_num for s in single):
                return f"act-{m.group(1)}"
    # 默认回退
    return P.chapter_act_of(chapter_num)


# ---------- 角色速查表 ----------


def build_character_registry(root: Path) -> str:
    """从 characters/*.md 的 front-matter 构建速查表。目标 500-1000 字。"""
    chars_dir = root / "characters"
    if not chars_dir.is_dir():
        return "（characters/ 目录不存在）"

    files: list[Path] = []
    for name in ("protagonist.md", "antagonist.md"):
        p = chars_dir / name
        if p.is_file():
            files.append(p)
    for p in sorted((chars_dir / "supporting").glob("*.md")) if (chars_dir / "supporting").is_dir() else []:
        files.append(p)

    if not files:
        return "（无角色文件）"

    lines: list[str] = ["## 角色速查表", ""]
    lines.append("| 姓名 | 身份 | 角色 | 核心特质 | 语言风格 |")
    lines.append("|------|------|------|---------|---------|")
    relationships_all: list[str] = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        name = fm.get("name", p.stem)
        identity = fm.get("identity", "")
        role = fm.get("role", "")
        traits = fm.get("traits", [])
        if isinstance(traits, list):
            traits_s = "、".join(str(t) for t in traits[:4])
        else:
            traits_s = str(traits)
        lang = fm.get("language_style", "")
        lines.append(f"| {name} | {identity} | {role} | {traits_s} | {lang} |")
        for r in fm.get("relationships", []) or []:
            if isinstance(r, dict):
                relationships_all.append(
                    f"- {name} ↔ {r.get('name', '?')}：{r.get('relation', '')}（{r.get('dynamic', '')}）"
                )

    if relationships_all:
        lines.append("")
        lines.append("## 关系列表")
        lines.append("")
        lines.extend(relationships_all)

    return "\n".join(lines)


# ---------- 角色快速卡 ----------


def build_character_quick_card(root: Path, character_name: str) -> str:
    """单个角色的快速卡（300-500 字）。按 name 字段匹配。"""
    chars_dir = root / "characters"
    if not chars_dir.is_dir():
        return f"（未找到角色：{character_name}）"

    candidates = list(chars_dir.rglob("*.md"))
    for p in candidates:
        text = p.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        if fm.get("name") == character_name or p.stem == character_name:
            traits = fm.get("traits", [])
            if isinstance(traits, list):
                traits_s = "、".join(str(t) for t in traits)
            else:
                traits_s = str(traits)
            lines = [
                f"## 角色快速卡：{fm.get('name', p.stem)}",
                "",
                f"- **身份**：{fm.get('identity', '')}",
                f"- **角色**：{fm.get('role', '')}",
                f"- **年龄**：{fm.get('age', '?')}",
                f"- **核心特质**：{traits_s}",
                f"- **语言风格**：{fm.get('language_style', '')}",
                f"- **成长弧线**：{fm.get('growth_arc', '')}",
                "",
                "### 关键信息（正文摘要）",
                "",
            ]
            # 截取 body 前 600 字
            body_clean = re.sub(r"\n{3,}", "\n\n", body).strip()
            lines.append(body_clean[:600])
            return "\n".join(lines)
    return f"（未找到角色：{character_name}）"


# ---------- 章节叙事编织提取 ----------


def extract_chapter_narrative_weave(root: Path, chapter_num: int) -> str:
    """从 narrative-weave.md 提取与当前章节相关的内容。"""
    f = root / "narrative-weave.md"
    if not f.is_file():
        return f"（narrative-weave.md 不存在）"
    text = f.read_text(encoding="utf-8")
    cn = f"ch{chapter_num:02d}"
    cn_short = f"第{chapter_num}章"

    lines: list[str] = [f"## 章节叙事编织（{cn_short}）", ""]

    # 找所有 markdown 表格
    table_blocks = re.findall(r"((?:^\|.*\|\s*\n)+)", text, re.MULTILINE)
    matched_tables: list[str] = []
    for tbl in table_blocks:
        if cn in tbl or cn_short in tbl or f" {chapter_num} " in tbl:
            matched_tables.append(tbl.rstrip())

    # 也找以 ch{num} 开头的列表项
    list_pattern = re.compile(rf"^[\-\*]\s+.*(?:{cn}|{cn_short}|第\s*{chapter_num}\s*章).*$", re.MULTILINE)
    matched_lists = list_pattern.findall(text)

    if not matched_tables and not matched_lists:
        lines.append(f"（narrative-weave.md 中未找到第 {chapter_num} 章相关条目）")
        return "\n".join(lines)

    if matched_tables:
        lines.append("### 相关表格")
        lines.append("")
        lines.extend(t for t in matched_tables)
        lines.append("")

    if matched_lists:
        lines.append("### 相关列表项")
        lines.append("")
        lines.extend(matched_lists)
        lines.append("")

    return "\n".join(lines)


# ---------- 章节艺术设计提取 ----------


def extract_chapter_art_design(root: Path, chapter_num: int) -> str:
    """从 art-design.md 提取与当前章节相关的内容。"""
    f = root / "art-design.md"
    if not f.is_file():
        return "（art-design.md 不存在）"
    text = f.read_text(encoding="utf-8")
    cn = f"ch{chapter_num:02d}"
    cn_short = f"第{chapter_num}章"

    lines: list[str] = [f"## 章节艺术设计（{cn_short}）", ""]

    # 找含章节号的表格
    table_blocks = re.findall(r"((?:^\|.*\|\s*\n)+)", text, re.MULTILINE)
    matched = [t for t in table_blocks if cn in t or cn_short in t]
    if matched:
        lines.append("### 逐章相关表格")
        lines.append("")
        lines.extend(t for t in matched)
        lines.append("")

    # 提取意象定义（## 意象 段落）
    img_match = re.search(r"^##\s*意象[^\n]*\n([\s\S]*?)(?=^##\s|\Z)", text, re.MULTILINE)
    if img_match:
        lines.append("### 意象定义")
        lines.append("")
        lines.append(img_match.group(1).strip()[:1500])
        lines.append("")

    if not matched and not img_match:
        lines.append(f"（art-design.md 中未找到第 {chapter_num} 章相关条目）")

    return "\n".join(lines)


# ---------- 风格阶段提取 ----------


def extract_style_stage_notes(root: Path, act: str) -> str:
    """从 style-guide.md 提取风格要点。

    - 文件较小或无清晰标题结构时，加载全文
    - 否则按二级标题切片加载所有章节
    """
    f = root / "style-guide.md"
    if not f.is_file():
        return "（style-guide.md 不存在）"
    text = f.read_text(encoding="utf-8").strip()

    h2_matches = list(re.finditer(r"^##\s+\S", text, re.MULTILINE))

    if len(h2_matches) < 3 or len(text) < 2000:
        return f"## 风格指南（{act}，全文）\n\n{text}\n"

    lines: list[str] = [f"## 风格指南（{act}）", ""]

    head = text[: h2_matches[0].start()].strip()
    if head:
        lines.append(head)
        lines.append("")

    for i, m in enumerate(h2_matches):
        start = m.start()
        end = h2_matches[i + 1].start() if i + 1 < len(h2_matches) else len(text)
        lines.append(text[start:end].strip())
        lines.append("")

    return "\n".join(lines)


# ---------- 世界观速查 ----------


def build_world_quickref(root: Path) -> str:
    """合并 world/setting.md + world/rules.md 为 1000-2000 字速查。"""
    parts: list[str] = ["## 世界观速查", ""]

    setting = root / "world" / "setting.md"
    rules = root / "world" / "rules.md"

    if setting.is_file():
        text = setting.read_text(encoding="utf-8")
        parts.append("### 世界概况（setting.md 压缩）")
        parts.append("")
        # 保留标题、表格、要点；长段落压缩
        cur_section: list[str] = []
        section_paras = 0
        for line in text.splitlines():
            if line.startswith("#"):
                if cur_section:
                    parts.append("\n".join(cur_section))
                    parts.append("")
                cur_section = [line]
                section_paras = 0
            elif line.startswith("|") or line.strip().startswith("-") or line.strip().startswith("*"):
                cur_section.append(line)
            elif not line.strip():
                cur_section.append(line)
            else:
                if section_paras < 5 and len(line) < 150:
                    cur_section.append(line)
                    section_paras += 1
        if cur_section:
            parts.append("\n".join(cur_section))
        parts.append("")
    else:
        parts.append("（world/setting.md 不存在）")
        parts.append("")

    if rules.is_file():
        text = rules.read_text(encoding="utf-8")
        parts.append("### 力量体系与战斗规则（rules.md 摘要）")
        parts.append("")
        parts.append(text[:1500])
        parts.append("")
    else:
        parts.append("（world/rules.md 不存在）")
        parts.append("")

    return "\n".join(parts)


# ---------- 叙事编织摘要 ----------


def build_narrative_weave_summary(root: Path) -> str:
    """全量 narrative-weave.md 压缩为约 50%。"""
    f = root / "narrative-weave.md"
    if not f.is_file():
        return "（narrative-weave.md 不存在）"
    text = f.read_text(encoding="utf-8")
    parts: list[str] = ["## 叙事编织摘要", ""]
    # 表格完整保留
    last_end = 0
    for tbl_match in re.finditer(r"((?:^\|.*\|\s*\n)+)", text, re.MULTILINE):
        # 表格前的散文
        prose = text[last_end : tbl_match.start()]
        if prose.strip():
            parts.append(_compress_prose(prose))
            parts.append("")
        parts.append(tbl_match.group(1).rstrip())
        parts.append("")
        last_end = tbl_match.end()
    # 末尾散文
    rest = text[last_end:]
    if rest.strip():
        parts.append(_compress_prose(rest))
    return "\n".join(parts)


def _compress_prose(text: str) -> str:
    """压缩散文：保留标题 + 每段前 2 行。"""
    out: list[str] = []
    para: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if para:
                # 取标题 + 前 2 行
                if para[0].startswith("#"):
                    out.append(para[0])
                    out.extend(para[1:3])
                else:
                    out.extend(para[:2])
                para = []
        else:
            para.append(line)
    if para:
        if para[0].startswith("#"):
            out.append(para[0])
            out.extend(para[1:3])
        else:
            out.extend(para[:2])
    return "\n".join(out)


# ---------- 艺术设计摘要 ----------


def build_art_design_summary(root: Path) -> str:
    """全量 art-design.md 压缩为约 50%。"""
    f = root / "art-design.md"
    if not f.is_file():
        return "（art-design.md 不存在）"
    text = f.read_text(encoding="utf-8")
    parts: list[str] = ["## 艺术设计摘要", ""]
    # 取意象定义（## 意象 段）
    img_match = re.search(r"^##\s*意象[^\n]*\n([\s\S]*?)(?=^##\s|\Z)", text, re.MULTILINE)
    if img_match:
        parts.append("### 意象定义（完整保留）")
        parts.append("")
        parts.append(img_match.group(1).strip()[:2000])
        parts.append("")

    # 逐章表格压缩
    for tbl_match in re.finditer(r"((?:^\|.*\|\s*\n)+)", text, re.MULTILINE):
        tbl = tbl_match.group(1)
        # 跳过意象定义
        if img_match and tbl_match.start() < img_match.end() and tbl_match.start() >= img_match.start():
            continue
        parts.append("### 表格（保留结构）")
        parts.append("")
        parts.append(tbl.rstrip()[:1000])
        parts.append("")

    # 散文
    if not parts[2:]:
        parts.append(_compress_prose(text))
    return "\n".join(parts)


# ---------- 前章摘要 ----------


def build_previous_chapter_summary(root: Path, chapter_num: int) -> str:
    """读取前一章的 写作备注 + 完整正文。"""
    if chapter_num <= 1:
        return "（无前章）"
    prev_num = chapter_num - 1
    # 找前章文件
    candidates = list((root / "chapters").rglob(f"ch{prev_num:02d}.md"))
    if not candidates:
        return f"（未找到前章文件 ch{prev_num:02d}.md）"
    p = candidates[0]
    text = p.read_text(encoding="utf-8")

    # 抽 写作备注 段
    m = WRITING_NOTES_RE.search(text)
    notes = ""
    if m:
        notes = text[m.start() :].strip()
    else:
        # 回退：末尾 300 字
        notes = "（无写作备注，末尾摘要）\n" + text[-300:]

    return f"## 前章摘要（第 {prev_num} 章：{p.name}）\n\n{notes}"


# ---------- 上下文组装：章节写手 ----------


def assemble_writer_context(root: Path, chapter_num: int) -> str:
    """按 context-procedures.md 顺序组装写手上下文。"""
    act = chapter_act(root, chapter_num)
    parts: list[str] = [
        f"# 章节写作上下文（第 {chapter_num} 章 · {act}）",
        "",
    ]

    # 1. 章节大纲
    outline_path = root / "outline" / "chapters" / f"ch{chapter_num:02d}.md"
    if outline_path.is_file():
        parts.append("## 1. 章节大纲")
        parts.append("")
        parts.append(outline_path.read_text(encoding="utf-8"))
        parts.append("")
    else:
        rel = outline_path.relative_to(root)
        parts.append(
            f"## 1. 章节大纲\n\n"
            f"（未找到大纲：{rel}。"
            f"如需写本章，请先用 `fictia stage chapter outline {chapter_num}` 标记就绪）\n"
        )

    # 2. 风格指南（本阶段精选）
    parts.append("## 2. 风格指南（本阶段精选）")
    parts.append("")
    parts.append(extract_style_stage_notes(root, act))
    parts.append("")

    # 3. 世界观速查
    parts.append("## 3. 世界观速查")
    parts.append("")
    parts.append(build_world_quickref(root))
    parts.append("")

    # 4. 角色速查表
    parts.append("## 4. 角色速查表")
    parts.append("")
    parts.append(build_character_registry(root))
    parts.append("")

    # 5. 本章叙事编织
    parts.append("## 5. 本章叙事编织")
    parts.append("")
    parts.append(extract_chapter_narrative_weave(root, chapter_num))
    parts.append("")

    # 6. 本章艺术设计
    parts.append("## 6. 本章艺术设计")
    parts.append("")
    parts.append(extract_chapter_art_design(root, chapter_num))
    parts.append("")

    # 7. 前章摘要
    parts.append("## 7. 前章摘要")
    parts.append("")
    parts.append(build_previous_chapter_summary(root, chapter_num))
    parts.append("")

    # 8. 前章完整正文
    if chapter_num > 1:
        prev_files = list((root / "chapters").rglob(f"ch{chapter_num - 1:02d}.md"))
        if prev_files:
            parts.append("## 8. 前章完整正文")
            parts.append("")
            parts.append(prev_files[0].read_text(encoding="utf-8"))
            parts.append("")

    sources = S.build_source_context(root)
    if "无源文本素材" not in sources:
        parts.append("## 9. 源文本参考")
        parts.append("")
        parts.append(sources)
        parts.append("")

    # 10. 用户笔记摘要（按需：summary.md 存在即加载）
    notes_summary = build_notes_summary(root)
    if notes_summary:
        parts.append("## 10. 用户笔记摘要")
        parts.append("")
        parts.append(notes_summary)
        parts.append("")

    return "\n".join(parts)


# ---------- 上下文组装：编辑审核 ----------


def assemble_editor_context(root: Path, chapter_num: int) -> str:
    """按 context-procedures.md 顺序组装编辑审核上下文。"""
    parts: list[str] = [f"# 编辑审核上下文（第 {chapter_num} 章）", ""]

    # 1. 章节正文
    ch_files = list((root / "chapters").rglob(f"ch{chapter_num:02d}.md"))
    if ch_files:
        parts.append("## 1. 章节正文")
        parts.append("")
        parts.append(ch_files[0].read_text(encoding="utf-8"))
        parts.append("")
    else:
        parts.append(f"## 1. 章节正文\n\n（ch{chapter_num:02d}.md 不存在）\n")

    # 2. 章节大纲（含目标字数）
    outline_path = root / "outline" / "chapters" / f"ch{chapter_num:02d}.md"
    if outline_path.is_file():
        text = outline_path.read_text(encoding="utf-8")
        parts.append("## 2. 章节大纲（用于字数验证）")
        parts.append("")
        parts.append(text)
        parts.append("")
    else:
        parts.append(f"## 2. 章节大纲\n\n（{outline_path} 不存在）\n")

    # 3. 艺术设计摘要
    parts.append("## 3. 艺术设计摘要")
    parts.append("")
    parts.append(build_art_design_summary(root))
    parts.append("")

    # 4. 叙事编织摘要
    parts.append("## 4. 叙事编织摘要")
    parts.append("")
    parts.append(build_narrative_weave_summary(root))
    parts.append("")

    # 5. 世界观速查
    parts.append("## 5. 世界观速查")
    parts.append("")
    parts.append(build_world_quickref(root))
    parts.append("")

    # 6. 角色速查表
    parts.append("## 6. 角色速查表")
    parts.append("")
    parts.append(build_character_registry(root))
    parts.append("")

    sources = S.build_source_context(root)
    if "无源文本素材" not in sources:
        parts.append("## 7. 源文本参考")
        parts.append("")
        parts.append(sources)
        parts.append("")

    # 8. 用户笔记摘要（按需）
    notes_summary = build_notes_summary(root)
    if notes_summary:
        parts.append("## 8. 用户笔记摘要")
        parts.append("")
        parts.append(notes_summary)
        parts.append("")

    return "\n".join(parts)


# ---------- 上下文组装：一致性校验 ----------


def assemble_consistency_context(root: Path) -> str:
    """组装一致性校验上下文：所有章节写作备注 + 最新章节完整 + 各速查。"""
    parts: list[str] = ["# 一致性校验上下文", ""]

    chapters_dir = root / "chapters"
    ch_files = sorted(chapters_dir.rglob("ch*.md")) if chapters_dir.is_dir() else []

    # 1. 所有章节：先前章节仅 写作备注，最新章节完整正文
    parts.append("## 1. 各章摘要")
    parts.append("")
    if not ch_files:
        parts.append("（无章节文件）")
        parts.append("")
    else:
        latest = ch_files[-1]
        for p in ch_files[:-1]:
            text = p.read_text(encoding="utf-8")
            m = WRITING_NOTES_RE.search(text)
            if m:
                parts.append(f"### {p.name}")
                parts.append("")
                parts.append(text[m.start() :].strip())
                parts.append("")
            else:
                parts.append(f"### {p.name}（无写作备注）")
                parts.append("")
                parts.append(text[-300:])
                parts.append("")
        # 完整正文
        parts.append(f"## 1.5 最新章节完整正文（{latest.name}）")
        parts.append("")
        parts.append(latest.read_text(encoding="utf-8"))
        parts.append("")

    # 2. 艺术设计摘要
    parts.append("## 2. 艺术设计摘要")
    parts.append("")
    parts.append(build_art_design_summary(root))
    parts.append("")

    # 3. 叙事编织摘要
    parts.append("## 3. 叙事编织摘要")
    parts.append("")
    parts.append(build_narrative_weave_summary(root))
    parts.append("")

    # 4. 世界观速查
    parts.append("## 4. 世界观速查")
    parts.append("")
    parts.append(build_world_quickref(root))
    parts.append("")

    sources = S.build_source_context(root)
    if "无源文本素材" not in sources:
        parts.append("## 4.5 源文本参考")
        parts.append("")
        parts.append(sources)
        parts.append("")

    # 5. world/timeline.md（完整）
    timeline = root / "world" / "timeline.md"
    if timeline.is_file():
        parts.append("## 5. world/timeline.md（完整）")
        parts.append("")
        parts.append(timeline.read_text(encoding="utf-8"))
        parts.append("")

    # 6. 角色速查表
    parts.append("## 6. 角色速查表")
    parts.append("")
    parts.append(build_character_registry(root))
    parts.append("")

    # 7. 用户笔记摘要（按需）
    notes_summary = build_notes_summary(root)
    if notes_summary:
        parts.append("## 7. 用户笔记摘要")
        parts.append("")
        parts.append(notes_summary)
        parts.append("")

    return "\n".join(parts)


# ---------- 审核/校验报告解析 ----------


def parse_review_verdict(text: str) -> dict:
    """从编辑审核报告中解析：综合评分、严重问题数、一般问题数。

    只在「总体评价」section（文件开头到第一个 ``## `` 或 ``### `` 标题之前）
    内匹配评分，避免误抓修复日志/评分细项表里的字母。
    """
    grade = _extract_grade(text)
    severe_count = _count_table_rows_after_header(text, "严重问题")
    normal_count = _count_table_rows_after_header(text, "一般问题")
    return {
        "grade": grade,
        "severe": severe_count,
        "normal": normal_count,
        "passed": (grade == "A" and severe_count == 0 and normal_count == 0),
    }


def _extract_grade(text: str) -> str | None:
    """从报告中解析综合评分字母（A-D）。

    只匹配包含「综合评分」关键词的形态（``**综合评分**：A`` 等）。
    这些关键词只出现在「总体评价」section 中，不会误抓修复日志
    或「评分细项」表里的 ``评分`` 列头。
    """
    for pat in [
        r"\*\*?综合评分\*\*?[：:]\s*\*?\*?([A-D])",
        r"综合评分\*\*?[：:]\s*\*?\*?([A-D])",
    ]:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


_NONE_MARKER_RE = re.compile(r"^(无|（无）|\(无\)|无问题|无重大问题|无明显问题|无特别|暂无|—|-)\s*[。.！!]?\s*$")


def _count_table_rows_after_header(text: str, header: str) -> int:
    """在 ``### 严重问题`` 标题之后、下一个同级或更高级标题之前的范围内，
    统计数据行数。

    关键修复点：
      1. **section 边界**：只在「严重问题」section 内部找表格，不跨过下一个
         ``### `` / ``## `` 标题。否则会把后续 section（如「细节问题」「审核修复日志」）
         的表格行数误算成本 section 的问题数。
      2. **「无」占位识别**：section 体内只有 ``无`` / ``（无）`` / ``暂无``
         等占位文字（无表格）时返回 0。
    """
    # 找到 section 标题（包括 ``### 严重问题（必须修改）`` 等带括号的形式）
    # 注意：f-string 中 ``#{{1,6}}`` 必须双花括号转义，否则 ``#{1,6}`` 会被当成
    # f-string 表达式解析为元组 ``(1, 6)``。
    m = re.search(rf"^(#{{1,6}})\s*{re.escape(header)}[^\n]*\n", text, re.MULTILINE)
    if not m:
        return 0
    marker = m.group(1)
    start = m.end()

    # 找下一个同级或更高级标题（同一 marker 或更少 #）
    next_section = re.search(rf"^#{{1,{len(marker)}}}\s+", text[start:], re.MULTILINE)
    end = start + next_section.start() if next_section else len(text)
    section_body = text[start:end]

    # section 体内的第一段非空文字：若是「无」占位，直接返回 0
    first_line = next((ln.strip() for ln in section_body.splitlines() if ln.strip()), "")
    if _NONE_MARKER_RE.match(first_line):
        return 0

    # 在 section 体内找第一个表格
    tbl_m = re.search(r"((?:^\|.*\|\s*\n)+)", section_body, re.MULTILINE)
    if not tbl_m:
        return 0
    tbl = tbl_m.group(1)
    lines = [l for l in tbl.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        return 0
    # 跳过表头与分隔行
    data_lines = [l for l in lines[2:] if not re.match(r"^\|[\s\-:|]+\|\s*$", l)]
    return len(data_lines)

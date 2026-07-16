"""
Source novel import helpers for rewrite/imitation/continuation workflows.
"""

from __future__ import annotations
import html
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from . import project as P


SUPPORTED_EXTS = {".epub", ".txt", ".md"}
SOURCE_WORKFLOWS = ("rewrite", "imitation", "continuation")


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _html_to_text(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|h[1-6]|li|section|article|chapter)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return _clean_text(html.unescape(text))


def _read_epub(path: Path) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        if rootfile is None or "full-path" not in rootfile.attrib:
            raise ValueError("EPUB 缺少 META-INF/container.xml rootfile")
        opf_path = rootfile.attrib["full-path"]
        opf_dir = posixpath.dirname(opf_path)
        opf = ET.fromstring(zf.read(opf_path))

        manifest: dict[str, str] = {}
        for item in opf.findall(".//{*}manifest/{*}item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            if item_id and href:
                manifest[item_id] = href

        for itemref in opf.findall(".//{*}spine/{*}itemref"):
            href = manifest.get(itemref.attrib.get("idref", ""))
            if not href:
                continue
            member = posixpath.normpath(posixpath.join(opf_dir, href))
            try:
                raw = zf.read(member)
            except KeyError:
                continue
            text = _html_to_text(_decode_bytes(raw))
            if text:
                parts.append(text)

    if not parts:
        raise ValueError("EPUB 未提取到正文内容")
    return _clean_text("\n\n".join(parts))


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError("仅支持 epub、txt、md 小说数据")
    if ext == ".epub":
        return _read_epub(path)
    return _clean_text(_decode_bytes(path.read_bytes()))


def _slug(value: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", value, flags=re.UNICODE)
    return slug.strip("-_.") or "source"


def _unique_source_path(root: Path, title: str) -> Path:
    source_dir = root / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    base = _slug(title)
    target = source_dir / f"{base}.md"
    index = 2
    while target.exists():
        target = source_dir / f"{base}-{index}.md"
        index += 1
    return target


def import_source(root: Path, path: Path, workflow: str, title: str | None = None) -> Path:
    if workflow not in SOURCE_WORKFLOWS:
        raise ValueError(f"未知源文本工作流: {workflow}")
    if not path.is_file():
        raise FileNotFoundError(path)

    source_text = extract_text(path)
    source_title = title or path.stem
    imported_at = P._utcnow_str()
    target = _unique_source_path(root, source_title)
    rel_target = target.relative_to(root).as_posix()

    target.write_text(
        f"# {source_title}\n\n"
        f"> 来源文件：`{path.name}`\n"
        f"> 数据格式：`{path.suffix.lower().lstrip('.')}`\n"
        f"> 工作流：`{workflow}`\n"
        f"> 导入时间：`{imported_at}`\n\n"
        "---\n\n"
        f"{source_text}\n",
        encoding="utf-8",
    )

    data = P.load_project(root)
    source_material = data.setdefault("source_material", {})
    source_material["workflow"] = workflow
    files = source_material.setdefault("files", [])
    files.append({
        "title": source_title,
        "workflow": workflow,
        "format": path.suffix.lower().lstrip("."),
        "original": str(path.resolve()),
        "text": rel_target,
        "importedAt": imported_at,
    })
    P.save_project(root, data)
    return target


def list_sources(root: Path) -> list[dict]:
    data = P.load_project(root)
    source_material = data.get("source_material") or {}
    files = source_material.get("files") or []
    return files if isinstance(files, list) else []


def _get_workflow(root: Path) -> str:
    """从 project.yaml 读取当前工作流类型。"""
    data = P.load_project(root)
    sm = data.get("source_material") or {}
    return sm.get("workflow", "")


def _strip_source_header(text: str) -> str:
    """去掉 source import 生成的元数据头（--- 之前的部分）。"""
    # 跳过 title (# ...) 和 blockquote (> ...) 头部
    lines = text.splitlines()
    body_start = 0
    in_header = True
    for i, line in enumerate(lines):
        stripped = line.strip()
        if in_header:
            if stripped == "---":
                body_start = i + 1
                in_header = False
            elif stripped.startswith("#") or stripped.startswith(">") or not stripped:
                continue
            else:
                # 非标准头部行，从这里开始
                body_start = i
                in_header = False
        else:
            break
    return "\n".join(lines[body_start:]).strip()


def _split_chapters(text: str) -> list[str]:
    """尝试按章节标题切分文本。返回章节列表（可能只有 1 个元素）。"""
    # 匹配常见章节标记：第X章、Chapter X、卷X、第X节
    pattern = re.compile(
        r"^(?:第[一二三四五六七八九十百千\d]+[章回节卷篇]|"
        r"Chapter\s+\d+|"
        r"卷[一二三四五六七八九十百千\d]+)",
        re.MULTILINE,
    )
    splits = list(pattern.finditer(text))
    if len(splits) < 2:
        return [text] if text.strip() else []

    chapters = []
    for i, m in enumerate(splits):
        start = m.start()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        chapter_text = text[start:end].strip()
        if chapter_text:
            chapters.append(chapter_text)
    return chapters


def _estimate_char_count(text: str) -> int:
    """估算中文字数（去掉标点和空白）。"""
    return len(re.sub(r"[\s\W]", "", text))


# --------------------------------------------------------------------------- #
# 工作流特定的上下文构建
# --------------------------------------------------------------------------- #


def build_rewrite_context(root: Path, max_chars: int = 12000) -> str:
    """改写工作流：提供情节骨架 + 头尾节选。

    改写需要理解原作的整体结构和关键情节，但不需要逐字参考。
    提供：开头节选（理解起始设定）+ 结尾节选（理解收束方向）+ 章节结构概览。
    """
    entries = list_sources(root)
    if not entries:
        return "（无源文本素材）"

    parts = [
        "## 源文本素材（改写模式）",
        "",
        "以下是原作文本。改写要求：保留核心情节骨架和人物功能，重构表达、节奏和细节。",
        "请勿大段复用原文表达。重点参考情节走向和结构设计。",
        "",
    ]

    for item in entries:
        rel = item.get("text", "")
        path = root / rel
        parts.append(f"### {item.get('title') or path.stem}")
        parts.append("")
        if not path.is_file():
            parts.append("（源文本文件不存在）")
            parts.append("")
            continue

        raw = path.read_text(encoding="utf-8")
        text = _strip_source_header(raw)

        # 章节结构概览
        chapters = _split_chapters(text)
        if len(chapters) > 3:
            parts.append(f"**章节结构**（共 {len(chapters)} 章）：")
            for i, ch in enumerate(chapters, 1):
                # 提取每章首行作为摘要
                first_line = ch.split("\n")[0].strip()[:60]
                parts.append(f"  - 第{i}章: {first_line}")
            parts.append("")

        # 头部节选（开头 40%）
        head_size = int(max_chars * 0.4)
        if len(text) <= head_size:
            parts.append("**原文（完整）**：")
            parts.append(text)
        else:
            parts.append("**原文开头节选**：")
            parts.append(text[:head_size].rstrip())
            parts.append("")

        # 尾部节选（结尾 40%）
        tail_size = int(max_chars * 0.4)
        if len(text) > head_size + tail_size:
            parts.append("**原文结尾节选**：")
            parts.append(text[-tail_size:].lstrip())
            parts.append("")

        parts.append("")
    return "\n".join(parts)


def build_imitation_context(root: Path, max_chars: int = 6000) -> str:
    """仿写工作流：只提供风格特征，不提供情节/人物/设定。

    仿写需要提取原作的语言风格指纹：句式、节奏、词汇层次、描写密度、对话风格。
    不提供具体情节、人物名、地名、专有名词，避免无意复用。
    """
    entries = list_sources(root)
    if not entries:
        return "（无源文本素材）"

    parts = [
        "## 源文本风格指纹（仿写模式）",
        "",
        "以下是原作的风格分析样本。仿写要求：提炼类型公式、节奏、语言特征，",
        "创作全新故事。**严禁**复用原作的专有名词、设定、人物和情节。",
        "只参考以下风格维度：句式节奏、描写密度、对话风格、叙事距离。",
        "",
    ]

    for item in entries:
        rel = item.get("text", "")
        path = root / rel
        parts.append(f"### {item.get('title') or path.stem}")
        parts.append("")
        if not path.is_file():
            parts.append("（源文本文件不存在）")
            parts.append("")
            continue

        raw = path.read_text(encoding="utf-8")
        text = _strip_source_header(raw)

        # 提取风格样本：取不同位置的段落，避免连续段落暴露情节
        sample_size = min(800, max_chars // 4)
        samples = _extract_style_samples(text, sample_size, n_samples=4)

        parts.append("**风格分析样本**（从不同位置抽取，仅用于风格参考）：")
        parts.append("")
        for i, sample in enumerate(samples, 1):
            # 替换专有名词为占位符，避免泄露
            anonymized = _anonymize_proper_nouns(sample)
            parts.append(f"样本 {i}：")
            parts.append(f"> {anonymized}")
            parts.append("")

        # 句式统计
        stats = _analyze_sentence_stats(text)
        parts.append("**句式特征统计**：")
        parts.append(f"- 平均句长：{stats['avg_sentence_len']} 字")
        parts.append(f"- 短句比例（<15字）：{stats['short_ratio']:.0%}")
        parts.append(f"- 长句比例（>40字）：{stats['long_ratio']:.0%}")
        parts.append(f"- 对话占比：{stats['dialogue_ratio']:.0%}")
        parts.append(f"- 段落平均长度：{stats['avg_para_len']} 字")
        parts.append("")
    return "\n".join(parts)


def build_continuation_context(root: Path, max_chars: int = 12000) -> str:
    """续写工作流：重点提供断点附近的上下文。

    续写需要理解故事在何处中断：最后几章的内容、人物当前状态、未解伏笔。
    提供：源文本末尾（断点处）的大量内容 + 开头简述（用于人物/设定交叉引用）。
    """
    entries = list_sources(root)
    if not entries:
        return "（无源文本素材）"

    parts = [
        "## 源文本素材（续写模式）",
        "",
        "以下是原作文本。续写要求：从文本末尾断点处继续写作，",
        "保持人物性格、语言风格、世界观和伏笔逻辑的连续性。",
        "重点阅读断点附近的文本，理解当前人物状态和未解悬念。",
        "",
    ]

    for item in entries:
        rel = item.get("text", "")
        path = root / rel
        parts.append(f"### {item.get('title') or path.stem}")
        parts.append("")
        if not path.is_file():
            parts.append("（源文本文件不存在）")
            parts.append("")
            continue

        raw = path.read_text(encoding="utf-8")
        text = _strip_source_header(raw)
        total_chars = len(text)

        # 章节结构（简述）
        chapters = _split_chapters(text)
        if len(chapters) > 3:
            parts.append(f"**全书结构**（共 {len(chapters)} 章，总计约 {_estimate_char_count(text)} 字）：")
            for i, ch in enumerate(chapters, 1):
                first_line = ch.split("\n")[0].strip()[:60]
                parts.append(f"  - 第{i}章: {first_line}")
            parts.append("")

        # 开头简述（10%）
        head_size = int(max_chars * 0.15)
        if total_chars > head_size:
            parts.append("**原文开头（简述）**：")
            parts.append(text[:head_size].rstrip())
            parts.append("...（中间章节省略）...")
            parts.append("")

        # 断点区域（85%）—— 最后 max_chars * 0.85 的内容
        tail_size = int(max_chars * 0.85)
        if total_chars <= tail_size:
            parts.append("**原文（完整，断点前全部内容）**：")
            parts.append(text)
        else:
            parts.append("**断点前文本（重点阅读）**：")
            parts.append(text[-tail_size:].lstrip())
        parts.append("")
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# 风格分析工具（用于仿写模式）
# --------------------------------------------------------------------------- #


def _extract_style_samples(text: str, sample_size: int, n_samples: int = 4) -> list[str]:
    """从文本不同位置抽取风格样本段落。

    策略：将文本分为 n_samples 段，每段取中间的 sample_size 字符。
    避免取开头和结尾（可能暴露情节设定）。
    """
    if len(text) <= sample_size * n_samples:
        # 文本太短，直接返回
        return [text[:sample_size]]

    segments = []
    seg_len = len(text) // n_samples
    for i in range(n_samples):
        start = i * seg_len + seg_len // 4  # 跳过段首
        end = min(start + sample_size, (i + 1) * seg_len)
        segment = text[start:end].strip()
        if segment:
            segments.append(segment)
    return segments


def _anonymize_proper_nouns(text: str) -> str:
    """用占位符替换文本内容，保留句式结构供风格分析。

    策略：保留标点符号（句号、逗号、引号、感叹号等）和数字，
    遮蔽中文字符块。这样 LLM 能看到：
    - 句式长短节奏（标点分布）
    - 对话比例（引号数量）
    - 段落结构（空行分布）
    - 叹/问比例（！？）
    但看不到具体内容和专有名词。
    """
    # 匹配连续中文字符（2字以上），替换为等长占位符
    cn_run = re.compile(r"[一-鿿]{2,}")
    result = cn_run.sub(lambda m: "□" * len(m.group()), text)
    return result


def _analyze_sentence_stats(text: str) -> dict:
    """分析文本的句式统计特征。"""
    # 按句末标点切句
    sentences = re.split(r"[。！？!?]", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return {
            "avg_sentence_len": 0,
            "short_ratio": 0.0,
            "long_ratio": 0.0,
            "dialogue_ratio": 0.0,
            "avg_para_len": 0,
        }

    # 句长统计
    lens = [len(re.sub(r"\s", "", s)) for s in sentences]
    avg_len = sum(lens) / len(lens) if lens else 0
    short_count = sum(1 for l in lens if l < 15)
    long_count = sum(1 for l in lens if l > 40)

    # 对话占比（含引号的句子）
    dialogue_markers = re.compile(r'[""「」『』『』]')
    dialogue_count = sum(1 for s in sentences if dialogue_markers.search(s))

    # 段落统计
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    para_lens = [len(re.sub(r"\s", "", p)) for p in paragraphs]
    avg_para = sum(para_lens) / len(para_lens) if para_lens else 0

    return {
        "avg_sentence_len": round(avg_len),
        "short_ratio": short_count / len(sentences) if sentences else 0,
        "long_ratio": long_count / len(sentences) if sentences else 0,
        "dialogue_ratio": dialogue_count / len(sentences) if sentences else 0,
        "avg_para_len": round(avg_para),
    }


# --------------------------------------------------------------------------- #
# 入口：按 workflow 分发
# --------------------------------------------------------------------------- #


def build_source_context(root: Path, max_chars: int = 12000) -> str:
    """按工作流类型构建源文本上下文。

    - rewrite（改写）：情节骨架 + 头尾节选
    - imitation（仿写）：风格指纹（匿名化样本 + 句式统计）
    - continuation（续写）：断点前文本（末尾大量内容）
    - 无 source_material：返回通用参考（向后兼容）
    """
    workflow = _get_workflow(root)

    if workflow == "rewrite":
        return build_rewrite_context(root, max_chars)
    elif workflow == "imitation":
        return build_imitation_context(root, max_chars)
    elif workflow == "continuation":
        return build_continuation_context(root, max_chars)
    else:
        # 无 source_material 或未知 workflow → 向后兼容的通用模式
        return _build_generic_source_context(root, max_chars)


def _build_generic_source_context(root: Path, max_chars: int = 12000) -> str:
    """通用源文本上下文（向后兼容，无 workflow 时使用）。"""
    entries = list_sources(root)
    if not entries:
        return "（无源文本素材）"

    parts = ["## 源文本素材", ""]
    per_file = max(2000, max_chars // max(1, len(entries)))
    for item in entries:
        rel = item.get("text", "")
        path = root / rel
        parts.append(f"### {item.get('title') or path.stem}")
        parts.append(f"- 工作流：{item.get('workflow', '')}")
        parts.append(f"- 格式：{item.get('format', '')}")
        parts.append(f"- 路径：{rel}")
        parts.append("")
        if not path.is_file():
            parts.append("（源文本文件不存在）")
            parts.append("")
            continue
        text = path.read_text(encoding="utf-8")
        if len(text) <= per_file:
            parts.append(text)
        else:
            head = per_file // 2
            tail = per_file - head
            parts.append(text[:head].rstrip())
            parts.append("\n...（中段省略，完整文本见上方路径）...\n")
            parts.append(text[-tail:].lstrip())
        parts.append("")
    return "\n".join(parts)

"""向量检索（RAG）的核心模块。

分两部分：
  1. 纯函数部分（chunker + 路径解析 + dataclass）—— 不依赖 zvec，可单测
  2. zvec 真实部分（collection lifecycle + index + search）—— 见下方 VectorStore

Chunker 规则：
  - 章节：先 strip `### 写作备注` 以下内容；按空行切段；每段 > CHUNK_MAX_CHARS
    时按句号切窗（CHUNK_OVERLAP 重叠）
  - 笔记：notes/summary.md 同上规则
  - 源文本：sources/*.md，先去 YAML front-matter（---...--- 之间的内容），
    再同上规则

数据落盘位置：<project_root>/.fictia/zvec/{chapters,notes,sources}/
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# 软导入 zvec —— 未装时整个模块仍可 import，只是 VectorStore 不可用
try:
    import zvec  # type: ignore
    _ZVEC = zvec
except ImportError:  # pragma: no cover
    _ZVEC = None

from lib.embeddings import EmbeddingProvider, get_provider


# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

VECTOR_ROOT_DIRNAME = ".fictia"
ZVEC_DIRNAME = "zvec"
COLLECTIONS = ("chapters", "notes", "sources", "design", "world", "outlines")

CHUNK_MAX_CHARS = 500
CHUNK_OVERLAP = 50

_WRITING_NOTES_MARKER = "### 写作备注"
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
_SENTENCE_END_RE = re.compile(r"(?<=[。！？!?])\s*")


# --------------------------------------------------------------------------- #
# 异常
# --------------------------------------------------------------------------- #


class VectorError(Exception):
    """vector 模块统一异常类型。"""


def require_zvec() -> None:
    """确保 zvec 可用；不可用时抛清晰错误。"""
    if _ZVEC is None:
        raise VectorError(
            "zvec 未安装。请运行 `pip install zvec` 后重试。"
            "（也可继续使用其他命令——只有 `vector` 子命令族依赖 zvec。）"
        )


def _doc_id(doc) -> str:
    """从 zvec Doc 对象或 dict 中提取 id。"""
    return doc.id if not isinstance(doc, dict) else doc.get("id", "")


# --------------------------------------------------------------------------- #
# Dataclass
# --------------------------------------------------------------------------- #


@dataclass
class Chunk:
    """一段可被嵌入并索引的文本块。

    text         实际用于嵌入的文本
    chunk_index  同一来源内的块序号（0-based）
    metadata     附加信息：chapter / path / note_id / source_slug / workflow 等
    """

    text: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)


@dataclass
class Hit:
    """一次检索命中。"""

    id: str
    collection: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #


def vector_root(project_root: Path) -> Path:
    """返回向量数据目录路径（不一定存在）。"""
    return project_root / VECTOR_ROOT_DIRNAME / ZVEC_DIRNAME


def resolve_project_root(explicit: Optional[str]) -> Path:
    """解析项目根目录。

    优先级：
      1. 显式参数 explicit（绝对或相对路径）
      2. 复用 lib.project.find_project_root()（向上查找 project.yaml）
    """
    if explicit:
        return Path(explicit).resolve()
    from lib.project import find_project_root

    found = find_project_root()
    if not found:
        raise VectorError(
            "未找到 project.yaml。请在项目目录内运行，或显式传入 --project <path>。"
        )
    return found


# --------------------------------------------------------------------------- #
# Chunker
# --------------------------------------------------------------------------- #


def strip_writing_notes(text: str) -> str:
    """从章节文本中剥离 `### 写作备注` 及之后的内容。"""
    idx = text.find(_WRITING_NOTES_MARKER)
    if idx == -1:
        return text
    return text[:idx].rstrip()


def strip_frontmatter(text: str) -> str:
    """剥离 YAML front-matter（开头两个 --- 之间的内容）。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text
    return text[m.end():]


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """把长段落按句号切窗。

    算法：
      1. 如果 text 长度 ≤ max_chars，原样返回
      2. 否则按句末标点（。！？!?）切句
      3. 滑动窗口拼句：累加直到超 max_chars，记录一个窗口
      4. 下个窗口从上一窗口倒数 overlap 字符开始（保持重叠）

    句号边界可能很稀疏（甚至没有）；如果某单句就 > max_chars 或找不到
    句号边界，强制按 max_chars 硬切（带 overlap）。
    """
    if len(text) <= max_chars:
        return [text]

    # 句末切分（保留标点）
    sentences = _SENTENCE_END_RE.split(text)
    sentences = [s for s in sentences if s]

    # 退化路径：未切出任何句末标点（整段无标点），强制硬切
    if len(sentences) <= 1:
        return _hard_split(text, max_chars, overlap)

    windows: list[str] = []
    buf = ""
    for s in sentences:
        if not buf:
            buf = s
        elif len(buf) + len(s) <= max_chars:
            buf = buf + s
        else:
            windows.append(buf)
            tail = buf[-overlap:] if overlap > 0 and len(buf) > overlap else ""
            buf = tail + s
            # 单句本身就超 max_chars —— 硬切
            while len(buf) > max_chars:
                windows.append(buf[:max_chars])
                buf = buf[max_chars - overlap :] if overlap > 0 else buf[max_chars:]

    if buf:
        windows.append(buf)
    return windows


def _hard_split(text: str, max_chars: int, overlap: int) -> list[str]:
    """无标点长段落的硬切：每 max_chars 一窗，保留 overlap。"""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + max_chars, n)
        out.append(text[i:end])
        if end >= n:
            break
        i = end - overlap if overlap > 0 else end
    return out


def _chunk_text(text: str) -> list[str]:
    """通用切段：按空行切段 + 长段切窗 + 过滤空白。"""
    paragraphs = _PARAGRAPH_SPLIT_RE.split(text)
    out: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        out.extend(_split_long(p, CHUNK_MAX_CHARS, CHUNK_OVERLAP))
    return [c for c in out if c.strip()]


def chunk_chapter(text: str, chapter: int, path: str) -> list[Chunk]:
    """章节文本 → Chunk 列表。

    处理：strip 写作备注 → 切段 → 长段切窗 → 包成 Chunk（带 chapter/path 元数据）。
    """
    cleaned = strip_writing_notes(text)
    pieces = _chunk_text(cleaned)
    return [
        Chunk(text=p, chunk_index=i, metadata={"chapter": chapter, "path": path})
        for i, p in enumerate(pieces)
    ]


def chunk_notes(text: str, note_id: str = "summary") -> list[Chunk]:
    """笔记文本 → Chunk 列表（带 note_id 元数据）。"""
    pieces = _chunk_text(text)
    return [
        Chunk(text=p, chunk_index=i, metadata={"note_id": note_id})
        for i, p in enumerate(pieces)
    ]


def chunk_source(text: str, slug: str, workflow: str = "") -> list[Chunk]:
    """源文本 → Chunk 列表（先去 YAML front-matter，带 source_slug 元数据）。"""
    cleaned = strip_frontmatter(text)
    pieces = _chunk_text(cleaned)
    return [
        Chunk(text=p, chunk_index=i, metadata={"source_slug": slug, "workflow": workflow})
        for i, p in enumerate(pieces)
    ]


# --------------------------------------------------------------------------- #
# 新增 chunk 策略：section / scene / table_row
# --------------------------------------------------------------------------- #


_SECTION_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)")


def chunk_by_section(text: str, metadata: dict, max_chars: int = CHUNK_MAX_CHARS) -> list[Chunk]:
    """按 ## / ### 标题切段，每段作为一个 chunk。

    heading 作为 chunk 前缀提供上下文；超长段落按句号切窗。
    用于：design files, world files。
    """
    # 先去 front-matter
    cleaned = strip_frontmatter(text)

    sections: list[tuple[str, str]] = []
    lines = cleaned.splitlines()
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        m = _SECTION_HEADING_RE.match(line)
        if m and len(m.group(1)) <= 3:  # # ~ ###
            if current_body:
                body_text = "\n".join(current_body).strip()
                if body_text:
                    sections.append((current_heading, body_text))
            current_heading = line.strip()
            current_body = []
        else:
            current_body.append(line)

    if current_body:
        body_text = "\n".join(current_body).strip()
        if body_text:
            sections.append((current_heading, body_text))

    chunks: list[Chunk] = []
    chunk_idx = 0
    for heading, body in sections:
        # heading 作为上下文前缀
        text_block = f"{heading}\n{body}" if heading else body
        pieces = _split_long(text_block, max_chars, CHUNK_OVERLAP)
        for piece in pieces:
            section_name = re.sub(r"^#{1,3}\s*", "", heading).strip() if heading else ""
            chunks.append(
                Chunk(
                    text=piece,
                    chunk_index=chunk_idx,
                    metadata={**metadata, "section": section_name},
                )
            )
            chunk_idx += 1

    return chunks


_SCENE_RE = re.compile(r"(?=^###\s|^\*\*场景\s*\d)", re.MULTILINE)


def chunk_by_scene(text: str, metadata: dict, max_chars: int = CHUNK_MAX_CHARS) -> list[Chunk]:
    """按场景切段（### 场景 N 或 **场景 N**）。

    先提取 ## 场景序列 下的内容，再按场景分割。
    用于：outline/chapters/*.md。
    """
    cleaned = strip_frontmatter(text)

    # 提取场景序列 section
    scene_section = re.search(
        r"^##\s*场景序列[^\n]*\n([\s\S]*?)(?=^##\s|\Z)",
        cleaned,
        re.MULTILINE,
    )
    if not scene_section:
        # 没找到场景序列，回退到 section 切分
        return chunk_by_section(text, metadata, max_chars)

    scene_body = scene_section.group(1)
    scenes = _SCENE_RE.split(scene_body)

    chunks: list[Chunk] = []
    chunk_idx = 0
    for i, scene in enumerate(scenes):
        scene = scene.strip()
        if not scene or len(scene) < 20:
            continue
        pieces = _split_long(scene, max_chars, CHUNK_OVERLAP)
        for piece in pieces:
            chunks.append(
                Chunk(
                    text=piece,
                    chunk_index=chunk_idx,
                    metadata={**metadata, "scene_index": i + 1},
                )
            )
            chunk_idx += 1

    # 如果场景序列为空，回退到 section 切分
    if not chunks:
        return chunk_by_section(text, metadata, max_chars)

    return chunks


_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")


def chunk_by_table_row(text: str, metadata: dict) -> list[Chunk]:
    """按表格行切段，每行带表头上下文。

    非表格部分按 section 切分。
    用于：art-design.md（逐章情感表）、timeline.md。
    """
    cleaned = strip_frontmatter(text)
    chunks: list[Chunk] = []
    chunk_idx = 0

    # 提取所有表格块
    table_blocks = re.findall(r"((?:^\|.*\|[ \t]*\n?)+)", cleaned, re.MULTILINE)
    table_positions: list[tuple[int, int]] = []

    for block in table_blocks:
        start = cleaned.find(block)
        end = start + len(block)
        table_positions.append((start, end))

        rows = [l.strip() for l in block.splitlines() if l.strip().startswith("|")]
        if len(rows) < 3:
            continue
        # 表头
        header = rows[0]
        header_cells = [c.strip() for c in header.split("|") if c.strip()]
        # 跳过分隔行（rows[1]），从 rows[2] 开始
        for row_line in rows[2:]:
            cells = [c.strip() for c in row_line.split("|") if c.strip()]
            if len(cells) < len(header_cells):
                continue
            # 构造带上下文的文本
            row_text = " | ".join(
                f"{h}: {c}" for h, c in zip(header_cells, cells)
            )
            chunks.append(
                Chunk(
                    text=row_text,
                    chunk_index=chunk_idx,
                    metadata={**metadata, "row_type": "table_row"},
                )
            )
            chunk_idx += 1

    # 非表格部分按 section 切分
    non_table_parts: list[str] = []
    last_end = 0
    for start, end in sorted(table_positions):
        between = cleaned[last_end:start].strip()
        if between:
            non_table_parts.append(between)
        last_end = end
    tail = cleaned[last_end:].strip()
    if tail:
        non_table_parts.append(tail)

    for part in non_table_parts:
        section_chunks = chunk_by_section(part, metadata)
        for c in section_chunks:
            c.chunk_index = chunk_idx
            chunk_idx += 1
            chunks.append(c)

    return chunks


# --------------------------------------------------------------------------- #
# 文本读 + 章节文件路径
# --------------------------------------------------------------------------- #


def chapter_file_path(project_root: Path, chapter: int) -> Optional[Path]:
    """根据 chapter 号推断正文文件路径。

    优先匹配 act-1/chNN.md / act-2/chNN.md / act-3/chNN.md。
    找不到返回 None。
    """
    for act in (1, 2, 3):
        p = project_root / "chapters" / f"act-{act}" / f"ch{chapter:02d}.md"
        if p.is_file():
            return p
    return None


def outline_file_path(project_root: Path, chapter: int) -> Path:
    """大纲文件路径（标准位置）。不一定存在。"""
    return project_root / "outline" / "chapters" / f"ch{chapter:02d}.md"


def notes_summary_path(project_root: Path) -> Path:
    """notes/summary.md 路径。不一定存在。"""
    return project_root / "notes" / "summary.md"


def sources_dir(project_root: Path) -> Path:
    """sources/ 目录。不一定存在。"""
    return project_root / "sources"


# --------------------------------------------------------------------------- #
# zvec 集成（懒加载 VectorStore）
# --------------------------------------------------------------------------- #


def _make_collection_schema(name: str, dim: int):
    """构造 zvec collection schema。

    每个 collection 都包含：
      - vec: 向量字段
      - text: 全文检索字段
      - 各 collection 特有的 metadata 字段（nullable）
    """
    require_zvec()
    # 通用字段
    fields = [
        _ZVEC.FieldSchema("text", _ZVEC.DataType.STRING,
                          index_param=_ZVEC.FtsIndexParam()),
    ]
    # collection 特有 metadata
    if name == "chapters":
        fields.append(_ZVEC.FieldSchema("chapter", _ZVEC.DataType.INT64))
        fields.append(_ZVEC.FieldSchema("path", _ZVEC.DataType.STRING))
    elif name == "notes":
        fields.append(_ZVEC.FieldSchema("note_id", _ZVEC.DataType.STRING))
    elif name == "sources":
        fields.append(_ZVEC.FieldSchema("source_slug", _ZVEC.DataType.STRING))
        fields.append(_ZVEC.FieldSchema("workflow", _ZVEC.DataType.STRING, nullable=True))
    elif name == "design":
        fields.append(_ZVEC.FieldSchema("source", _ZVEC.DataType.STRING))
        fields.append(_ZVEC.FieldSchema("file_stem", _ZVEC.DataType.STRING))
        fields.append(_ZVEC.FieldSchema("section", _ZVEC.DataType.STRING, nullable=True))
    elif name == "world":
        fields.append(_ZVEC.FieldSchema("source", _ZVEC.DataType.STRING))
        fields.append(_ZVEC.FieldSchema("file_stem", _ZVEC.DataType.STRING))
        fields.append(_ZVEC.FieldSchema("section", _ZVEC.DataType.STRING, nullable=True))
    elif name == "outlines":
        fields.append(_ZVEC.FieldSchema("chapter", _ZVEC.DataType.INT64))
        fields.append(_ZVEC.FieldSchema("source", _ZVEC.DataType.STRING))
        fields.append(_ZVEC.FieldSchema("scene_index", _ZVEC.DataType.INT64, nullable=True))

    return _ZVEC.CollectionSchema(
        name=name,
        fields=fields,
        vectors=_ZVEC.VectorSchema("vec", _ZVEC.DataType.VECTOR_FP32, dim),
    )


def open_store(project_root: Path, provider: EmbeddingProvider) -> "VectorStore":
    """打开（或创建）向量存储。

    三种 collection 自动确保存在。已存在的 collection 用 provider.dim 校验
    一致性（dim 不同则报错）。
    """
    require_zvec()
    base = vector_root(project_root)
    base.mkdir(parents=True, exist_ok=True)
    return VectorStore(base=base, provider=provider)


class VectorStore:
    """对一组 zvec collection 的封装。

    collection layout：
      <base>/chapters/     — 章节正文
      <base>/notes/        — 笔记摘要
      <base>/sources/      — 源文本
      <base>/design/       — 设计文件（genre-analysis, blueprint, style-guide, art-design, narrative-weave, characters）
      <base>/world/        — 世界观文件（setting, rules, timeline）
      <base>/outlines/     — 大纲文件（act-*.md, chapters/ch*.md）

    每个 collection 一旦以某种 dim 创建，后续必须用同 dim 的 provider 打开。
    """

    def __init__(self, base: Path, provider: EmbeddingProvider) -> None:
        self.base = base
        self.provider = provider
        self.dim = provider.dim
        self._cache: dict[str, "zvec.Collection"] = {}
        for name in COLLECTIONS:
            self._cache[name] = self._ensure(name)

    def close(self) -> None:
        """释放所有 collection 连接，解除文件锁。"""
        import gc
        # 逐个删除引用，让 C++ 析构函数释放文件锁
        keys = list(self._cache.keys())
        for k in keys:
            col = self._cache.pop(k)
            del col
        gc.collect()

    # ---- collection lifecycle ----

    def _ensure(self, name: str, read_only: bool = False):
        """懒创建/打开 collection。"""
        path = self.base / name
        if path.is_dir():
            opt = _ZVEC.CollectionOption(read_only=read_only)
            col = _ZVEC.open(path=str(path), option=opt)
        else:
            schema = _make_collection_schema(name, self.dim)
            col = _ZVEC.create_and_open(path=str(path), schema=schema)
        return col

    def _col(self, name: str):
        if name not in COLLECTIONS:
            raise VectorError(f"未知 collection: {name}；可选：{COLLECTIONS}")
        return self._cache[name]

    # ---- index ----

    def _embed_in_batches(self, texts: list[str], batch_size: int = 16) -> list[list[float]]:
        """分批嵌入，避免一次传入过多文本。"""
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            out.extend(self.provider.embed(batch))
        return out

    def _delete_ids_starting_with(self, name: str, prefix: str) -> int:
        """删除 collection 中 id 以 prefix 开头的所有条目。

        zvec API 通过 query+filter 实现：先查所有 id 以 prefix 开头的，
        再逐个删除。zvec 0.5 提供 delete_by_filter / delete(ids) 接口，
        这里用一种保守实现：query 出 id 列表后逐个删除。
        """
        col = self._col(name)
        # 防御性：先尝试用 query+filter 找到匹配 id
        try:
            hits = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
                filter=f'id LIKE "{prefix}%"',
            )
        except Exception:
            # 旧版 zvec 可能不支持 filter；改为全量扫描
            hits = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
            )
            hits = [h for h in hits if _doc_id(h).startswith(prefix)]

        deleted = 0
        for h in hits:
            try:
                col.delete([_doc_id(h)])
                deleted += 1
            except Exception:
                pass
        return deleted

    def index_chunks(self, name: str, chunks: list[Chunk], id_prefix: str = "") -> int:
        """把 Chunk 列表嵌入并 upsert 到指定 collection。

        id 格式：{id_prefix}{chunk_index:04d}
        """
        if not chunks:
            return 0
        col = self._col(name)
        texts = [c.text for c in chunks]
        vectors = self._embed_in_batches(texts)
        docs = []
        for c, v in zip(chunks, vectors):
            doc_id = f"{id_prefix}{c.chunk_index:04d}"
            docs.append(
                _ZVEC.Doc(
                    id=doc_id,
                    vectors={"vec": v},
                    fields={**c.metadata, "text": c.text},
                )
            )
        col.insert(docs)
        return len(docs)

    def index_chapter(self, chapter: int, force: bool = False) -> int:
        """索引指定章节正文。先按 chapter 号找文件。"""
        root_path = self.base.parent.parent  # .fictia/zvec → .fictia → project_root
        path = chapter_file_path(root_path, chapter)
        if not path:
            raise VectorError(f"章节 {chapter} 的正文文件不存在（chapters/act-X/ch{chapter:02d}.md）")
        text = path.read_text(encoding="utf-8")
        chunks = chunk_chapter(text, chapter=chapter, path=str(path.relative_to(root_path)))
        if force:
            self._delete_ids_starting_with("chapters", f"ch{chapter:02d}_")
        return self.index_chunks("chapters", chunks, id_prefix=f"ch{chapter:02d}_")

    def index_chapter_outline(self, chapter: int, force: bool = False) -> int:
        """索引指定章节的大纲（outline/chapters/chNN.md）。"""
        root_path = self.base.parent.parent
        path = outline_file_path(root_path, chapter)
        if not path.is_file():
            raise VectorError(f"章节 {chapter} 的大纲文件不存在：{path}")
        text = path.read_text(encoding="utf-8")
        chunks = chunk_chapter(text, chapter=chapter, path=str(path.relative_to(root_path)))
        if force:
            self._delete_ids_starting_with("chapters", f"outline{chapter:02d}_")
        return self.index_chunks("chapters", chunks, id_prefix=f"outline{chapter:02d}_")

    def index_notes(self, force: bool = False) -> int:
        """索引 notes/summary.md。"""
        root_path = self.base.parent.parent
        path = notes_summary_path(root_path)
        if not path.is_file():
            raise VectorError(f"笔记摘要文件不存在：{path}")
        text = path.read_text(encoding="utf-8")
        chunks = chunk_notes(text, note_id="summary")
        if force:
            self._delete_ids_starting_with("notes", "notes_")
        return self.index_chunks("notes", chunks, id_prefix="notes_")

    def index_sources(self, force: bool = False) -> int:
        """索引 sources/*.md（每个文件作为一个 source_slug）。"""
        root_path = self.base.parent.parent
        sdir = sources_dir(root_path)
        if not sdir.is_dir():
            return 0
        total = 0
        for f in sorted(sdir.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            slug = f.stem
            chunks = chunk_source(text, slug=slug)
            if force:
                self._delete_ids_starting_with("sources", f"sources_{slug}_")
            total += self.index_chunks("sources", chunks, id_prefix=f"sources_{slug}_")
        return total

    # ---- design / world / outlines ----

    def index_design_file(self, rel_path: str, force: bool = False) -> int:
        """索引单个设计文件到 design collection。"""
        root_path = self.base.parent.parent
        path = root_path / rel_path
        if not path.is_file():
            raise VectorError(f"设计文件不存在：{path}")
        text = path.read_text(encoding="utf-8")
        from pathlib import PurePosixPath
        stem = PurePosixPath(rel_path).stem
        chunks = chunk_by_section(text, metadata={"source": rel_path, "file_stem": stem})
        id_prefix = f"design_{stem}_"
        if force:
            self._delete_ids_starting_with("design", id_prefix)
        return self.index_chunks("design", chunks, id_prefix=id_prefix)

    def index_world_file(self, rel_path: str, force: bool = False) -> int:
        """索引单个世界观文件到 world collection。"""
        root_path = self.base.parent.parent
        path = root_path / rel_path
        if not path.is_file():
            raise VectorError(f"世界观文件不存在：{path}")
        text = path.read_text(encoding="utf-8")
        from pathlib import PurePosixPath
        stem = PurePosixPath(rel_path).stem
        chunks = chunk_by_section(text, metadata={"source": rel_path, "file_stem": stem})
        id_prefix = f"world_{stem}_"
        if force:
            self._delete_ids_starting_with("world", id_prefix)
        return self.index_chunks("world", chunks, id_prefix=id_prefix)

    def index_outline(self, chapter: int, force: bool = False) -> int:
        """索引指定章节大纲到 outlines collection。"""
        root_path = self.base.parent.parent
        path = outline_file_path(root_path, chapter)
        if not path.is_file():
            raise VectorError(f"大纲文件不存在：{path}")
        text = path.read_text(encoding="utf-8")
        chunks = chunk_by_scene(
            text,
            metadata={"chapter": chapter, "source": str(path.relative_to(root_path))},
        )
        id_prefix = f"outline_ch{chapter:02d}_"
        if force:
            self._delete_ids_starting_with("outlines", id_prefix)
        return self.index_chunks("outlines", chunks, id_prefix=id_prefix)

    def index_design_all(self, force: bool = False) -> int:
        """索引所有设计文件（通过 meta-index 发现）。"""
        from lib.meta_index import get_files_by_vector_collection, load_meta_index, discover_project_files

        root_path = self.base.parent.parent
        total = 0

        # 尝试从 meta-index 读取
        meta = load_meta_index(root_path)
        design_entries = []
        for section in ("design_files", "world_files", "character_files"):
            for entry_dict in meta.get(section, []):
                if entry_dict.get("vector_collection") == "design":
                    design_entries.append(entry_dict)

        # 如果 meta-index 为空，回退到 discover
        if not design_entries:
            from lib.meta_index import FileEntry
            all_files = discover_project_files(root_path)
            design_entries = [e.to_dict() for e in all_files if e.vector_collection == "design"]

        for entry in design_entries:
            rel_path = entry.get("path", "")
            if not rel_path:
                continue
            # 处理 glob 模式
            if entry.get("glob"):
                for f in sorted(root_path.glob(rel_path)):
                    try:
                        total += self.index_design_file(
                            str(f.relative_to(root_path)).replace("\\", "/"), force=force
                        )
                    except VectorError as e:
                        import sys
                        sys.stderr.write(f"⚠ {rel_path}: {e}\n")
            else:
                try:
                    total += self.index_design_file(rel_path, force=force)
                except VectorError as e:
                    import sys
                    sys.stderr.write(f"⚠ {rel_path}: {e}\n")
        return total

    def index_world_all(self, force: bool = False) -> int:
        """索引所有世界观文件。"""
        from lib.meta_index import load_meta_index, discover_project_files

        root_path = self.base.parent.parent
        total = 0

        meta = load_meta_index(root_path)
        world_entries = []
        for entry_dict in meta.get("world_files", []):
            if entry_dict.get("vector_collection") == "world":
                world_entries.append(entry_dict)

        if not world_entries:
            all_files = discover_project_files(root_path)
            world_entries = [e.to_dict() for e in all_files if e.vector_collection == "world"]

        for entry in world_entries:
            rel_path = entry.get("path", "")
            if not rel_path:
                continue
            try:
                total += self.index_world_file(rel_path, force=force)
            except VectorError as e:
                import sys
                sys.stderr.write(f"⚠ {rel_path}: {e}\n")
        return total

    def index_outlines_all(self, force: bool = False) -> int:
        """索引所有大纲文件。"""
        root_path = self.base.parent.parent
        total = 0

        # 幕级大纲
        for f in sorted((root_path / "outline").glob("act-*.md")):
            rel = str(f.relative_to(root_path)).replace("\\", "/")
            stem = f.stem
            text = f.read_text(encoding="utf-8")
            chunks = chunk_by_section(text, metadata={"source": rel, "file_stem": stem})
            id_prefix = f"outline_{stem}_"
            if force:
                self._delete_ids_starting_with("outlines", id_prefix)
            total += self.index_chunks("outlines", chunks, id_prefix=id_prefix)

        # 章节大纲
        outline_dir = root_path / "outline" / "chapters"
        if outline_dir.is_dir():
            import re as _re
            for f in sorted(outline_dir.glob("ch*.md")):
                m = _re.match(r"ch(\d+)\.md", f.name)
                if m:
                    ch = int(m.group(1))
                    try:
                        total += self.index_outline(ch, force=force)
                    except VectorError as e:
                        import sys
                        sys.stderr.write(f"⚠ outline ch{ch}: {e}\n")
        return total

    # ---- search ----

    def search(
        self,
        query: str,
        top_k: int = 8,
        collection: Optional[str] = None,
    ) -> list[Hit]:
        """跨（指定）collection 语义检索。"""
        require_zvec()
        if collection and collection not in COLLECTIONS:
            raise VectorError(f"未知 collection: {collection}；可选：{COLLECTIONS}")
        targets = [collection] if collection else list(COLLECTIONS)
        vec = self.provider.embed([query])[0]
        hits: list[Hit] = []
        for name in targets:
            try:
                col = self._col(name)
            except VectorError:
                continue
            try:
                results = col.query(_ZVEC.VectorQuery("vec", vector=vec), topk=top_k)
            except Exception as e:
                raise VectorError(f"zvec query failed on {name}: {e}") from e
            for r in results:
                # zvec 0.5 returns Doc objects; older versions may return dicts
                if isinstance(r, dict):
                    rid = r.get("id", "")
                    rtext = r.get("text", "")
                    rscore = float(r.get("score", 0.0))
                    rmeta = {k: v for k, v in r.items() if k not in ("id", "score", "text", "vec")}
                else:
                    rid = r.id
                    rtext = r.fields.get("text", "") if r.fields else ""
                    rscore = float(r.score) if r.score is not None else 0.0
                    rmeta = {k: v for k, v in (r.fields or {}).items() if k != "text"}
                hits.append(
                    Hit(
                        id=rid,
                        collection=name,
                        text=rtext,
                        score=rscore,
                        metadata=rmeta,
                    )
                )
        # 跨 collection 时按 score 降序截断
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    # ---- status / clear ----

    def status(self) -> dict:
        """各 collection 的 chunk 数量 + 当前 embedding model / dim。"""
        out: dict = {
            "embedding_model": getattr(self.provider, "name", "unknown"),
            "vector_dim": self.dim,
            "collections": {},
        }
        for name in COLLECTIONS:
            path = self.base / name
            count = 0
            if path.is_dir():
                try:
                    col = self._col(name)
                    # 估算 chunk 数：用 query topk=1 触发 collection 检查；
                    # 真正数量需要全量 scan，这里通过文件大小粗估
                    # 更精确的实现需 zvec 提供 count() 接口
                    count = self._approx_count(name)
                except Exception:
                    count = 0
            out["collections"][name] = count
        out["total_chunks"] = sum(out["collections"].values())
        return out

    def _approx_count(self, name: str) -> int:
        """粗估 collection 中的 doc 数量。

        zvec 0.5 没有暴露 count() 接口；通过 query topk=10000 扫描。
        如果 collection 真实 > 10000，会被低估。
        """
        try:
            col = self._col(name)
            results = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
            )
            return len(results)
        except Exception:
            return 0

    def clear(self, collection: Optional[str] = None) -> list[str]:
        """清空指定（或全部）collection。返回被清空的 collection 名列表。"""
        targets = [collection] if collection else list(COLLECTIONS)
        cleared: list[str] = []
        for name in targets:
            if name not in COLLECTIONS:
                raise VectorError(f"未知 collection: {name}")
            try:
                col = self._col(name)
                # 删所有 doc：query topk=10000 取 id，批量 delete
                results = col.query(
                    _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                    topk=10000,
                )
                if results:
                    col.delete([r["id"] for r in results])
                cleared.append(name)
            except Exception as e:
                raise VectorError(f"清空 {name} 失败：{e}") from e
        return cleared


# --------------------------------------------------------------------------- #
# Convenience: 单例构造
# --------------------------------------------------------------------------- #

_STORE_CACHE: dict[str, VectorStore] = {}


def open_store_with_default_provider(project_root: Path, mode: Optional[str] = None) -> VectorStore:
    """用 get_provider() 默认 provider 打开 VectorStore（同进程缓存，避免重复加锁）。"""
    cache_key = str(project_root.resolve())
    if cache_key in _STORE_CACHE:
        return _STORE_CACHE[cache_key]
    provider = get_provider(mode)
    store = open_store(project_root, provider)
    _STORE_CACHE[cache_key] = store
    return store


def close_all_stores() -> None:
    """释放所有缓存的 VectorStore（用于测试清理 / 临时目录场景）。"""
    import gc
    for store in _STORE_CACHE.values():
        store.close()
    _STORE_CACHE.clear()
    gc.collect()
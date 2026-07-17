"""Meta Index — 产出文件注册表管理。

在项目根目录维护 meta-index.yaml，声明所有 agent 产出文件的元数据。
用途：向量索引发现、实体提取路由、增量更新检测。

不依赖 zvec，可独立使用。

支持两种文件来源：
  1. 项目产出文件（project root 内）
  2. 技能级参考文件（references/writing-craft/ + references/genre-cards/）
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #


@dataclass
class FileEntry:
    """meta-index.yaml 中的一个文件条目。"""

    path: str
    stage: str
    stage_num: int
    type: str  # design | world | character | outline_act | outline_chapter | chapter | review
    indexable: bool
    chunk_strategy: str  # section | paragraph | scene | table_row
    entity_collections: list[str] = field(default_factory=list)
    vector_collection: Optional[str] = None  # design | world | outlines | chapters | notes | sources
    glob: bool = False
    depends_on: list[str] = field(default_factory=list)
    version: int = 1
    content_hash: str = ""
    # 角色文件特有
    character_name: str = ""
    character_role: str = ""

    def to_dict(self) -> dict:
        d = {
            "path": self.path,
            "stage": self.stage,
            "stage_num": self.stage_num,
            "type": self.type,
            "indexable": self.indexable,
            "chunk_strategy": self.chunk_strategy,
            "version": self.version,
            "content_hash": self.content_hash,
        }
        if self.entity_collections:
            d["entity_collections"] = self.entity_collections
        if self.vector_collection:
            d["vector_collection"] = self.vector_collection
        if self.glob:
            d["glob"] = True
        if self.depends_on:
            d["depends_on"] = self.depends_on
        if self.character_name:
            d["character_name"] = self.character_name
        if self.character_role:
            d["character_role"] = self.character_role
        return d

    @staticmethod
    def from_dict(d: dict) -> "FileEntry":
        return FileEntry(
            path=d.get("path", ""),
            stage=d.get("stage", ""),
            stage_num=d.get("stage_num", 0),
            type=d.get("type", ""),
            indexable=d.get("indexable", False),
            chunk_strategy=d.get("chunk_strategy", "section"),
            entity_collections=d.get("entity_collections", []),
            vector_collection=d.get("vector_collection"),
            glob=d.get("glob", False),
            depends_on=d.get("depends_on", []),
            version=d.get("version", 1),
            content_hash=d.get("content_hash", ""),
            character_name=d.get("character_name", ""),
            character_role=d.get("character_role", ""),
        )


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #


def compute_content_hash(path: Path) -> str:
    """计算文件内容的 SHA-256 前 16 位。"""
    if not path.is_file():
        return ""
    h = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return f"sha256:{h}"


def _rel(path: Path, root: Path) -> str:
    """返回相对于 root 的 POSIX 路径。"""
    return str(path.relative_to(root)).replace("\\", "/")


# --------------------------------------------------------------------------- #
# 文件发现
# --------------------------------------------------------------------------- #

# 静态文件映射：(相对路径, stage, stage_num, type, entity_collections, vector_collection, chunk_strategy)
_STATIC_FILES: list[tuple[str, str, int, str, list[str], str, str]] = [
    ("genre-analysis.md", "genre_analysis", 1, "design", [], "design", "section"),
    ("blueprint.md", "architecture", 2, "design", [], "design", "section"),
    ("style-guide.md", "style", 3, "design", [], "design", "section"),
    ("art-design.md", "art_design", 4, "design", [], "design", "table_row"),
    (
        "narrative-weave.md",
        "narrative_weave",
        5,
        "design",
        ["foreshadowing", "easter_eggs", "storylines"],
        "design",
        "section",
    ),
    ("world/setting.md", "world", 6, "world", ["locations"], "world", "section"),
    ("world/rules.md", "world", 6, "world", ["items"], "world", "section"),
    ("world/timeline.md", "world", 6, "world", ["timeline"], "world", "table_row"),
]


def discover_project_files(root: Path) -> list[FileEntry]:
    """扫描项目目录，发现所有产出文件并生成 FileEntry 列表。"""
    entries: list[FileEntry] = []

    # ── 静态文件 ──
    for rel_path, stage, num, ftype, colls, vcol, strategy in _STATIC_FILES:
        p = root / rel_path
        if p.is_file():
            entries.append(
                FileEntry(
                    path=rel_path,
                    stage=stage,
                    stage_num=num,
                    type=ftype,
                    indexable=True,
                    chunk_strategy=strategy,
                    entity_collections=list(colls),
                    vector_collection=vcol,
                    content_hash=compute_content_hash(p),
                )
            )

    # ── 角色文件 ──
    for name in ("protagonist.md", "antagonist.md"):
        p = root / "characters" / name
        if p.is_file():
            entries.append(
                FileEntry(
                    path=f"characters/{name}",
                    stage="characters",
                    stage_num=7,
                    type="character",
                    indexable=True,
                    chunk_strategy="section",
                    entity_collections=["characters"],
                    vector_collection="design",
                    character_role=name.replace(".md", ""),
                    content_hash=compute_content_hash(p),
                )
            )

    supporting = root / "characters" / "supporting"
    if supporting.is_dir():
        for f in sorted(supporting.glob("*.md")):
            entries.append(
                FileEntry(
                    path=_rel(f, root),
                    stage="characters",
                    stage_num=7,
                    type="character",
                    indexable=True,
                    chunk_strategy="section",
                    entity_collections=["characters"],
                    vector_collection="design",
                    character_role="supporting",
                    content_hash=compute_content_hash(f),
                )
            )

    # ── 大纲文件 ──
    for f in sorted((root / "outline").glob("act-*.md")):
        entries.append(
            FileEntry(
                path=_rel(f, root),
                stage="story",
                stage_num=8,
                type="outline_act",
                indexable=True,
                chunk_strategy="section",
                entity_collections=[],
                vector_collection="outlines",
                content_hash=compute_content_hash(f),
            )
        )

    outline_ch_dir = root / "outline" / "chapters"
    if outline_ch_dir.is_dir():
        for f in sorted(outline_ch_dir.glob("ch*.md")):
            entries.append(
                FileEntry(
                    path=_rel(f, root),
                    stage="story",
                    stage_num=8,
                    type="outline_chapter",
                    indexable=True,
                    chunk_strategy="scene",
                    entity_collections=["events"],
                    vector_collection="outlines",
                    content_hash=compute_content_hash(f),
                )
            )

    # ── 章节文件 ──
    chapters_dir = root / "chapters"
    if chapters_dir.is_dir():
        for act_dir in sorted(chapters_dir.glob("act-*")):
            for f in sorted(act_dir.glob("ch*.md")):
                entries.append(
                    FileEntry(
                        path=_rel(f, root),
                        stage="chapters",
                        stage_num=9,
                        type="chapter",
                        indexable=True,
                        chunk_strategy="paragraph",
                        entity_collections=[],
                        vector_collection="chapters",
                        content_hash=compute_content_hash(f),
                    )
                )

    # ── 审核文件 ──
    reviews_dir = root / "reviews"
    if reviews_dir.is_dir():
        for f in sorted(reviews_dir.glob("ch*-review.md")):
            entries.append(
                FileEntry(
                    path=_rel(f, root),
                    stage="editor",
                    stage_num=10,
                    type="review",
                    indexable=False,
                    chunk_strategy="section",
                    entity_collections=[],
                    vector_collection=None,
                    content_hash=compute_content_hash(f),
                )
            )
        cr = reviews_dir / "consistency-report.md"
        if cr.is_file():
            entries.append(
                FileEntry(
                    path=_rel(cr, root),
                    stage="consistency",
                    stage_num=11,
                    type="review",
                    indexable=False,
                    chunk_strategy="section",
                    entity_collections=[],
                    vector_collection=None,
                    content_hash=compute_content_hash(cr),
                )
            )

    # ── 笔记文件 ──
    notes_summary = root / "notes" / "summary.md"
    if notes_summary.is_file():
        entries.append(
            FileEntry(
                path="notes/summary.md",
                stage="notes",
                stage_num=0,
                type="notes",
                indexable=True,
                chunk_strategy="paragraph",
                entity_collections=[],
                vector_collection="notes",
                content_hash=compute_content_hash(notes_summary),
            )
        )

    # ── 源文本 ──
    sources_dir = root / "sources"
    if sources_dir.is_dir():
        for f in sorted(sources_dir.glob("*.md")):
            entries.append(
                FileEntry(
                    path=_rel(f, root),
                    stage="source",
                    stage_num=0,
                    type="source",
                    indexable=True,
                    chunk_strategy="paragraph",
                    entity_collections=[],
                    vector_collection="sources",
                    content_hash=compute_content_hash(f),
                )
            )

    return entries


# --------------------------------------------------------------------------- #
# 按类型分组
# --------------------------------------------------------------------------- #

_SECTION_MAP = {
    "design": "design_files",
    "world": "world_files",
    "character": "character_files",
    "outline_act": "outline_files",
    "outline_chapter": "outline_files",
    "chapter": "chapter_files",
    "review": "review_files",
    "notes": "auxiliary_files",
    "source": "auxiliary_files",
}


def group_entries(entries: list[FileEntry]) -> dict[str, list[dict]]:
    """按 type 分组，返回 meta-index.yaml 的 sections 结构。"""
    groups: dict[str, list[dict]] = {}
    for e in entries:
        section = _SECTION_MAP.get(e.type, "other")
        groups.setdefault(section, []).append(e.to_dict())
    return groups


# --------------------------------------------------------------------------- #
# YAML 序列化（最小化实现，避免依赖 PyYAML）
# --------------------------------------------------------------------------- #


def _yaml_quote(s: str) -> str:
    """YAML 字符串引号。"""
    if not s:
        return '""'
    # 纯数字或布尔值需要引号
    if s.isdigit() or s.lower() in ("true", "false", "null", "yes", "no"):
        return f'"{s}"'
    # 含特殊字符需要引号
    special = set(':{}[],"\'&*?|->!%@`#\n')
    if any(c in special for c in s) or s.startswith(" ") or s.endswith(" "):
        return f'"{s}"'
    return s


def _dump_yaml_value(v, indent: int = 0) -> str:
    """递归序列化一个值为 YAML。"""
    prefix = "  " * indent
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(v)
    if v is None:
        return "null"
    if isinstance(v, str):
        return _yaml_quote(v)
    if isinstance(v, list):
        if not v:
            return "[]"
        lines = []
        for item in v:
            if isinstance(item, dict):
                # 列表中的 dict：第一个键在 - 后面，其余缩进
                keys = list(item.items())
                first_k, first_v = keys[0]
                lines.append(f"{prefix}- {_yaml_quote(first_k)}: {_dump_yaml_value(first_v)}")
                for k, val in keys[1:]:
                    lines.append(f"{prefix}  {_yaml_quote(k)}: {_dump_yaml_value(val)}")
            else:
                lines.append(f"{prefix}- {_dump_yaml_value(item)}")
        return "\n".join(lines)
    if isinstance(v, dict):
        if not v:
            return "{}"
        lines = []
        for k, val in v.items():
            lines.append(f"{prefix}{_yaml_quote(k)}: {_dump_yaml_value(val, indent + 1)}")
        return "\n".join(lines)
    return str(v)


def dump_meta_index_yaml(data: dict) -> str:
    """将 meta-index 数据序列化为 YAML 字符串。"""
    lines = [
        "# meta-index.yaml — Fictia 产出文件注册表",
        "# 由 `fictia meta sync` 自动生成，也可手动编辑",
        "# 用途：向量索引发现、实体提取路由、增量更新检测",
        "",
        f"version: {data.get('version', 2)}",
        f'last_sync: "{data.get("last_sync", "")}"',
        "",
    ]

    section_order = [
        ("design_files", "设计文件（stage 1-5 产出）"),
        ("world_files", "世界观文件（stage 6 产出）"),
        ("character_files", "角色文件（stage 7 产出）"),
        ("outline_files", "大纲文件（stage 8 产出）"),
        ("chapter_files", "章节文件（stage 9 产出）"),
        ("review_files", "审核文件（stage 10-11 产出）"),
        ("auxiliary_files", "辅助文件（笔记、源文本）"),
    ]

    for section_key, comment in section_order:
        items = data.get(section_key, [])
        lines.append(f"# {'─' * 45}")
        lines.append(f"# {comment}")
        lines.append(f"# {'─' * 45}")
        lines.append(f"{section_key}:")
        if not items:
            lines.append("  []")
        else:
            # 用 _dump_yaml_value 处理整个列表（它会正确生成 "- key: value" 格式）
            list_yaml = _dump_yaml_value(items, indent=1)
            lines.append(list_yaml)
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# YAML 反序列化（最小化实现）
# --------------------------------------------------------------------------- #


def _parse_yaml_scalar(s: str):
    """解析 YAML 标量值。"""
    s = s.strip()
    if s in ("null", "~", ""):
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    # 去引号
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        return s[1:-1]
    # 整数
    try:
        return int(s)
    except ValueError:
        pass
    # 浮点
    try:
        return float(s)
    except ValueError:
        pass
    return s


def load_meta_index_yaml(text: str) -> dict:
    """最小化 YAML 解析器，只处理 meta-index 的固定结构。

    策略：按行解析，利用已知的 section 结构。
    """
    data: dict = {"version": 2, "last_sync": ""}
    lines = text.splitlines()

    # 提取顶层 version 和 last_sync（只匹配无缩进的行）
    for line in lines:
        if line.startswith(" ") or line.startswith("\t"):
            continue  # 跳过缩进行（属于 section 内部）
        stripped = line.strip()
        if stripped.startswith("version:"):
            val = stripped.split(":", 1)[1].strip()
            try:
                data["version"] = int(val)
            except ValueError:
                pass
        elif stripped.startswith("last_sync:"):
            val = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            data["last_sync"] = val

    # 按 section 切分
    section_keys = (
        "design_files", "world_files", "character_files",
        "outline_files", "chapter_files", "review_files", "auxiliary_files",
    )

    current_section = None
    section_lines: dict[str, list[str]] = {k: [] for k in section_keys}

    for line in lines:
        stripped = line.strip()
        # 检查是否是 section 开头
        matched = False
        for key in section_keys:
            if stripped == f"{key}:" or stripped.startswith(f"{key}:"):
                current_section = key
                matched = True
                # 如果同一行有值（如 "key: []"）
                after = stripped[len(key) + 1:].strip()
                if after and after != "[]":
                    section_lines[key].append(after)
                break
        if not matched and current_section:
            if stripped and not stripped.startswith("#"):
                section_lines[current_section].append(line)

    # 解析每个 section 的条目
    for key in section_keys:
        data[key] = _parse_file_entries(section_lines[key])

    return data


def _parse_file_entries(lines: list[str]) -> list[dict]:
    """解析 YAML 列表中的 dict 条目（缩进格式）。"""
    entries: list[dict] = []
    current: dict | None = None

    for line in lines:
        # 去掉前导空白用于检测缩进
        stripped = line.strip()
        if not stripped or stripped == "[]":
            continue

        # 检测列表项标记 "- key: value"
        m = re.match(r"^\s*-\s+(\w[\w_]*)\s*:\s*(.*)", line)
        if m:
            # 新条目
            if current is not None:
                entries.append(current)
            current = {}
            key = m.group(1)
            val = m.group(2).strip()
            current[key] = _parse_yaml_scalar(val)
            continue

        # 续行 "  key: value"（属于当前条目）
        m2 = re.match(r"^\s+(\w[\w_]*)\s*:\s*(.*)", line)
        if m2 and current is not None:
            key = m2.group(1)
            val = m2.group(2).strip()
            # 检查是否是列表值（简化处理：逗号分隔）
            if val.startswith("[") and val.endswith("]"):
                # 内联列表
                inner = val[1:-1].strip()
                if not inner:
                    current[key] = []
                else:
                    current[key] = [
                        _parse_yaml_scalar(x.strip())
                        for x in inner.split(",")
                    ]
            else:
                current[key] = _parse_yaml_scalar(val)
            continue

    if current is not None:
        entries.append(current)

    return entries


# --------------------------------------------------------------------------- #
# 文件 I/O
# --------------------------------------------------------------------------- #

META_INDEX_FILENAME = "meta-index.yaml"


def meta_index_path(root: Path) -> Path:
    """返回 meta-index.yaml 的路径。"""
    return root / META_INDEX_FILENAME


def load_meta_index(root: Path) -> dict:
    """加载 meta-index.yaml。不存在则返回空结构。"""
    path = meta_index_path(root)
    if not path.is_file():
        return {
            "version": 2,
            "last_sync": "",
            "design_files": [],
            "world_files": [],
            "character_files": [],
            "outline_files": [],
            "chapter_files": [],
            "review_files": [],
            "auxiliary_files": [],
        }
    text = path.read_text(encoding="utf-8")
    return load_meta_index_yaml(text)


def save_meta_index(root: Path, data: dict) -> None:
    """保存 meta-index.yaml。"""
    path = meta_index_path(root)
    text = dump_meta_index_yaml(data)
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# 同步逻辑
# --------------------------------------------------------------------------- #


def _entries_to_map(data: dict) -> dict[str, dict]:
    """把 meta-index 数据展平为 {path: entry_dict} 映射。"""
    result: dict[str, dict] = {}
    for section in (
        "design_files", "world_files", "character_files",
        "outline_files", "chapter_files", "review_files", "auxiliary_files",
    ):
        for entry in data.get(section, []):
            p = entry.get("path", "")
            if p:
                result[p] = entry
    return result


def sync_meta_index(root: Path) -> dict:
    """同步 meta-index.yaml：发现新文件、更新 hash、递增 version。

    返回：
        {
            "added": [新发现的文件路径],
            "updated": [内容变化的文件路径],
            "removed": [不再存在的文件路径],
            "unchanged": int,
        }
    """
    # 加载现有
    existing = load_meta_index(root)
    old_map = _entries_to_map(existing)

    # 重新发现
    new_entries = discover_project_files(root)
    new_map: dict[str, dict] = {}
    for e in new_entries:
        new_map[e.path] = e.to_dict()

    added = []
    updated = []
    removed = []
    unchanged = 0

    # 对比
    for path, new_entry in new_map.items():
        if path not in old_map:
            added.append(path)
        elif new_entry["content_hash"] != old_map[path].get("content_hash"):
            updated.append(path)
            # 保留旧 version 并递增
            new_entry["version"] = old_map[path].get("version", 0) + 1
        else:
            # 保持旧数据（包括 version）
            new_map[path] = old_map[path]
            unchanged += 1

    for path in old_map:
        if path not in new_map:
            removed.append(path)

    # 重建 data
    from datetime import datetime, timezone

    result_data: dict = {
        "version": 2,
        "last_sync": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # 按 section 重新分组
    for section in (
        "design_files", "world_files", "character_files",
        "outline_files", "chapter_files", "review_files", "auxiliary_files",
    ):
        result_data[section] = []

    for path, entry in new_map.items():
        ftype = entry.get("type", "")
        section = _SECTION_MAP.get(ftype, "other")
        result_data.setdefault(section, []).append(entry)

    save_meta_index(root, result_data)

    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "unchanged": unchanged,
    }


def init_meta_index(root: Path) -> dict:
    """首次生成 meta-index.yaml（强制重建）。"""
    entries = discover_project_files(root)

    from datetime import datetime, timezone

    data: dict = {
        "version": 2,
        "last_sync": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    for section in (
        "design_files", "world_files", "character_files",
        "outline_files", "chapter_files", "review_files", "auxiliary_files",
    ):
        data[section] = []

    for e in entries:
        section = _SECTION_MAP.get(e.type, "other")
        data.setdefault(section, []).append(e.to_dict())

    save_meta_index(root, data)

    return {
        "total": len(entries),
        "indexable": sum(1 for e in entries if e.indexable),
        "path": str(meta_index_path(root)),
    }


# --------------------------------------------------------------------------- #
# 查询工具
# --------------------------------------------------------------------------- #


def get_indexable_files(root: Path) -> list[FileEntry]:
    """返回所有 indexable=true 的文件条目。"""
    data = load_meta_index(root)
    result: list[FileEntry] = []
    for section in (
        "design_files", "world_files", "character_files",
        "outline_files", "chapter_files", "auxiliary_files",
    ):
        for entry_dict in data.get(section, []):
            entry = FileEntry.from_dict(entry_dict)
            if entry.indexable:
                result.append(entry)
    return result


def get_stale_files(root: Path) -> list[FileEntry]:
    """返回内容已变化但 version 未更新的文件（hash 不匹配）。"""
    data = load_meta_index(root)
    stale: list[FileEntry] = []
    for section in (
        "design_files", "world_files", "character_files",
        "outline_files", "chapter_files", "auxiliary_files",
    ):
        for entry_dict in data.get(section, []):
            entry = FileEntry.from_dict(entry_dict)
            if not entry.indexable:
                continue
            p = root / entry.path
            current_hash = compute_content_hash(p)
            if current_hash and current_hash != entry.content_hash:
                stale.append(entry)
    return stale


def get_files_by_vector_collection(root: Path, collection: str) -> list[FileEntry]:
    """返回指定 vector collection 的所有文件条目。"""
    data = load_meta_index(root)
    result: list[FileEntry] = []
    for section in (
        "design_files", "world_files", "character_files",
        "outline_files", "chapter_files", "auxiliary_files",
    ):
        for entry_dict in data.get(section, []):
            entry = FileEntry.from_dict(entry_dict)
            if entry.vector_collection == collection:
                result.append(entry)
    return result

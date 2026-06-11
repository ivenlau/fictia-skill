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


def build_source_context(root: Path, max_chars: int = 12000) -> str:
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

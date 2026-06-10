"""
小说导出器：把 chapters/ 拼成单一 md 或 txt 文件。
"""

from __future__ import annotations
import re
from pathlib import Path
from . import project as P
from .words import WRITING_NOTES_RE


def _gather_chapters(root: Path) -> list[Path]:
    """Glob chapters/act-*/ch*.md，按文件名排序。"""
    ch_dir = root / "chapters"
    if not ch_dir.is_dir():
        return []
    files = list(ch_dir.rglob("ch*.md"))
    # 按文件名字符串排序（ch01, ch02, ... ch50 自然有序）
    files.sort(key=lambda p: p.name)
    return files


def _clean_chapter_text(text: str) -> str:
    """剥离 `### 写作备注` 及其后所有内容；移除前导 `---` 分隔符。"""
    m = WRITING_NOTES_RE.search(text)
    if m:
        text = text[: m.start()]
    # 移除末尾的 ---
    text = re.sub(r"\n-{3,}\s*\Z", "", text)
    return text.strip()


def _strip_markdown(text: str) -> str:
    """去除基础 markdown 符号（#、*、_、`、链接等）用于 txt 导出。"""
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    return text


def export(root: Path, fmt: str) -> Path:
    """导出小说。fmt = 'md' | 'txt'。返回输出路径。"""
    data = P.load_project(root)
    name = data.get("name", "novel")
    author = data.get("author", "")
    files = _gather_chapters(root)
    if not files:
        raise FileNotFoundError("没有可导出的章节文件")

    out_dir = root
    if fmt == "md":
        out_path = out_dir / f"{name}.md"
        header = f"# {name}\n"
        if author:
            header += f"\n作者：{author}\n"
        header += "\n---\n"
        body = "\n\n---\n\n".join(_clean_chapter_text(f.read_text(encoding="utf-8")) for f in files)
        out_path.write_text(header + body + "\n", encoding="utf-8")
    elif fmt == "txt":
        out_path = out_dir / f"{name}.txt"
        title_line = name
        underline = "=" * len(title_line)
        header = f"{title_line}\n{underline}\n"
        body = "\n\n".join(_strip_markdown(_clean_chapter_text(f.read_text(encoding="utf-8"))) for f in files)
        out_path.write_text(header + body + "\n", encoding="utf-8")
    else:
        raise ValueError(f"unsupported format: {fmt}")

    return out_path

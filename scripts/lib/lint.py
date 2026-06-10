"""
项目结构 lint：检查 project.yaml schema、产出文件存在性、YAML front-matter、写作备注等。
"""

from __future__ import annotations
import re
from pathlib import Path
from . import project as P
from .yaml_subset import load as yaml_load


FRONTMATTER_RE = re.compile(r"^---\s*$", re.MULTILINE)
WRITING_NOTES_RE = re.compile(r"^#{1,6}\s*写作备注\s*$", re.MULTILINE)


def _has_frontmatter(text: str) -> bool:
    """判断文件是否以 YAML front-matter 开头。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    # 找到第二个 ---
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return True
    return False


def _has_writing_notes(text: str) -> bool:
    return bool(WRITING_NOTES_RE.search(text))


def _has_weave_notes(text: str) -> bool:
    """outline/chapters/chXX.md 应有 weave_notes 字段。"""
    return bool(re.search(r"^weave_notes\s*:", text, re.MULTILINE))


def lint_project(root: Path) -> list[dict]:
    """返回检查问题列表。每项 = {level, code, message, path}。"""
    issues: list[dict] = []
    yaml_path = root / "project.yaml"
    if not yaml_path.is_file():
        issues.append({"level": "error", "code": "yaml-missing", "message": "project.yaml 不存在", "path": str(yaml_path)})
        return issues

    # yaml 解析
    try:
        data = P.load_project(root)
    except Exception as e:
        issues.append({"level": "error", "code": "yaml-invalid", "message": f"project.yaml 解析失败: {e}", "path": str(yaml_path)})
        return issues

    # 必填字段
    for k in ["name", "author", "genre", "target_words", "target_volumes", "chapter_target_words"]:
        if not data.get(k):
            issues.append({"level": "warning", "code": "field-missing", "message": f"缺少字段: {k}", "path": "project.yaml"})

    # 阶段产出文件存在性
    for _, key, name in P.STAGES:
        outputs = P.STAGE_OUTPUTS.get(key, [])
        for rel in outputs:
            if rel.endswith(".gitkeep"):
                continue
            p = root / rel
            if not p.exists():
                issues.append({
                    "level": "info",
                    "code": "output-missing",
                    "message": f"{name} 产出文件不存在: {rel}",
                    "path": rel,
                })

    # 角色文件 front-matter
    chars_dir = root / "characters"
    if chars_dir.is_dir():
        for md in chars_dir.rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            if not _has_frontmatter(text):
                issues.append({
                    "level": "warning",
                    "code": "frontmatter-missing",
                    "message": "角色文件缺少 YAML front-matter",
                    "path": str(md.relative_to(root)),
                })

    # 章节文件 写作备注
    ch_dir = root / "chapters"
    if ch_dir.is_dir():
        for md in ch_dir.rglob("ch*.md"):
            text = md.read_text(encoding="utf-8")
            if not _has_writing_notes(text):
                issues.append({
                    "level": "warning",
                    "code": "writing-notes-missing",
                    "message": "章节文件缺少 ### 写作备注",
                    "path": str(md.relative_to(root)),
                })

    # 章节大纲 weave_notes
    outline_ch = root / "outline" / "chapters"
    if outline_ch.is_dir():
        for md in outline_ch.glob("ch*.md"):
            text = md.read_text(encoding="utf-8")
            if not _has_weave_notes(text):
                issues.append({
                    "level": "info",
                    "code": "weave-notes-missing",
                    "message": "大纲文件缺少 weave_notes 字段",
                    "path": str(md.relative_to(root)),
                })

    return issues

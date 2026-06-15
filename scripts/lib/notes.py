"""用户笔记管理（notes/ 目录下的 raw.md / summary.md）。

设计目标：
- raw.md 是原始记录的 append-only 日志，verbatim 保留用户输入，永不删除
- summary.md 是蒸馏后的额外上下文，按主题分类
- 状态流转：pending → summarized | reverted
- 项目文件（style-guide / 角色 / 大纲等）不由此模块修改——那些改动走"内容修改"工作流

主代理在"步骤 7a"自动跑蒸馏，无需用户确认。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

NOTES_DIR = "notes"
RAW_FILE = "raw.md"
SUMMARY_FILE = "summary.md"

STATUS_PENDING = "pending"
STATUS_SUMMARIZED = "summarized"
STATUS_REVERTED = "reverted"

# raw.md 标题行格式：`## N001 · 2026-06-15T10:00:00Z`
_HEADER_RE = re.compile(r"^##\s+(N\d{3,})\s+·\s+(\S+)\s*$")
# raw.md 字段行格式：`- **key**：value`
_FIELD_RE = re.compile(r"^-\s+\*\*([^*]+)\*\*\s*[:：]\s*(.*)$")

DEFAULT_RAW_HEADER = """# 用户笔记原始记录

> 此文件为 append-only 日志，verbatim 保留用户输入，永不删除。
> 状态：pending → summarized | reverted
> 蒸馏结果见 summary.md。

"""


def _utcnow_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_id(existing_ids: list[str]) -> str:
    """生成下一个 N 编号。"""
    nums = []
    for i in existing_ids:
        m = re.match(r"N(\d+)", i)
        if m:
            nums.append(int(m.group(1)))
    nxt = (max(nums) + 1) if nums else 1
    return f"N{nxt:03d}"


def _parse_entries(text: str) -> list[dict]:
    """解析 raw.md 为条目列表。"""
    entries: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        m = _HEADER_RE.match(line.strip())
        if m:
            if cur:
                entries.append(cur)
            cur = {"id": m.group(1), "timestamp": m.group(2), "fields": {}}
            continue
        if cur is not None:
            fm = _FIELD_RE.match(line)
            if fm:
                cur["fields"][fm.group(1).strip()] = fm.group(2).strip()
    if cur:
        entries.append(cur)
    return entries


def _format_entry(entry: dict) -> str:
    """把条目格式化为 raw.md 文本块。"""
    lines = [f"## {entry['id']} · {entry['timestamp']}"]
    for k, v in entry["fields"].items():
        lines.append(f"- **{k}**：{v}")
    return "\n".join(lines) + "\n"


def _ensure_files(root: Path) -> tuple[Path, Path]:
    """确保 notes/ 目录与 raw.md 存在；summary.md 按需创建。"""
    notes_dir = root / NOTES_DIR
    notes_dir.mkdir(parents=True, exist_ok=True)
    raw_path = notes_dir / RAW_FILE
    if not raw_path.is_file():
        raw_path.write_text(DEFAULT_RAW_HEADER, encoding="utf-8")
    summary_path = notes_dir / SUMMARY_FILE
    return raw_path, summary_path


def add(
    root: Path,
    text: str,
    source: str = "user",
    stage: str = "",
    chapter: str = "",
) -> str:
    """追加一条笔记到 raw.md，返回新条目的 ID。

    状态默认 pending，由后续 apply 流程蒸馏到 summary.md。
    """
    raw_path, _ = _ensure_files(root)
    content = raw_path.read_text(encoding="utf-8")
    existing = _parse_entries(content)
    new_id = _next_id([e["id"] for e in existing])
    entry = {
        "id": new_id,
        "timestamp": _utcnow_str(),
        "fields": {
            "来源": source,
            "原始文本": text,
            "状态": STATUS_PENDING,
        },
    }
    if stage:
        entry["fields"]["阶段"] = stage
    if chapter:
        entry["fields"]["章节"] = chapter

    block = _format_entry(entry)
    if content and not content.endswith("\n"):
        content += "\n"
    if not content.endswith("\n\n"):
        content += "\n"
    content += block
    raw_path.write_text(content, encoding="utf-8")
    return new_id


def list_entries(root: Path, status: str | None = None) -> list[dict]:
    """列出条目，可按状态过滤。status=None 表示全部。"""
    raw_path, _ = _ensure_files(root)
    entries = _parse_entries(raw_path.read_text(encoding="utf-8"))
    if status and status != "all":
        entries = [e for e in entries if e["fields"].get("状态") == status]
    return entries


def show(root: Path, entry_id: str) -> dict | None:
    """按 ID 查询条目。"""
    raw_path, _ = _ensure_files(root)
    for e in _parse_entries(raw_path.read_text(encoding="utf-8")):
        if e["id"] == entry_id:
            return e
    return None


def _update_status(root: Path, entry_id: str, new_status: str, **extra) -> bool:
    """更新条目状态或附加字段。返回是否找到并更新成功。"""
    raw_path, _ = _ensure_files(root)
    content = raw_path.read_text(encoding="utf-8")
    entries = _parse_entries(content)
    target = None
    for e in entries:
        if e["id"] == entry_id:
            target = e
            break
    if target is None:
        return False
    target["fields"]["状态"] = new_status
    for k, v in extra.items():
        target["fields"][k] = v

    # 重新组装 raw.md：保留 header，替换所有条目块
    parts = content.split("\n", 1)
    header = parts[0] if parts else "# 用户笔记原始记录"
    rest = parts[1] if len(parts) > 1 else ""
    # 在 header 之后追加空行与全部条目
    rebuilt = header + "\n\n"
    for e in entries:
        rebuilt += _format_entry(e) + "\n"
    raw_path.write_text(rebuilt, encoding="utf-8")
    return True


def link(root: Path, entry_id: str, target: str) -> bool:
    """标记条目已映射到某文件/段落（状态 → summarized）。"""
    return _update_status(root, entry_id, STATUS_SUMMARIZED, 映射到=target)


def revert(root: Path, entry_id: str) -> bool:
    """标记条目为 reverted（从 summary.md 移除蒸馏结果，但保留 raw 记录）。"""
    return _update_status(root, entry_id, STATUS_REVERTED)


def load_summary(root: Path) -> str:
    """读取 summary.md（如不存在返回空字符串，供 context 组装使用）。"""
    _, summary_path = _ensure_files(root)
    if not summary_path.is_file():
        return ""
    return summary_path.read_text(encoding="utf-8")


def load_raw_for_context(root: Path) -> str:
    """读取 raw.md，供 orchestrator 在 apply 阶段引用。"""
    raw_path, _ = _ensure_files(root)
    if not raw_path.is_file():
        return ""
    return raw_path.read_text(encoding="utf-8")

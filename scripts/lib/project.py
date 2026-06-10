"""
Fictia 项目核心库：project.yaml 读写、状态推进、依赖图、传播规则。
"""

from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime, timezone
from .yaml_subset import load as yaml_load, dump as yaml_dump


def _utcnow_str() -> str:
    """UTC 时间字符串，兼容 Python 3.12+（弃用 utcnow）。"""
    try:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except AttributeError:
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# 11 个阶段的有序定义
STAGES: list[tuple[str, str]] = [
    ("01", "genre_analysis", "题材分析"),
    ("02", "architecture", "架构设计"),
    ("03", "style", "风格设计"),
    ("04", "art_design", "艺术设计"),
    ("05", "narrative_weave", "叙事编织"),
    ("06", "world", "世界观构建"),
    ("07", "characters", "人物设计"),
    ("08", "story", "故事设计"),
    ("09", "chapters", "章节写作"),
    ("10", "editor", "编辑审核"),
    ("11", "consistency", "一致性校验"),
]

STAGE_NAME: dict[str, str] = {k: name for _, k, name in STAGES}
STAGE_NUM: dict[str, str] = {k: num for num, k, _ in STAGES}

# 依赖图：阶段 → 依赖阶段列表
STAGE_DEPS: dict[str, list[str]] = {
    "genre_analysis": [],
    "architecture": ["genre_analysis"],
    "style": ["genre_analysis", "architecture"],
    "art_design": ["genre_analysis", "architecture", "style"],
    "narrative_weave": ["genre_analysis", "architecture", "art_design", "style"],
    "world": ["genre_analysis", "architecture", "art_design", "narrative_weave"],
    "characters": ["world", "architecture", "style", "art_design", "narrative_weave"],
    "story": ["architecture", "art_design", "narrative_weave", "world", "characters"],
    "chapters": ["style", "art_design", "narrative_weave", "world", "characters", "story"],
    "editor": ["chapters", "style"],
    "consistency": ["chapters"],
}

# 传播规则：阶段 → 修改后受影响的下游
PROPAGATION: dict[str, list[str]] = {
    "genre_analysis": ["architecture", "style", "art_design", "narrative_weave", "world", "characters", "story", "chapters"],
    "architecture": ["narrative_weave", "story", "chapters"],
    "style": ["chapters", "editor"],
    "art_design": ["narrative_weave", "characters", "story", "chapters"],
    "narrative_weave": ["characters", "story", "chapters"],
    "world": ["characters", "story", "chapters"],
    "characters": ["story", "chapters"],
    "story": ["chapters"],
    "chapters": ["consistency"],
    "editor": [],
    "consistency": [],
}

# 状态值
STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_PENDING_CONFIRM = "pending_confirm"
STATUS_CONFIRMED = "confirmed"
STATUS_NEEDS_UPDATE = "needs_update"
STATUS_FAILED = "failed"

# 各阶段产出文件（用于 init 占位）
STAGE_OUTPUTS: dict[str, list[str]] = {
    "genre_analysis": ["genre-analysis.md"],
    "architecture": ["blueprint.md"],
    "style": ["style-guide.md"],
    "art_design": ["art-design.md"],
    "narrative_weave": ["narrative-weave.md"],
    "world": ["world/setting.md", "world/rules.md", "world/timeline.md"],
    "characters": ["characters/protagonist.md", "characters/antagonist.md", "characters/supporting/.gitkeep", "characters/relationships.md"],
    "story": ["outline/act-1.md", "outline/act-2.md", "outline/act-3.md", "outline/chapters/.gitkeep"],
    "chapters": ["chapters/act-1/.gitkeep", "chapters/act-2/.gitkeep", "chapters/act-3/.gitkeep"],
    "editor": ["reviews/.gitkeep"],
    "consistency": [],
}


def find_project_root(start: str | Path | None = None) -> Path | None:
    """从 start 向上查找含 project.yaml 的目录。"""
    cur = Path(start or os.getcwd()).resolve()
    for _ in range(20):
        if (cur / "project.yaml").is_file():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


def normalize_stage_status(raw: object) -> str:
    """把项目 yaml 中阶段的取值（字符串或 dict）规范为 status 字符串。"""
    if raw is None:
        return STATUS_NOT_STARTED
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return str(raw.get("status", STATUS_NOT_STARTED))
    return STATUS_NOT_STARTED


def load_project(root: Path) -> dict:
    """读取并规范化项目数据。"""
    path = root / "project.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"project.yaml not found in {root}")
    text = path.read_text(encoding="utf-8")
    data = yaml_load(text) or {}
    # 规范化 pipeline
    pipeline = data.get("pipeline") or {}
    norm_pipeline: dict[str, dict] = {}
    for _, key, _ in STAGES:
        raw = pipeline.get(key)
        if raw is None:
            norm_pipeline[key] = {
                "status": STATUS_NOT_STARTED,
                "confirmedAt": None,
                "outputFiles": [],
            }
        elif isinstance(raw, str):
            norm_pipeline[key] = {
                "status": raw,
                "confirmedAt": None,
                "outputFiles": [],
            }
        elif isinstance(raw, dict):
            norm_pipeline[key] = {
                "status": str(raw.get("status", STATUS_NOT_STARTED)),
                "confirmedAt": raw.get("confirmedAt"),
                "outputFiles": list(raw.get("outputFiles") or []),
            }
        else:
            norm_pipeline[key] = {
                "status": STATUS_NOT_STARTED,
                "confirmedAt": None,
                "outputFiles": [],
            }
    data["pipeline"] = norm_pipeline
    return data


def save_project(root: Path, data: dict) -> None:
    """把项目数据写回 project.yaml。"""
    data = dict(data)
    data["last_modified"] = _utcnow_str()
    path = root / "project.yaml"
    path.write_text(yaml_dump(data) + "\n", encoding="utf-8")


def get_stage_status(data: dict, stage: str) -> str:
    return normalize_stage_status((data.get("pipeline") or {}).get(stage))


def set_stage_status(data: dict, stage: str, status: str) -> None:
    if stage not in STAGE_NAME:
        raise ValueError(f"unknown stage: {stage}")
    pipeline = data.setdefault("pipeline", {})
    entry = pipeline.setdefault(stage, {"status": STATUS_NOT_STARTED, "confirmedAt": None, "outputFiles": []})
    if not isinstance(entry, dict):
        entry = {"status": entry, "confirmedAt": None, "outputFiles": []}
        pipeline[stage] = entry
    entry["status"] = status
    if status == STATUS_CONFIRMED and not entry.get("confirmedAt"):
        entry["confirmedAt"] = _utcnow_str()
    elif status != STATUS_CONFIRMED:
        entry["confirmedAt"] = None


def is_stage_runnable(data: dict, stage: str) -> bool:
    """判断阶段是否可执行：所有依赖已 confirmed，且自身未开始或需更新。"""
    if stage not in STAGE_NAME:
        return False
    deps = STAGE_DEPS.get(stage, [])
    for d in deps:
        if get_stage_status(data, d) != STATUS_CONFIRMED:
            return False
    s = get_stage_status(data, stage)
    return s in (STATUS_NOT_STARTED, STATUS_NEEDS_UPDATE)


def next_runnable_stage(data: dict) -> tuple[str, str, str] | None:
    """返回下一个可执行阶段：(编号, key, 中文名)。若全部完成返回 None。"""
    for num, key, name in STAGES:
        if is_stage_runnable(data, key):
            return (num, key, name)
    return None


def all_confirmed(data: dict) -> bool:
    return all(get_stage_status(data, k) == STATUS_CONFIRMED for _, k, _ in STAGES)


def invalidate_downstream(data: dict, stage: str) -> list[str]:
    """把 stage 下游所有 confirmed 的阶段置为 needs_update，返回被改变的 key 列表。"""
    if stage not in STAGE_NAME:
        raise ValueError(f"unknown stage: {stage}")
    changed: list[str] = []
    visited: set[str] = set()
    queue: list[str] = list(PROPAGATION.get(stage, []))
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        if get_stage_status(data, cur) == STATUS_CONFIRMED:
            set_stage_status(data, cur, STATUS_NEEDS_UPDATE)
            changed.append(cur)
        # 递归传播
        for nxt in PROPAGATION.get(cur, []):
            if nxt not in visited:
                queue.append(nxt)
    return changed


def get_milestone(data: dict) -> tuple[bool, int]:
    """返回 (是否到达里程碑, 下一里程碑值)。"""
    chapters = data.get("chapters") or {}
    confirmed = int(chapters.get("confirmed") or 0)
    if confirmed <= 0:
        return (False, 0)
    next_ms = ((confirmed // 5) + 1) * 5
    if confirmed % 5 == 0:
        return (True, confirmed)
    return (False, next_ms)


def increment_chapters(data: dict, count: int = 1) -> None:
    chapters = data.setdefault("chapters", {"total": 0, "written": 0, "confirmed": 0})
    chapters["written"] = int(chapters.get("written") or 0) + count
    chapters["confirmed"] = int(chapters.get("confirmed") or 0) + count


def chapter_act_of(chapter_num: int) -> str:
    """默认章节-幕映射（无 blueprint 时）。"""
    if chapter_num <= 3:
        return "act-prologue"
    if chapter_num <= 15:
        return "act-1"
    if chapter_num <= 30:
        return "act-2"
    if chapter_num <= 45:
        return "act-3"
    return "act-epilogue"

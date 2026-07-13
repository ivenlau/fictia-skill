"""Dynamic Writing Space — 状态更新器。

在章节写作完成后，从写作备注中提取实体状态变更并更新 entity store。

写作备注格式扩展（向后兼容旧格式）：

  ### 写作备注
  - **字数**: 3200
  - **伏笔操作**:
    - 埋设: F003 (神秘玉佩的来历)
    - 推进: F001 (林远身世线索)
  - **人物状态更新**: 林远左臂受伤 (第12段)
  - **地点变更**: 北域冰原 → state: active
  - **物品状态**: 神秘玉佩 → state: discovered
  - **事件结案**: 北域围猎 → state: concluded
  - **下章衔接点**: ...

解析策略：
  1. 伏笔操作 → foreshadowing collection 状态更新
  2. 人物状态更新 → characters collection 状态更新
  3. 地点变更 → locations collection 状态更新
  4. 物品状态 → items collection 状态更新
  5. 事件结案 → events collection 状态更新
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lib.entity_store import EntityStore
from lib.entity_schema import (
    is_valid_transition,
    make_entity_id,
    make_slug,
)
from lib.words import WRITING_NOTES_RE


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #


@dataclass
class EntityStateChange:
    """一次实体状态变更。"""

    collection: str
    name: str  # 实体名称（用于匹配）
    entity_id: str | None = None  # 精确 ID（优先）
    new_state: str | None = None
    description: str = ""  # 变更描述
    extra_fields: dict | None = None


# --------------------------------------------------------------------------- #
# 解析器
# --------------------------------------------------------------------------- #


def parse_writing_notes_for_updates(
    chapter_text: str, chapter: int
) -> list[EntityStateChange]:
    """从章节文本的写作备注中提取状态变更。"""
    m = WRITING_NOTES_RE.search(chapter_text)
    if not m:
        return []

    notes_text = chapter_text[m.start() :]
    changes: list[EntityStateChange] = []

    # 1. 伏笔操作
    _parse_foreshadow_ops(notes_text, chapter, changes)

    # 2. 人物状态更新
    _parse_character_updates(notes_text, chapter, changes)

    # 3. 地点变更
    _parse_location_updates(notes_text, chapter, changes)

    # 4. 物品状态
    _parse_item_updates(notes_text, chapter, changes)

    # 5. 事件结案
    _parse_event_updates(notes_text, chapter, changes)

    return changes


def _parse_foreshadow_ops(
    text: str, chapter: int, changes: list[EntityStateChange]
) -> None:
    """解析伏笔操作。"""
    # 匹配：
    # - 埋设: F003 (描述)
    # - 推进: F001 描述
    # - 回收: F002 描述
    pattern = re.compile(
        r"[-*]\s*(埋设|推进|回收|铺垫|强化)[：:]\s*(.+)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        op_raw = m.group(1).strip()
        rest = m.group(2).strip()

        # 提取 ID
        fo_id = ""
        desc = rest
        id_match = re.match(r"(?:伏笔ID[-_])?([A-Z]+\d+|F\d+)[：:（(\s]*(.*)", rest)
        if id_match:
            fo_id = id_match.group(1)
            desc = id_match.group(2).strip()

        # 映射操作到状态
        state_map = {
            "埋设": "planted",
            "铺垫": "planted",
            "推进": "seeded",
            "强化": "escalated",
            "回收": "resolved",
        }
        new_state = state_map.get(op_raw.lower())

        if fo_id and new_state:
            changes.append(
                EntityStateChange(
                    collection="foreshadowing",
                    name=fo_id,
                    new_state=new_state,
                    description=desc,
                )
            )


def _parse_character_updates(
    text: str, chapter: int, changes: list[EntityStateChange]
) -> None:
    """解析人物状态更新。"""
    # 匹配：- **人物状态更新**: 林远左臂受伤 (第12段)
    pattern = re.compile(
        r"人物状态更新[：:]\s*(.+)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        update_text = m.group(1).strip()
        # 尝试提取角色名（前 2-4 个中文字符）
        name_match = re.match(r"([一-鿿]{2,4})", update_text)
        if name_match:
            name = name_match.group(1)
            changes.append(
                EntityStateChange(
                    collection="characters",
                    name=name,
                    new_state="major_change",
                    description=update_text,
                )
            )


def _parse_location_updates(
    text: str, chapter: int, changes: list[EntityStateChange]
) -> None:
    """解析地点变更。"""
    # 匹配：- **地点变更**: 北域冰原 → state: active
    pattern = re.compile(
        r"地点变更[：:]\s*(.+?)[\s]*[→→][\s]*(?:state[：:]?\s*)?(\w+)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        new_state = m.group(2).strip()
        changes.append(
            EntityStateChange(
                collection="locations",
                name=name,
                new_state=new_state,
            )
        )

    # 也匹配简单格式：- **新增设定**: 北域冰原的暴风雪规则
    pattern2 = re.compile(
        r"新增设定[：:]\s*(.+)",
        re.IGNORECASE,
    )
    for m in pattern2.finditer(text):
        desc = m.group(1).strip()
        if desc and desc != "无":
            # 提取地点名（取前几个字）
            name_match = re.match(r"([一-鿿]{2,6})", desc)
            if name_match:
                changes.append(
                    EntityStateChange(
                        collection="locations",
                        name=name_match.group(1),
                        new_state="active",
                        description=desc,
                    )
                )


def _parse_item_updates(
    text: str, chapter: int, changes: list[EntityStateChange]
) -> None:
    """解析物品状态。"""
    # 匹配：- **物品状态**: 神秘玉佩 → state: discovered
    pattern = re.compile(
        r"物品状态[：:]\s*(.+?)[\s]*[→→][\s]*(?:state[：:]?\s*)?(\w+)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        new_state = m.group(2).strip()
        changes.append(
            EntityStateChange(
                collection="items",
                name=name,
                new_state=new_state,
            )
        )


def _parse_event_updates(
    text: str, chapter: int, changes: list[EntityStateChange]
) -> None:
    """解析事件结案。"""
    # 匹配：- **事件结案**: 北域围猎 → state: concluded
    pattern = re.compile(
        r"事件结案[：:]\s*(.+?)[\s]*[→→][\s]*(?:state[：:]?\s*)?(\w+)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        new_state = m.group(2).strip()
        changes.append(
            EntityStateChange(
                collection="events",
                name=name,
                new_state=new_state,
            )
        )


# --------------------------------------------------------------------------- #
# 应用变更
# --------------------------------------------------------------------------- #


def apply_entity_changes(
    store: EntityStore,
    changes: list[EntityStateChange],
    chapter: int,
) -> list[str]:
    """将状态变更应用到 entity store。

    返回成功更新的实体 id 列表。
    """
    updated: list[str] = []

    for change in changes:
        # 查找实体
        entity = None
        if change.entity_id:
            entity = store.get_entity(change.collection, change.entity_id)
        if entity is None:
            # 按名称查找
            matches = store.search_entities_by_names(
                change.collection, [change.name]
            )
            if matches:
                entity = matches[0]

        if entity is None:
            # 新实体 → 创建
            slug = make_slug(change.name)
            from lib.entity_schema import EntityDoc

            doc = EntityDoc(
                id=make_entity_id(change.collection, slug),
                text=change.description or change.name,
                collection=change.collection,
                state=change.new_state or "introduced",
                state_ch=chapter,
                fields={
                    "name": change.name,
                    "tags": "",
                    "related": "",
                    **(change.extra_fields or {}),
                },
            )
            store.upsert_entity(doc)
            updated.append(doc.id)
            continue

        # 已有实体 → 状态更新
        entity_id = entity.get("id", "")
        old_state = entity.get("state", "")
        new_state = change.new_state

        if new_state and is_valid_transition(change.collection, old_state, new_state):
            ok = store.update_entity_state(
                change.collection,
                entity_id,
                new_state,
                chapter,
                new_text=change.description or None,
                extra_fields=change.extra_fields,
            )
            if ok:
                updated.append(entity_id)

    return updated


# --------------------------------------------------------------------------- #
# 便捷函数
# --------------------------------------------------------------------------- #


def update_entities_from_chapter(
    store: EntityStore,
    chapter_text: str,
    chapter: int,
) -> list[str]:
    """从已完成章节的文本中提取并应用实体状态变更。"""
    changes = parse_writing_notes_for_updates(chapter_text, chapter)
    if not changes:
        return []
    return apply_entity_changes(store, changes, chapter)

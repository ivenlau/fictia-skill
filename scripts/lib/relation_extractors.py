"""Dynamic Writing Space — 关系提取器。

从现有 entity 字段中自动提取关系三元组，写入 relations collection。

数据来源：
  1. characters/*.md 的 relationships 字段 → 角色间关系
  2. events 的 participants / causes / effects → 事件因果链
  3. storylines 的 key_chars → 故事线-角色绑定
  4. items 的 owner → 物品归属
  5. entities 的 related 字段 → 通用关联

每个 extractor 返回 list[tuple[source_id, rel_type, target_id, text]]。
"""
from __future__ import annotations

import re
from pathlib import Path

from lib.entity_schema import (
    EntityDoc,
    make_entity_id,
    make_slug,
)
from lib.entity_store import EntityStore
from lib.context import parse_frontmatter


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #


def _name_to_entity_id(name: str, collection: str) -> str:
    """从实体名称推断 entity id（取最新版本的 id 前缀）。"""
    slug = make_slug(name)
    return make_entity_id(collection, slug)


def _find_entity_by_name(store: EntityStore, collection: str, name: str) -> str | None:
    """在 store 中查找实体，返回其 id。找不到则返回 None。"""
    matches = store.search_entities_by_names(collection, [name])
    if matches:
        return matches[0].get("id", "")
    return None


def _resolve_entity_id(
    store: EntityStore, name: str, collection: str
) -> str:
    """解析实体名称为 id。优先精确查找，找不到则用 slug 推断。"""
    found = _find_entity_by_name(store, collection, name)
    if found:
        return found
    return _name_to_entity_id(name, collection)


# --------------------------------------------------------------------------- #
# 1. 角色关系提取器
# --------------------------------------------------------------------------- #


def extract_character_relations(
    store: EntityStore, project_root: Path
) -> list[tuple[str, str, str, str]]:
    """从 characters/*.md 的 relationships 字段提取角色间关系。"""
    chars_dir = project_root / "characters"
    if not chars_dir.is_dir():
        return []

    triples: list[tuple[str, str, str, str]] = []
    files: list[Path] = []

    for name in ("protagonist.md", "antagonist.md"):
        p = chars_dir / name
        if p.is_file():
            files.append(p)
    supporting = chars_dir / "supporting"
    if supporting.is_dir():
        files.extend(sorted(supporting.glob("*.md")))

    for p in files:
        text = p.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        char_name = fm.get("name", p.stem)
        char_id = _resolve_entity_id(store, char_name, "characters")

        relationships = fm.get("relationships", []) or []
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            other_name = rel.get("name", "")
            rel_desc = rel.get("relation", rel.get("type", "related_to"))
            if not other_name:
                continue

            other_id = _resolve_entity_id(store, other_name, "characters")

            # 推断关系类型
            rel_type = _infer_rel_type(rel_desc)
            text_desc = f"{char_name} 与 {other_name} 的关系：{rel_desc}"

            triples.append((char_id, rel_type, other_id, text_desc))

    return triples


def _infer_rel_type(desc: str) -> str:
    """从关系描述推断关系类型。"""
    desc_lower = desc.lower()
    mapping = {
        "师": "mentor",
        "徒": "apprentice",
        "父": "family",
        "母": "family",
        "兄": "family",
        "弟": "family",
        "姐": "family",
        "妹": "family",
        "子": "family",
        "女": "family",
        "妻": "lover",
        "夫": "lover",
        "恋": "lover",
        "爱": "lover",
        "友": "friend",
        "敌": "enemy",
        "仇": "enemy",
        "盟": "ally",
        "对手": "rival",
        "竞争": "rival",
        "守护": "protects",
        "保护": "protects",
        "侍": "serves",
        "忠": "serves",
        "控制": "controls",
        "支配": "controls",
    }
    for keyword, rel_type in mapping.items():
        if keyword in desc:
            return rel_type
    return "related_to"


# --------------------------------------------------------------------------- #
# 2. 事件关系提取器
# --------------------------------------------------------------------------- #


def extract_event_relations(
    store: EntityStore,
) -> list[tuple[str, str, str, str]]:
    """从 events 的 participants/causes/effects 字段提取关系。"""
    events = store.list_entities("events")
    triples: list[tuple[str, str, str, str]] = []

    for evt in events:
        evt_id = evt.get("id", "")
        evt_name = evt.get("name", "")
        participants = evt.get("participants", "")
        causes = evt.get("causes", "")
        effects = evt.get("effects", "")
        location = evt.get("location", "")

        # 参与者 → participates 关系
        if participants:
            for char_name in _split_names(participants):
                char_id = _resolve_entity_id(store, char_name, "characters")
                text = f"{char_name} 参与了事件「{evt_name}」"
                triples.append((char_id, "participates", evt_id, text))

        # 地点 → located_at 关系
        if location:
            for loc_name in _split_names(location):
                loc_id = _resolve_entity_id(store, loc_name, "locations")
                text = f"事件「{evt_name}」发生在 {loc_name}"
                triples.append((evt_id, "located_at", loc_id, text))

        # 因果链
        if causes:
            for cause_name in _split_names(causes):
                cause_id = _find_event_id(store, cause_name)
                if cause_id:
                    text = f"事件「{cause_name}」导致了「{evt_name}」"
                    triples.append((cause_id, "causes", evt_id, text))

        if effects:
            for effect_name in _split_names(effects):
                effect_id = _find_event_id(store, effect_name)
                if effect_id:
                    text = f"事件「{evt_name}」影响了「{effect_name}」"
                    triples.append((evt_id, "affects", effect_id, text))

    return triples


def _split_names(text: str) -> list[str]:
    """拆分逗号/顿号分隔的名称列表。"""
    if not text:
        return []
    names = re.split(r"[、，,;；\s]+", text.strip())
    return [n.strip() for n in names if n.strip()]


def _find_event_id(store: EntityStore, name: str) -> str | None:
    """查找事件 id。"""
    return _find_entity_by_name(store, "events", name)


# --------------------------------------------------------------------------- #
# 3. 故事线关系提取器
# --------------------------------------------------------------------------- #


def extract_storyline_relations(
    store: EntityStore,
) -> list[tuple[str, str, str, str]]:
    """从 storylines 的 key_chars 字段提取故事线-角色绑定。"""
    storylines = store.list_entities("storylines")
    triples: list[tuple[str, str, str, str]] = []

    for sl in storylines:
        sl_id = sl.get("id", "")
        sl_name = sl.get("name", "")
        key_chars = sl.get("key_chars", "")

        if key_chars:
            for char_name in _split_names(key_chars):
                char_id = _resolve_entity_id(store, char_name, "characters")
                text = f"{char_name} 是故事线「{sl_name}」的关键角色"
                triples.append((sl_id, "key_char", char_id, text))

    return triples


# --------------------------------------------------------------------------- #
# 4. 物品归属提取器
# --------------------------------------------------------------------------- #


def extract_item_relations(
    store: EntityStore,
) -> list[tuple[str, str, str, str]]:
    """从 items 的 owner 字段提取物品归属关系。"""
    items = store.list_entities("items")
    triples: list[tuple[str, str, str, str]] = []

    for item in items:
        item_id = item.get("id", "")
        item_name = item.get("name", "")
        owner = item.get("owner", "")

        if owner:
            for owner_name in _split_names(owner):
                owner_id = _resolve_entity_id(store, owner_name, "characters")
                text = f"{owner_name} 持有物品「{item_name}」"
                triples.append((owner_id, "owns", item_id, text))

    return triples


# --------------------------------------------------------------------------- #
# 5. related 字段提取器（通用关联）
# --------------------------------------------------------------------------- #


def extract_related_field_relations(
    store: EntityStore,
) -> list[tuple[str, str, str, str]]:
    """从所有实体的 related 字段提取通用关联关系。"""
    from lib.entity_schema import ENTITY_COLLECTIONS

    triples: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for collection in ENTITY_COLLECTIONS:
        if collection == "relations":
            continue
        entities = store.list_entities(collection)
        for entity in entities:
            entity_id = entity.get("id", "")
            entity_name = entity.get("name", "")
            related = entity.get("related", "")

            if not related:
                continue

            for rel_name in _split_names(related):
                # 尝试在同 collection 中查找
                rel_id = _resolve_entity_id(store, rel_name, collection)
                if rel_id == entity_id:
                    continue

                # 去重（双向）
                edge_key = tuple(sorted([entity_id, rel_id]) + ["related_to"])
                if edge_key in seen:
                    continue
                seen.add(edge_key)

                text = f"{entity_name} 与 {rel_name} 相关联"
                triples.append((entity_id, "related_to", rel_id, text))

    return triples


# --------------------------------------------------------------------------- #
# 全量提取
# --------------------------------------------------------------------------- #


def extract_all_relations(
    store: EntityStore, project_root: Path
) -> list[tuple[str, str, str, str]]:
    """从所有来源提取关系三元组。

    Returns:
        [(source_id, rel_type, target_id, text), ...]
    """
    all_triples: list[tuple[str, str, str, str]] = []

    # 1. 角色关系（需要 project_root 读取 md 文件）
    all_triples.extend(extract_character_relations(store, project_root))

    # 2. 事件关系
    all_triples.extend(extract_event_relations(store))

    # 3. 故事线关系
    all_triples.extend(extract_storyline_relations(store))

    # 4. 物品归属
    all_triples.extend(extract_item_relations(store))

    # 5. related 字段通用关联
    all_triples.extend(extract_related_field_relations(store))

    return all_triples


def build_knowledge_graph(
    store: EntityStore, project_root: Path
) -> int:
    """构建知识图谱：提取所有关系并写入 relations collection。

    Returns:
        写入的关系数量。
    """
    triples = extract_all_relations(store, project_root)
    if not triples:
        return 0

    # 转换为 store.upsert_relations 需要的格式
    formatted = [(src, rel, tgt, text) for src, rel, tgt, text in triples]
    return store.upsert_relations(formatted)

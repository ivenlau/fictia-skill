"""Dynamic Writing Space — 实体数据模型。

定义：
  - 8 个 entity collection 的名称、状态枚举、状态转移规则
  - EntityDoc dataclass（待索引的实体文档）
  - 各 collection 的 zvec schema 构造函数

不依赖 zvec，可独立单测。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# --------------------------------------------------------------------------- #
# Collection 名称
# --------------------------------------------------------------------------- #

ENTITY_COLLECTIONS = (
    "characters",
    "locations",
    "items",
    "events",
    "foreshadowing",
    "easter_eggs",
    "storylines",
    "timeline",
    "relations",
)


# --------------------------------------------------------------------------- #
# 状态枚举
# --------------------------------------------------------------------------- #


class CharacterState(str, Enum):
    INTRODUCED = "introduced"
    ACTIVE = "active"
    MAJOR_CHANGE = "major_change"
    ABSENT = "absent"
    EXIT = "exit"
    DEATH = "death"


class LocationState(str, Enum):
    INTRODUCED = "introduced"
    ACTIVE = "active"
    DESTROYED = "destroyed"
    SEALED = "sealed"
    ABANDONED = "abandoned"


class ItemState(str, Enum):
    UNKNOWN = "unknown"
    HIDDEN = "hidden"
    DISCOVERED = "discovered"
    OWNED = "owned"
    USED = "used"
    DESTROYED = "destroyed"
    LOST = "lost"


class EventState(str, Enum):
    PENDING = "pending"
    HAPPENING = "happening"
    CONCLUDED = "concluded"
    CONSEQUENCE = "consequence"


class ForeshadowingState(str, Enum):
    PLANTED = "planted"
    SEEDED = "seeded"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class EasterEggState(str, Enum):
    PLANTED = "planted"
    HINTED = "hinted"
    DISCOVERABLE = "discoverable"
    REVEALED = "revealed"


class StorylineState(str, Enum):
    DORMANT = "dormant"
    ACTIVE = "active"
    ESCALATING = "escalating"
    CLIMAX = "climax"
    RESOLVED = "resolved"


class TimelineState(str, Enum):
    PAST = "past"
    CURRENT = "current"
    FORESHADOWED = "foreshadowed"


class RelationsState(str, Enum):
    ACTIVE = "active"
    CHANGED = "changed"
    DISSOLVED = "dissolved"


# collection → 状态枚举映射
STATE_ENUMS: dict[str, type] = {
    "characters": CharacterState,
    "locations": LocationState,
    "items": ItemState,
    "events": EventState,
    "foreshadowing": ForeshadowingState,
    "easter_eggs": EasterEggState,
    "storylines": StorylineState,
    "timeline": TimelineState,
    "relations": RelationsState,
}


# --------------------------------------------------------------------------- #
# 合法状态转移
# --------------------------------------------------------------------------- #

VALID_TRANSITIONS: dict[str, dict[str, list[str]]] = {
    "characters": {
        CharacterState.INTRODUCED: [CharacterState.ACTIVE],
        CharacterState.ACTIVE: [
            CharacterState.MAJOR_CHANGE,
            CharacterState.ABSENT,
            CharacterState.EXIT,
            CharacterState.DEATH,
        ],
        CharacterState.MAJOR_CHANGE: [CharacterState.ACTIVE],
        CharacterState.ABSENT: [
            CharacterState.ACTIVE,
            CharacterState.EXIT,
            CharacterState.DEATH,
        ],
    },
    "locations": {
        LocationState.INTRODUCED: [LocationState.ACTIVE],
        LocationState.ACTIVE: [
            LocationState.DESTROYED,
            LocationState.SEALED,
            LocationState.ABANDONED,
        ],
    },
    "items": {
        ItemState.UNKNOWN: [ItemState.HIDDEN, ItemState.DISCOVERED],
        ItemState.HIDDEN: [ItemState.DISCOVERED],
        ItemState.DISCOVERED: [ItemState.OWNED, ItemState.DESTROYED, ItemState.LOST],
        ItemState.OWNED: [ItemState.USED, ItemState.DESTROYED, ItemState.LOST],
        ItemState.USED: [ItemState.OWNED, ItemState.DESTROYED, ItemState.LOST],
        ItemState.LOST: [ItemState.DISCOVERED, ItemState.OWNED],
    },
    "events": {
        EventState.PENDING: [EventState.HAPPENING],
        EventState.HAPPENING: [EventState.CONCLUDED],
        EventState.CONCLUDED: [EventState.CONSEQUENCE],
    },
    "foreshadowing": {
        ForeshadowingState.PLANTED: [
            ForeshadowingState.SEEDED,
            ForeshadowingState.ABANDONED,
        ],
        ForeshadowingState.SEEDED: [
            ForeshadowingState.ESCALATED,
            ForeshadowingState.RESOLVED,
            ForeshadowingState.ABANDONED,
        ],
        ForeshadowingState.ESCALATED: [
            ForeshadowingState.RESOLVED,
            ForeshadowingState.ABANDONED,
        ],
    },
    "easter_eggs": {
        EasterEggState.PLANTED: [EasterEggState.HINTED],
        EasterEggState.HINTED: [EasterEggState.DISCOVERABLE],
        EasterEggState.DISCOVERABLE: [EasterEggState.REVEALED],
    },
    "storylines": {
        StorylineState.DORMANT: [StorylineState.ACTIVE],
        StorylineState.ACTIVE: [StorylineState.ESCALATING, StorylineState.RESOLVED],
        StorylineState.ESCALATING: [StorylineState.CLIMAX, StorylineState.RESOLVED],
        StorylineState.CLIMAX: [StorylineState.RESOLVED],
    },
    "timeline": {
        TimelineState.PAST: [],
        TimelineState.CURRENT: [TimelineState.PAST],
        TimelineState.FORESHADOWED: [TimelineState.CURRENT, TimelineState.PAST],
    },
    "relations": {
        RelationsState.ACTIVE: [RelationsState.CHANGED, RelationsState.DISSOLVED],
        RelationsState.CHANGED: [RelationsState.ACTIVE, RelationsState.DISSOLVED],
    },
}


def is_valid_transition(collection: str, from_state: str, to_state: str) -> bool:
    """检查状态转移是否合法。"""
    transitions = VALID_TRANSITIONS.get(collection, {})
    allowed = transitions.get(from_state, [])
    return to_state in allowed


# --------------------------------------------------------------------------- #
# 实体文档
# --------------------------------------------------------------------------- #


@dataclass
class EntityDoc:
    """一个待写入 zvec entity collection 的文档。

    id 格式: "{type}_{slug}_v{version:03d}"  如 "char_lin_yuan_v001"
    version 从 1 开始，每次状态变更递增。
    """

    id: str
    text: str
    collection: str
    state: str
    state_ch: int | None = None
    version: int = 1
    fields: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.collection not in ENTITY_COLLECTIONS:
            raise ValueError(
                f"未知 collection: {self.collection}；可选：{ENTITY_COLLECTIONS}"
            )


# --------------------------------------------------------------------------- #
# 关系类型
# --------------------------------------------------------------------------- #

RELATION_TYPES = (
    # 角色间关系
    "friend",        # 朋友
    "enemy",         # 敌人
    "mentor",        # 师徒（导师方）
    "apprentice",    # 师徒（学徒方）
    "family",        # 家族/血缘
    "lover",         # 恋人
    "ally",          # 盟友
    "rival",         # 对手
    "protects",      # 守护
    "serves",        # 侍奉/效忠
    "controls",      # 控制/支配
    # 实体间关系
    "located_at",    # 位于
    "owns",          # 持有/拥有
    "participates",  # 参与（事件）
    "causes",        # 导致（事件因果）
    "affects",       # 影响
    "reveals",       # 揭示（伏笔）
    "belongs_to",    # 属于（故事线）
    "key_char",      # 关键角色（故事线）
    "related_to",    # 通用关联
)


# --------------------------------------------------------------------------- #
# 各 collection 的元数据字段定义
# --------------------------------------------------------------------------- #

# 通用字段（所有 collection 都有）
_COMMON_FIELDS = [
    ("text", "STRING"),
    ("state", "STRING"),
    ("state_ch", "INT64"),
    ("name", "STRING"),
    ("tags", "STRING"),
    ("related", "STRING"),
    ("version", "INT64"),
    ("archived", "STRING"),  # "true" / "false"，默认 "false"
]

# 各 collection 特有字段
COLLECTION_EXTRA_FIELDS: dict[str, list[tuple[str, str]]] = {
    "characters": [
        ("role", "STRING"),
        ("identity", "STRING"),
        ("traits", "STRING"),
        ("lang_style", "STRING"),
        ("arc_keyword", "STRING"),
        ("emotional", "STRING"),
        ("chapter", "INT64"),
    ],
    "locations": [
        ("region", "STRING"),
        ("first_ch", "INT64"),
        ("last_ch", "INT64"),
    ],
    "items": [
        ("owner", "STRING"),
        ("power", "STRING"),
    ],
    "events": [
        ("chapter", "INT64"),
        ("participants", "STRING"),
        ("location", "STRING"),
        ("causes", "STRING"),
        ("effects", "STRING"),
    ],
    "foreshadowing": [
        ("plant_ch", "INT64"),
        ("resolve_ch", "INT64"),
        ("type", "STRING"),
    ],
    "easter_eggs": [
        ("type", "STRING"),
        ("target_ch", "INT64"),
    ],
    "storylines": [
        ("type", "STRING"),
        ("priority", "STRING"),
        ("key_chars", "STRING"),
    ],
    "timeline": [
        ("event_time", "STRING"),
        ("chapter", "INT64"),
        ("era", "STRING"),
    ],
    "relations": [
        ("source_id", "STRING"),
        ("target_id", "STRING"),
        ("rel_type", "STRING"),
        ("chapter", "INT64"),
        ("confidence", "STRING"),
    ],
}


def get_collection_fields(collection: str) -> list[tuple[str, str]]:
    """返回指定 collection 的全部元数据字段（通用 + 特有）。"""
    extra = COLLECTION_EXTRA_FIELDS.get(collection, [])
    return _COMMON_FIELDS + extra


# --------------------------------------------------------------------------- #
# Entity ID 工具
# --------------------------------------------------------------------------- #

# collection → 类型前缀
_COLLECTION_PREFIX: dict[str, str] = {
    "characters": "char",
    "locations": "loc",
    "items": "item",
    "events": "evt",
    "foreshadowing": "fwd",
    "easter_eggs": "egg",
    "storylines": "arc",
    "timeline": "tl",
    "relations": "rel",
}


def make_entity_id(collection: str, slug: str, version: int = 1) -> str:
    """构造 entity id。

    格式: "{prefix}_{slug}_v{version:03d}"
    """
    prefix = _COLLECTION_PREFIX.get(collection, collection[:3])
    return f"{prefix}_{slug}_v{version:03d}"


def parse_entity_id(entity_id: str) -> tuple[str, str, int]:
    """解析 entity id → (prefix, slug, version)。

    例: "char_lin_yuan_v003" → ("char", "lin_yuan", 3)
    """
    parts = entity_id.rsplit("_v", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return (entity_id, entity_id, 0)
    slug_part = parts[0]
    version = int(parts[1])
    # 从 slug_part 中分离 prefix（第一个 _ 之前）
    sep = slug_part.find("_")
    if sep == -1:
        return (slug_part, slug_part, version)
    prefix = slug_part[:sep]
    slug = slug_part[sep + 1 :]
    return (prefix, slug, version)


def make_slug(name: str) -> str:
    """从中文名称生成稳定的 slug。

    策略：用 name 的 UTF-8 编码 hex 摘要作为 slug，
    确保只包含 ASCII 字符（zvec doc_id 不支持中文）。
    """
    import hashlib

    h = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    # 尝试保留可读部分：只保留 ASCII 字母和数字
    clean = ""
    for ch in name:
        if ch.isascii() and ch.isalnum():
            clean += ch
    if not clean:
        return h
    # 截断到 8 字符 + hash 后缀
    return f"{clean[:8]}_{h}"


# --------------------------------------------------------------------------- #
# 关系 ID 工具
# --------------------------------------------------------------------------- #


def make_relation_slug(source_id: str, rel_type: str, target_id: str) -> str:
    """从 (source, rel_type, target) 生成稳定的 slug。"""
    import hashlib

    raw = f"{source_id}|{rel_type}|{target_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_relation_id(
    source_id: str, rel_type: str, target_id: str, version: int = 1
) -> str:
    """构造关系文档 id。

    格式: "rel_{hash16}_v{version:03d}"
    """
    slug = make_relation_slug(source_id, rel_type, target_id)
    return f"rel_{slug}_v{version:03d}"


def parse_relation_id(relation_id: str) -> tuple[str, int]:
    """解析关系 id → (slug, version)。"""
    prefix = "rel_"
    if not relation_id.startswith(prefix):
        return (relation_id, 0)
    rest = relation_id[len(prefix):]
    parts = rest.rsplit("_v", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return (rest, 0)
    return (parts[0], int(parts[1]))

"""单元测试：entity_schema.py 的数据模型、状态枚举、ID 工具。

不依赖 zvec，纯函数测试。

运行：
    python3 scripts/tests/test_entity_schema.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows 控制台 UTF-8 兼容
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.entity_schema import (
    ENTITY_COLLECTIONS,
    STATE_ENUMS,
    VALID_TRANSITIONS,
    CharacterState,
    EntityDoc,
    EasterEggState,
    EventState,
    ForeshadowingState,
    ItemState,
    LocationState,
    StorylineState,
    TimelineState,
    _COLLECTION_PREFIX,
    get_collection_fields,
    is_valid_transition,
    make_entity_id,
    make_slug,
    parse_entity_id,
)


# --------------------------------------------------------------------------- #
# 状态枚举
# --------------------------------------------------------------------------- #


def test_character_states() -> None:
    assert CharacterState.INTRODUCED == "introduced"
    assert CharacterState.ACTIVE == "active"
    assert CharacterState.DEATH == "death"


def test_all_collections_have_states() -> None:
    for col in ENTITY_COLLECTIONS:
        assert col in STATE_ENUMS, f"{col} 缺少状态枚举"


def test_all_states_covered_in_transitions() -> None:
    for col in ENTITY_COLLECTIONS:
        assert col in VALID_TRANSITIONS, f"{col} 缺少状态转移定义"


# --------------------------------------------------------------------------- #
# 状态转移
# --------------------------------------------------------------------------- #


def test_valid_transitions_characters() -> None:
    assert is_valid_transition("characters", "introduced", "active")
    assert is_valid_transition("characters", "active", "major_change")
    assert is_valid_transition("characters", "active", "death")
    assert not is_valid_transition("characters", "introduced", "death")
    assert not is_valid_transition("characters", "death", "active")


def test_valid_transitions_foreshadowing() -> None:
    assert is_valid_transition("foreshadowing", "planted", "seeded")
    assert is_valid_transition("foreshadowing", "seeded", "resolved")
    assert not is_valid_transition("foreshadowing", "planted", "resolved")
    assert not is_valid_transition("foreshadowing", "resolved", "planted")


def test_valid_transitions_unknown_collection() -> None:
    assert not is_valid_transition("nonexistent", "a", "b")


# --------------------------------------------------------------------------- #
# EntityDoc
# --------------------------------------------------------------------------- #


def test_entity_doc_creation() -> None:
    doc = EntityDoc(
        id="char_test_v001",
        text="测试角色",
        collection="characters",
        state="introduced",
    )
    assert doc.id == "char_test_v001"
    assert doc.version == 1


def test_entity_doc_invalid_collection() -> None:
    try:
        EntityDoc(id="x", text="t", collection="nonexistent", state="s")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "未知 collection" in str(e)


# --------------------------------------------------------------------------- #
# ID 工具
# --------------------------------------------------------------------------- #


def test_make_entity_id() -> None:
    assert make_entity_id("characters", "lin_yuan") == "char_lin_yuan_v001"
    assert make_entity_id("foreshadowing", "F001", 3) == "fwd_F001_v003"


def test_parse_entity_id() -> None:
    prefix, slug, ver = parse_entity_id("char_lin_yuan_v003")
    assert prefix == "char"
    assert slug == "lin_yuan"
    assert ver == 3


def test_parse_entity_id_no_version() -> None:
    prefix, slug, ver = parse_entity_id("simple_id")
    assert ver == 0


def test_make_slug_chinese() -> None:
    slug = make_slug("林远")
    assert "林远" in slug or len(slug) > 0  # 应包含可读部分或 hash


def test_make_slug_empty() -> None:
    slug = make_slug("")
    assert len(slug) > 0  # hash 兜底


# --------------------------------------------------------------------------- #
# 字段定义
# --------------------------------------------------------------------------- #


def test_get_collection_fields_characters() -> None:
    fields = get_collection_fields("characters")
    names = [f[0] for f in fields]
    assert "name" in names
    assert "role" in names
    assert "state" in names


def test_get_collection_fields_foreshadowing() -> None:
    fields = get_collection_fields("foreshadowing")
    names = [f[0] for f in fields]
    assert "plant_ch" in names
    assert "resolve_ch" in names
    assert "type" in names


def test_all_collections_have_common_fields() -> None:
    for col in ENTITY_COLLECTIONS:
        fields = get_collection_fields(col)
        names = [f[0] for f in fields]
        assert "name" in names, f"{col} 缺少 name 字段"
        assert "state" in names, f"{col} 缺少 state 字段"


# --------------------------------------------------------------------------- #
# Test runner
# --------------------------------------------------------------------------- #


TEST_FUNCTIONS = [
    test_character_states,
    test_all_collections_have_states,
    test_all_states_covered_in_transitions,
    test_valid_transitions_characters,
    test_valid_transitions_foreshadowing,
    test_valid_transitions_unknown_collection,
    test_entity_doc_creation,
    test_entity_doc_invalid_collection,
    test_make_entity_id,
    test_parse_entity_id,
    test_parse_entity_id_no_version,
    test_make_slug_chinese,
    test_make_slug_empty,
    test_get_collection_fields_characters,
    test_get_collection_fields_foreshadowing,
    test_all_collections_have_common_fields,
]


def main() -> int:
    failed: list[str] = []
    for fn in TEST_FUNCTIONS:
        name = fn.__name__
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            print(f"  ✗ {name}: AssertionError: {e}")
            failed.append(name)
        except Exception as e:
            print(f"  ✗ {name}: {type(e).__name__}: {e}")
            failed.append(name)
    total = len(TEST_FUNCTIONS)
    print()
    print(f"{'PASS' if not failed else 'FAIL'}: {total - len(failed)}/{total} tests passed")
    if failed:
        print("Failed tests:")
        for name in failed:
            print(f"  - {name}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

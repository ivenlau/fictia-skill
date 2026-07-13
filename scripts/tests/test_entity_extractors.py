"""单元测试：entity_extractors.py 的提取器。

不依赖 zvec，使用临时项目目录。

运行：
    python3 scripts/tests/test_entity_extractors.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Windows 控制台 UTF-8 兼容
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.entity_extractors import (
    CharacterExtractor,
    EasterEggExtractor,
    EventExtractor,
    ForeshadowingExtractor,
    ItemExtractor,
    LocationExtractor,
    StorylineExtractor,
    TimelineExtractor,
    extract_all,
    extract_collection,
)


# --------------------------------------------------------------------------- #
# 工具：创建临时项目
# --------------------------------------------------------------------------- #


def _make_project() -> Path:
    """创建一个最小临时项目结构。"""
    tmp = Path(tempfile.mkdtemp())

    # characters
    chars = tmp / "characters"
    chars.mkdir()
    (chars / "protagonist.md").write_text(
        "---\nname: 林远\nrole: protagonist\nidentity: 落魄世家子弟\n"
        "traits:\n  - 坚韧\n  - 聪慧\nlanguage_style: 简洁克制\n"
        "relationships:\n  - name: 苏瑶\n    relation: 青梅竹马\n---\n\n"
        "林远是北域林家的后裔。\n",
        encoding="utf-8",
    )
    (chars / "antagonist.md").write_text(
        "---\nname: 黑衣人\nrole: antagonist\nidentity: 神秘势力\n"
        "traits:\n  - 狡诈\nlanguage_style: 低沉沙哑\n---\n\n"
        "黑衣人的真实身份未知。\n",
        encoding="utf-8",
    )
    supp = chars / "supporting"
    supp.mkdir()
    (supp / "mentor.md").write_text(
        "---\nname: 老者\nrole: core_supporting\nidentity: 隐世高人\n"
        "traits:\n  - 慈祥\n  - 深不可测\nlanguage_style: 平淡如水\n---\n\n"
        "老者在北域冰原隐居多年。\n",
        encoding="utf-8",
    )

    # world
    world = tmp / "world"
    world.mkdir()
    (world / "setting.md").write_text(
        "# 世界概况\n\n## 北域冰原\n\n北域冰原位于大陆最北端，终年冰雪覆盖。\n\n"
        "## 南境学院\n\n南境学院是大陆最大的修炼学府。\n",
        encoding="utf-8",
    )
    (world / "rules.md").write_text(
        "# 力量体系\n\n## 法器\n\n| 名称 | 等级 | 描述 |\n|------|------|------|\n"
        "| 神秘玉佩 | 未知 | 林远祖传之物 |\n\n"
        "## 修炼等级\n\n练气、筑基、金丹、元婴。\n",
        encoding="utf-8",
    )
    (world / "timeline.md").write_text(
        "# 时间线\n\n| 时间 | 事件 | 描述 |\n|------|------|------|\n"
        "| 第一年 | 林家灭门 | 林远失去家族 |\n| 第三年 | 入学 | 林远进入南境学院 |\n",
        encoding="utf-8",
    )

    # narrative-weave
    (tmp / "narrative-weave.md").write_text(
        "# 叙事编织\n\n## 伏笔表\n\n"
        "| 编号 | 类型 | 描述 | 埋设章节 |\n|------|------|------|----------|\n"
        "| F001 | 暗线 | 林远身世之谜 | ch01 |\n"
        "| F003 | 铺垫 | 神秘玉佩的来历 | ch05 |\n\n"
        "## 彩蛋表\n\n"
        "| 名称 | 类型 | 描述 | 揭示章节 |\n|------|------|------|----------|\n"
        "| 致敬经典 | 致敬 | 某经典桥段的化用 | ch20 |\n\n"
        "## 支线表\n\n"
        "| 名称 | 类型 | 描述 | 优先级 |\n|------|------|------|--------|\n"
        "| 感情线 | 感情 | 林远与苏瑶 | primary |\n"
        "| 身世暗线 | 悬疑 | 林远家族秘密 | secondary |\n",
        encoding="utf-8",
    )

    # outline
    outline = tmp / "outline" / "chapters"
    outline.mkdir(parents=True)
    (outline / "ch01.md").write_text(
        "# 第1章: 开端\n\n## 角色调度\n\n| 角色 | 起始状态 | 结束状态 |\n"
        "|------|---------|--------|\n| 林远 | introduced | active |\n\n"
        "## 场景序列\n\n### 场景1\n- 地点/时间：北域冰原 / 第一年冬天\n"
        "- 场景目标：林远在冰原中醒来\n- 角色：林远\n\n"
        "## 伏笔/支线/彩蛋指令\n\n- 埋设: F001 (林远身世之谜)\n",
        encoding="utf-8",
    )

    return tmp


# --------------------------------------------------------------------------- #
# CharacterExtractor
# --------------------------------------------------------------------------- #


def test_character_extractor() -> None:
    tmp = _make_project()
    try:
        docs = CharacterExtractor().extract(tmp)
        assert len(docs) == 3  # protagonist, antagonist, mentor
        names = [d.fields["name"] for d in docs]
        assert "林远" in names
        assert "黑衣人" in names
        assert "老者" in names

        # 检查林远的字段
        lin = [d for d in docs if d.fields["name"] == "林远"][0]
        assert lin.state == "introduced"
        assert lin.collection == "characters"
        assert "林家" in lin.text or "北域" in lin.text
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# LocationExtractor
# --------------------------------------------------------------------------- #


def test_location_extractor() -> None:
    tmp = _make_project()
    try:
        docs = LocationExtractor().extract(tmp)
        assert len(docs) >= 2
        names = [d.fields["name"] for d in docs]
        assert "北域冰原" in names
        assert "南境学院" in names
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# ItemExtractor
# --------------------------------------------------------------------------- #


def test_item_extractor() -> None:
    tmp = _make_project()
    try:
        docs = ItemExtractor().extract(tmp)
        assert len(docs) >= 1
        names = [d.fields["name"] for d in docs]
        assert "神秘玉佩" in names
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# ForeshadowingExtractor
# --------------------------------------------------------------------------- #


def test_foreshadowing_extractor() -> None:
    tmp = _make_project()
    try:
        docs = ForeshadowingExtractor().extract(tmp)
        assert len(docs) >= 2
        names = [d.fields["name"] for d in docs]
        assert "F001" in names
        assert "F003" in names
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# EasterEggExtractor
# --------------------------------------------------------------------------- #


def test_easter_egg_extractor() -> None:
    tmp = _make_project()
    try:
        docs = EasterEggExtractor().extract(tmp)
        assert len(docs) >= 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# StorylineExtractor
# --------------------------------------------------------------------------- #


def test_storyline_extractor() -> None:
    tmp = _make_project()
    try:
        docs = StorylineExtractor().extract(tmp)
        assert len(docs) >= 2
        names = [d.fields["name"] for d in docs]
        assert "感情线" in names
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# EventExtractor
# --------------------------------------------------------------------------- #


def test_event_extractor() -> None:
    tmp = _make_project()
    try:
        docs = EventExtractor().extract(tmp)
        assert len(docs) >= 1
        assert docs[0].state == "pending"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# TimelineExtractor
# --------------------------------------------------------------------------- #


def test_timeline_extractor() -> None:
    tmp = _make_project()
    try:
        docs = TimelineExtractor().extract(tmp)
        assert len(docs) >= 2
        names = [d.fields["name"] for d in docs]
        assert "林家灭门" in names
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# extract_all / extract_collection
# --------------------------------------------------------------------------- #


def test_extract_all() -> None:
    tmp = _make_project()
    try:
        results = extract_all(tmp)
        assert "characters" in results
        assert "locations" in results
        assert len(results["characters"]) == 3
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_extract_collection_unknown() -> None:
    docs = extract_collection(Path("/tmp"), "nonexistent")
    assert docs == []


# --------------------------------------------------------------------------- #
# Test runner
# --------------------------------------------------------------------------- #


TEST_FUNCTIONS = [
    test_character_extractor,
    test_location_extractor,
    test_item_extractor,
    test_foreshadowing_extractor,
    test_easter_egg_extractor,
    test_storyline_extractor,
    test_event_extractor,
    test_timeline_extractor,
    test_extract_all,
    test_extract_collection_unknown,
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

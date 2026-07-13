"""单元测试：outline_parser.py 的大纲解析。

不依赖 zvec，纯函数测试。使用临时大纲文件。

运行：
    python3 scripts/tests/test_outline_parser.py
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

from lib.outline_parser import (
    OutlineHints,
    format_outline_hints,
    parse_outline,
)


# --------------------------------------------------------------------------- #
# 基本解析
# --------------------------------------------------------------------------- #


def test_parse_empty_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "ch01.md"
        p.write_text("", encoding="utf-8")
        hints = parse_outline(1, p)
        assert hints.chapter == 1
        assert hints.target_words == 3000


def test_parse_missing_file() -> None:
    hints = parse_outline(1, Path("/nonexistent/ch01.md"))
    assert hints.chapter == 1
    assert hints.character_names == []


# --------------------------------------------------------------------------- #
# 目标字数
# --------------------------------------------------------------------------- #


def test_extract_target_words() -> None:
    content = """# 第1章: 测试

## 节奏与篇幅
- 目标字数：3500
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "ch01.md"
        p.write_text(content, encoding="utf-8")
        hints = parse_outline(1, p)
        assert hints.target_words == 3500


# --------------------------------------------------------------------------- #
# 角色调度
# --------------------------------------------------------------------------- #


def test_extract_character_dispatch() -> None:
    content = """# 第1章: 测试

## 角色调度

| 角色 | 起始状态 | 结束状态 | 弧光关键词 |
|------|---------|---------|-----------|
| 林远 | active | major_change | 成长 |
| 苏瑶 | absent | active | 重逢 |

## 场景序列
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "ch01.md"
        p.write_text(content, encoding="utf-8")
        hints = parse_outline(1, p)
        assert "林远" in hints.character_names
        assert "苏瑶" in hints.character_names
        assert hints.character_states.get("林远") == "active"


# --------------------------------------------------------------------------- #
# 场景序列
# --------------------------------------------------------------------------- #


def test_extract_scene_locations() -> None:
    content = """# 第1章: 测试

## 场景序列

### 场景1
- 地点：北域冰原
- 场景目标：林远遭遇伏击
- POV：林远

### 场景2
- 地点：南境学院
- 场景目标：苏瑶收到消息
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "ch01.md"
        p.write_text(content, encoding="utf-8")
        hints = parse_outline(1, p)
        assert "北域冰原" in hints.locations
        assert "南境学院" in hints.locations
        assert len(hints.scene_events) >= 2


# --------------------------------------------------------------------------- #
# 伏笔操作
# --------------------------------------------------------------------------- #


def test_extract_foreshadow_ops() -> None:
    content = """# 第1章: 测试

## 伏笔/支线/彩蛋指令

- 埋设: F003 (神秘玉佩的来历)
- 推进: F001 (林远身世线索在第三段提及)
- 回收: F002 (老者身份揭晓)

## 场景序列
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "ch01.md"
        p.write_text(content, encoding="utf-8")
        hints = parse_outline(1, p)
        assert len(hints.foreshadow_ops) >= 3
        ops_by_id = {op.fo_id: op for op in hints.foreshadow_ops}
        assert "F003" in ops_by_id
        assert ops_by_id["F003"].op == "plant"


# --------------------------------------------------------------------------- #
# 格式化
# --------------------------------------------------------------------------- #


def test_format_outline_hints() -> None:
    hints = OutlineHints(
        chapter=5,
        target_words=3000,
        character_names=["林远", "苏瑶"],
        locations=["北域冰原"],
    )
    output = format_outline_hints(hints)
    assert "ch05" in output
    assert "林远" in output
    assert "北域冰原" in output


# --------------------------------------------------------------------------- #
# Test runner
# --------------------------------------------------------------------------- #


TEST_FUNCTIONS = [
    test_parse_empty_file,
    test_parse_missing_file,
    test_extract_target_words,
    test_extract_character_dispatch,
    test_extract_scene_locations,
    test_extract_foreshadow_ops,
    test_format_outline_hints,
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

"""单元测试：lib.context.build_semantic_search。

聚焦：
  - zvec 未装时返回空字符串（graceful degradation）
  - lib.vector 不可用时返回空字符串
  - 输出格式：包含 ## 语义检索结果 / **查询** / **命中** 等关键标记
  - top_k 限制生效（命中数 ≤ top_k）

不依赖 zvec 已装。真实 round-trip 测试在 test_vector_zvec_integration.py 中
用 pytest.importorskip 守卫。

运行：
    python3 scripts/tests/test_context_semantic_search.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import context as C  # noqa: E402
from lib.vector import close_all_stores  # noqa: E402


# --------------------------------------------------------------------------- #
# Graceful degradation
# --------------------------------------------------------------------------- #


def _tmpdir():
    """创建临时目录，忽略 zvec rocksdb 文件锁导致的清理错误。"""
    import tempfile
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def test_returns_empty_when_no_project() -> None:
    """无 project.yaml / 无 zvec → 空字符串，不抛错。"""
    with _tmpdir() as tmp:
        out = C.build_semantic_search(Path(tmp), "林远在北域受伤", top_k=5)
        # zvec 缺 + 无项目根 → 返回空字符串
        assert out == ""
        close_all_stores()


def test_returns_empty_when_zvec_missing() -> None:
    """明确无 zvec → 空字符串。"""
    from lib import vector as V
    with _tmpdir() as tmp:
        tmp_path = Path(tmp)
        # 临时把 _ZVEC 置为 None 模拟"未装"
        saved_zvec = V._ZVEC
        V._ZVEC = None
        try:
            out = C.build_semantic_search(tmp_path, "test query", top_k=5)
            assert out == ""
        finally:
            V._ZVEC = saved_zvec
            close_all_stores()


def test_returns_empty_when_lib_vector_missing() -> None:
    """lib.vector 不可用时返回空字符串。"""
    with _tmpdir() as tmp:
        tmp_path = Path(tmp)
        # 把 lib.vector 从 sys.modules 临时移除
        saved = sys.modules.pop("lib.vector", None)
        try:
            # 重新 import lib.context 使其 build_semantic_search 重新尝试 import vector
            importlib.reload(C)
            out = C.build_semantic_search(tmp_path, "test query", top_k=5)
            assert out == ""
        finally:
            if saved is not None:
                sys.modules["lib.vector"] = saved
            # 再次 reload 恢复
            importlib.reload(C)
            close_all_stores()


# --------------------------------------------------------------------------- #
# 格式验证（用 mock lib.vector 模拟命中）
# --------------------------------------------------------------------------- #


def test_format_includes_required_sections() -> None:
    """模拟命中时输出包含 ## 语义检索结果 / **查询** / **命中** 等关键标记。"""
    with _tmpdir() as tmp:
        tmp_path = Path(tmp)
        # 构造 mock hit
        from dataclasses import dataclass

        @dataclass
        class MockHit:
            id: str
            collection: str
            text: str
            score: float
            metadata: dict

        mock_hits = [
            MockHit(id="ch03:0001", collection="chapters", text="林远在北域受伤。",
                    score=0.87, metadata={"chapter": 3}),
            MockHit(id="notes:0000", collection="notes", text="主题：林远背景。",
                    score=0.81, metadata={"note_id": "summary"}),
        ]

        class MockStore:
            def __init__(self, root, provider): pass
            def search(self, query, top_k=8, collection=None): return mock_hits[:top_k]

        # 把 lib.vector 替换为 stub
        import types

        def mock_open_store_with_default_provider(root, mode=None):
            return MockStore(root=root, provider="stub")

        fake_vec = types.ModuleType("lib.vector")
        fake_vec.open_store_with_default_provider = mock_open_store_with_default_provider
        fake_vec.VectorError = type("VectorError", (Exception,), {})
        sys.modules["lib.vector"] = fake_vec

        try:
            # 注意：不 reload(C)；build_semantic_search 内部用
            # `importlib.import_module("lib.vector")`，从 sys.modules 取到 fake_vec
            out = C.build_semantic_search(tmp_path, "林远在北域受伤", top_k=8)
            assert out != ""
            assert "## 语义检索结果" in out
            assert "**查询**：林远在北域受伤" in out
            assert "**命中**：2 条" in out
            assert "[chapters]" in out
            assert "[notes]" in out
            assert "0.87" in out
            assert "0.81" in out
            assert "第 3 章" in out
            assert "> 林远在北域受伤" in out
        finally:
            sys.modules.pop("lib.vector", None)


def test_top_k_limit() -> None:
    """top_k=1 → 最多 1 条命中。"""
    with _tmpdir() as tmp:
        tmp_path = Path(tmp)
        from dataclasses import dataclass

        @dataclass
        class MockHit:
            id: str
            collection: str
            text: str
            score: float
            metadata: dict

        mock_hits = [
            MockHit(id="ch01:0000", collection="chapters", text="hit 1", score=0.9, metadata={"chapter": 1}),
            MockHit(id="ch02:0000", collection="chapters", text="hit 2", score=0.8, metadata={"chapter": 2}),
            MockHit(id="ch03:0000", collection="chapters", text="hit 3", score=0.7, metadata={"chapter": 3}),
        ]

        class MockStore:
            def __init__(self, root, provider): pass
            def search(self, query, top_k=8, collection=None): return mock_hits[:top_k]

        import types
        def mock_open_store_with_default_provider(root, mode=None):
            return MockStore(root=root, provider="stub")
        fake_vec = types.ModuleType("lib.vector")
        fake_vec.open_store_with_default_provider = mock_open_store_with_default_provider
        fake_vec.VectorError = type("VectorError", (Exception,), {})
        sys.modules["lib.vector"] = fake_vec

        try:
            out = C.build_semantic_search(tmp_path, "query", top_k=1)
            assert "**命中**：1 条" in out
            assert "hit 1" in out
            assert "hit 2" not in out
            assert "hit 3" not in out
        finally:
            sys.modules.pop("lib.vector", None)


def test_empty_hits_returns_empty() -> None:
    """无命中时返回空字符串。"""
    with _tmpdir() as tmp:
        tmp_path = Path(tmp)
        class MockStore:
            def __init__(self, root, provider): pass
            def search(self, query, top_k=8, collection=None): return []

        import types
        def mock_open_store_with_default_provider(root, mode=None):
            return MockStore(root=root, provider="stub")
        fake_vec = types.ModuleType("lib.vector")
        fake_vec.open_store_with_default_provider = mock_open_store_with_default_provider
        fake_vec.VectorError = type("VectorError", (Exception,), {})
        sys.modules["lib.vector"] = fake_vec

        try:
            out = C.build_semantic_search(tmp_path, "query", top_k=5)
            assert out == ""
        finally:
            sys.modules.pop("lib.vector", None)


# --------------------------------------------------------------------------- #
# Test runner
# --------------------------------------------------------------------------- #


TEST_FUNCTIONS = [
    test_returns_empty_when_no_project,
    test_returns_empty_when_zvec_missing,
    test_returns_empty_when_lib_vector_missing,
    test_format_includes_required_sections,
    test_top_k_limit,
    test_empty_hits_returns_empty,
]


def main() -> int:
    failed: list[str] = []
    for fn in TEST_FUNCTIONS:
        name = fn.__name__
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            # 打印详细 traceback 帮助定位
            import traceback
            tb = traceback.format_exc()
            # 找出最后一行 assert
            for line in tb.splitlines():
                if "assert " in line:
                    print(f"  ✗ {name}: {line.strip()}")
                    break
            else:
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
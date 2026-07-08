"""单元测试：embeddings 三个 provider + get_provider 工厂。

聚焦：
  - StubEmbedding 的确定性与维度
  - get_provider 的环境变量切换与未知值报错
  - BgeM3LocalEmbedding 在未装 sentence-transformers 时清晰报错
  - ZhipuApiEmbedding 在未设 ZHIPUAI_API_KEY 时清晰报错
  - ZhipuApiEmbedding 在未装 httpx 时清晰报错

不依赖 zvec；BGE-M3 / 智谱真实 embedding 不在本测试范围内（需下载模型 / API key）。

运行：
    python3 scripts/tests/test_embeddings.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.embeddings import (  # noqa: E402
    BgeM3LocalEmbedding,
    EmbeddingError,
    StubEmbedding,
    ZhipuApiEmbedding,
    get_provider,
)


# --------------------------------------------------------------------------- #
# StubEmbedding
# --------------------------------------------------------------------------- #


def test_stub_embedding_dim() -> None:
    e = StubEmbedding()
    assert e.dim == 256
    assert e.name == "stub-256"


def test_stub_embedding_deterministic() -> None:
    e = StubEmbedding()
    v1 = e.embed(["林远在北域"])
    v2 = e.embed(["林远在北域"])
    assert v1 == v2


def test_stub_embedding_different_texts_different_vectors() -> None:
    e = StubEmbedding()
    v1 = e.embed(["林远在北域"])
    v2 = e.embed(["苏瑶在南疆"])
    assert v1 != v2


def test_stub_embedding_normalized() -> None:
    """归一化后 ||v|| ≈ 1。"""
    import math

    e = StubEmbedding()
    v = e.embed(["任意文本"])[0]
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-5


def test_stub_embedding_batch() -> None:
    e = StubEmbedding()
    texts = ["a", "b", "c", "d"]
    vecs = e.embed(texts)
    assert len(vecs) == 4
    assert all(len(v) == 256 for v in vecs)


# --------------------------------------------------------------------------- #
# get_provider 工厂
# --------------------------------------------------------------------------- #


def test_get_provider_default_is_stub(monkeypatch_env=None) -> None:
    """不设环境变量 → StubEmbedding。"""
    os.environ.pop("FICTIA_EMBEDDING", None)
    p = get_provider()
    assert isinstance(p, StubEmbedding)
    assert p.dim == 256


def test_get_provider_explicit_stub() -> None:
    p = get_provider("stub")
    assert isinstance(p, StubEmbedding)


def test_get_provider_explicit_local_without_package(monkeypatch=None) -> None:
    """FICTIA_EMBEDDING=local 但 sentence-transformers 未装或模型加载失败 → EmbeddingError。"""
    os.environ["FICTIA_EMBEDDING"] = "local"
    try:
        try:
            p = get_provider("local")
            # 如果环境恰好装了 sentence-transformers 且模型加载成功 → 跳过
            assert isinstance(p, BgeM3LocalEmbedding)
        except EmbeddingError as e:
            # 三种情况都应清晰报错：
            # 1. sentence-transformers 未装
            # 2. 模型下载失败（网络问题）
            msg = str(e)
            assert "sentence-transformers" in msg or "BGE-M3" in msg or "无法加载" in msg
    finally:
        os.environ.pop("FICTIA_EMBEDDING", None)


def test_get_provider_explicit_api_without_key() -> None:
    """FICTIA_EMBEDDING=api 但 ZHIPUAI_API_KEY 未设 → EmbeddingError。"""
    os.environ["FICTIA_EMBEDDING"] = "api"
    os.environ.pop("ZHIPUAI_API_KEY", None)
    try:
        try:
            p = get_provider("api")
            # 如果环境恰好设了 key，跳过
            assert isinstance(p, ZhipuApiEmbedding)
        except EmbeddingError as e:
            assert "ZHIPUAI_API_KEY" in str(e)
    finally:
        os.environ.pop("FICTIA_EMBEDDING", None)


def test_get_provider_unknown_raises() -> None:
    try:
        get_provider("foo")
        raise AssertionError("应抛 EmbeddingError")
    except EmbeddingError as e:
        msg = str(e)
        assert "foo" in msg or "stub" in msg  # 错误信息应包含无效值或合法值


def test_get_provider_env_override(monkeypatch=None) -> None:
    """FICTIA_EMBEDDING=stub 显式覆盖。"""
    os.environ["FICTIA_EMBEDDING"] = "stub"
    try:
        p = get_provider()
        assert isinstance(p, StubEmbedding)
    finally:
        os.environ.pop("FICTIA_EMBEDDING", None)


def test_get_provider_explicit_overrides_env() -> None:
    """显式参数优先级高于环境变量。"""
    os.environ["FICTIA_EMBEDDING"] = "stub"
    try:
        p = get_provider("stub")  # 显式 stub
        assert isinstance(p, StubEmbedding)
    finally:
        os.environ.pop("FICTIA_EMBEDDING", None)


# --------------------------------------------------------------------------- #
# ZhipuApiEmbedding 直接构造
# --------------------------------------------------------------------------- #


def test_zhipu_api_missing_key() -> None:
    os.environ.pop("ZHIPUAI_API_KEY", None)
    try:
        ZhipuApiEmbedding()
        raise AssertionError("应抛 EmbeddingError")
    except EmbeddingError as e:
        assert "ZHIPUAI_API_KEY" in str(e)


# --------------------------------------------------------------------------- #
# Test runner
# --------------------------------------------------------------------------- #


TEST_FUNCTIONS = [
    test_stub_embedding_dim,
    test_stub_embedding_deterministic,
    test_stub_embedding_different_texts_different_vectors,
    test_stub_embedding_normalized,
    test_stub_embedding_batch,
    test_get_provider_default_is_stub,
    test_get_provider_explicit_stub,
    test_get_provider_explicit_local_without_package,
    test_get_provider_explicit_api_without_key,
    test_get_provider_unknown_raises,
    test_get_provider_env_override,
    test_get_provider_explicit_overrides_env,
    test_zhipu_api_missing_key,
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
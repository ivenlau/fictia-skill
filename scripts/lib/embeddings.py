"""Embedding provider 协议与三个实现。

FICTIA_EMBEDDING 环境变量（或 get_provider 显式参数）控制实际使用的 provider：
    stub（默认）→ StubEmbedding，hash-based 256 维，无语义，仅用于跑通工具链
    local        → BgeM3LocalEmbedding，BAAI/bge-m3，1024 维，需 sentence-transformers
    api          → ZhipuApiEmbedding，智谱 embedding-2，1024 维，需 ZHIPUAI_API_KEY

local 与 api 都是 1024 维，切换时不需要重建索引。
stub → local/api 切换时必须重建索引（dim 不同）。
"""
from __future__ import annotations

import hashlib
import math
import os
import struct
from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    """统一的 embedding 协议。

    所有 provider 必须实现：
      - name: 人类可读名称，含模型与维度
      - dim:  向量维度
      - embed(texts) -> list[list[float]]: 批量嵌入
    """

    name: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddingError(Exception):
    """embedding 相关错误的统一异常类型。"""


# --------------------------------------------------------------------------- #
# Stub：hash-based deterministic embedding
# --------------------------------------------------------------------------- #


class StubEmbedding:
    """确定性 hash embedding，256 维。零依赖、零 API key。

    用 SHA-256 派生稳定伪随机向量；同文本永远得到同向量，不同文本得到不同向量。
    **无语义**——只是占位实现，用于跑通工具链。
    """

    name = "stub-256"
    dim = 256

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_to_vector(t, self.dim) for t in texts]


def _hash_to_vector(text: str, dim: int) -> list[float]:
    """把文本通过 SHA-256 派生稳定伪随机向量，归一化到单位球面。

    算法：
      1. text → UTF-8 → sha256 → seed
      2. 反复 sha256(seed + counter) 产出 32 字节 block
      3. 每个 block 切 8 个 uint32，每个 uint32 映射到 [-1, 1] 区间
         （直接 unpack 成 float32 会随机溢出成 inf/nan，故用 uint32 转换）
      4. L2 归一化

    同文本永远得到同向量；不同文本得到不同向量；归一化后余弦相似度有意义。
    """
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    n_rounds = math.ceil(dim / 8)  # 每轮产出 8 个 float，共需 ceil(dim/8) 轮
    vec: list[float] = []
    for i in range(n_rounds):
        block = hashlib.sha256(seed + struct.pack("<I", i)).digest()
        for j in range(0, 32, 4):
            if len(vec) >= dim:
                break
            # uint32 → [0, 1) → [-1, 1)
            u = struct.unpack("<I", block[j : j + 4])[0]
            vec.append((u / 0xFFFFFFFF) * 2.0 - 1.0)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# --------------------------------------------------------------------------- #
# Local: BGE-M3 via sentence-transformers
# --------------------------------------------------------------------------- #


class BgeM3LocalEmbedding:
    """BAAI/bge-m3 via sentence-transformers。本地离线、中文 SOTA。

    安装：pip install sentence-transformers
    首次使用自动下载模型到 ~/.cache/huggingface/（~2.3GB）。
    硬件需求：CPU 4GB+ 可用内存；GPU 4GB+ 显存可大幅加速。
    """

    name = "bge-m3-1024"
    dim = 1024
    _MODEL_ID = "BAAI/bge-m3"

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:
            raise EmbeddingError(
                "未安装 sentence-transformers。请运行 `pip install sentence-transformers` 后重试。"
            ) from e
        try:
            self._model = SentenceTransformer(self._MODEL_ID)
        except Exception as e:
            # 网络问题、模型下载失败等都归一为 EmbeddingError
            raise EmbeddingError(
                f"无法加载 BGE-M3 模型（{self._MODEL_ID}）：{e}\n"
                "可能原因：网络问题（无法访问 huggingface.co）、磁盘空间不足、或 model id 错误。"
            ) from e

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        # normalize_embeddings=True 让余弦相似度等价于点积（zvec 默认用 cosine）
        return self._model.encode(list(texts), normalize_embeddings=True).tolist()


# --------------------------------------------------------------------------- #
# Server: 本地常驻 embedding 服务
# --------------------------------------------------------------------------- #


class ServerEmbedding:
    """连接本地常驻 embedding 服务，避免每次冷启动加载模型。

    环境变量：
        FICTIA_EMBED_SERVER — 服务地址，默认 http://127.0.0.1:8700

    安装：pip install httpx
    """

    name = "server-bge-m3-1024"
    dim = 1024

    def __init__(self) -> None:
        self._url = os.environ.get("FICTIA_EMBED_SERVER", "http://127.0.0.1:8700")
        try:
            import httpx  # type: ignore
        except ImportError as e:
            raise EmbeddingError(
                "未安装 httpx。请运行 `pip install httpx` 后重试。"
            ) from e
        # 验证服务是否可达
        try:
            resp = httpx.get(f"{self._url}/health", timeout=5)
            resp.raise_for_status()
            info = resp.json()
            self.dim = info.get("dim", 1024)
            self.name = f"server-{info.get('model', 'unknown')}-{self.dim}"
        except Exception as e:
            raise EmbeddingError(
                f"无法连接 embedding 服务 {self._url}：{e}\n"
                "请先启动服务：python embed_server.py --port 8700"
            ) from e

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import httpx  # type: ignore

        resp = httpx.post(
            f"{self._url}/embed",
            json={"texts": list(texts)},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["vectors"]


# --------------------------------------------------------------------------- #
# API: 智谱 embedding-2 via HTTP
# --------------------------------------------------------------------------- #


class ZhipuApiEmbedding:
    """智谱 embedding-2 via HTTP API。云端、中文 SOTA。

    安装：pip install httpx
    环境变量：ZHIPUAI_API_KEY
    端点：https://open.bigmodel.cn/api/paas/v4/embeddings
    模型：embedding-2（1024 维）
    """

    name = "zhipu-embedding-2-1024"
    dim = 1024
    API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
    MODEL = "embedding-2"
    ENV_KEY = "ZHIPUAI_API_KEY"

    def __init__(self) -> None:
        self._api_key = os.environ.get(self.ENV_KEY)
        if not self._api_key:
            raise EmbeddingError(
                f"未设置 {self.ENV_KEY} 环境变量。请先 `export {self.ENV_KEY}=your_key_here`。"
            )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            import httpx  # type: ignore
        except ImportError as e:
            raise EmbeddingError(
                "未安装 httpx。请运行 `pip install httpx` 后重试。"
            ) from e

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.MODEL, "input": list(texts)}
        try:
            resp = httpx.post(self.API_URL, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise EmbeddingError(f"智谱 API 请求失败：{e}") from e

        data = resp.json()
        try:
            return [item["embedding"] for item in data["data"]]
        except (KeyError, TypeError) as e:
            raise EmbeddingError(f"智谱 API 返回结构异常：{data}") from e


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #


_VALID_MODES = ("stub", "local", "api", "server")


def get_provider(name: str | None = None) -> EmbeddingProvider:
    """获取 embedding provider 实例。

    解析顺序：
      1. 显式参数 name
      2. 环境变量 FICTIA_EMBEDDING
      3. 默认 "stub"

    取值：stub | local | api
    """
    mode = (name or os.environ.get("FICTIA_EMBEDDING") or "stub").lower().strip()
    if mode not in _VALID_MODES:
        raise EmbeddingError(
            f"未知 FICTIA_EMBEDDING={mode!r}；可选值：{', '.join(_VALID_MODES)}"
        )
    if mode == "stub":
        return StubEmbedding()
    if mode == "local":
        return BgeM3LocalEmbedding()
    if mode == "api":
        return ZhipuApiEmbedding()
    if mode == "server":
        return ServerEmbedding()
    # unreachable
    raise EmbeddingError(f"未知 mode: {mode}")


def get_provider_name() -> str:
    """返回当前应使用的 provider 名称（不实例化）。"""
    mode = (os.environ.get("FICTIA_EMBEDDING") or "stub").lower().strip()
    return mode if mode in _VALID_MODES else "stub"
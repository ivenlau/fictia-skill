"""常驻 BGE-M3 Embedding + Entity 服务。

启动后模型只加载一次，entity collection 一次打开，后续请求走 HTTP，毫秒级响应。

用法：
    python embed_server.py [--port 8700] [--host 127.0.0.1]

API：
    POST /embed           {"texts": ["文本1", "文本2"]}  → {"vectors": [[...], [...]]}
    POST /search          {"query": "查询", "collection": "chapters", "top_k": 5} → {"results": [...]}
    POST /entity/search   {"query": "查询", "collection": "characters", "top_k": 5} → {"results": [...]}
    GET  /health          → {"status": "ok", "dim": 1024}
"""

import argparse
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

# --------------------------------------------------------------------------- #
# 模型加载（全局，只执行一次）
# --------------------------------------------------------------------------- #

print("[embed-server] 加载 BGE-M3 模型...", flush=True)
t0 = time.time()

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-m3")
DIM = model.get_sentence_embedding_dimension()

print(f"[embed-server] 模型加载完成 ({time.time() - t0:.1f}s, dim={DIM})", flush=True)

# --------------------------------------------------------------------------- #
# zvec 集成（惰性加载）
# --------------------------------------------------------------------------- #

_zvec_collections = {}


def get_collection(name: str):
    """惰性打开 zvec collection，缓存复用。"""
    if name in _zvec_collections:
        return _zvec_collections[name]

    try:
        import zvec
    except ImportError:
        return None

    # 查找项目目录
    project_root = _find_project_root()
    if not project_root:
        return None

    path = project_root / ".fictia" / "zvec" / name
    if not path.exists():
        return None

    try:
        col = zvec.open(path=str(path))
        _zvec_collections[name] = col
        return col
    except Exception:
        return None


def _find_project_root() -> Path | None:
    """从当前目录向上查找 project.yaml。"""
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents]:
        if (d / "project.yaml").exists():
            return d
    return None


# --------------------------------------------------------------------------- #
# FastAPI App
# --------------------------------------------------------------------------- #

app = FastAPI(title="Fictia Embedding Server")


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    dim: int


class SearchRequest(BaseModel):
    query: str
    collection: str = "chapters"
    top_k: int = 5


class SearchResult(BaseModel):
    id: str
    score: float
    text: str
    metadata: dict = {}


class SearchResponse(BaseModel):
    results: list[SearchResult]


@app.get("/health")
def health():
    return {"status": "ok", "dim": DIM, "model": "BAAI/bge-m3"}


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    vectors = model.encode(req.texts, normalize_embeddings=True)
    return EmbedResponse(vectors=vectors.tolist(), dim=DIM)


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    import zvec
    col = get_collection(req.collection)
    if col is None:
        return SearchResponse(results=[])

    q_vec = model.encode([req.query], normalize_embeddings=True)[0].tolist()
    hits = col.query(zvec.VectorQuery("vec", vector=q_vec), topk=req.top_k)

    results = []
    for hit in hits:
        # zvec 0.5 返回 Doc 对象，有 id 和 fields 属性
        if hasattr(hit, "id"):
            doc_id = hit.id
            fields = hit.fields or {}
            score = getattr(hit, "score", 0.0)
        else:
            doc_id = hit.get("_zvec_g_doc_id", "")
            fields = hit
            score = hit.get("_score", 0.0)

        results.append(
            SearchResult(
                id=doc_id,
                score=score,
                text=fields.get("text", ""),
                metadata={
                    k: v
                    for k, v in fields.items()
                    if k != "text" and not k.startswith("_")
                },
            )
        )
    return SearchResponse(results=results)


# --------------------------------------------------------------------------- #
# Entity 搜索（常驻 entity store，避免每次 CLI 都重新打开 collection）
# --------------------------------------------------------------------------- #

_entity_store = None


def get_entity_store():
    """惰性初始化 entity store（只打开一次 collection）。"""
    global _entity_store
    if _entity_store is not None:
        return _entity_store

    project_root = _find_project_root()
    if not project_root:
        return None

    # 构造一个简单的 provider 包装
    class _ServerProvider:
        name = "server-bge-m3-1024"
        dim = DIM
        def embed(self, texts):
            return model.encode(list(texts), normalize_embeddings=True).tolist()

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from lib.entity_store import EntityStore
        base = project_root / ".fictia" / "zvec"
        _entity_store = EntityStore(base=base, provider=_ServerProvider())
        return _entity_store
    except Exception as e:
        print(f"[embed-server] Entity store init failed: {e}", flush=True)
        return None


class EntitySearchRequest(BaseModel):
    query: str
    collection: str | None = None
    top_k: int = 5
    state: str | None = None


class EntitySearchResult(BaseModel):
    name: str
    state: str
    collection: str
    score: float
    text: str


class EntitySearchResponse(BaseModel):
    results: list[EntitySearchResult]


@app.post("/entity/search", response_model=EntitySearchResponse)
def entity_search(req: EntitySearchRequest):
    store = get_entity_store()
    if store is None:
        return EntitySearchResponse(results=[])

    from lib.entity_retriever import EntityRetriever
    retriever = EntityRetriever(store)
    results = retriever.retrieve_on_demand(
        req.query,
        collection=req.collection,
        top_k=req.top_k,
        state=req.state,
    )

    return EntitySearchResponse(
        results=[
            EntitySearchResult(
                name=e.get("name", "?"),
                state=e.get("state", "?"),
                collection=e.get("_collection", req.collection or "?"),
                score=e.get("score", 0.0),
                text=e.get("text", "")[:200],
            )
            for e in results
        ]
    )


class WritingSpaceRequest(BaseModel):
    chapter: int


class WritingSpaceResponse(BaseModel):
    content: str


@app.post("/entity/writing-space", response_model=WritingSpaceResponse)
def entity_writing_space(req: WritingSpaceRequest):
    store = get_entity_store()
    if store is None:
        return WritingSpaceResponse(content="（entity store 不可用）")

    project_root = _find_project_root()
    if not project_root:
        return WritingSpaceResponse(content="（未找到项目目录）")

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from lib.writing_space import WritingSpaceAssembler
        assembler = WritingSpaceAssembler(project_root, store)
        content = assembler.assemble(req.chapter)
        return WritingSpaceResponse(content=content)
    except Exception as e:
        return WritingSpaceResponse(content=f"（组装失败：{e}）")


# --------------------------------------------------------------------------- #
# 启动
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fictia Embedding Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8700)
    args = parser.parse_args()

    print(f"[embed-server] 启动服务 http://{args.host}:{args.port}", flush=True)
    print(f"[embed-server] API 文档 http://{args.host}:{args.port}/docs", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")

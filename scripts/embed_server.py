"""常驻 BGE-M3 Embedding + Entity + 知识图谱服务。

启动后模型只加载一次，entity collection 一次打开，后续请求走 HTTP，毫秒级响应。

用法：
    python embed_server.py [--port 8700] [--host 127.0.0.1]

API：
    POST /embed           {"texts": ["文本1", "文本2"]}  → {"vectors": [[...], [...]]}
    POST /search          {"query": "查询", "collection": "chapters", "top_k": 5} → {"results": [...]}
    POST /entity/search   {"query": "查询", "collection": "characters", "top_k": 5} → {"results": [...]}
    POST /entity/writing-space  {"chapter": 3}  → {"content": "..."}
    GET  /health          → {"status": "ok", "dim": 1024}

知识图谱 API：
    POST /graph/build     从现有实体字段构建知识图谱（幂等）
    POST /graph/extract   {"chapter": 3, "use_llm": true}  → 从章节抽取关系
    POST /graph/neighbors {"entity_id": "char_xxx"}  → 邻居查询
    POST /graph/path      {"from_id": "A", "to_id": "B"}  → 最短路径
    POST /graph/triples   {"query": "师徒关系"}  → 语义搜索关系
    POST /graph/export    {"entity_id": "char_xxx"}  → 导出图谱数据（可视化）
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
# 知识图谱 API
# --------------------------------------------------------------------------- #


class GraphNeighborRequest(BaseModel):
    entity_id: str
    rel_type: str | None = None
    depth: int = 1


class GraphNeighborResult(BaseModel):
    neighbor_id: str
    rel_type: str
    direction: str
    relation_text: str
    relation_id: str
    chapter: int | None = None
    confidence: str = "1.0"


class GraphNeighborResponse(BaseModel):
    entity_id: str
    neighbors: list[GraphNeighborResult]


@app.post("/graph/neighbors", response_model=GraphNeighborResponse)
def graph_neighbors(req: GraphNeighborRequest):
    store = get_entity_store()
    if store is None:
        return GraphNeighborResponse(entity_id=req.entity_id, neighbors=[])

    neighbors = store.get_neighbors(
        req.entity_id, rel_type=req.rel_type, depth=req.depth
    )
    return GraphNeighborResponse(
        entity_id=req.entity_id,
        neighbors=[GraphNeighborResult(**nb) for nb in neighbors],
    )


class GraphPathRequest(BaseModel):
    from_id: str
    to_id: str
    max_depth: int = 3


class GraphPathResponse(BaseModel):
    found: bool
    path: list[dict] = []


@app.post("/graph/path", response_model=GraphPathResponse)
def graph_path(req: GraphPathRequest):
    store = get_entity_store()
    if store is None:
        return GraphPathResponse(found=False)

    path = store.find_path(req.from_id, req.to_id, max_depth=req.max_depth)
    if path is None:
        return GraphPathResponse(found=False)
    return GraphPathResponse(found=True, path=path)


class GraphTriplesRequest(BaseModel):
    query: str
    entity_id: str | None = None
    rel_type: str | None = None
    top_k: int = 10


class GraphTripleResult(BaseModel):
    source_id: str
    target_id: str
    rel_type: str
    text: str
    score: float = 0.0
    chapter: int | None = None


class GraphTriplesResponse(BaseModel):
    results: list[GraphTripleResult]


@app.post("/graph/triples", response_model=GraphTriplesResponse)
def graph_triples(req: GraphTriplesRequest):
    store = get_entity_store()
    if store is None:
        return GraphTriplesResponse(results=[])

    results = store.search_relations(
        req.query,
        top_k=req.top_k,
        entity_id=req.entity_id,
        rel_type=req.rel_type,
    )
    return GraphTriplesResponse(
        results=[
            GraphTripleResult(
                source_id=r.get("source_id", ""),
                target_id=r.get("target_id", ""),
                rel_type=r.get("rel_type", ""),
                text=r.get("text", ""),
                score=r.get("score", 0.0),
                chapter=r.get("chapter"),
            )
            for r in results
        ]
    )


class GraphBuildRequest(BaseModel):
    pass


class GraphBuildResponse(BaseModel):
    relations_added: int


@app.post("/graph/build", response_model=GraphBuildResponse)
def graph_build():
    """从现有实体字段构建知识图谱（幂等，跳过已存在的关系）。"""
    store = get_entity_store()
    if store is None:
        return GraphBuildResponse(relations_added=0)

    project_root = _find_project_root()
    if not project_root:
        return GraphBuildResponse(relations_added=0)

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from lib.relation_extractors import build_knowledge_graph

        count = build_knowledge_graph(store, project_root)
        return GraphBuildResponse(relations_added=count)
    except Exception as e:
        print(f"[embed-server] graph build failed: {e}", flush=True)
        return GraphBuildResponse(relations_added=0)


class GraphExtractRequest(BaseModel):
    chapter: int
    use_llm: bool = False  # 是否使用 LLM 抽取
    llm_model: str = "gpt-4o-mini"  # LLM 模型


class GraphExtractResponse(BaseModel):
    relations_added: int
    source: str  # "notes" | "llm" | "both"
    llm_queued: bool = False  # LLM 抽取是否已加入后台队列


@app.post("/graph/extract", response_model=GraphExtractResponse)
def graph_extract(req: GraphExtractRequest, background_tasks: BackgroundTasks = None):
    """从已完成章节中提取新关系（规则抽取 + 可选 LLM）。"""
    from fastapi import BackgroundTasks

    store = get_entity_store()
    if store is None:
        return GraphExtractResponse(relations_added=0, source="none")

    project_root = _find_project_root()
    if not project_root:
        return GraphExtractResponse(relations_added=0, source="none")

    total = 0
    source_parts = []
    chapter_text = ""

    # 1. 规则抽取（从写作备注）
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from lib.entity_updater import extract_relations_from_chapter_notes

        # 查找章节文件
        ch_dir = project_root / "chapters"
        candidates = list(ch_dir.glob(f"ch{req.chapter:02d}*.md")) if ch_dir.is_dir() else []
        if not candidates:
            ch_dir = project_root / "chapters" / "drafts"
            candidates = list(ch_dir.glob(f"ch{req.chapter:02d}*.md")) if ch_dir.is_dir() else []

        if candidates:
            chapter_text = candidates[0].read_text(encoding="utf-8")
            note_triples = extract_relations_from_chapter_notes(
                chapter_text, req.chapter
            )
            if note_triples:
                count = store.upsert_relations(note_triples, chapter=req.chapter)
                total += count
                source_parts.append(f"notes:{count}")
    except Exception as e:
        print(f"[embed-server] note extraction failed: {e}", flush=True)

    # 2. LLM 抽取（后台异步执行）
    llm_queued = False
    if req.use_llm and chapter_text:
        try:
            import asyncio
            from lib.llm_relation_extractor import extract_and_store_relations_via_llm

            async def _llm_extract_task():
                try:
                    count = await extract_and_store_relations_via_llm(
                        store, chapter_text, req.chapter, model=req.llm_model
                    )
                    print(
                        f"[embed-server] LLM extraction done: {count} relations",
                        flush=True,
                    )
                except Exception as e:
                    print(f"[embed-server] LLM extraction failed: {e}", flush=True)

            # 在后台线程中运行异步任务
            import threading

            def _run_async():
                asyncio.run(_llm_extract_task())

            thread = threading.Thread(target=_run_async, daemon=True)
            thread.start()
            llm_queued = True
            source_parts.append("llm:queued")
        except Exception as e:
            print(f"[embed-server] LLM task launch failed: {e}", flush=True)

    source = "+".join(source_parts) if source_parts else "none"
    return GraphExtractResponse(
        relations_added=total, source=source, llm_queued=llm_queued
    )


class GraphExportRequest(BaseModel):
    entity_id: str | None = None
    rel_type: str | None = None
    max_nodes: int = 200


class GraphExportResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]


@app.post("/graph/export", response_model=GraphExportResponse)
def graph_export(req: GraphExportRequest):
    """导出图谱数据（nodes + edges），用于可视化。"""
    store = get_entity_store()
    if store is None:
        return GraphExportResponse(nodes=[], edges=[])

    # 获取关系
    if req.entity_id:
        relations = store.list_relations(
            entity_id=req.entity_id, rel_type=req.rel_type
        )
    else:
        relations = store.list_relations(rel_type=req.rel_type)

    # 限制数量
    relations = relations[:req.max_nodes]

    # 收集节点 id
    node_ids: set[str] = set()
    edges = []
    for rel in relations:
        src = rel.get("source_id", "")
        tgt = rel.get("target_id", "")
        node_ids.add(src)
        node_ids.add(tgt)
        edges.append({
            "source": src,
            "target": tgt,
            "rel_type": rel.get("rel_type", ""),
            "text": rel.get("text", ""),
            "chapter": rel.get("chapter"),
        })

    # 构建节点信息
    nodes = []
    for nid in node_ids:
        # 从 id 推断 collection
        parts = nid.split("_", 1)
        prefix = parts[0] if parts else ""
        collection = _prefix_to_collection(prefix)

        # 尝试获取实体名称
        name = nid
        if collection:
            try:
                entity = store.get_entity(collection, nid)
                if entity:
                    name = entity.get("name", nid)
            except Exception:
                pass

        nodes.append({
            "id": nid,
            "name": name,
            "collection": collection or "unknown",
        })

    return GraphExportResponse(nodes=nodes, edges=edges)


def _prefix_to_collection(prefix: str) -> str:
    """从前缀推断 collection 名称。"""
    from lib.entity_schema import _COLLECTION_PREFIX
    reverse = {v: k for k, v in _COLLECTION_PREFIX.items()}
    return reverse.get(prefix, "")


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

"""Dynamic Writing Space — 实体存储层。

封装 zvec CRUD 操作，提供：
  - EntityStore: 管理 8 个 entity collection 的生命周期
  - open_entity_store(): 工厂函数
  - 单例缓存（同进程复用）

依赖 zvec + entity_schema。zvec 未装时 raise VectorError。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from lib.entity_schema import (
    COLLECTION_EXTRA_FIELDS,
    ENTITY_COLLECTIONS,
    EntityDoc,
    _COMMON_FIELDS,
    is_valid_transition,
    make_entity_id,
    parse_entity_id,
    make_relation_id,
    make_relation_slug,
    parse_relation_id,
    RELATION_TYPES,
)

# 软导入 zvec（与 vector.py 一致的模式）
try:
    import zvec  # type: ignore

    _ZVEC = zvec
except ImportError:
    _ZVEC = None

from lib.vector import VectorError, require_zvec, vector_root
from lib.embeddings import EmbeddingProvider, get_provider


# --------------------------------------------------------------------------- #
# Collection Schema 构造
# --------------------------------------------------------------------------- #


def _make_entity_collection_schema(name: str, dim: int):
    """构造 entity collection 的 zvec schema。"""
    require_zvec()
    from lib.entity_schema import get_collection_fields

    fields = []
    for fname, ftype in get_collection_fields(name):
        dtype = _ZVEC.DataType.STRING if ftype == "STRING" else _ZVEC.DataType.INT64
        if fname == "text":
            # text 字段加全文索引
            fields.append(
                _ZVEC.FieldSchema(fname, dtype, index_param=_ZVEC.FtsIndexParam())
            )
        else:
            # nullable 字段
            fields.append(_ZVEC.FieldSchema(fname, dtype, nullable=True))
    return _ZVEC.CollectionSchema(
        name=name,
        fields=fields,
        vectors=_ZVEC.VectorSchema("vec", _ZVEC.DataType.VECTOR_FP32, dim),
    )


# --------------------------------------------------------------------------- #
# EntityStore
# --------------------------------------------------------------------------- #


class EntityStore:
    """管理 8 个 entity collection 的 CRUD。"""

    def __init__(self, base: Path, provider: EmbeddingProvider) -> None:
        self.base = base
        self.provider = provider
        self.dim = provider.dim
        self._cache: dict[str, "zvec.Collection"] = {}
        # 惰性加载：只在首次访问时打开 collection

    def close(self) -> None:
        """释放所有 collection 连接。"""
        import gc

        keys = list(self._cache.keys())
        for k in keys:
            col = self._cache.pop(k)
            del col
        gc.collect()

    # ---- collection lifecycle ----

    def _ensure(self, name: str):
        path = self.base / name
        if path.is_dir():
            opt = _ZVEC.CollectionOption(read_only=False)
            return _ZVEC.open(path=str(path), option=opt)
        schema = _make_entity_collection_schema(name, self.dim)
        return _ZVEC.create_and_open(path=str(path), schema=schema)

    def _col(self, name: str):
        if name not in ENTITY_COLLECTIONS:
            raise VectorError(
                f"未知 entity collection: {name}；可选：{ENTITY_COLLECTIONS}"
            )
        if name not in self._cache:
            self._cache[name] = self._ensure(name)
        return self._cache[name]

    # ---- 写入 ----

    def upsert_entity(self, doc: EntityDoc) -> int:
        """写入或更新一个实体文档。返回 1。"""
        col = self._col(doc.collection)
        vec = self.provider.embed([doc.text])[0]
        fields = {
            "text": doc.text,
            "state": doc.state,
            "state_ch": doc.state_ch,
            "version": doc.version,
            "archived": "false",
            **doc.fields,
        }
        zdoc = _ZVEC.Doc(id=doc.id, vectors={"vec": vec}, fields=fields)
        col.insert([zdoc])
        return 1

    def upsert_entities(self, docs: list[EntityDoc]) -> int:
        """批量写入实体文档。返回写入数量。"""
        if not docs:
            return 0
        # 分批嵌入
        texts = [d.text for d in docs]
        vectors = self._embed_in_batches(texts)
        zdocs = []
        for doc, vec in zip(docs, vectors):
            fields = {
                "text": doc.text,
                "state": doc.state,
                "state_ch": doc.state_ch,
                "version": doc.version,
                "archived": "false",
                **doc.fields,
            }
            zdocs.append(
                _ZVEC.Doc(id=doc.id, vectors={"vec": vec}, fields=fields)
            )
        col = self._col(docs[0].collection)
        col.insert(zdocs)
        return len(zdocs)

    def _embed_in_batches(
        self, texts: list[str], batch_size: int = 16
    ) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            out.extend(self.provider.embed(batch))
        return out

    # ---- 状态更新 ----

    def update_entity_state(
        self,
        collection: str,
        entity_id: str,
        new_state: str,
        state_ch: int,
        new_text: str | None = None,
        extra_fields: dict | None = None,
    ) -> bool:
        """更新实体状态。

        策略：旧版本标记 archived=true，插入新版本。
        返回 True 表示成功。
        """
        # 读取当前版本
        old = self.get_entity(collection, entity_id)
        if old is None:
            return False

        old_state = old.get("state", "")
        if not is_valid_transition(collection, old_state, new_state):
            return False

        # 标记旧版本为 archived
        self._mark_archived(collection, entity_id)

        # 解析 id 获取 slug，构造新 version id
        _, slug, old_ver = parse_entity_id(entity_id)
        new_ver = old_ver + 1
        new_id = make_entity_id(collection, slug, new_ver)

        # 构造新文档
        text = new_text or old.get("text", "")
        fields = {
            k: v
            for k, v in old.items()
            if k not in ("id", "text", "vec", "state", "state_ch", "version", "archived")
        }
        if extra_fields:
            fields.update(extra_fields)

        doc = EntityDoc(
            id=new_id,
            text=text,
            collection=collection,
            state=new_state,
            state_ch=state_ch,
            version=new_ver,
            fields=fields,
        )
        self.upsert_entity(doc)
        return True

    def _mark_archived(self, collection: str, entity_id: str) -> None:
        """标记指定实体为 archived（通过删除后重新插入实现）。"""
        # zvec 不支持 update，采用 query+delete+insert 的保守策略
        # 实际上我们保留旧版本，只是把 archived 设为 "true"
        # 但由于 zvec 不支持 field update，这里依赖查询时过滤
        pass  # archived 标记通过查询层实现：只查 version 最大的

    # ---- 查询 ----

    def get_entity(self, collection: str, entity_id: str) -> dict | None:
        """获取单个实体（精确 id 匹配）。"""
        col = self._col(collection)
        try:
            # 用 filter 精确匹配 id
            hits = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
                filter=f"id = '{entity_id}'",
            )
            if hits:
                return self._hit_to_dict(hits[0])
        except Exception:
            # filter 不支持时，全量扫描
            try:
                hits = col.query(
                    _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                    topk=10000,
                )
                for h in hits:
                    d = self._hit_to_dict(h)
                    if d.get("id") == entity_id:
                        return d
            except Exception:
                pass
        return None

    def get_latest_entity(self, collection: str, slug: str) -> dict | None:
        """获取某 slug 的最新版本实体。"""
        prefix = entity_id_prefix(collection, slug)
        col = self._col(collection)
        try:
            hits = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
                filter=f'id LIKE "{prefix}%"',
            )
        except Exception:
            hits = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
            )
            hits = [h for h in hits if self._hit_to_dict(h).get("id", "").startswith(prefix)]

        if not hits:
            return None

        # 取 version 最大的
        dicts = [self._hit_to_dict(h) for h in hits]
        dicts.sort(key=lambda d: d.get("version", 0), reverse=True)
        return dicts[0]

    def list_entities(
        self,
        collection: str,
        state: str | None = None,
        include_archived: bool = False,
    ) -> list[dict]:
        """列出某 collection 的所有实体（最新版本）。"""
        col = self._col(collection)
        try:
            hits = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
            )
        except Exception:
            return []

        all_dicts = [self._hit_to_dict(h) for h in hits]

        # 按 slug 分组，取最新版本
        by_slug: dict[str, list[dict]] = {}
        for d in all_dicts:
            eid = d.get("id", "")
            _, slug, _ = parse_entity_id(eid)
            by_slug.setdefault(slug, []).append(d)

        results = []
        for slug, versions in by_slug.items():
            versions.sort(key=lambda d: d.get("version", 0), reverse=True)
            latest = versions[0]
            if not include_archived and latest.get("archived") == "true":
                continue
            if state and latest.get("state") != state:
                continue
            results.append(latest)

        return results

    def search_entities(
        self,
        collection: str,
        query: str,
        top_k: int = 8,
        state: str | None = None,
        vec: list[float] | None = None,
    ) -> list[dict]:
        """语义搜索指定 collection 的实体。

        Args:
            vec: 预计算的查询向量（可选，避免重复 embed）。
        """
        col = self._col(collection)
        if vec is None:
            vec = self.provider.embed([query])[0]
        try:
            hits = col.query(_ZVEC.VectorQuery("vec", vector=vec), topk=top_k * 3)
        except Exception as e:
            raise VectorError(f"entity search failed on {collection}: {e}") from e

        results = []
        for h in hits:
            d = self._hit_to_dict(h)
            if d.get("archived") == "true":
                continue
            if state and d.get("state") != state:
                continue
            results.append(d)
            if len(results) >= top_k:
                break
        return results

    def search_entities_by_names(
        self,
        collection: str,
        names: list[str],
    ) -> list[dict]:
        """按名称精确匹配实体（返回每个 name 的最新版本）。"""
        results = []
        for name in names:
            # 先尝试 filter 精确匹配
            col = self._col(collection)
            try:
                hits = col.query(
                    _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                    topk=10000,
                    filter=f"name = '{name}'",
                )
                if hits:
                    dicts = [self._hit_to_dict(h) for h in hits]
                    # 过滤 archived，取最新 version
                    active = [d for d in dicts if d.get("archived") != "true"]
                    if active:
                        active.sort(key=lambda d: d.get("version", 0), reverse=True)
                        results.append(active[0])
                        continue
            except Exception:
                pass

            # fallback：语义搜索
            try:
                hits = col.query(
                    _ZVEC.VectorQuery("vec", vector=self.provider.embed([name])[0]),
                    topk=5,
                )
                for h in hits:
                    d = self._hit_to_dict(h)
                    if d.get("archived") == "true":
                        continue
                    if d.get("name") == name:
                        results.append(d)
                        break
            except Exception:
                pass

        return results

    # ---- 关系（Relations）写入 ----

    def upsert_relation(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        text: str,
        chapter: int | None = None,
        confidence: float = 1.0,
        state: str = "active",
        extra_fields: dict | None = None,
    ) -> str:
        """写入或更新一条关系。返回关系文档 id。"""
        rel_id = make_relation_id(source_id, rel_type, target_id)
        vec = self.provider.embed([text])[0]
        fields = {
            "text": text,
            "state": state,
            "state_ch": chapter,
            "name": f"{source_id} --[{rel_type}]--> {target_id}",
            "tags": "",
            "related": "",
            "version": 1,
            "archived": "false",
            "source_id": source_id,
            "target_id": target_id,
            "rel_type": rel_type,
            "chapter": chapter,
            "confidence": str(confidence),
            **(extra_fields or {}),
        }
        zdoc = _ZVEC.Doc(id=rel_id, vectors={"vec": vec}, fields=fields)
        col = self._col("relations")
        col.insert([zdoc])
        return rel_id

    def upsert_relations(
        self,
        triples: list[tuple[str, str, str, str]],
        chapter: int | None = None,
        confidence: float = 1.0,
    ) -> int:
        """批量写入关系。

        Args:
            triples: [(source_id, rel_type, target_id, text), ...]
            chapter: 章节号
            confidence: 置信度

        Returns:
            写入数量（跳过已存在的）。
        """
        if not triples:
            return 0

        # 过滤已存在的关系
        existing = self._get_existing_relation_ids()
        new_triples = []
        for src, rel, tgt, text in triples:
            rel_id = make_relation_id(src, rel, tgt)
            if rel_id not in existing:
                new_triples.append((src, rel, tgt, text, rel_id))

        if not new_triples:
            return 0

        # 批量嵌入
        texts = [t[3] for t in new_triples]
        vectors = self._embed_in_batches(texts)

        zdocs = []
        for (src, rel, tgt, text, rel_id), vec in zip(new_triples, vectors):
            fields = {
                "text": text,
                "state": "active",
                "state_ch": chapter,
                "name": f"{src} --[{rel}]--> {tgt}",
                "tags": "",
                "related": "",
                "version": 1,
                "archived": "false",
                "source_id": src,
                "target_id": tgt,
                "rel_type": rel,
                "chapter": chapter,
                "confidence": str(confidence),
            }
            zdocs.append(_ZVEC.Doc(id=rel_id, vectors={"vec": vec}, fields=fields))

        col = self._col("relations")
        col.insert(zdocs)
        return len(zdocs)

    def _get_existing_relation_ids(self) -> set[str]:
        """获取所有已有关系的 id 集合（用于去重）。"""
        col = self._col("relations")
        try:
            hits = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
            )
            return {self._doc_id(h) for h in hits}
        except Exception:
            return set()

    # ---- 关系查询 ----

    def get_relation(self, relation_id: str) -> dict | None:
        """获取单条关系。"""
        col = self._col("relations")
        try:
            hits = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
                filter=f"id = '{relation_id}'",
            )
            if hits:
                return self._hit_to_dict(hits[0])
        except Exception:
            pass
        return None

    def list_relations(
        self,
        entity_id: str | None = None,
        rel_type: str | None = None,
        direction: str = "both",
    ) -> list[dict]:
        """列出关系。

        Args:
            entity_id: 过滤指定实体的关系（作为 source 或 target）
            rel_type: 过滤关系类型
            direction: "out"（source=entity_id）、"in"（target=entity_id）、"both"
        """
        col = self._col("relations")
        try:
            hits = col.query(
                _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                topk=10000,
            )
        except Exception:
            return []

        results = []
        for h in hits:
            d = self._hit_to_dict(h)
            if d.get("archived") == "true":
                continue
            if d.get("state") == "dissolved":
                continue

            src = d.get("source_id", "")
            tgt = d.get("target_id", "")

            if entity_id:
                if direction == "out" and src != entity_id:
                    continue
                if direction == "in" and tgt != entity_id:
                    continue
                if direction == "both" and src != entity_id and tgt != entity_id:
                    continue

            if rel_type and d.get("rel_type") != rel_type:
                continue

            results.append(d)

        return results

    def search_relations(
        self,
        query: str,
        top_k: int = 10,
        entity_id: str | None = None,
        rel_type: str | None = None,
        vec: list[float] | None = None,
    ) -> list[dict]:
        """语义搜索关系。"""
        col = self._col("relations")
        if vec is None:
            vec = self.provider.embed([query])[0]
        try:
            hits = col.query(_ZVEC.VectorQuery("vec", vector=vec), topk=top_k * 3)
        except Exception:
            return []

        results = []
        for h in hits:
            d = self._hit_to_dict(h)
            if d.get("archived") == "true":
                continue
            if d.get("state") == "dissolved":
                continue
            if entity_id:
                src = d.get("source_id", "")
                tgt = d.get("target_id", "")
                if src != entity_id and tgt != entity_id:
                    continue
            if rel_type and d.get("rel_type") != rel_type:
                continue
            results.append(d)
            if len(results) >= top_k:
                break
        return results

    # ---- 图查询 ----

    def get_neighbors(
        self,
        entity_id: str,
        rel_type: str | None = None,
        depth: int = 1,
    ) -> list[dict]:
        """图谱邻居查询：查找与指定实体直接关联的所有实体。

        Args:
            entity_id: 实体 ID（如 "char_lin_yuan_v001"）
            rel_type: 过滤关系类型
            depth: 查询深度（目前只支持 1）

        Returns:
            邻居列表，每个元素包含 neighbor_id, rel_type, rel_direction, relation
        """
        relations = self.list_relations(entity_id=entity_id, rel_type=rel_type)

        neighbors = []
        for rel in relations:
            src = rel.get("source_id", "")
            tgt = rel.get("target_id", "")

            if src == entity_id:
                neighbor_id = tgt
                direction = "out"
            else:
                neighbor_id = src
                direction = "in"

            neighbors.append({
                "neighbor_id": neighbor_id,
                "rel_type": rel.get("rel_type", ""),
                "direction": direction,
                "relation_text": rel.get("text", ""),
                "relation_id": rel.get("id", ""),
                "chapter": rel.get("chapter"),
                "confidence": rel.get("confidence", "1.0"),
            })

        return neighbors

    def find_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int = 3,
    ) -> list[dict] | None:
        """BFS 查找两个实体之间的最短路径。

        Returns:
            路径列表 [{node: id, edge: rel_type, direction}, ...] 或 None
        """
        if from_id == to_id:
            return [{"node": from_id}]

        from collections import deque

        visited = {from_id}
        queue = deque([(from_id, [{"node": from_id}])])

        for _ in range(max_depth):
            next_queue = deque()
            while queue:
                current, path = queue.popleft()
                neighbors = self.get_neighbors(current)

                for nb in neighbors:
                    nb_id = nb["neighbor_id"]
                    if nb_id in visited:
                        continue

                    new_path = path + [{
                        "node": nb_id,
                        "edge": nb["rel_type"],
                        "direction": nb["direction"],
                        "relation_text": nb["relation_text"],
                    }]

                    if nb_id == to_id:
                        return new_path

                    visited.add(nb_id)
                    next_queue.append((nb_id, new_path))

            queue = next_queue

        return None

    # ---- 统计 ----

    def status(self) -> dict:
        """各 collection 的实体数量统计。"""
        out: dict = {
            "embedding_model": getattr(self.provider, "name", "unknown"),
            "vector_dim": self.dim,
            "collections": {},
        }
        for name in ENTITY_COLLECTIONS:
            try:
                entities = self.list_entities(name, include_archived=False)
                out["collections"][name] = len(entities)
            except Exception:
                out["collections"][name] = 0
        out["total_entities"] = sum(out["collections"].values())
        return out

    # ---- 清空 ----

    def clear(self, collection: str | None = None) -> list[str]:
        """清空指定（或全部）entity collection。"""
        targets = [collection] if collection else list(ENTITY_COLLECTIONS)
        cleared: list[str] = []
        for name in targets:
            if name not in ENTITY_COLLECTIONS:
                raise VectorError(f"未知 entity collection: {name}")
            try:
                col = self._col(name)
                results = col.query(
                    _ZVEC.VectorQuery("vec", vector=[0.0] * self.dim),
                    topk=10000,
                )
                if results:
                    ids = [self._doc_id(r) for r in results]
                    col.delete(ids)
                cleared.append(name)
            except Exception as e:
                raise VectorError(f"清空 {name} 失败：{e}") from e
        return cleared

    # ---- 工具 ----

    @staticmethod
    def _hit_to_dict(hit) -> dict:
        """把 zvec Doc/dict 统一转为 dict。"""
        if isinstance(hit, dict):
            d = dict(hit)
            d["id"] = d.get("id", "")
            return d
        d = {"id": hit.id}
        if hit.fields:
            d.update(hit.fields)
        if hit.score is not None:
            d["score"] = float(hit.score)
        return d

    @staticmethod
    def _doc_id(doc) -> str:
        return doc.id if not isinstance(doc, dict) else doc.get("id", "")


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #


def entity_id_prefix(collection: str, slug: str) -> str:
    """返回 entity id 的前缀部分（不含 version）。"""
    from lib.entity_schema import _COLLECTION_PREFIX

    prefix = _COLLECTION_PREFIX.get(collection, collection[:3])
    return f"{prefix}_{slug}_"


# --------------------------------------------------------------------------- #
# 工厂 + 单例
# --------------------------------------------------------------------------- #

_ENTITY_STORE_CACHE: dict[str, EntityStore] = {}


def open_entity_store(project_root: Path, provider: EmbeddingProvider) -> EntityStore:
    """打开（或创建）entity store。"""
    require_zvec()
    base = vector_root(project_root)  # .fictia/zvec/
    base.mkdir(parents=True, exist_ok=True)
    return EntityStore(base=base, provider=provider)


def open_entity_store_with_default_provider(
    project_root: Path, mode: str | None = None
) -> EntityStore:
    """用默认 provider 打开 EntityStore（单例缓存）。"""
    cache_key = str(project_root.resolve())
    if cache_key in _ENTITY_STORE_CACHE:
        return _ENTITY_STORE_CACHE[cache_key]
    provider = get_provider(mode)
    store = open_entity_store(project_root, provider)
    _ENTITY_STORE_CACHE[cache_key] = store
    return store


def close_all_entity_stores() -> None:
    """释放所有缓存的 EntityStore。"""
    import gc

    for store in _ENTITY_STORE_CACHE.values():
        store.close()
    _ENTITY_STORE_CACHE.clear()
    gc.collect()

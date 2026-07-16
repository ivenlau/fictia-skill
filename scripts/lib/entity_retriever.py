"""Dynamic Writing Space — 实体检索器。

基于 OutlineHints 从 EntityStore 中检索写作所需的实体。

检索策略：
  1. 必读实体（大纲明确提到的）→ 精确查询
  2. 关联实体（必读实体的 related 展开）→ 扩展查询
  3. 上下文实体（时间线/故事线/近期事件）→ 窗口查询
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from lib.entity_store import EntityStore
from lib.outline_parser import OutlineHints, ForeshadowOp
from lib.entity_schema import parse_entity_id


# --------------------------------------------------------------------------- #
# 检索结果
# --------------------------------------------------------------------------- #


@dataclass
class RetrievedEntities:
    """一次检索的结果集。"""

    # 必读实体（大纲明确提到的）
    mandatory_characters: list[dict] = field(default_factory=list)
    mandatory_locations: list[dict] = field(default_factory=list)
    mandatory_foreshadowing: list[dict] = field(default_factory=list)

    # 关联实体（必读实体的 related 展开）
    related_characters: list[dict] = field(default_factory=list)
    related_locations: list[dict] = field(default_factory=list)

    # 上下文实体
    timeline_window: list[dict] = field(default_factory=list)
    active_storylines: list[dict] = field(default_factory=list)
    recent_events: list[dict] = field(default_factory=list)

    # 按需检索结果（agent 主动查询）
    on_demand: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 检索器
# --------------------------------------------------------------------------- #


class EntityRetriever:
    """基于大纲线索检索实体。"""

    def __init__(self, store: EntityStore) -> None:
        self.store = store

    def retrieve_for_chapter(self, hints: OutlineHints) -> RetrievedEntities:
        """根据大纲线索组装实体集。"""
        result = RetrievedEntities()

        # 1. 必读实体：按名称精确匹配
        if hints.character_names:
            result.mandatory_characters = self.store.search_entities_by_names(
                "characters", hints.character_names
            )

        if hints.locations:
            result.mandatory_locations = self.store.search_entities_by_names(
                "locations", hints.locations
            )

        # 2. 伏笔：按 ID 或名称匹配
        if hints.foreshadow_ops:
            result.mandatory_foreshadowing = self._retrieve_foreshadowing(
                hints.foreshadow_ops
            )

        # 3. 关联实体展开
        result.related_characters = self._expand_related(
            "characters", result.mandatory_characters
        )
        result.related_locations = self._expand_related(
            "locations", result.mandatory_locations
        )

        # 4. 时间窗口
        result.timeline_window = self._retrieve_timeline_window(
            hints.chapter, window=3
        )

        # 5. 活跃故事线
        result.active_storylines = self.store.list_entities(
            "storylines", state="active"
        )
        # 也包含 escalating 和 climax 状态
        result.active_storylines.extend(
            self.store.list_entities("storylines", state="escalating")
        )
        result.active_storylines.extend(
            self.store.list_entities("storylines", state="climax")
        )

        # 6. 近期事件
        result.recent_events = self._retrieve_recent_events(
            hints.chapter, lookback=3
        )

        return result

    def retrieve_on_demand(
        self,
        query: str,
        collection: str | None = None,
        top_k: int = 8,
        state: str | None = None,
    ) -> list[dict]:
        """按需语义检索（agent 主动调用）。"""
        # 预计算查询向量，避免跨 collection 重复 embed
        vec = self.store.provider.embed([query])[0]

        if collection:
            return self.store.search_entities(
                collection, query, top_k=top_k, state=state, vec=vec
            )

        # 跨 collection 检索
        from lib.entity_schema import ENTITY_COLLECTIONS

        all_results: list[dict] = []
        for col in ENTITY_COLLECTIONS:
            try:
                hits = self.store.search_entities(col, query, top_k=3, state=state, vec=vec)
                all_results.extend(hits)
            except Exception:
                continue

        # 按 score 排序（如果有）
        all_results.sort(key=lambda d: d.get("score", 0), reverse=True)
        return all_results[:top_k]

    # ---- 内部方法 ----

    def _retrieve_foreshadowing(self, ops: list[ForeshadowOp]) -> list[dict]:
        """按伏笔 ID 或描述检索。"""
        results: list[dict] = []
        seen_ids: set[str] = set()

        for op in ops:
            # 先尝试按名称匹配
            matches = self.store.search_entities_by_names(
                "foreshadowing", [op.fo_id]
            )
            for m in matches:
                mid = m.get("id", "")
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    results.append(m)

            # 如果没找到，用语义搜索
            if not matches and op.hint:
                try:
                    hits = self.store.search_entities(
                        "foreshadowing", op.hint, top_k=3
                    )
                    for h in hits:
                        hid = h.get("id", "")
                        if hid not in seen_ids:
                            seen_ids.add(hid)
                            results.append(h)
                except Exception:
                    pass

        return results

    def _expand_related(
        self, collection: str, seeds: list[dict]
    ) -> list[dict]:
        """从种子实体展开关联实体（双源：related 字段 + 知识图谱）。"""
        seed_ids: set[str] = {d.get("id", "") for d in seeds}
        related_slugs: set[str] = set()
        graph_related_ids: set[str] = set()

        for seed in seeds:
            seed_id = seed.get("id", "")

            # 来源 1：related 字段（原有逻辑）
            related_str = seed.get("related", "")
            if related_str:
                for slug in related_str.split(","):
                    slug = slug.strip()
                    if slug:
                        related_slugs.add(slug)

            # 来源 2：知识图谱邻居查询
            try:
                neighbors = self.store.get_neighbors(seed_id)
                for nb in neighbors:
                    nb_id = nb["neighbor_id"]
                    if nb_id not in seed_ids:
                        graph_related_ids.add(nb_id)
            except Exception:
                pass  # relations collection 可能不存在

        results: list[dict] = []

        # 按名称查询 related 字段的关联实体
        if related_slugs:
            name_results = self.store.search_entities_by_names(
                collection, list(related_slugs)
            )
            results.extend(name_results)

        # 按 id 查询图谱关联实体
        if graph_related_ids:
            for entity_id in graph_related_ids:
                # 推断 collection
                from lib.entity_schema import parse_entity_id
                prefix, slug, _ = parse_entity_id(entity_id)
                # 尝试在目标 collection 中查找
                try:
                    entity = self.store.get_entity(collection, entity_id)
                    if entity and entity.get("id", "") not in seed_ids:
                        results.append(entity)
                except Exception:
                    pass

        # 去重
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in results:
            rid = r.get("id", "")
            if rid and rid not in seen and rid not in seed_ids:
                seen.add(rid)
                deduped.append(r)

        return deduped

    def _retrieve_timeline_window(
        self, chapter: int, window: int = 3
    ) -> list[dict]:
        """检索 chapter ± window 范围内的时间线事件。"""
        all_entities = self.store.list_entities("timeline")
        results = []
        for entity in all_entities:
            ch = entity.get("chapter")
            if ch is not None and isinstance(ch, int):
                if abs(ch - chapter) <= window:
                    results.append(entity)
        # 按章节号排序
        results.sort(key=lambda d: d.get("chapter", 0))
        return results

    def _retrieve_recent_events(
        self, chapter: int, lookback: int = 3
    ) -> list[dict]:
        """检索前 lookback 章的事件。"""
        all_events = self.store.list_entities("events")
        results = []
        for event in all_events:
            ch = event.get("chapter")
            if ch is not None and isinstance(ch, int):
                if chapter - lookback <= ch < chapter:
                    results.append(event)
        # 按章节号排序
        results.sort(key=lambda d: d.get("chapter", 0))
        return results

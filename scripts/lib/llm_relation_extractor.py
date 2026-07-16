"""Dynamic Writing Space — LLM 关系抽取器。

用 LLM 从章节正文中自动抽取实体关系三元组。

支持的 LLM 后端：
  1. OpenAI 兼容 API（默认）
  2. 本地 embed_server 的 /embed 端点（用于向量化）

用法：
    from lib.llm_relation_extractor import extract_relations_via_llm
    triples = await extract_relations_via_llm(chapter_text, chapter)
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from lib.entity_schema import make_entity_id, make_slug


# --------------------------------------------------------------------------- #
# LLM 调用
# --------------------------------------------------------------------------- #


EXTRACTION_PROMPT = """你是一个小说知识图谱抽取助手。请从以下小说章节正文中，抽取所有有意义的实体关系三元组。

## 实体类型
- character: 角色（如：林远、清风长老）
- location: 地点（如：青云门、北域冰原）
- item: 物品/法器（如：神秘玉佩、青云剑）
- event: 事件/场景（如：北域围猎、入门考验）

## 关系类型
- friend: 朋友
- enemy: 敌人
- mentor: 师徒（导师方）
- apprentice: 师徒（学徒方）
- family: 家族/血缘
- lover: 恋人
- ally: 盟友
- rival: 对手
- protects: 守护
- located_at: 位于
- owns: 持有/拥有
- participates: 参与（事件）
- causes: 导致（事件因果）
- affects: 影响
- reveals: 揭示
- related_to: 通用关联

## 输出格式
请输出 JSON 数组，每个元素包含：
- source: 源实体名称
- source_type: 源实体类型（character/location/item/event）
- target: 目标实体名称
- target_type: 目标实体类型
- rel_type: 关系类型（从上面列表选）
- text: 关系的自然语言描述（一句话）

## 注意事项
1. 只抽取明确出现在文本中的关系，不要推测
2. 实体名称使用文本中的原始名称
3. 每个关系只输出一次（去重）
4. 如果没有有意义的关系，输出空数组 []

## 章节正文
{chapter_text}

## 输出（纯 JSON 数组，不要包含其他文字）
"""


async def call_llm_api(
    prompt: str,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> str:
    """调用 OpenAI 兼容的 LLM API。

    Args:
        prompt: 用户 prompt
        api_base: API 基础 URL（默认从环境变量读取）
        api_key: API 密钥（默认从环境变量读取）
        model: 模型名称
        temperature: 温度
        max_tokens: 最大输出 token 数

    Returns:
        LLM 的文本响应
    """
    import httpx

    api_base = api_base or os.environ.get(
        "FICTIA_LLM_API_BASE", "https://api.openai.com/v1"
    )
    api_key = api_key or os.environ.get("FICTIA_LLM_API_KEY", "")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是小说知识图谱抽取助手，只输出 JSON 数组。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{api_base.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def parse_llm_response(response: str) -> list[dict]:
    """解析 LLM 返回的 JSON 数组。

    处理各种格式变体（带 markdown 代码块、前后有文字等）。
    """
    # 尝试直接解析
    text = response.strip()

    # 去掉 markdown 代码块
    if text.startswith("```"):
        # 去掉第一行和最后一行
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 找到 JSON 数组的起止位置
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    text = text[start : end + 1]

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    return []


def triples_from_llm_result(
    llm_result: list[dict], chapter: int
) -> list[tuple[str, str, str, str]]:
    """将 LLM 抽取结果转换为 (source_id, rel_type, target_id, text) 格式。

    同时验证关系类型是否合法。
    """
    from lib.entity_schema import RELATION_TYPES

    valid_types = set(RELATION_TYPES)
    triples: list[tuple[str, str, str, str]] = []

    for item in llm_result:
        source = item.get("source", "").strip()
        target = item.get("target", "").strip()
        rel_type = item.get("rel_type", "related_to").strip()
        text = item.get("text", "").strip()
        source_type = item.get("source_type", "character").strip()
        target_type = item.get("target_type", "character").strip()

        if not source or not target:
            continue

        # 验证关系类型
        if rel_type not in valid_types:
            rel_type = "related_to"

        # 生成 entity id
        source_id = _name_to_entity_id(source, source_type)
        target_id = _name_to_entity_id(target, target_type)

        if source_id == target_id:
            continue

        # 生成描述文本
        if not text:
            text = f"{source} 与 {target} 的关系：{rel_type}"

        triples.append((source_id, rel_type, target_id, text))

    return triples


def _name_to_entity_id(name: str, entity_type: str) -> str:
    """从实体名称和类型推断 entity id。"""
    type_to_collection = {
        "character": "characters",
        "location": "locations",
        "item": "items",
        "event": "events",
    }
    collection = type_to_collection.get(entity_type, "characters")
    slug = make_slug(name)
    return make_entity_id(collection, slug)


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #


async def extract_relations_via_llm(
    chapter_text: str,
    chapter: int,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
) -> list[tuple[str, str, str, str]]:
    """用 LLM 从章节正文中抽取关系三元组。

    Args:
        chapter_text: 章节全文
        chapter: 章节号
        api_base: LLM API 地址
        api_key: LLM API 密钥
        model: 模型名称

    Returns:
        [(source_id, rel_type, target_id, text), ...]
    """
    # 截取正文（去掉写作备注部分）
    from lib.words import WRITING_NOTES_RE

    m = WRITING_NOTES_RE.search(chapter_text)
    if m:
        chapter_text = chapter_text[: m.start()]

    # 限制文本长度（避免 token 超限）
    if len(chapter_text) > 8000:
        chapter_text = chapter_text[:8000] + "\n...(正文截断)"

    prompt = EXTRACTION_PROMPT.format(chapter_text=chapter_text)

    try:
        response = await call_llm_api(
            prompt, api_base=api_base, api_key=api_key, model=model
        )
    except Exception as e:
        print(f"[llm-extractor] LLM call failed: {e}", flush=True)
        return []

    llm_result = parse_llm_response(response)
    if not llm_result:
        return []

    triples = triples_from_llm_result(llm_result, chapter)
    return triples


async def extract_and_store_relations_via_llm(
    store,
    chapter_text: str,
    chapter: int,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
) -> int:
    """用 LLM 抽取关系并写入 store。

    Returns:
        写入的关系数量。
    """
    triples = await extract_relations_via_llm(
        chapter_text, chapter, api_base=api_base, api_key=api_key, model=model
    )
    if not triples:
        return 0
    return store.upsert_relations(triples, chapter=chapter, confidence=0.9)

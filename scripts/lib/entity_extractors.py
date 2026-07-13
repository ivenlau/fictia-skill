"""Dynamic Writing Space — 实体提取器。

从现有项目文件中提取实体，生成 EntityDoc 列表。

提取器列表：
  - CharacterExtractor:   characters/*.md       → characters collection
  - LocationExtractor:    world/setting.md       → locations collection
  - ItemExtractor:        world/rules.md         → items collection
  - ForeshadowingExtractor: narrative-weave.md   → foreshadowing collection
  - EasterEggExtractor:   narrative-weave.md     → easter_eggs collection
  - StorylineExtractor:   narrative-weave.md     → storylines collection
  - EventExtractor:       outline/chapters/*.md  → events collection
  - TimelineExtractor:    world/timeline.md      → timeline collection

每个 extractor 都是纯函数：读文件 → 解析 → 返回 list[EntityDoc]。
不依赖 zvec，可独立单测。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from lib.entity_schema import (
    EntityDoc,
    make_entity_id,
    make_slug,
)
from lib.context import parse_frontmatter


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #


def _read_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _split_sections(text: str) -> list[tuple[str, str]]:
    """按 ## 标题切分 markdown 文本。返回 [(heading, body), ...]。"""
    sections: list[tuple[str, str]] = []
    lines = text.splitlines()
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        if line.startswith("## "):
            # 保存上一个 section
            sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = line.strip()
            current_body = []
        else:
            current_body.append(line)

    # 保存最后一个 section
    sections.append((current_heading, "\n".join(current_body).strip()))

    return sections


def _parse_md_table(text: str) -> list[dict[str, str]]:
    """解析 markdown 表格为 list[dict]。"""
    lines = [l.strip() for l in text.splitlines() if l.strip().startswith("|")]
    if len(lines) < 3:
        return []
    # 表头
    headers = [h.strip() for h in lines[0].split("|") if h.strip()]
    # 跳过分隔行
    rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= len(headers):
            rows.append(dict(zip(headers, cells[: len(headers)])))
    return rows


# --------------------------------------------------------------------------- #
# CharacterExtractor
# --------------------------------------------------------------------------- #


class CharacterExtractor:
    """从 characters/*.md 提取角色实体。"""

    def extract(self, project_root: Path) -> list[EntityDoc]:
        chars_dir = project_root / "characters"
        if not chars_dir.is_dir():
            return []

        docs: list[EntityDoc] = []
        files: list[Path] = []

        # protagonist.md, antagonist.md
        for name in ("protagonist.md", "antagonist.md"):
            p = chars_dir / name
            if p.is_file():
                files.append(p)
        # supporting/*.md
        supporting = chars_dir / "supporting"
        if supporting.is_dir():
            files.extend(sorted(supporting.glob("*.md")))

        for p in files:
            text = _read_file(p)
            if not text:
                continue
            fm, body = parse_frontmatter(text)
            char_name = fm.get("name", p.stem)
            slug = make_slug(char_name)

            # 构造语义文本：front-matter 关键信息 + body 前 600 字
            traits = fm.get("traits", [])
            if isinstance(traits, list):
                traits_s = "、".join(str(t) for t in traits)
            else:
                traits_s = str(traits)

            semantic_text = (
                f"角色：{char_name}\n"
                f"身份：{fm.get('identity', '')}\n"
                f"角色类型：{fm.get('role', '')}\n"
                f"核心特质：{traits_s}\n"
                f"语言风格：{fm.get('language_style', '')}\n"
                f"成长弧线：{fm.get('growth_arc', '')}\n"
            )
            # 加入 body 摘要
            body_clean = re.sub(r"\n{3,}", "\n\n", body).strip()
            if body_clean:
                semantic_text += f"\n{body_clean[:600]}"

            # 关联角色
            related_ids: list[str] = []
            for rel in fm.get("relationships", []) or []:
                if isinstance(rel, dict):
                    rel_name = rel.get("name", "")
                    if rel_name:
                        related_ids.append(make_slug(rel_name))

            docs.append(
                EntityDoc(
                    id=make_entity_id("characters", slug),
                    text=semantic_text,
                    collection="characters",
                    state="introduced",
                    state_ch=None,
                    fields={
                        "name": char_name,
                        "role": fm.get("role", ""),
                        "identity": fm.get("identity", ""),
                        "traits": traits_s,
                        "lang_style": fm.get("language_style", ""),
                        "arc_keyword": "",
                        "emotional": "",
                        "tags": "",
                        "related": ",".join(related_ids),
                    },
                )
            )

        return docs


# --------------------------------------------------------------------------- #
# LocationExtractor
# --------------------------------------------------------------------------- #


class LocationExtractor:
    """从 world/setting.md 按 ## 标题分节提取地点实体。"""

    def extract(self, project_root: Path) -> list[EntityDoc]:
        setting_path = project_root / "world" / "setting.md"
        text = _read_file(setting_path)
        if not text:
            return []

        sections = _split_sections(text)
        docs: list[EntityDoc] = []

        for heading, body in sections:
            if not body:
                continue
            # 从 heading 提取地名
            loc_name = re.sub(r"^##\s*", "", heading).strip()
            if not loc_name:
                continue

            slug = make_slug(loc_name)
            # 尝试从 heading 推断 region
            region = ""
            region_match = re.search(r"[（(](.+?)[）)]", loc_name)
            if region_match:
                region = region_match.group(1)

            docs.append(
                EntityDoc(
                    id=make_entity_id("locations", slug),
                    text=body[:1000],
                    collection="locations",
                    state="introduced",
                    state_ch=None,
                    fields={
                        "name": loc_name,
                        "region": region,
                        "tags": "",
                        "related": "",
                    },
                )
            )

        return docs


# --------------------------------------------------------------------------- #
# ItemExtractor
# --------------------------------------------------------------------------- #


class ItemExtractor:
    """从 world/rules.md 提取物品/法器/装备实体。

    策略：
      1. 扫描 ## 标题含关键词的 section，从其表格中提取条目
      2. 也从列表项中提取
    """

    _KEYWORDS = ("法器", "装备", "物品", "道具", "神器", "灵药", "丹药", "灵石")

    def extract(self, project_root: Path) -> list[EntityDoc]:
        rules_path = project_root / "world" / "rules.md"
        text = _read_file(rules_path)
        if not text:
            return []

        docs: list[EntityDoc] = []
        seen_names: set[str] = set()

        # 策略 1：找标题含关键词的 section，从其表格中提取
        sections = _split_sections(text)
        for heading, body in sections:
            if not any(kw in heading for kw in self._KEYWORDS):
                continue

            # 从表格提取
            table_blocks = re.findall(r"((?:^\|.*\|[ \t]*\n?)+)", body, re.MULTILINE)
            for block in table_blocks:
                rows = _parse_md_table(block)
                for row in rows:
                    name = list(row.values())[0] if row else ""
                    if not name or name in ("名称", "物品名", "法器名"):
                        continue
                    if name in seen_names:
                        continue
                    seen_names.add(name)
                    slug = make_slug(name)
                    row_text = " ".join(row.values())
                    docs.append(
                        EntityDoc(
                            id=make_entity_id("items", slug),
                            text=row_text,
                            collection="items",
                            state="unknown",
                            state_ch=None,
                            fields={
                                "name": name,
                                "owner": "",
                                "power": "",
                                "tags": "",
                                "related": "",
                            },
                        )
                    )

            # 从列表项提取
            for line in body.splitlines():
                line = line.strip()
                if not line.startswith(("-", "*", "·")):
                    continue
                item_text = re.sub(r"^[-*·]\s*", "", line)
                if not item_text:
                    continue
                name_match = re.match(r"^(.+?)[：:（(]", item_text)
                name = name_match.group(1).strip() if name_match else item_text[:20]
                if name in seen_names:
                    continue
                seen_names.add(name)
                slug = make_slug(name)
                docs.append(
                    EntityDoc(
                        id=make_entity_id("items", slug),
                        text=item_text,
                        collection="items",
                        state="unknown",
                        state_ch=None,
                        fields={
                            "name": name,
                            "owner": "",
                            "power": "",
                            "tags": "",
                            "related": "",
                        },
                    )
                )

        return docs


# --------------------------------------------------------------------------- #
# ForeshadowingExtractor
# --------------------------------------------------------------------------- #


class ForeshadowingExtractor:
    """从 narrative-weave.md 的伏笔表提取伏笔实体。"""

    def extract(self, project_root: Path) -> list[EntityDoc]:
        weave_path = project_root / "narrative-weave.md"
        text = _read_file(weave_path)
        if not text:
            return []

        docs: list[EntityDoc] = []

        # 找伏笔相关表格（标题含"伏笔"的 section 下的表格）
        sections = _split_sections(text)
        for heading, body in sections:
            if "伏笔" not in heading and "foreshadow" not in heading.lower():
                continue
            table_blocks = re.findall(r"((?:^\|.*\|[ \t]*\n?)+)", body, re.MULTILINE)
            for block in table_blocks:
                rows = _parse_md_table(block)
                for row in rows:
                    # 常见表头：编号、类型、描述、埋设章节、计划回收章节
                    fo_id = row.get("编号", row.get("ID", row.get("id", "")))
                    fo_type = row.get("类型", row.get("type", ""))
                    fo_desc = row.get("描述", row.get("内容", row.get("说明", "")))
                    fo_plant = row.get("埋设章节", row.get("埋设", row.get("plant", "")))
                    fo_resolve = row.get("计划回收", row.get("回收章节", row.get("resolve", "")))

                    if not fo_desc:
                        # 尝试用所有值拼接
                        fo_desc = " ".join(row.values())

                    name = fo_id or fo_desc[:20]
                    slug = make_slug(name)

                    plant_ch = self._parse_chapter_num(fo_plant)
                    resolve_ch = self._parse_chapter_num(fo_resolve)

                    docs.append(
                        EntityDoc(
                            id=make_entity_id("foreshadowing", slug),
                            text=fo_desc,
                            collection="foreshadowing",
                            state="planted",
                            state_ch=plant_ch,
                            fields={
                                "name": name,
                                "type": fo_type,
                                "plant_ch": plant_ch,
                                "resolve_ch": resolve_ch,
                                "tags": "",
                                "related": "",
                            },
                        )
                    )

        return docs

    @staticmethod
    def _parse_chapter_num(s: str) -> int | None:
        if not s:
            return None
        m = re.search(r"(\d+)", s)
        return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- #
# EasterEggExtractor
# --------------------------------------------------------------------------- #


class EasterEggExtractor:
    """从 narrative-weave.md 的彩蛋表提取彩蛋实体。"""

    def extract(self, project_root: Path) -> list[EntityDoc]:
        weave_path = project_root / "narrative-weave.md"
        text = _read_file(weave_path)
        if not text:
            return []

        docs: list[EntityDoc] = []
        sections = _split_sections(text)

        for heading, body in sections:
            if "彩蛋" not in heading and "easter" not in heading.lower():
                continue
            table_blocks = re.findall(r"((?:^\|.*\|[ \t]*\n?)+)", body, re.MULTILINE)
            for block in table_blocks:
                rows = _parse_md_table(block)
                for row in rows:
                    egg_name = row.get("名称", row.get("编号", row.get("ID", "")))
                    egg_type = row.get("类型", row.get("type", ""))
                    egg_desc = row.get("描述", row.get("内容", ""))
                    egg_target = row.get("揭示章节", row.get("目标章节", row.get("target", "")))

                    if not egg_desc:
                        egg_desc = " ".join(row.values())

                    name = egg_name or egg_desc[:20]
                    slug = make_slug(name)
                    target_ch = None
                    if egg_target:
                        m = re.search(r"(\d+)", egg_target)
                        if m:
                            target_ch = int(m.group(1))

                    docs.append(
                        EntityDoc(
                            id=make_entity_id("easter_eggs", slug),
                            text=egg_desc,
                            collection="easter_eggs",
                            state="planted",
                            state_ch=None,
                            fields={
                                "name": name,
                                "type": egg_type,
                                "target_ch": target_ch,
                                "tags": "",
                                "related": "",
                            },
                        )
                    )

        return docs


# --------------------------------------------------------------------------- #
# StorylineExtractor
# --------------------------------------------------------------------------- #


class StorylineExtractor:
    """从 narrative-weave.md 的支线表提取故事线实体。"""

    def extract(self, project_root: Path) -> list[EntityDoc]:
        weave_path = project_root / "narrative-weave.md"
        text = _read_file(weave_path)
        if not text:
            return []

        docs: list[EntityDoc] = []
        sections = _split_sections(text)

        for heading, body in sections:
            if "支线" not in heading and "故事线" not in heading and "storyline" not in heading.lower():
                continue
            table_blocks = re.findall(r"((?:^\|.*\|[ \t]*\n?)+)", body, re.MULTILINE)
            for block in table_blocks:
                rows = _parse_md_table(block)
                for row in rows:
                    sl_name = row.get("名称", row.get("支线", row.get("故事线", "")))
                    sl_type = row.get("类型", row.get("type", ""))
                    sl_desc = row.get("描述", row.get("内容", row.get("说明", "")))
                    sl_priority = row.get("优先级", row.get("priority", ""))
                    sl_chars = row.get("关联角色", row.get("角色", row.get("characters", "")))

                    if not sl_desc:
                        sl_desc = " ".join(row.values())

                    name = sl_name or sl_desc[:20]
                    slug = make_slug(name)

                    docs.append(
                        EntityDoc(
                            id=make_entity_id("storylines", slug),
                            text=sl_desc,
                            collection="storylines",
                            state="dormant",
                            state_ch=None,
                            fields={
                                "name": name,
                                "type": sl_type,
                                "priority": sl_priority,
                                "key_chars": sl_chars,
                                "tags": "",
                                "related": "",
                            },
                        )
                    )

        return docs


# --------------------------------------------------------------------------- #
# EventExtractor
# --------------------------------------------------------------------------- #


class EventExtractor:
    """从 outline/chapters/*.md 提取事件实体。

    策略：解析 '## 场景序列' 中的每个场景作为独立事件。
    """

    def extract(self, project_root: Path) -> list[EntityDoc]:
        outline_dir = project_root / "outline" / "chapters"
        if not outline_dir.is_dir():
            return []

        docs: list[EntityDoc] = []

        for outline_file in sorted(outline_dir.glob("ch*.md")):
            # 从文件名提取章节号
            ch_match = re.match(r"ch(\d+)\.md", outline_file.name)
            if not ch_match:
                continue
            chapter = int(ch_match.group(1))

            text = _read_file(outline_file)
            if not text:
                continue

            # 提取场景序列
            scene_section = re.search(
                r"^##\s*场景序列[^\n]*\n([\s\S]*?)(?=^##\s|\Z)",
                text,
                re.MULTILINE,
            )
            if not scene_section:
                continue

            scene_body = scene_section.group(1)
            # 按 ### 或 **场景 N** 切分
            scenes = re.split(r"(?=^###\s|^\*\*场景\s*\d)", scene_body, flags=re.MULTILINE)

            for i, scene in enumerate(scenes):
                scene = scene.strip()
                if not scene or len(scene) < 20:
                    continue

                # 提取场景目标
                goal_match = re.search(r"场景目标[：:]\s*(.+)", scene)
                scene_goal = goal_match.group(1).strip() if goal_match else ""

                # 提取地点
                loc_match = re.search(r"地点[：:]\s*(.+)", scene)
                location = loc_match.group(1).strip() if loc_match else ""

                # 提取参与角色
                char_match = re.search(r"(?:角色|参与|人物)[：:]\s*(.+)", scene)
                participants = char_match.group(1).strip() if char_match else ""

                event_name = scene_goal or f"ch{chapter:02d}_场景{i+1}"
                slug = make_slug(f"ch{chapter:02d}_s{i+1}_{event_name[:10]}")

                docs.append(
                    EntityDoc(
                        id=make_entity_id("events", slug),
                        text=scene[:1000],
                        collection="events",
                        state="pending",
                        state_ch=chapter,
                        fields={
                            "name": event_name,
                            "chapter": chapter,
                            "participants": participants,
                            "location": location,
                            "causes": "",
                            "effects": "",
                            "tags": "",
                            "related": "",
                        },
                    )
                )

        return docs


# --------------------------------------------------------------------------- #
# TimelineExtractor
# --------------------------------------------------------------------------- #


class TimelineExtractor:
    """从 world/timeline.md 提取时间线事件实体。"""

    def extract(self, project_root: Path) -> list[EntityDoc]:
        timeline_path = project_root / "world" / "timeline.md"
        text = _read_file(timeline_path)
        if not text:
            return []

        docs: list[EntityDoc] = []

        # 策略 1：表格
        table_blocks = re.findall(r"((?:^\|.*\|[ \t]*\n?)+)", text, re.MULTILINE)
        for block in table_blocks:
            rows = _parse_md_table(block)
            for row in rows:
                tl_time = row.get("时间", row.get("时期", row.get("time", "")))
                tl_event = row.get("事件", row.get("事件名", row.get("event", "")))
                tl_desc = row.get("描述", row.get("内容", row.get("description", "")))
                tl_era = row.get("时代", row.get("阶段", row.get("era", "")))

                if not tl_desc:
                    tl_desc = " ".join(row.values())

                name = tl_event or tl_desc[:20]
                slug = make_slug(name)

                docs.append(
                    EntityDoc(
                        id=make_entity_id("timeline", slug),
                        text=tl_desc,
                        collection="timeline",
                        state="past",
                        state_ch=None,
                        fields={
                            "name": name,
                            "event_time": tl_time,
                            "chapter": None,
                            "era": tl_era,
                            "tags": "",
                            "related": "",
                        },
                    )
                )

        # 策略 2：列表项
        if not table_blocks:
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith(("-", "*", "·")):
                    continue
                item = re.sub(r"^[-*·]\s*", "", line)
                if not item:
                    continue
                name = item[:30]
                slug = make_slug(name)
                docs.append(
                    EntityDoc(
                        id=make_entity_id("timeline", slug),
                        text=item,
                        collection="timeline",
                        state="past",
                        state_ch=None,
                        fields={
                            "name": name,
                            "event_time": "",
                            "chapter": None,
                            "era": "",
                            "tags": "",
                            "related": "",
                        },
                    )
                )

        return docs


# --------------------------------------------------------------------------- #
# 全量提取
# --------------------------------------------------------------------------- #

ALL_EXTRACTORS = {
    "characters": CharacterExtractor,
    "locations": LocationExtractor,
    "items": ItemExtractor,
    "foreshadowing": ForeshadowingExtractor,
    "easter_eggs": EasterEggExtractor,
    "storylines": StorylineExtractor,
    "events": EventExtractor,
    "timeline": TimelineExtractor,
}


def extract_all(project_root: Path) -> dict[str, list[EntityDoc]]:
    """从项目文件提取所有类型的实体。

    返回 {collection_name: [EntityDoc, ...]}。
    """
    results: dict[str, list[EntityDoc]] = {}
    for name, cls in ALL_EXTRACTORS.items():
        try:
            results[name] = cls().extract(project_root)
        except Exception:
            results[name] = []
    return results


def extract_collection(project_root: Path, collection: str) -> list[EntityDoc]:
    """提取指定类型的实体。"""
    cls = ALL_EXTRACTORS.get(collection)
    if cls is None:
        return []
    return cls().extract(project_root)

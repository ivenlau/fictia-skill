# Dynamic Writing Space 设计方案

> 目标：将 Fictia 从"固定管道组装上下文"重构为"静态设计文档 + 动态实体状态 + 按需检索组装写作空间"的架构。

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    写作空间 (Writing Space)               │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  静态层      │  │  必读动态层   │  │  按需检索层    │  │
│  │  (Always)    │  │  (Mandatory) │  │  (On-Demand)  │  │
│  │             │  │              │  │               │  │
│  │ style-guide │  │ 本章大纲      │  │ 相关事件      │  │
│  │ art-design  │  │ 活跃角色卡    │  │ 历史事件      │  │
│  │ world/rules │  │ 活跃地点      │  │ 物品详情      │  │
│  │ 前章正文     │  │ 活跃伏笔      │  │ 彩蛋线索      │  │
│  │ 源文本参考   │  │ 时间线上下文  │  │ 相关故事线    │  │
│  │ 用户笔记     │  │ 前章写作备注  │  │ 更多角色      │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
│         ▲                ▲                 ▲            │
│         │                │                 │            │
│    读文件/md        entity:search      entity:search    │
└─────────────────────────────────────────────────────────┘
                         │
           ┌─────────────┼──────────────┐
           ▼             ▼              ▼
   ┌──────────┐  ┌──────────────┐  ┌──────────┐
   │ 静态文档  │  │ entity store │  │ outline  │
   │ (files)  │  │ (zvec)       │  │ 解析器    │
   └──────────┘  └──────────────┘  └──────────┘
```

### 核心原则

1. **静态文档 = 人类可读的设计产出**，变更频率低，以文件为单位读取
2. **动态实体 = 有状态的向量文档**，随章节推进不断更新，以 entity 为单位检索
3. **写作空间 = 静态 + 必读动态 + 按需动态**，由编排器根据大纲线索自动组装
4. **大纲是组装锚点**：从大纲中提取角色/地点/事件/伏笔线索，驱动必读层和检索层

---

## 2. 数据模型

### 2.1 Entity 文档结构

每个实体在 zvec collection 中是一个 `Doc`，通用 schema：

```
id          STRING    "{type}_{slug}_{version}"    如 "char_lin_yuan_v003"
text        STRING    实体描述全文（用于语义检索的主文本）
state       STRING    当前状态（枚举值）
state_ch    INT64     状态生效的章节号
name        STRING    实体名称
tags        STRING    逗号分隔的标签（用于过滤）
related     STRING    逗号分隔的关联实体 id
chapter     INT64     首次引入章节（nullable）
```

**版本策略**：每次状态变更生成新 version（v001, v002...），旧版本保留但标记 `archived=true`。
查询时默认只返回最新版本（`version` 最大的那条）。

### 2.2 Collection 定义

#### `characters` — 角色

```
text        STRING    角色卡全文（从 md 文件提取）
state       STRING    introduced | active | major_change | absent | exit | death
state_ch    INT64
name        STRING    角色姓名
role        STRING    protagonist | antagonist | core_supporting | ...
identity    STRING    社会身份
traits      STRING    核心特质（逗号分隔）
lang_style  STRING    语言风格
arc_keyword STRING    当前弧光关键词
emotional   STRING    当前情感状态
chapter     INT64
tags        STRING
related     STRING    关联角色 id
```

**text 内容来源**：`characters/protagonist.md` 等文件的 YAML front-matter + 正文关键段落。
随章节推进，agent 可更新 `state`、`arc_keyword`、`emotional` 等字段。

#### `locations` — 地点

```
text        STRING    地点描述（环境、氛围、关键特征）
state       STRING    introduced | active | destroyed | sealed | abandoned
state_ch    INT64
name        STRING    地点名称
region      STRING    所属区域（如"北域"、"学院"）
first_ch    INT64     首次出现章节
last_ch     INT64     最后出现章节
tags        STRING
related     STRING    关联地点 id
```

**text 内容来源**：`world/setting.md` 中地理/建筑相关段落 + 章节中的场景描写。

#### `items` — 物品/道具

```
text        STRING    物品描述（外观、能力、来历）
state       STRING    unknown | hidden | discovered | owned | used | destroyed | lost
state_ch    INT64
name        STRING    物品名称
owner       STRING    当前持有者
power       STRING    能力/作用
tags        STRING
related     STRING
```

**text 内容来源**：`world/rules.md` 中物品/法器相关段落 + 章节中物品首次出现的描写。

#### `events` — 事件

```
text        STRING    事件描述（起因、经过、结果、影响）
state       STRING    pending | happening | concluded | consequence
state_ch    INT64
name        STRING    事件名称
chapter     INT64     发生章节
participants STRING   参与角色 id（逗号分隔）
location    STRING    发生地点
causes      STRING    前因事件 id
effects     STRING    后果事件 id
tags        STRING
related     STRING
```

**text 内容来源**：章节大纲中的"核心事件" + 章节正文中的事件描写。

#### `foreshadowing` — 伏笔

```
text        STRING    伏笔内容描述
state       STRING    planted | seeded | escalated | resolved | abandoned
state_ch    INT64     当前状态对应的章节
name        STRING    伏笔名称/编号
plant_ch    INT64     埋设章节
resolve_ch  INT64     计划回收章节（nullable）
type        STRING    伏笔类型（悬念/误导/铺垫/暗线）
tags        STRING
related     STRING
```

**text 内容来源**：`narrative-weave.md` 伏笔表 + `outline/chapters/chNN.md` 中的 `weave_notes`。

#### `easter_eggs` — 彩蛋

```
text        STRING    彩蛋内容描述
state       STRING    planted | hinted | discoverable | revealed
state_ch    INT64
name        STRING    彩蛋名称
type        STRING    彩蛋类型（致敬/互文/隐藏线索/伏线彩蛋）
target_ch   INT64     计划揭示章节
tags        STRING
related     STRING
```

**text 内容来源**：`narrative-weave.md` 彩蛋表。

#### `storylines` — 故事线/支线

```
text        STRING    故事线描述（目标、进展、当前状态）
state       STRING    dormant | active | escalating | climax | resolved
state_ch    INT64
name        STRING    故事线名称
type        STRING    主线 | 感情线 | 权谋线 | 成长线 | ...
priority    STRING    primary | secondary | tertiary
key_chars   STRING    关联角色 id
tags        STRING
related     STRING
```

**text 内容来源**：`narrative-weave.md` 支线表 + 章节大纲中的支线推进指令。

#### `timeline` — 时间线事件

```
text        STRING    时间线事件描述
state       STRING    past | current | foreshadowed
state_ch    INT64
name        STRING    事件名称
event_time  STRING    故事内时间（如"第三年春天"、"大战前三天"）
chapter     INT64     对应章节
era         STRING    时代/阶段
tags        STRING
related     STRING
```

**text 内容来源**：`world/timeline.md` + 章节大纲中的时间线标注。

### 2.3 状态机

#### 角色状态转移图

```
                ┌──────────┐
                │introduced│ (首次出场)
                └────┬─────┘
                     ▼
                ┌──────────┐
           ┌───>│  active   │<──────────────┐
           │    └────┬─────┘               │
           │         ▼                      │
           │    ┌──────────┐          ┌─────┴────┐
           │    │major_change│────────>│  active   │
           │    └────┬─────┘  (成长后) └──────────┘
           │         ▼
           │    ┌──────────┐
           │    │  absent   │ (暂时退场)
           │    └────┬─────┘
           │         ▼
           └─── (回归 active)
                 │
                 ▼
           ┌──────────┐    ┌──────────┐
           │   exit    │ 或 │  death   │
           └──────────┘    └──────────┘
```

#### 伏笔状态转移图

```
    ┌─────────┐     ┌─────────┐     ┌───────────┐     ┌──────────┐
    │ planted  │────>│ seeded  │────>│ escalated │────>│ resolved │
    └─────────┘     └─────────┘     └───────────┘     └──────────┘
                                                           │
                       ┌──────────┐                        │
                       │ abandoned │<───────────────────────┘
                       └──────────┘          (可选路径)
```

#### 通用状态转移规则

```python
# 状态转移由事件触发，不是任意跳转
VALID_TRANSITIONS = {
    "characters": {
        "introduced": ["active"],
        "active": ["major_change", "absent", "exit", "death"],
        "major_change": ["active"],
        "absent": ["active", "exit", "death"],
    },
    "foreshadowing": {
        "planted": ["seeded", "abandoned"],
        "seeded": ["escalated", "resolved", "abandoned"],
        "escalated": ["resolved", "abandoned"],
    },
    # ... 其他类型
}
```

---

## 3. 索引器设计

### 3.1 索引触发时机

| 触发事件 | 索引动作 |
|---------|---------|
| 阶段 7（人物设计）确认 | 从 `characters/*.md` 提取 → 写入 `characters` collection |
| 阶段 6（世界观）确认 | 从 `world/*.md` 提取地点/物品 → 写入 `locations`、`items` |
| 阶段 5（叙事编织）确认 | 从 `narrative-weave.md` 提取伏笔/彩蛋/故事线 → 写入 `foreshadowing`、`easter_eggs`、`storylines` |
| 阶段 8（故事设计）确认 | 从大纲提取事件/时间线 → 写入 `events`、`timeline` |
| `stage chapter outline N` | 从该章大纲提取事件和伏笔指令 → 更新 `events`、`foreshadowing` |
| 章节写完确认 | 从章节写作备注提取状态变更 → 更新所有受影响实体 |
| 一致性校验确认 | 校验实体状态一致性，修复冲突 |

### 3.2 提取器架构

```python
# scripts/lib/entity_extractors.py

from dataclasses import dataclass
from typing import Protocol

@dataclass
class EntityDoc:
    """一个待索引的实体文档。"""
    id: str                    # "{type}_{slug}_{version}"
    text: str                  # 语义检索主文本
    collection: str            # 目标 collection 名
    fields: dict               # 元数据字段
    state: str                 # 当前状态
    state_ch: int | None       # 状态生效章节

class EntityExtractor(Protocol):
    """从项目文件提取实体的协议。"""
    def extract(self, project_root: Path) -> list[EntityDoc]: ...

# 具体提取器：

class CharacterExtractor:
    """从 characters/*.md 提取角色实体。

    解析 YAML front-matter → 构造角色卡文本。
    front-matter 中的 growth_arc 转为 arc_keyword。
    relationships 转为 related 字段（需先建立 name→id 映射）。
    """

class LocationExtractor:
    """从 world/setting.md 提取地点实体。

    按 ## 标题分节，每节作为一个地点实体。
    提取 region（从标题层级推断）。
    场景描写段落作为 text。
    """

class ForeshadowingExtractor:
    """从 narrative-weave.md 伏笔表提取伏笔实体。

    解析 Markdown 表格行 → 构造伏笔文档。
    weave_notes 中的指令更新 state。
    """

class EventExtractor:
    """从 outline/chapters/chNN.md 提取事件实体。

    解析 '## 场景序列' 中的每个场景 → 一个事件实体。
    解析 '## 角色调度' → 更新 participants。
    解析 '## 剧情大纲' → 构造事件摘要。
    """

class TimelineExtractor:
    """从 world/timeline.md + 大纲时间线标注提取时间线实体。

    解析时间线表格 → 构造时间线事件文档。
    从大纲中提取章节对应的故事内时间。
    """
```

### 3.3 状态更新器

```python
# scripts/lib/entity_updater.py

class EntityUpdater:
    """在章节写作后更新实体状态。"""

    def update_from_chapter(
        self,
        project_root: Path,
        chapter: int,
        chapter_text: str,
        writing_notes: dict,
    ) -> list[EntityDoc]:
        """从已完成章节的写作备注中提取状态变更。

        写作备注格式：
        - **人物状态更新**: 林远左臂受伤 (第12段)
        - **伏笔操作**:
          - 埋设: 伏笔ID-F003 (神秘玉佩的来历)
          - 推进: 伏笔ID-F001
        - **新增设定**: 北域冰原的暴风雪规则

        解析后：
        1. 角色状态更新 → characters collection
        2. 伏笔埋设/推进/回收 → foreshadowing collection
        3. 新增地点/物品 → locations/items collection
        4. 事件结案 → events collection
        """
```

---

## 4. 写作空间组装器

### 4.1 核心流程

```
                    outline/chapters/chNN.md
                            │
                            ▼
                    ┌───────────────┐
                    │  大纲解析器     │
                    │  (OutlineParser)│
                    └───────┬───────┘
                            │
                ┌───────────┼───────────┐
                ▼           ▼           ▼
         角色线索      地点线索      伏笔线索
         (names)      (places)     (foreshadow_ids)
                │           │           │
                ▼           ▼           ▼
        ┌───────────────────────────────────┐
        │        实体检索器 (EntityRetriever) │
        │                                   │
        │  1. 必读实体（大纲明确提到的）       │
        │     → 精确查询 (name/id 匹配)      │
        │     → 返回当前最新状态              │
        │                                   │
        │  2. 关联实体（必读实体的 related）   │
        │     → 扩展检索                     │
        │     → 过滤：state 为 active 的      │
        │                                   │
        │  3. 上下文实体（时间线/故事线）      │
        │     → 时间窗口查询                  │
        │     → 返回 chapter ± 3 范围内的     │
        └───────────────┬───────────────────┘
                        │
                        ▼
        ┌───────────────────────────────────┐
        │       写作空间组装器                │
        │       (WritingSpaceAssembler)      │
        │                                   │
        │  静态层：                           │
        │    style-guide.md (act 提取)        │
        │    art-design.md (act 提取)         │
        │    world/rules.md (速查)            │
        │    前章正文                         │
        │    源文本参考                       │
        │    用户笔记                         │
        │                                   │
        │  必读动态层：                       │
        │    本章大纲 (完整)                   │
        │    必读角色卡 (当前状态)              │
        │    必读地点描述 (当前状态)            │
        │    活跃伏笔列表 (本章需操作的)        │
        │    时间线上下文 (前3章)              │
        │    前章写作备注                      │
        │                                   │
        │  按需检索层：                       │
        │    相关事件 (语义检索)               │
        │    更多角色 (语义检索)               │
        │    历史地点 (语义检索)               │
        │    故事线状态 (过滤查询)             │
        └───────────────┬───────────────────┘
                        │
                        ▼
              .fictia-cache/chNN-writer-context.md
```

### 4.2 大纲解析器

```python
# scripts/lib/outline_parser.py

@dataclass
class OutlineHints:
    """从大纲中提取的线索，驱动实体检索。"""

    chapter: int
    target_words: int

    # 角色线索
    character_names: list[str]       # 从"角色调度"表提取
    character_states: dict[str, str] # 角色 → 本章起始状态

    # 地点线索
    locations: list[str]             # 从场景序列的"地点"字段提取

    # 伏笔线索
    foreshadow_ops: list[ForeshadowOp]  # 从 weave_notes 提取
    # plant / seed / escalate / resolve

    # 事件线索
    scene_events: list[str]          # 从场景序列的"场景目标"提取

    # 时间线线索
    story_time: str | None           # 从大纲时间标注提取

    # 故事线线索
    active_storylines: list[str]     # 从大纲中提及的支线提取

def parse_outline(chapter: int, outline_path: Path) -> OutlineHints:
    """解析章节大纲，提取所有实体线索。

    解析策略：
    1. '## 角色调度' 表格 → character_names, character_states
    2. '## 场景序列' 中的 地点/时间 → locations, story_time
    3. '## 伏笔/支线/彩蛋指令' + weave_notes → foreshadow_ops
    4. '## 场景序列' 中的 场景目标 → scene_events
    5. 正则匹配角色名（兜底）→ 补充 character_names
    """
```

### 4.3 实体检索器

```python
# scripts/lib/entity_retriever.py

@dataclass
class RetrievedEntities:
    """一次检索的结果集。"""

    # 必读实体（大纲明确提到的）
    mandatory_characters: list[Hit]
    mandatory_locations: list[Hit]
    mandatory_foreshadowing: list[Hit]

    # 关联实体（必读实体的 related 展开）
    related_characters: list[Hit]
    related_locations: list[Hit]

    # 上下文实体
    timeline_window: list[Hit]       # 前后 N 章的时间线事件
    active_storylines: list[Hit]     # 所有 active 状态的故事线
    recent_events: list[Hit]         # 前 3 章的事件

    # 按需检索结果（agent 主动查询）
    on_demand: list[Hit]

class EntityRetriever:
    """基于大纲线索检索实体。"""

    def __init__(self, store: VectorStore):
        self.store = store

    def retrieve_for_chapter(self, hints: OutlineHints) -> RetrievedEntities:
        """根据大纲线索组装实体集。"""

        # 1. 精确查询必读实体
        chars = self._retrieve_by_names("characters", hints.character_names)
        locs = self._retrieve_by_names("locations", hints.locations)
        fores = self._retrieve_by_ops(hints.foreshadow_ops)

        # 2. 展开关联实体
        related_chars = self._expand_related("characters", chars)
        related_locs = self._expand_related("locations", locs)

        # 3. 时间窗口查询
        timeline = self._retrieve_timeline_window(hints.chapter, window=3)

        # 4. 活跃故事线
        storylines = self._retrieve_by_state("storylines", "active")

        # 5. 近期事件
        events = self._retrieve_recent_events(hints.chapter, lookback=3)

        return RetrievedEntities(...)

    def _retrieve_by_names(self, collection: str, names: list[str]) -> list[Hit]:
        """按名称精确匹配（用 filter 或语义检索）。"""
        # 策略：先尝试 filter 精确匹配，不够再语义补充
        ...

    def _expand_related(self, collection: str, seeds: list[Hit]) -> list[Hit]:
        """从种子实体的 related 字段展开关联实体。"""
        # 只返回 state 为 active 的关联实体
        ...

    def _retrieve_timeline_window(self, chapter: int, window: int) -> list[Hit]:
        """检索 chapter ± window 范围内的时间线事件。"""
        # filter: state_ch >= chapter - window AND state_ch <= chapter + window
        ...
```

### 4.4 写作空间组装器

```python
# scripts/lib/writing_space.py

class WritingSpaceAssembler:
    """组装完整的写作空间上下文。"""

    def __init__(
        self,
        project_root: Path,
        store: VectorStore,
        retriever: EntityRetriever,
    ):
        self.project_root = project_root
        self.store = store
        self.retriever = retriever

    def assemble(self, chapter: int) -> str:
        """为指定章节组装写作空间，输出 markdown。"""

        # ── 静态层 ──
        style = self._load_style_for_act(chapter)
        art = self._load_art_for_act(chapter)
        rules = self._load_world_rules()
        prev_chapter = self._load_previous_chapter(chapter)
        source_ref = self._load_source_reference()
        user_notes = self._load_user_notes()

        # ── 大纲解析 → 线索 ──
        outline_path = self.project_root / "outline" / "chapters" / f"ch{chapter:02d}.md"
        hints = parse_outline(chapter, outline_path)
        outline_text = outline_path.read_text(encoding="utf-8")

        # ── 必读动态层 ──
        entities = self.retriever.retrieve_for_chapter(hints)

        # ── 组装 ──
        sections = []

        # Part 1: 本章大纲（必读，完整）
        sections.append(self._section("本章大纲", outline_text))

        # Part 2: 必读角色卡
        sections.append(self._section(
            "本章活跃角色",
            self._format_character_cards(entities.mandatory_characters)
        ))

        # Part 3: 必读地点
        sections.append(self._section(
            "本章场景地点",
            self._format_location_descriptions(entities.mandatory_locations)
        ))

        # Part 4: 本章伏笔操作
        sections.append(self._section(
            "伏笔指令与当前状态",
            self._format_foreshadowing(entities.mandatory_foreshadowing, hints.foreshadow_ops)
        ))

        # Part 5: 时间线上下文
        sections.append(self._section(
            "时间线上下文",
            self._format_timeline(entities.timeline_window)
        ))

        # Part 6: 活跃故事线
        sections.append(self._section(
            "活跃故事线",
            self._format_storylines(entities.active_storylines)
        ))

        # Part 7: 近期事件回顾
        sections.append(self._section(
            "近期事件",
            self._format_events(entities.recent_events)
        ))

        # Part 8: 关联实体（灰色地带，供参考）
        if entities.related_characters:
            sections.append(self._section(
                "相关角色（关联检索）",
                self._format_character_cards(entities.related_characters)
            ))

        # Part 9: 静态层
        sections.append(self._section("风格指南", style))
        sections.append(self._section("艺术设计", art))
        sections.append(self._section("世界观速查", rules))
        sections.append(self._section("前章正文", prev_chapter))

        # Part 10: 可选静态层
        if source_ref:
            sections.append(self._section("源文本参考", source_ref))
        if user_notes:
            sections.append(self._section("用户笔记", user_notes))

        return "\n\n---\n\n".join(sections)
```

---

## 5. CLI 接口设计

### 5.1 新增子命令

```bash
# ── 实体管理 ──

# 从项目文件批量提取并索引所有实体（首次建立 or 全量重建）
fictia entity index-all [--project <path>]

# 索引特定类型的实体
fictia entity index characters [--project <path>]
fictia entity index locations [--project <path>]
fictia entity index foreshadowing [--project <path>]
fictia entity index events [--project <path>]
fictia entity index timeline [--project <path>]
fictia entity index storylines [--project <path>]
fictia entity index items [--project <path>]
fictia entity index easter-eggs [--project <path>]

# 更新单个实体状态（章节写完后由编排器调用）
fictia entity update <collection> <entity_id> \
    --state <new_state> \
    --state-ch <chapter> \
    [--text <new_text>] \
    [--fields key=value ...]

# 查询实体
fictia entity get <collection> <entity_id>          # 获取单个实体
fictia entity list <collection> [--state <state>]    # 列出某 collection 的实体
fictia entity status                                 # 各 collection 统计

# 实体语义搜索（跨 collection 或指定 collection）
fictia entity search "<query>" \
    [--collection <name>] \
    [--state <state>] \
    [--top-k N]

# ── 写作空间 ──

# 为指定章节组装写作空间上下文
fictia ctx writing-space --chapter N [--project <path>]

# 解析大纲线索（调试用）
fictia ctx outline-hints --chapter N [--project <path>]
```

### 5.2 对现有命令的影响

| 现有命令 | 变化 |
|---------|------|
| `fictia vector index-chapter N` | 保留，仍用于全文 chunk 索引（与 entity 索引并行） |
| `fictia vector search` | 保留，但新增 `entity search` 作为结构化检索入口 |
| `fictia ctx assemble writer --chapter N` | 内部改为调用 `WritingSpaceAssembler`，输出格式不变 |
| `fictia stage chapter outline N` | 确认后自动触发 entity 提取（大纲中的事件/伏笔） |
| `fictia consistency confirm --chapter N` | 确认后自动触发 entity 状态更新 |

---

## 6. 与现有系统的集成

### 6.1 数据流变更

```
之前：
  文件 (characters/*.md, world/*.md, ...)
    → 固定管道 ctx assemble
    → 写手拿到 monolithic context

之后：
  文件 → Entity Extractors → zvec entity collections
                                ↓
  大纲 → OutlineParser → OutlineHints
                                ↓
                      EntityRetriever → RetrievedEntities
                                ↓
  文件 (static) + entities → WritingSpaceAssembler → 写手拿到精细化 context
```

### 6.2 向后兼容

- **不删除** 现有的 `chapters/notes/sources` chunk collection——它们用于全文语义搜索（"找出所有提到'北域'的段落"）
- **新增** 8 个 entity collection 用于结构化实体检索
- `ctx assemble writer` 的**输出格式不变**，只是内部实现更精细
- 现有的 `vector search` 命令**保留**，新增 `entity search` 命令

### 6.3 project.yaml 新增字段

```yaml
# 新增
entity_index:
  last_full_index: "2026-07-10T10:00:00Z"
  collections:
    characters: { count: 12, last_updated: "2026-07-10T10:00:00Z" }
    locations: { count: 8, last_updated: "2026-07-10T10:00:00Z" }
    events: { count: 25, last_updated: "2026-07-10T10:00:00Z" }
    foreshadowing: { count: 15, last_updated: "2026-07-10T10:00:00Z" }
    # ...
```

---

## 7. 实现分期

### Phase 1: 实体数据模型 + 提取器（核心）

**目标**：能从现有项目文件提取实体并存入 zvec。

- [ ] `scripts/lib/entity_schema.py` — EntityDoc dataclass, collection schema 定义, 状态枚举
- [ ] `scripts/lib/entity_extractors.py` — 8 个 extractor 实现
- [ ] `scripts/lib/entity_store.py` — EntityStore 类（封装 zvec CRUD + 状态查询）
- [ ] `scripts/tests/test_entity_schema.py` — 数据模型单元测试
- [ ] `scripts/tests/test_entity_extractors.py` — 提取器单元测试

### Phase 2: 大纲解析器 + 实体检索器

**目标**：能从大纲提取线索，检索相关实体。

- [ ] `scripts/lib/outline_parser.py` — OutlineHints 解析
- [ ] `scripts/lib/entity_retriever.py` — EntityRetriever 实现
- [ ] `scripts/tests/test_outline_parser.py`
- [ ] `scripts/tests/test_entity_retriever.py`

### Phase 3: 写作空间组装器 + CLI 集成

**目标**：端到端可用，替换现有 ctx assemble writer。

- [ ] `scripts/lib/writing_space.py` — WritingSpaceAssembler 实现
- [ ] `scripts/fictia` CLI 新增 `entity` 和 `ctx writing-space` 子命令
- [ ] 修改 `ctx assemble writer` 内部调用 WritingSpaceAssembler
- [ ] `scripts/tests/test_writing_space.py`

### Phase 4: 状态更新器 + 自动化集成

**目标**：章节写完后自动更新实体状态。

- [ ] `scripts/lib/entity_updater.py` — 从写作备注提取状态变更
- [ ] 集成到 `stage chapter increment` — 自动触发 entity 更新
- [ ] 集成到 `consistency confirm` — 校验 entity 状态一致性
- [ ] `scripts/tests/test_entity_updater.py`

### Phase 5: 优化 + Agent 自主检索

**目标**：让 agent 能自主发起 entity 查询。

- [ ] SKILL.md 更新：写手 agent prompt 增加"可选实体检索"指令
- [ ] `fictia entity search` 命令优化（支持组合过滤）
- [ ] 性能优化：entity 缓存、批量查询
- [ ] 文档更新

---

## 8. 写作备注格式扩展

当前写作备注已有伏笔操作和人物状态更新。需新增字段以支持更丰富的实体状态变更：

```markdown
### 写作备注

- **字数**: 3200
- **伏笔操作**:
  - 埋设: foreshadow_F003 (神秘玉佩的来历)
  - 推进: foreshadow_F001 (林远身世线索在第三段提及)
- **副线进度**: 感情线推进 (林远与苏瑶重逢)
- **新增设定**: 无
- **人物状态更新**: 林远左臂受伤 (第12段)
- **地点变更**: location_北域冰原 → state: active (首次进入)
- **物品状态**: item_神秘玉佩 → state: discovered (第8段发现)
- **事件结案**: event_北域围猎 → state: concluded
- **下章衔接点**: 本章结尾林远决定前往北域，下章从北域入口开始
```

---

## 9. 示例：第 16 章的写作空间

假设小说已写到第 16 章，大纲提到：林远在北域冰原遭遇伏击，发现神秘玉佩的线索，与苏瑶通过传音符短暂联系。

### 大纲解析结果 (OutlineHints)

```json
{
  "chapter": 16,
  "target_words": 3000,
  "character_names": ["林远", "苏瑶", "黑衣人"],
  "character_states": {
    "林远": "active",
    "苏瑶": "absent",
    "黑衣人": "introduced"
  },
  "locations": ["北域冰原", "南境"],
  "foreshadow_ops": [
    {"id": "F001", "op": "seeded", "hint": "林远身世线索"},
    {"id": "F003", "op": "planted", "hint": "神秘玉佩来历"}
  ],
  "scene_events": ["遭遇伏击", "发现玉佩线索", "传音联系"],
  "story_time": "北行第七天",
  "active_storylines": ["感情线", "身世暗线"]
}
```

### 写作空间输出结构

```
# 写作空间 · 第 16 章

## 本章大纲
[完整 outline/chapters/ch16.md 内容]

## 本章活跃角色
### 林远（状态: active）
[角色卡：身份、特质、当前情感、语言风格、成长弧光当前节点]
### 苏瑶（状态: absent，远程出场）
[角色卡精简版]
### 黑衣人（状态: introduced，本章首次出场）
[角色卡：基础信息 + 出场设定]

## 本章场景地点
### 北域冰原（状态: active）
[地点描述：环境、氛围、已知信息]

## 伏笔指令与当前状态
| 伏笔 | 操作 | 当前状态 | 描述 |
|------|------|---------|------|
| F001 身世线索 | seeded | planted→seeded | 在第三段埋入线索 |
| F003 神秘玉佩 | planted | 新建 | 本章首次提及来历 |

## 时间线上下文
- ch13: 林远离开学院
- ch14: 进入北域边界
- ch15: 北域遭遇暴风雪
- **ch16: 北域冰原（本章）**
- ch17: ???

## 活跃故事线
- 身世暗线（dormant→active，本章推进）
- 感情线（active，苏瑶远程出场推进）

## 近期事件
- ch15: 暴风雪中失去补给
- ch14: 在北域边界遇到行商

## 风格指南
[act 对应的风格提取]

## 世界观速查
[world/rules.md 压缩]

## 前章正文
[ch15 完整正文]

## 前章写作备注
[ch15 写作备注]

## 用户笔记
[notes/summary.md]
```

---

## 10. 关键设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 实体版本化 | 每次状态变更生成新 version | 保留历史，支持回溯和一致性校验 |
| 全文 chunk 与 entity 并存 | 保留两套 | chunk 用于模糊语义搜索，entity 用于精确状态查询 |
| 大纲作为组装锚点 | 必读 | 大纲是唯一确定"本章需要什么"的可靠来源 |
| 状态更新时机 | 章节确认后 | 避免写作中状态不稳定 |
| 静态/动态边界 | 有变化=动态 | 与用户定义一致 |
| 提取器从 md 文件提取 | 不废弃 md 文件 | 人类可读性、git 友好、向后兼容 |

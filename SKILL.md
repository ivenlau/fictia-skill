---
name: fictia
description: >
  Fictia AI 小说创作流水线——11 阶段、11 专用 agent 的中文长篇小说生成流程。
  触发条件：用户提及 Fictia、AI 小说创作、流水线写作、小说创作、写作流水线、
  多 agent 小说系统，或需要进行题材分析、人物设计、章节写作、一致性校验等小说创作任务。
---

# Fictia — AI 小说创作流水线

Claude 即流水线——直接扮演各 agent，从 `references/agents/` 读取 agent prompt，
从项目文件收集上下文，生成产出，通过 `project.yaml` 管理状态。
使用本地零依赖 CLI 处理机械化环节，并配合 Read/Write/Edit/Glob/Grep 完成创作产出。

## 路径约定

**FICTIA_HOME**：本 SKILL.md 所在的目录。启动时先用 Glob 定位 SKILL.md，以其父目录作为 FICTIA_HOME。

CLI 调用统一使用 `python "${FICTIA_HOME}/scripts/fictia" <command>`。
读取 agent prompt 等资源文件时，使用 `${FICTIA_HOME}/references/agents/...` 等路径。
执行时将 `${FICTIA_HOME}` 替换为实际绝对路径。

## 启动判定

用户调用本 skill 时：

1. **定位项目**：从当前目录向上查找 `project.yaml`。
2. **分支到对应工作流**：
   - 未找到项目 → **新建项目**工作流
   - 项目存在，阶段未开始 → **启动流水线**工作流
   - 项目存在，部分阶段已确认 → **继续流水线**工作流
   - 用户要求导出 → **导出**工作流
   - 用户要求修改已有内容 → **内容修改**工作流
   - 一般性问题 → 直接回答

## 状态面板

**每次进入已有项目的工作流时显示**（继续流水线、内容修改、导出）。新建项目时不显示（尚无 `project.yaml`）。

### 渲染方式

1. 先确定 FICTIA_HOME（本 SKILL.md 所在目录）。
2. 用 Bash 工具执行 `python "${FICTIA_HOME}/scripts/fictia" status`。
3. **将命令输出的 ASCII 面板原样展示给用户作为第一条回复。** 不可跳过、不可省略、不可合并到后续文字中。

## 工作流：新建项目

1. 与用户讨论题材、目标字数、卷数、核心设定。
2. 创建项目（见"新建项目创建"小节）。
3. 进入流水线执行。

## 工作流：小说改写 / 仿写 / 续写

当用户提供已有小说数据并要求改写、仿写或续写时，仍使用现有 01-11 阶段流水线；区别只是先导入源文本，并在后续阶段把源文本作为参考上下文。

1. **确认模式**：
   - `rewrite`（改写）：保留核心情节/人物功能，重构表达、节奏和细节。
   - `imitation`（仿写）：提取题材、叙事结构、节奏、语言风格，创作新故事；不照搬设定和正文。
   - `continuation`（续写）：分析已给文本的情节、人物、伏笔和风格，从断点继续写。
2. **创建或进入项目**：如无 `project.yaml`，先按新建项目流程创建项目；如已有项目，先显示状态面板。
3. **导入源文本**：运行 `python "${FICTIA_HOME}/scripts/fictia" source import <file> --workflow <rewrite|imitation|continuation>`。支持 `.epub`、`.txt`、`.md`，导入后会规范化为 `sources/*.md` 并写入 `project.yaml.source_material`。
4. **执行现有阶段**：
   - 阶段 1-3：从源文本提炼题材、结构、风格约束。
   - 阶段 4-8：按目标模式重建艺术设计、叙事、世界、人物和大纲。
   - 阶段 9-11：继续使用写作、编辑、一致性校验流程；`ctx assemble` 会自动带入源文本参考。
5. **合规约束**：改写/仿写时避免大段复用原文；续写时只延续用户提供文本中的上下文、人物和伏笔。

## 并行模式（可选）

适用场景：长篇创作中希望故事设计（stage 8）和章节写作（stage 9）同时进行——某章大纲完成后即可立即进入该章写作，不必等所有章节大纲完成。

**默认关闭**，开启不影响现有流程（`story` 阶段仍可独立 confirm）。

### 启用 / 关闭 / 查询

```bash
python "${FICTIA_HOME}/scripts/fictia" parallel-design on      # 开启
python "${FICTIA_HOME}/scripts/fictia" parallel-design off     # 关闭（恢复原严格顺序）
python "${FICTIA_HOME}/scripts/fictia" parallel-design status  # 查询
```

### 状态字段

- `pipeline_settings.parallel_design: bool`（默认 `false`）—— 模式开关
- `chapters.outlines: dict[str, timestamp]` —— 每章大纲的就绪时间戳，例如 `ch01: "2026-06-17T10:00:00Z"`

老项目加载时自动回填空 map，无需手动迁移。

### 启用后的工作流

1. 先确认上游设计阶段：`style / art_design / narrative_weave / world / characters`（顺序按依赖图）。
2. 进入 stage 8 故事设计，逐章产出 `outline/chapters/chNN.md`。
3. 每章大纲写完后，运行 `python "${FICTIA_HOME}/scripts/fictia" stage chapter outline --chapter N` 标记就绪（这一步会**自动开启并行模式**）。
4. 立即可进入该章写作：
   - `python "${FICTIA_HOME}/scripts/fictia" stage chapter next` —— 找出下一可写章节号
   - `python "${FICTIA_HOME}/scripts/fictia" stage chapter status` —— 查看所有章节的大纲就绪/写作/确认状态
5. stage 8 仍可继续推进更多章节大纲，与已写章节解耦。

### 章节可写判定（`is_chapter_writable`）

第 N 章可写当且仅当：
- 上游五个设计阶段（`style / art_design / narrative_weave / world / characters`）全部 `confirmed`
- `chapters.outlines.chNN` 时间戳存在
- `outline/chapters/chNN.md` 文件存在
- `chapters.written < N`（章节尚未写到该号）

### 不变的行为

- **失效传播**：修改 stage 8 后，已写章节沿用现有 `needs_update` 机制（`PROPAGATION["story"] = ["chapters"]`），下次编辑审核时会感知到差异。
- **编辑审核**（stage 10）、**一致性校验**（stage 11）：行为完全不变。
- **章节计数、里程碑检查、状态面板**（`status`）：正常。
- **串行模式**（`parallel_design=false`）：恢复为原有"全部故事设计完成后才能写作"的严格顺序，老项目零行为变化。

### 与 09 章节写手 agent 的协作

写手 agent 的 prompt 已增加"前置条件"段，要求运行 `stage chapter outline N` 后再写。subagent 阶段仍由主代理统一调度，主代理在调用 09 agent 前先运行 `stage chapter next` 确认目标章节号。

---

## 向量检索（可选 RAG 能力）

适用场景：长篇创作需要跨章节语义检索（如"找出所有'林远受伤'的场景"、"林远与苏瑶的所有互动"、"凡涉及北域的伏笔"）。

### 启用

1. 安装 zvec：`pip install zvec`
2. 选择 embedding 模式（二选一）：

   **本地模式**（BGE-M3，中文 SOTA，免费离线，需 ~2.3GB 模型）：
   ```bash
   pip install sentence-transformers
   export FICTIA_EMBEDDING=local
   ```

   **API 模式**（智谱 embedding-2，云端，需 API key）：
   ```bash
   pip install httpx
   export ZHIPUAI_API_KEY=your_key_here
   export FICTIA_EMBEDDING=api
   ```

3. **无需手动索引** —— `fictia stage chapter outline --chapter N` 与 `fictia consistency confirm --chapter N` 会自动入库
4. 检索：`fictia vector search "<query>" --top-k 8`

### 集成到 agent 上下文

```bash
fictia ctx semantic-search "林远在北域受伤" --chapter 16 --top-k 8
```

把检索结果格式化为 markdown，可粘贴到 09-chapter-writer / 10-editor / 11-consistency-checker agent 的上下文中。

### Embedding 切换

- `stub`（默认）：hash-based 256-dim，无语义，仅跑通工具链
- `local`：BGE-M3 本地，1024-dim
- `api`：智谱 embedding-2 云端，1024-dim
- `local` ↔ `api` 都是 1024-dim，切换**不需要重建索引**
- `stub` → `local|api` 必须 `fictia vector clear && index-all` 重建

### 笔记与源文本

笔记（`notes/summary.md`）与源文本（`sources/*.md`）需手动索引：

```bash
fictia vector index-notes
fictia vector index-source
```

向量数据存放在 `<project>/.fictia/zvec/`，已加入 `.gitignore`。

---

## 动态写作空间（可选 Entity RAG）

适用场景：长篇创作中需要精细化的实体状态管理——角色状态随章节变化、伏笔生命周期追踪、地点/物品/事件的状态流转。

### 核心概念

**静态数据**（以文件为单位读取）：风格指南、艺术设计、世界观规则、前章正文、源文本、用户笔记。

**动态实体**（以 entity 为单位检索，有状态、有版本）：

| Collection | 实体类型 | 状态流转示例 |
|-----------|---------|------------|
| `characters` | 角色 | introduced → active → major_change → exit/death |
| `locations` | 地点 | introduced → active → destroyed/sealed/abandoned |
| `items` | 物品 | unknown → hidden → discovered → owned → destroyed |
| `events` | 事件 | pending → happening → concluded → consequence |
| `foreshadowing` | 伏笔 | planted → seeded → escalated → resolved/abandoned |
| `easter_eggs` | 彩蛋 | planted → hinted → discoverable → revealed |
| `storylines` | 故事线 | dormant → active → escalating → climax → resolved |
| `timeline` | 时间线 | past → current → foreshadowed |
| `relations` | 关系 | active → changed → dissolved |

### 启用

同向量检索，需先安装 zvec 和选择 embedding 模式。

### 初始化实体索引

从现有项目文件（characters/*.md、world/*.md、narrative-weave.md、outline/chapters/*.md）批量提取实体：

```bash
fictia entity index-all          # 全量提取所有 8 类实体
fictia entity index characters   # 仅提取角色
fictia entity index foreshadowing # 仅提取伏笔
```

### 写作空间组装

为指定章节组装完整的写作空间上下文（静态 + 必读动态 + 按需检索）：

```bash
fictia ctx writing-space --chapter 16
# → .fictia-cache/ch16-writing-space.md
```

写作空间包含三层：
1. **静态层**：风格指南、艺术设计、世界观速查、前章正文、源文本、用户笔记
2. **必读动态层**：本章大纲、大纲中提到的角色卡（当前状态）、地点、伏笔指令、时间线、活跃故事线
3. **按需检索层**：agent 可通过 `fictia entity search` 自主查询更多实体

### 实体查询

```bash
fictia entity status                          # 各 collection 统计
fictia entity list characters                 # 列出所有角色
fictia entity list foreshadowing --state planted  # 列出已埋设的伏笔
fictia entity get characters char_lin_yuan_v001   # 获取单个实体详情
fictia entity search "北域" --collection locations # 语义搜索地点
fictia entity search "林远受伤" --top-k 5         # 跨 collection 语义搜索
```

### 大纲线索解析（调试用）

```bash
fictia entity outline-hints --chapter 16
# 输出大纲中提取的角色、地点、伏笔、事件等线索
```

### 状态更新

章节写完后，写作备注中的状态变更会自动解析：

```markdown
### 写作备注
- **人物状态更新**: 林远左臂受伤 (第12段)
- **地点变更**: 北域冰原 → state: active
- **物品状态**: 神秘玉佩 → state: discovered
- **事件结案**: 北域围猎 → state: concluded
```

也可手动更新：

```bash
fictia entity update characters char_lin_yuan_v001 --state major_change --state-ch 16
```

### 实体数据位置

实体数据存放在 `<project>/.fictia/zvec/{characters,locations,items,events,foreshadowing,easter_eggs,storylines,timeline}/`，已加入 `.gitignore`。

与现有的 chunk-based 全文检索（chapters/notes/sources）并存——chunk 用于模糊语义搜索，entity 用于精确状态查询。

---

## 知识图谱（可选 Graph RAG）

适用场景：需要查询实体间关系网络（如"林远的师徒关系"、"哪些角色参与了北域围猎"、"伏笔 F001 关联哪些角色"）。

### 核心概念

在 8 个 entity collection 之上，新增 `relations` collection 存储实体间的关系三元组：

```
(源实体) --[关系类型]--> (目标实体)
例: (林远) --[mentor]--> (清风长老)
```

**支持 20+ 种关系类型**：friend、enemy、mentor、family、lover、ally、rival、protects、owns、participates、causes、affects、reveals、located_at、belongs_to、key_char、related_to 等。

### 启用

同向量检索和动态写作空间，需先安装 zvec 和选择 embedding 模式。

### 构建图谱

**自动构建**（推荐）：`entity index-all` 会自动从已有实体字段构建知识图谱：

```bash
fictia entity index-all
# → characters: 12 entities
# → locations: 8 entities
# → ...
# ✓ 知识图谱已构建: 47 条关系
```

**手动构建**：

```bash
fictia graph build
```

数据来源（自动从已有字段提取，无需手动维护）：
- `characters/*.md` 的 `relationships` 字段 → 角色间关系
- `events` 的 `participants`/`causes`/`effects` → 事件因果链
- `storylines` 的 `key_chars` → 故事线-角色绑定
- `items` 的 `owner` → 物品归属
- 所有实体的 `related` 字段 → 通用关联

### 图谱查询

```bash
fictia graph status                          # 图谱统计（关系数、类型分布）
fictia graph neighbors char_lin_yuan_v001    # 某角色的关系网
fictia graph neighbors char_lin_yuan_v001 --rel-type mentor  # 按关系类型过滤
fictia graph path char_lin_yuan_v001 loc_qingyun_v001        # 两实体间最短路径
fictia graph search "师徒关系"                # 语义搜索关系
fictia graph search "林远参与的事件" --top-k 5
```

### 章节后自动抽取

**自动触发**（推荐）：`stage chapter increment` 会自动从章节写作备注中抽取新关系：

```bash
fictia stage chapter increment
# chapters: written=3, confirmed=3
# ✓ 自动抽取关系: 2 条（第3章）
```

**手动抽取**：

```bash
fictia graph extract --chapter 3
```

写作备注中支持抽取的关系信号：
- 伏笔操作 → (伏笔, reveals, 角色)
- 人物状态更新 → (事件, affects, 角色)
- 物品状态变更 → (角色, owns, 物品)
- 事件结案 → (事件, affects, 相关实体)

### LLM 异步抽取（可选）

配置 LLM API 后，可从章节正文自动抽取更丰富的关系：

```bash
export FICTIA_LLM_API_BASE=https://api.openai.com/v1
export FICTIA_LLM_API_KEY=sk-xxx

# 通过 HTTP API 触发（需先启动 embed_server）
curl -X POST http://127.0.0.1:8700/graph/extract \
  -d '{"chapter": 3, "use_llm": true}'
```

### 图谱导出（可视化）

```bash
fictia graph export
# → .fictia-cache/graph-export.json
# 包含 nodes[] 和 edges[]，可直接用于 D3.js / ECharts 力导向图
```

### 集成到写作空间

图谱查询已集成到 `EntityRetriever`，写作空间组装时会自动通过图谱展开关联实体：

- **原有逻辑**：从 `related` 字段展开（逗号分隔字符串）
- **增强逻辑**：同时从 `relations` collection 查询图谱邻居（1跳）
- 双源合并去重，检索更全面

### 实体数据位置

关系数据存放在 `<project>/.fictia/zvec/relations/`，与 8 个 entity collection 并存。

---

## 头脑风暴模式

**设计阶段（01-08）默认启用头脑风暴。** 章节写作/编辑/校验（09-11）不启用。

### 模式配置

```bash
python "${FICTIA_HOME}/scripts/fictia" brainstorm-mode on       # 开启（默认）
python "${FICTIA_HOME}/scripts/fictia" brainstorm-mode off      # 关闭（直接产出）
python "${FICTIA_HOME}/scripts/fictia" brainstorm-mode status   # 查询
```

状态字段：`pipeline_settings.brainstorm_mode: bool`（默认 `true`）。

### 三段式协议（设计阶段 01-08）

当 `brainstorm_mode=true` 时，每个设计阶段的执行分为三段：

#### 第一段：探索（Explore）

主代理读取全部输入后，**在生成正式产出之前**，先向用户展示 3-5 个创意方向：

每个方向必须包含：
- **方向名称**：一句话概括
- **具体示例**：不能只说"走暗黑风格"，要给出具体的设定/情节/风格示例
- **叙事价值**：选择这个方向，故事会获得什么
- **风险与代价**：选择这个方向，可能失去什么或面临什么挑战
- **参照作品**（如有）：同类方向的成功案例

**发散约束**（必须满足）：
- 至少一个**反直觉选项**：违反该题材常见套路的方向
- 至少一个**极端选项**：与推荐方案形成鲜明对比
- 给出**明确推荐**：主代理必须说"我推荐方向 X，因为..."

#### 第二段：共创（Co-Create）

展示方向后，进入多轮讨论：

- **一次只问一个问题**：避免信息过载
- 使用 `AskUserQuestion` 工具提问
- 用户可以：选择某个方向 / 修改某个方向 / 提出全新方向 / 要求继续探索某个方向
- 主代理根据用户反馈调整方向，可以继续追问
- **收敛信号**：用户明确说"就这个方向" / "按这个来" / "确认" 时，结束讨论

#### 第三段：产出（Produce）

方向确定后，按已确认的方向 + 用户约束生成完整产出。

产出文件末尾追加创意讨论记录：

```markdown
### 创意讨论记录
- **探索方向**：[列出所有展示过的方向]
- **用户选择**：[用户最终选择的方向]
- **关键决策**：[讨论中做出的重要决策]
- **被否决的方向**：[被否决的方向及原因]
```

### 非头脑风暴模式（`brainstorm_mode=false`）

跳过第一段和第二段，直接进入第三段产出。适用于批量模式、赶时间、或用户明确要求直接产出。

### 涉及范围

头脑风暴仅适用于**设计阶段（01-08）**：

| 阶段 | 头脑风暴重点 |
|------|------------|
| 01 题材分析 | 题材融合、反套路实验、跨题材可能性 |
| 02 架构设计 | 结构实验、节奏曲线变体、高潮布局 alternatives |
| 03 风格设计 | 语言实验（同段落多种写法）、叙事距离、POV 探索 |
| 04 艺术设计 | 意象系统、色彩基调、象征体系探索 |
| 05 叙事编织 | 伏笔策略（直叙/误导/暗线）、支线交织方案、信息释放节奏 |
| 06 世界观构建 | 力量体系创意、社会规则边界条件、"如果这个世界有一条被打破的规则？" |
| 07 人物设计 | 角色深度挖掘、隐藏秘密、道德灰度、反派动机正义性 |
| 08 故事设计 | 关键转折点 alternatives、场景变体、"如果角色做了相反的选择？" |

**不适用头脑风暴的阶段**：09（章节写作）、10（编辑审核）、11（一致性校验）——这些是质量导向，不是创意导向。

### 非设计阶段的重大决策

当用户在非头脑风暴阶段提出重大修改需求时（整体重构、多阶段联动修改），仍可使用 `AskUserQuestion` 询问是否开启独立的头脑风暴讨论，但不强制。

---

## 工作流：继续流水线

**用户清空上下文后重新进入时的主工作流。** 当用户调用 Fictia 且项目已存在、部分阶段已确认时，始终使用此工作流。

0. **【必做】显示状态面板**：用 Bash 执行 `python "${FICTIA_HOME}/scripts/fictia" status`，将输出原样展示给用户。此步不可跳过。
1. **确定下一阶段**：用 Bash 执行 `python "${FICTIA_HOME}/scripts/fictia" stage`，输出如 `阶段 09 · 章节写作（chapters）`。
2. 说明该阶段的目标和产出。
3. 执行该阶段（见"流水线执行协议"）。

## 流水线执行协议

### 步骤 1：读取 Agent Prompt

从 `references/agents/` 读取对应阶段的 prompt 文件：

| 阶段 | Prompt 文件 |
|------|------------|
| 1. 题材分析 | `references/agents/01-genre-analyst.md` |
| 2. 架构设计 | `references/agents/02-architect.md` |
| 3. 风格设计 | `references/agents/03-style-designer.md` |
| 4. 艺术设计 | `references/agents/04-art-director.md` |
| 5. 叙事编织 | `references/agents/05-narrative-weaver.md` |
| 6. 世界观构建 | `references/agents/06-world-builder.md` |
| 7. 人物设计 | `references/agents/07-character-designer.md` |
| 8. 故事设计 | `references/agents/08-story-designer.md` |
| 9. 章节写作 | `references/agents/09-chapter-writer.md` |
| 10. 编辑审核 | `references/agents/10-editor.md` |
| 11. 一致性校验 | `references/agents/11-consistency-checker.md` |

### 步骤 2：收集上下文

使用 CLI 组装上下文：

- **写手**（阶段 9）：`python "${FICTIA_HOME}/scripts/fictia" ctx assemble writer --chapter N` → `.fictia-cache/chNN-writer-context.md`
- **编辑**（阶段 10）：`python "${FICTIA_HOME}/scripts/fictia" ctx assemble editor --chapter N` → `.fictia-cache/chNN-editor-context.md`
- **一致性校验**（阶段 11）：`python "${FICTIA_HOME}/scripts/fictia" ctx assemble consistency` → `.fictia-cache/consistency-context.md`
- **其他阶段**（1-8）：按 agent prompt 中"上下文收集"部分手动读取输入文件

组装完成后，subagent 直接 Read 缓存文件即可。若必需的输入文件为空或缺失，中止该阶段并通知用户哪个上游阶段未产出。

### 步骤 3：执行 Agent 角色

已具备：agent prompt（角色、能力、输出格式、约束）+ 收集的上下文。

正式生成前，运行 `python "${FICTIA_HOME}/scripts/fictia" stage start <stage>` 将阶段标记为 `in_progress`。

**按 agent prompt 指令生成产出**。使用中文。严格遵循输出格式。

**两类阶段的执行方式不同**：
- **非 subagent 阶段（1-8）**：主代理直接扮演该 agent，按 prompt 指令生成产出并写入文件。若 `brainstorm_mode=true`，按"三段式协议"执行（探索→共创→产出），agent prompt 中包含各阶段的探索方向和发散约束。
- **subagent 阶段（9 / 10 / 11）**：主代理不直接生成，按下方"步骤 3a：Subagent 派发协议"调用 subagent 完成。

### 步骤 3a：Subagent 派发协议

阶段 9（章节写作）、10（编辑审核）、11（一致性校验）由 subagent 执行。主代理负责组装 prompt、调用 Agent 工具、读取产出、触发后续流程；不直接撰写章节正文、审核报告或一致性报告。

#### 通用派发流程

1. **组装 subagent prompt**：按下方对应模板填入项目信息、上下文路径、章节编号等。
2. **调用 Agent 工具**：类型 `general-purpose`，传入组装好的 prompt。
3. **subagent 收到 prompt 后**：先 `Read` 对应 agent prompt 文件（`${FICTIA_HOME}/references/agents/<NN>-<role>.md`）获取角色定义、专业能力和输出规范；再按规范读取上下文文件并完成产出。
4. **主代理读取产出**：从 subagent 写入的输出文件路径读取结果。
5. **触发后续流程**：进入步骤 4 状态更新、步骤 5-7 展示与确认（subagent 阶段的具体流转见"章节写作流程"和"里程碑一致性校验"）。

**单一信息源原则**：subagent 不再需要主代理重复粘贴角色定义或输出规范到 prompt 中——通过 Read agent prompt 文件保证 prompt 与 agent 定义始终一致。

#### 阶段 9：章节写作派发模板

- **模型**：`opus`
- **角色文件**：`${FICTIA_HOME}/references/agents/09-chapter-writer.md`
- **上下文来源**：`python "${FICTIA_HOME}/scripts/fictia" ctx assemble writer --chapter N` → `.fictia-cache/chNN-writer-context.md`
- **输出文件**：`chapters/act-{N}/ch{NN}.md`

**Prompt 模板**：

```
你是 Fictia 的章节写手。

请先 Read ${FICTIA_HOME}/references/agents/09-chapter-writer.md，按其中的角色定义、专业能力和输出规范完成任务。

## 项目信息
- 项目目录：{project_dir}
- 章节编号：ch{NN}
- 章节名：{章节名}
- 目标字数：{目标字数} 字
- 本章所在幕：act {N}

## 上下文
读取 .fictia-cache/ch{NN}-writer-context.md 获取本章大纲、风格指南精选、世界观速查、角色速查表、叙事配置、情感节拍、前章摘要等。

## 任务
撰写第 {N} 章正文并写入 chapters/act-{N}/ch{NN}.md。写完后统计正文字数，达标后向用户展示摘要。
```

#### 阶段 10：编辑审核派发模板

- **模型**：`sonnet`（与阶段 9 的 `opus` 交叉验证）
- **角色文件**：`${FICTIA_HOME}/references/agents/10-editor.md`
- **上下文来源**：`python "${FICTIA_HOME}/scripts/fictia" ctx assemble editor --chapter N` → `.fictia-cache/chNN-editor-context.md`
- **输出文件**：`reviews/ch{NN}-review.md`

**Prompt 模板**：

```
你是 Fictia 的编辑审核员。

请先 Read ${FICTIA_HOME}/references/agents/10-editor.md，按其中的角色定义、专业能力和输出规范完成任务。

## 项目信息
- 项目目录：{project_dir}
- 章节编号：ch{NN}
- 章节名：{章节名}
- 目标字数：{目标字数} 字
- 本章所在幕：act {N}

## 上下文
读取 .fictia-cache/ch{NN}-editor-context.md 获取待审核章节正文、本章大纲、风格指南精选、世界观速查、角色速查表、本章叙事配置等。

## 任务
对第 {N} 章进行全面质量审核，产出 reviews/ch{NN}-review.md。写完后评估是否触发修复循环（见"章节写作流程 > 阶段 2：审核-修复循环"）。
```

#### 阶段 11：一致性校验派发模板

- **模型**：`sonnet`
- **角色文件**：`${FICTIA_HOME}/references/agents/11-consistency-checker.md`
- **上下文来源**：`python "${FICTIA_HOME}/scripts/fictia" ctx assemble consistency` → `.fictia-cache/consistency-context.md`
- **输出文件**：`reviews/consistency-report.md`

**Prompt 模板**：

```
你是 Fictia 的一致性校验员。

请先 Read ${FICTIA_HOME}/references/agents/11-consistency-checker.md，按其中的角色定义、专业能力和输出规范完成任务。

## 项目信息
- 项目目录：{project_dir}
- 校验范围：第 {start} 章 至 第 {end} 章
- 校验日期：{date}

## 上下文
读取 .fictia-cache/consistency-context.md 获取已写章节摘要、世界观设定、角色速查表、叙事设计、风格指南、时间线等。

## 任务
跨章节检查第 {start}-{end} 章的一致性，产出 reviews/consistency-report.md。写完后评估是否触发修复轮次（见"里程碑一致性校验 > 步骤 3：修复循环"）。
```

#### 主代理在 subagent 阶段的后续动作

- **步骤 4（写入产出）**：subagent 已直接写入输出文件，主代理无需再次 Write。
- **步骤 5（更新项目状态）**：按 subagent 阶段的具体规则更新（如阶段 9 用 `stage chapter increment`）。
- **审核-修复循环**：由主代理根据 subagent 产出的审核/校验结果判断触发，仍由主代理调度（不嵌套 subagent）。
- **确认**：阶段 9-10 章节维度由主代理展示摘要等待用户确认；阶段 11 里程碑维度由主代理展示报告等待确认。

### 步骤 4：写入产出文件

使用 Write 工具写入 agent prompt 中"输出规范"部分指定的文件。

### 步骤 5：更新项目状态

非增量阶段产出写入后，运行 `python "${FICTIA_HOME}/scripts/fictia" stage ready <stage>` 标记为 `pending_confirm`，等待用户确认。**不要在用户确认前运行 `stage confirm`。**

修改已有阶段产出时，先运行 `python "${FICTIA_HOME}/scripts/fictia" stage invalidate <stage>`（自动 BFS 传播下游 `needs_update`）。

章节写作、编辑审核、一致性校验属于增量流程，按下方专门流程更新章节计数和报告状态，不用把整个 `chapters` 阶段提前 `confirm`。

### 步骤 6：向用户展示摘要

展示产出内容要点、关键决策、需要用户审核的部分。

### 步骤 7：等待确认

用户选择：
- **确认**：非增量阶段运行 `python "${FICTIA_HOME}/scripts/fictia" stage confirm <stage>` 标记为 `confirmed`。**不要自动进入下一阶段**，提醒用户：
  > 当前阶段已完成确认。为避免上下文膨胀影响后续生成质量，请使用 `/clear` 或 `/new` 清空当前对话上下文，然后重新调用 Fictia 技能继续下一个阶段。
- **修改**：用户提供修改指令 → 定向修改后重新展示
- **重做**：用户提供新方向 → 重新执行该阶段

**此规则适用于全部阶段（1–11）。** 每次确认后必须停下来提醒用户清上下文。唯一例外是审核-修复循环和里程碑一致性校验——它们是单次会话内的迭代循环，应连续完成。

### 步骤 7a：笔记自动整理（后台，无感）

笔记管理是后台维护，**不是创作主流程的一部分**。所有动作静默执行，不询问用户、不阻塞流程。

**自动记录触发**（orchestrator 启发式判断，无提示）：
- 用户发出修改/改写/偏好陈述指令
- 用户对审核/校验报告的方向性反应
- 阶段切换时的方向性发言

排除：状态查询、闲聊、确认词（"ok"/"继续"/"确认"等）。调用 `fictia notes add --text "..."` 追加到 `notes/raw.md`，状态默认 `pending`。

**自动整理触发**：阶段确认后、提醒用户清上下文前，静默跑整理。

1. 跑 `fictia notes list --status pending` 检查待整理条目
2. 读 `notes/raw.md` + 相关项目文件（仅参考，不修改项目文件）
3. 主代理推理：每条 pending 归类为
   - **蒸馏**：抽象偏好/规则，append 到 `notes/summary.md` 对应主题分类
   - **合并/过期**：合并到已有条目
4. 更新 raw.md 状态为 `summarized`（不删除，永不丢失）
5. **不**修改 style-guide / 角色 / 大纲等任何项目文件——那些改动走"内容修改"工作流
6. **不**展示报告、**不**询问确认、**不**阻塞主流程（失败时记 stderr 但不报错）

**章节写作自动加载**：`ctx assemble writer/editor/consistency` 检测到 `notes/summary.md` 存在即追加到上下文末尾。无需 flag。

**审计与回滚**（用户主动行为，不自动触发）：
- `fictia notes list` / `fictia notes show <id>` 浏览与查看
- `fictia notes revert <id>` 把某条标记为 `reverted`，从 summary.md 移除蒸馏结果
- 直接 Edit `notes/summary.md` 手动调整

## 阶段速查

| # | 阶段 | 产出文件 | 依赖 | 增量 |
|---|------|---------|------|------|
| 1 | 题材分析 | `genre-analysis.md` | 无 | 否 |
| 2 | 架构设计 | `blueprint.md` | genre_analysis | 否 |
| 3 | 风格设计 | `style-guide.md` | genre_analysis, architecture | 否 |
| 4 | 艺术设计 | `art-design.md` | genre_analysis, architecture, style | 否 |
| 5 | 叙事编织 | `narrative-weave.md` | genre_analysis, architecture, art_design, style | 否 |
| 6 | 世界观构建 | `world/setting.md`, `world/rules.md`, `world/timeline.md` | genre_analysis, architecture, art_design, narrative_weave | 是 |
| 7 | 人物设计 | `characters/protagonist.md`, `characters/antagonist.md`, `characters/supporting/*.md`, `characters/relationships.md` | world, architecture, style, art_design, narrative_weave | 是 |
| 8 | 故事设计 | `outline/act-*.md`, `outline/chapters/ch*.md` | architecture, art_design, narrative_weave, world, characters | 是 |
| 9 | 章节写作 | `chapters/act-N/chXX.md` | story, style, characters, world, narrative_weave, art_design | 是（逐章） |
| 10 | 编辑审核 | `reviews/chXX-review.md` | chapters, style | 是（逐章） |
| 11 | 一致性校验 | `reviews/consistency-report.md` | chapters | 是 |

## 传播规则

修改某阶段产出时，下游阶段可能失效。修改前必须警告用户：

| 修改阶段 | 失效下游 |
|---------|---------|
| genre_analysis | architecture, style, art_design, narrative_weave, world, characters, story, chapters |
| architecture | narrative_weave, story, chapters |
| style | chapters, editor |
| art_design | narrative_weave, characters, story, chapters |
| narrative_weave | characters, story, chapters |
| world | characters, story, chapters |
| characters | story, chapters |
| story | chapters |
| chapters | consistency |

修改前提示："修改[X]会导致以下阶段需要重新运行：[list]。确定要继续吗？"

确认后运行 `python "${FICTIA_HOME}/scripts/fictia" stage invalidate <stage>` 自动 BFS 传播下游 `needs_update`。

## 修改工作流

### 小修改（refine）

用户提供定向修改指令：
1. 读取当前产出文件
2. 使用 Edit 工具应用修改
3. 重新展示摘要

### 大修改（redo）

用户提供全新方向：
1. 将新方向纳入上下文，重新执行该阶段
2. 覆写产出文件
3. 重新展示摘要

### 修改指令建议

- **差**："写得更好"（太模糊）
- **好**："第二章的战斗场景节奏太慢，使用更多短句加速，增加紧迫感"
- **好**："主角的性格应该更果断，减少犹豫不决的描写"

## 新建项目创建

1. **收集需求**：
   - 项目名（英文，用作目录名）
   - 作者名
   - 题材与子题材
   - 目标字数（默认 300,000）
   - 目标卷数（默认 1）
   - 每章目标字数：默认使用 CLI 的 3000 字/章；若用户明确指定则传入 `--chapter-words` 使用用户值
   - 核心设定（一段话）

2. **创建项目**：运行 CLI 一键完成目录结构、`project.yaml` 和占位文件：
   ```bash
   python "${FICTIA_HOME}/scripts/fictia" init <项目名> --author <作者> --genre <题材> --target <目标字数> --volumes <卷数> --chapter-words <每章字数> --premise "<核心设定>"
   ```
   不指定 `--chapter-words` 时默认 3000 字/章。

5. **启动阶段 1**：开始题材分析。

## 工作流：导出

0. **【必做】显示状态面板**：用 Bash 执行 `python "${FICTIA_HOME}/scripts/fictia" status`，将输出原样展示给用户。
1. 确认格式（默认 `md`）：`txt`（纯文本）或 `md`（markdown）。
2. 运行 `python "${FICTIA_HOME}/scripts/fictia" export md` 或 `python "${FICTIA_HOME}/scripts/fictia" export txt`，自动完成章节收集、写作备注剥离、拼装和写入。
3. 报告输出路径和章节数。

## 章节写作流程

【强制】每章必须通过 写作 → 审核 → 修复 → 确认 完整循环。通过条件：**零严重问题、零一般问题、综合评分 = A**。

### 阶段 1：写作

1. 确定下一章：
   - **并行模式下**：运行 `python "${FICTIA_HOME}/scripts/fictia" stage chapter next`，CLI 会综合考虑上游设计阶段 confirmed、大纲文件存在、chapters.outlines 时间戳等条件给出下一可写章节号。
   - **串行模式下**：查看 `project.yaml` 的 `chapters` 字段（`written` + 1 = 下一章编号）。
   - 如计数与实际文件不一致，先用 `python "${FICTIA_HOME}/scripts/fictia" stage chapter set --total <N> --written <N> --confirmed <N>` 修正。
2. 读取下一章大纲：`outline/chapters/chXX.md`
3. 概述本章内容：场景、角色、事件、weave_notes 要求。
4. 检查 weave_notes：需要埋设/推进的伏笔、需要推进的支线。
5. 执行阶段 9（章节写手 agent）。

### 阶段 2：审核-修复循环

【强制，最多 3 轮】每章写完后自动触发审核-修复循环。

**修复触发**（满足任一即触发）：
- 严重问题（必须修改）表 ≥1 行
- 一般问题（建议修改）表 ≥1 行
- 综合评分为 B/C/D

**通过条件**（全部满足）：
- 零严重问题
- 零一般问题
- 综合评分 = A

**循环流程**：
1. 执行阶段 10（编辑 agent）→ 产出 `reviews/chXX-review.md`
2. 评估是否通过：`python "${FICTIA_HOME}/scripts/fictia" verdict review reviews/chXX-review.md`，返回 JSON 含 `passed`/`severe`/`normal`/`grade`
3. **未通过**（`passed=false`）：
   a. 按审核中的每个具体问题（严重 + 一般）定向修复 `chapters/act-{N}/chXX.md`
   b. 重新执行阶段 10 → 覆写 `reviews/chXX-review.md`
   c. 递增迭代计数器
   d. 第 1 或 2 轮仍未通过 → 回到步骤 2
   e. **3 轮后仍未通过** → 中止循环，展示所有轮次结果供用户决定
4. **通过** → 进入阶段 3
5. 在审核报告末尾追加修复日志：
   ```markdown
   ### 审核修复日志
   | 迭代 | 严重问题 | 一般问题 | 评分 | 主要修复内容 |
   |------|---------|---------|------|------------|
   | 1 | [N] | [N] | [A-D] | [摘要] |
   | 2 | [N] | [N] | [A-D] | [摘要] |
   ```

### 阶段 3：确认

通过后：
1. 向用户展示最终章节文本（或摘要）和审核报告（含修复日志）
2. 确认方式：用户在场则简述结果并确认；用户已指示批量/自动模式则自动确认
3. 更新状态：`python "${FICTIA_HOME}/scripts/fictia" stage chapter increment`（递增 `written` 和 `confirmed`）
4. 检查里程碑：`python "${FICTIA_HOME}/scripts/fictia" milestone` → 到达里程碑则触发阶段 4

### 阶段 4：里程碑一致性校验（每 5 章，提醒可跳过）

章节确认后，检查 `chapters.confirmed` 是否为 5 的倍数（5、10、15、20...）。

**到达里程碑 → 提醒用户做一致性校验**（见下方专节）。用户可以选择：
- **立即校验**：进入"里程碑一致性校验"主流程
- **稍后校验**：跳过本次提醒，下次确认章节时再次检查
- **跳过本次**：本次里程碑不校验，`consistency` 状态保持旧值

**不阻塞新章节写作**——即使本次跳过，用户确认下一章后仍可继续。

**未到里程碑 → 提醒用户清上下文后继续下一章。**

> 第 {N} 章已完成确认。为避免上下文膨胀影响后续章节的生成质量，请使用 `/clear` 或 `/new` 清空当前对话上下文，然后重新调用 Fictia 技能继续写作下一章。

## 工作流：内容修改（自由修改）

用户在已有项目中提出对小说内容的修改意见时（如"让反派提前出场"、"把第三章的战斗写得更激烈"），遵循本工作流。

**【必做】先显示状态面板**：用 Bash 执行 `python "${FICTIA_HOME}/scripts/fictia" status`，将输出原样展示给用户，然后继续下方流程。

**核心原则：先更新设计，再改写章节。**

### 步骤 1：分析修改请求

理解修改意图，归类为以下类型（可组合）：

| 修改类型 | 说明 | 示例 |
|---------|------|------|
| 结构调整 | 影响卷章划分、节奏曲线、高潮布局 | "把三卷改为四卷"、"大高潮提前到第二卷" |
| 角色变更 | 影响角色性格、能力、关系、成长弧线 | "让主角更果断"、"给反派增加悲情背景" |
| 伏笔/支线变更 | 影响伏笔体系、支线网络、叙事技巧 | "增加一条主角身世暗线"、"这根伏笔改成误导" |
| 情节变更 | 影响某章或数章的事件、场景、冲突 | "第五章增加一场追逐戏"、"删掉第三章的支线" |
| 世界观变更 | 影响设定、规则、时间线 | "修改力量体系等级"、"增加一个新种族" |
| 风格调整 | 影响语言风格、叙事手法 | "对话写得更口语化"、"战斗用短句加速" |
| 局部文字修改 | 仅影响措辞和描写 | "这段描写太冗长，精简一下" |

### 步骤 2：影响评估

| 修改类型 | 架构设计 | 世界观 | 叙事编织 | 人物设计 | 故事设计 | 章节 |
|---------|---------|--------|---------|---------|---------|------|
| 结构调整 | ✓ | | ✓ | | ✓ | ✓ |
| 角色变更 | | | ✓ | ✓ | ✓ | ✓ |
| 伏笔/支线变更 | | | ✓ | | ✓ | ✓ |
| 情节变更 | | | | | ✓ | ✓ |
| 世界观变更 | | ✓ | ✓ | ✓ | ✓ | ✓ |
| 风格调整 | | | | | | ✓ |
| 局部文字修改 | | | | | | ✓ |

多类型修改取影响类型的并集。

### 步骤 3：制定更新计划

按依赖从上游到下游排列更新顺序：

1. **架构设计** (blueprint.md)
2. **世界观** (world/)
3. **叙事编织/伏笔** (narrative-weave.md)
4. **人物设计** (characters/)
5. **故事设计/大纲** (outline/)
6. **章节重写/局部改写**

向用户展示计划，等待确认后再执行。

### 步骤 4：逐层更新设计文档

按计划顺序，对每个文档：
1. 读取当前内容
2. 只修改相关部分，保持其余不变
3. 局部修改用 Edit，大范围用 Write
4. 展示修改摘要
5. 更新状态：修改前先 `python "${FICTIA_HOME}/scripts/fictia" stage invalidate <stage>`，执行时 `stage start <stage>`，产出写入后 `stage ready <stage>`；用户确认后再 `stage confirm <stage>`

用户可在任一步骤提出调整，确认后进入下一步。

### 步骤 5：章节重写/局部改写

**局部改写**（涉及部分段落）：
1. 读取目标章节
2. 根据更新后的设计文档，使用 Edit 修改相关段落
3. 更新章节末尾写作备注
4. 展示修改结果

**整章重写**（涉及核心情节或大部分内容）：
1. 读取更新后的该章大纲
2. 执行阶段 9 重写该章
3. 进入阶段 2 审核-修复循环
4. 通过后展示结果

### 快速通道

以下情况跳过设计文档更新，直接修改章节：
- 纯文字润色
- 写作备注修正
- 格式修复

快速通道中仍需确认修改不与设计文档矛盾。

## 里程碑一致性校验（每 5 章，提醒可跳过）

`chapters.confirmed` 达到 5 的倍数时**提醒**用户做校验。**用户可跳过，本次不阻塞新章节写作**——`consistency.last_check_chapter` 与 `consistency.status` 保持旧值，下次到达里程碑时再次提醒。

### 步骤 1：执行一致性校验

执行阶段 11（一致性校验 agent）→ 产出 `reviews/consistency-report.md`

### 步骤 2：评估报告

运行 `python "${FICTIA_HOME}/scripts/fictia" verdict consistency reviews/consistency-report.md`，返回 JSON 含 `passed`/`severe`/`normal`/`grade`。

**修复触发**（`passed=false`，满足任一）：
- 严重问题（影响故事逻辑）≥1
- 一般问题（不影响主要逻辑但需要修正）≥1

**通过条件**（`passed=true`）：
- 零严重问题、零一般问题、一致性评分 = A

### 步骤 3：修复循环（最多 2 轮）

未通过时：
1. 按报告修复所有问题章节
2. 对每个修改章节重新执行阶段 10 → 更新 `reviews/chXX-review.md`，用 `python "${FICTIA_HOME}/scripts/fictia" verdict review` 验证通过
3. 重新执行阶段 11 → 覆写 `reviews/consistency-report.md`
4. 仍未通过 → 再重复一轮（最多 **2 轮**）
5. 2 轮后仍有问题 → 中止，展示完整结果供用户决定

通过 → 进入步骤 4。

### 步骤 4：确认并更新

1. 向用户展示一致性报告（长报告可摘要）
2. 确认
3. 运行 `python "${FICTIA_HOME}/scripts/fictia" consistency confirm --chapter <N>`，记录 `last_check_chapter`、`last_check_date` 和 `status: confirmed`。

### 步骤 5：继续

提醒用户清上下文后继续写作：

> 里程碑一致性校验已通过。为避免上下文膨胀影响后续章节的生成质量，请使用 `/clear` 或 `/new` 清空当前对话上下文，然后重新调用 Fictia 技能从第 {N+1} 章继续写作。

## 约束

- 所有生成内容使用**中文**。
- 遵守**流水线依赖**，不得执行前置阶段未确认的阶段。
- 修改早期阶段前必须**警告传播影响**。
- 每个 agent prompt 中的**约束部分**必须严格遵守。
- 角色文件必须包含 **YAML front-matter**。
- 章节文件必须包含**写作备注**。
- **使用 CLI 工具处理机械化环节**：面板渲染、状态推进、字数统计、上下文组装、审核解析、里程碑检查、导出——全部用 `fictia` CLI 完成，不做手动 Read/Edit。
- **章节间清上下文**：每章确认后（含里程碑校验通过后），提醒用户使用 `/clear` 或 `/new` 再继续下一章。禁止自动串联写下一章。唯一例外是单章内的审核-修复循环——它在单次会话内连续完成。
- **用户笔记 verbatim 保留**：所有用户方向性发言必须原样写入 `notes/raw.md`（通过 `fictia notes add`），不得改写或摘要后丢弃；状态可流转为 `summarized` / `reverted`，但 raw 条目永不删除。

## 参考文件

按需读取：
- `references/pipeline.md` — 完整依赖图、传播规则、状态值
- `references/project-structure.md` — 目录树、project.yaml schema、文件格式
- `references/context-procedures.md` — 上下文压缩与提取流程
- `references/agents/01-genre-analyst.md` 至 `references/agents/11-consistency-checker.md` — 各阶段 agent prompt
- `scripts/README.md` — CLI 工具完整子命令文档

## CLI 工具（scripts/fictia）

流水线中所有可机械化的环节由 `fictia` CLI 完成。**LLM 不做机械事。**

调用方式：`python "${FICTIA_HOME}/scripts/fictia" <command>`（所有平台通用）。

完整子命令文档见 `scripts/README.md`。

# 上下文收集流程

以下流程定义各 agent 如何收集和压缩上下文。

## 角色速查表（Tier 1）— `buildCharacterRegistry`

轻量级角色总览：

1. Glob 查找：`characters/protagonist.md`、`characters/antagonist.md`、`characters/supporting/*.md`
2. 每个文件仅读取 YAML front-matter（`---` 标记之间的内容）
3. 构建摘要表：姓名 | 身份 | 角色 | 核心特质 | 语言风格
4. 从 `relationships` 字段构建关系列表
5. 目标：总计 500-1000 字

所有需要角色信息的 agent 必须先加载此层。

## 角色快速卡 — `buildCharacterQuickCard`

单个角色的详细信息：

1. 读取角色完整文件
2. 从 front-matter 提取：name, role, identity, age, traits, relationships, growth_arc, language_style
3. 从正文提取：关键背景事件、动机、能力摘要
4. 压缩为卡片（300-500 字）

## 章节叙事编织提取 — `extractChapterNarrativeWeave`

从 `narrative-weave.md` 提取当前章节相关内容：

1. 读取 `narrative-weave.md`
2. 伏笔表（`| 编号 | 类型 | ...`）→ 筛选当前章节行
3. 伏笔埋设检查清单 → 筛选当前章节条目
4. 伏笔回收/解决状态 → 筛选当前章节条目
5. 未处理信号 → 筛选当前章节
6. 支线表 → 筛选相关行
7. 跳过其他章节条目

## 章节艺术设计提取 — `extractChapterArtDesign`

从 `art-design.md` 提取当前章节相关内容：

1. 读取 `art-design.md`
2. 逐章情感节拍表 → 筛选当前章节行
3. 相关意象定义
4. 逐章叙事技巧应用表 → 筛选当前章节行
5. 跳过其他章节条目

## 章节-幕映射

判断章节所属幕：

1. **优先读 blueprint**：读取 `blueprint.md`，查找幕定义中的章节范围（如 `chapters: [4, 15]`）
2. **默认回退**（blueprint 无可解析范围时）：
   - 序篇：ch1-3
   - 第一幕：ch4-15
   - 第二幕：ch16-30
   - 第三幕：ch31-45
   - 终篇：ch46-50

   非默认章数（非50章）时，blueprint 必须明确定义幕范围。

## 风格阶段提取 — `extractStyleStageNotes`

根据章节所在幕（用上述映射确定），从 `style-guide.md` 提取：

1. 整体文风和写作铁律
2. 句式规范与核心禁忌
3. 双时间线风格备注（如有）
4. 当前幕的风格演变轨迹行
5. 章节结构规范

## 世界观速查 — `buildWorldQuickRef`

压缩世界设定供需要世界上下文的 agent 使用：

1. `world/setting.md` → 保留：所有标题、表格、要点、短行（<150字）。跳过：长段描写（每节最多5段）
2. `world/rules.md` → 提取：力量体系摘要（来源、等级、核心限制）、战斗/魔法基础
3. 合并为速查参考（1000-2000字）

## 叙事编织摘要 — `buildNarrativeWeaveSummary`

全量叙事编织概览：

1. 完整读取 `narrative-weave.md`
2. 结构表格保持完整（伏笔表、支线表、彩蛋表）
3. 散文部分压缩为标题 + 前几行
4. 目标：原始大小的约 50%

## 艺术设计摘要 — `buildArtDesignSummary`

全量艺术设计概览：

1. 完整读取 `art-design.md`
2. 意象定义和散文概览保持完整
3. 逐章表格压缩为逐幕汇总（用章节-幕映射确定边界）
4. 情感节拍：按幕聚合（平均强度、主导情绪）
5. 技巧：按幕列出使用的技巧
6. 目标：原始大小的约 50%

## 前章摘要 — `buildPreviousChapterSummary`

写作新章节时，从前一章提取：

1. 读取前一章文件
2. 查找 `### 写作备注` 部分
3. 完整提取该部分（含字数、伏笔操作、角色状态更新、下章衔接）
4. 无写作备注时，提取末尾 300 字作为回退
5. 同时包含前一章完整正文

## 章节写作上下文组装

章节写手按以下顺序组装上下文：

1. 章节大纲（`outline/chapters/chXX.md` 完整内容）
2. 风格指南阶段提取（`extractStyleStageNotes`）
3. 世界观速查（`buildWorldQuickRef`）
4. 角色速查表（`buildCharacterRegistry`）
5. 本章叙事编织（`extractChapterNarrativeWeave`）
6. 本章艺术设计（`extractChapterArtDesign`）
7. 前章摘要（`buildPreviousChapterSummary`）
8. 前章完整正文
9. 源文本参考（改写/仿写/续写项目）
10. 用户笔记摘要（`notes/summary.md`，存在即加载；不存在跳过）

### 语义检索步骤（可选，由 agent 自行决定）

在第 8 步（前章完整正文）之后、第 9 步之前，可追加：

8.5. **语义检索**（需先启用 RAG；`fictia vector index-all` 索引后可用）：
   - 章节正文检索：`fictia ctx semantic-search "<query>" --chapter N --top-k 8`
   - 设计文件检索：`fictia ctx semantic-search "<query>" --collection design --top-k 5`
     （搜索 genre-analysis / blueprint / style-guide / art-design / narrative-weave / characters）
   - 世界观检索：`fictia ctx semantic-search "<query>" --collection world --top-k 5`
     （搜索 world/setting / world/rules / world/timeline）
   - 大纲检索：`fictia ctx semantic-search "<query>" --collection outlines --top-k 5`
     （搜索 act-*.md / outline/chapters/ch*.md）
   - 跨全库检索：`fictia ctx semantic-search "<query>" --top-k 8`（不指定 collection）
   - 用于补强：跨章节人物/事件回溯、伏笔 callback 检索、风格参照、设定查询
   - 不依赖 agent 主动调用；如果 agent 觉得不需要，可跳过此步

## 编辑审核上下文组装

编辑审核时组装：

1. 章节正文（完整）
2. 章节大纲（`outline/chapters/chXX.md`）→ 提取**目标字数**
3. 艺术设计摘要（`buildArtDesignSummary`）
4. 叙事编织摘要（`buildNarrativeWeaveSummary`）
5. 世界观速查（`buildWorldQuickRef`）
6. 角色速查表（`buildCharacterRegistry`）
7. 源文本参考（改写/仿写/续写项目）
8. 用户笔记摘要（`notes/summary.md`，存在即加载）

## 一致性校验上下文组装

一致性校验时组装：

1. 所有章节文件 — 最新章节完整正文，先前章节仅写作备注
2. 艺术设计摘要
3. 叙事编织摘要
4. 世界观速查
5. `world/timeline.md`（完整）
6. 角色速查表
7. 源文本参考（改写/仿写/续写项目）
8. 用户笔记摘要（`notes/summary.md`，存在即加载）

---
name: fictia
description: >
  Guide users through the Fictia AI novel-writing pipeline — an 11-stage workflow
  for creating complete Chinese novels with specialized AI agents. Use this skill when
  the user mentions Fictia, wants to write a novel using AI agents, asks about the novel
  creation pipeline, wants to continue writing a novel project, needs help with genre
  analysis / character design / chapter writing / consistency checking for a novel.
  Also trigger when the user asks about creating stories with structured AI-assisted
  workflows, mentions "小说创作", "写作流水线", or asks about multi-agent novel writing systems.
---

# Fictia — Standalone AI Novel Writing Pipeline

Fictia is a standalone AI novel-writing pipeline that orchestrates 11 specialized agents to produce complete Chinese novels. **Claude IS the pipeline** — you directly act as each agent, read agent prompts from `references/agents/`, gather context from project files, generate outputs using your own tools, and manage project state through `project.yaml`.

No external dependencies — use your native tools (Read, Write, Edit, Glob, Grep) for all file operations.

## Quick Start — Detect the Situation

When the user invokes this skill:

1. **Find the project**: Look for `project.yaml` in the current directory or walk up parent directories.

2. **Branch into the appropriate workflow**:
   - No project found → **New Project** workflow
   - Project found, stages not started → **Start Pipeline** workflow
   - Project found, some stages confirmed → **Continue Pipeline** workflow
   - User asks to export → **Export** workflow
   - User requests content modification (changing plot, characters, foreshadowing, etc.) → **Content Modification** workflow
   - User has a general question (not about changing novel content) → handle directly

## Workflow: New Project

When the user wants to start a new novel:

1. **Discuss the concept** with the user: genre, target word count, volume count, core premise. Help them think through these decisions.
2. **Create the project** (see New Project Creation section below).
3. **Guide through the pipeline** (see Pipeline Execution Protocol below).

## Workflow: Continue Pipeline

1. **Read `project.yaml`** to assess current state.
2. **Identify the next actionable stage** based on dependency rules:
   - Find stages with `not_started` or `needs_update` status
   - Check that all their dependencies are `confirmed`
   - The first such stage in pipeline order is the next step
3. **Explain what that stage does** and what it will produce.
4. **Execute the stage** (see Pipeline Execution Protocol below).

## Pipeline Execution Protocol

For each stage, follow this protocol:

### Step 1: Read Agent Prompt
Read the agent prompt file from `references/agents/`:

| Stage | Agent Prompt File |
|-------|------------------|
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

### Step 2: Gather Context
Read the input files specified in the agent prompt's **上下文收集** section. Use the procedures in `references/context-procedures.md` to compress and extract relevant context.

If a required input file is empty (placeholder only) or missing, halt execution of that stage and inform the user which upstream stage produced no output. Do not fabricate content from missing inputs.

### Step 3: Execute Agent Role
You now have:
- The agent prompt (defining role, capabilities, output format, constraints)
- The gathered context (input files, compressed summaries)

**Act as the agent.** Follow the agent prompt's instructions to generate the output. Write in Chinese. Use the specified output format exactly.

### Step 4: Write Output Files
Use the Write tool to write the output files as specified in the agent prompt's **输出规范** section.

### Step 5: Update Project State
Edit `project.yaml` to update the stage status:
- Set the completed stage to `pending_confirm`
- If downstream stages were invalidated (via propagation), set them to `needs_update`

### Step 6: Present Summary to User
Present a structured summary of what was generated:
- What the output contains (key points, structure)
- Quality highlights (strengths, notable decisions)
- Areas for the user to review

### Step 7: Wait for Confirmation
Ask the user to choose:
- **确认 (confirm)**: Accept the output, mark stage as `confirmed`, proceed to next stage
- **修改 (refine)**: User provides a directive for targeted changes → apply changes and re-present
- **重做 (redo)**: User provides a new direction → re-execute the stage with the new directive

## Stage-by-Stage Reference

| # | Stage | Produces | Dependencies | Incremental |
|---|-------|----------|-------------|-------------|
| 1 | 题材分析 | `genre-analysis.md` | None | No |
| 2 | 架构设计 | `blueprint.md` | genre_analysis | No |
| 3 | 风格设计 | `style-guide.md` | genre_analysis, architecture | No |
| 4 | 艺术设计 | `art-design.md` | genre_analysis, architecture, style | No |
| 5 | 叙事编织 | `narrative-weave.md` | genre_analysis, architecture, art_design, style | No |
| 6 | 世界观构建 | `world/setting.md`, `world/rules.md`, `world/timeline.md` | genre_analysis, architecture, art_design, narrative_weave | Yes |
| 7 | 人物设计 | `characters/protagonist.md`, `characters/antagonist.md`, `characters/supporting/*.md`, `characters/relationships.md` | world, architecture, style, art_design, narrative_weave | Yes |
| 8 | 故事设计 | `outline/act-*.md`, `outline/chapters/ch*.md` | architecture, art_design, narrative_weave, world, characters | Yes |
| 9 | 章节写作 | `chapters/act-N/chXX.md` | story, style, characters, world, narrative_weave, art_design | Yes (per chapter) |
| 10 | 编辑审核 | `reviews/chXX-review.md` | chapters, style | Yes (per chapter) |
| 11 | 一致性校验 | `reviews/consistency-report.md` | chapters | Yes |

## Propagation Rules

When a stage's output is modified, downstream stages may be invalidated. Check before suggesting edits:

| Modified Stage | Invalidates |
|---------------|-------------|
| genre_analysis | architecture, style, art_design, narrative_weave, world, characters, story, chapters |
| architecture | narrative_weave, story, chapters |
| style | chapters, editor |
| art_design | narrative_weave, characters, story, chapters |
| narrative_weave | characters, story, chapters |
| world | characters, story, chapters |
| characters | story, chapters |
| story | chapters |
| chapters | consistency |

Always warn the user: "修改[X]会导致以下阶段需要重新运行：[list]。确定要继续吗？"

## Refinement Workflow

### Small Changes (refine)
When the user provides a specific directive for targeted changes:
1. Read the current output file
2. Apply the changes using Edit tool
3. Re-present the summary

### Major Changes (redo)
When the user wants a substantially different direction:
1. Re-execute the stage with the new directive incorporated into the context
2. Overwrite the output file(s)
3. Re-present the summary

### Directive Tips
Help the user craft clear, specific directives:
- **Bad**: "写得更好" (too vague)
- **Good**: "第二章的战斗场景节奏太慢，使用更多短句加速，增加紧迫感"
- **Good**: "主角的性格应该更果断，减少犹豫不决的描写"

## New Project Creation

When the user wants to create a new Fictia project:

1. **Gather requirements**:
   - Project name (English, used as directory name)
   - Author name
   - Genre and sub-genre
   - Target word count (default: 300,000)
   - Target volume count (default: 1)
   - Chapter target words (default: 3,000)
   - Core premise (one paragraph)

2. **Create directory structure**:
   ```
   <project-name>/
   ├── project.yaml
   ├── genre-analysis.md
   ├── blueprint.md
   ├── style-guide.md
   ├── art-design.md
   ├── narrative-weave.md
   ├── world/
   │   ├── setting.md
   │   ├── rules.md
   │   └── timeline.md
   ├── characters/
   │   ├── protagonist.md
   │   ├── antagonist.md
   │   ├── supporting/
   │   └── relationships.md
   ├── outline/
   │   ├── act-1.md
   │   ├── act-2.md
   │   ├── act-3.md
   │   └── chapters/
   ├── chapters/
   │   ├── act-1/
   │   ├── act-2/
   │   └── act-3/
   └── reviews/
   ```

3. **Create `project.yaml`**:
   ```yaml
   name: <project-name>
   author: <author>
   genre: <genre>
   sub_genre: <sub-genre>
   target_words: <number>
   target_volumes: <number>
   chapter_target_words: <number>
   premise: <one paragraph>
   pipeline:
     genre_analysis: not_started
     architecture: not_started
     style: not_started
     art_design: not_started
     narrative_weave: not_started
     world: not_started
     characters: not_started
     story: not_started
     chapters: not_started
     editor: not_started
     consistency: not_started
   chapters:
     total: 0
     written: 0
     confirmed: 0
   ```

4. **Create placeholder files**: Write empty placeholder markdown files with titles for each expected output file.

5. **Begin Stage 1**: Start the pipeline with genre analysis.

## Workflow: Export

When the user wants to export the novel as a single file:

1. **Read `project.yaml`** to get the project name and author.
2. **Ask format** (if not specified): `txt` (plain text) or `md` (markdown). Default: `md`.
3. **Collect chapters**: Use Glob `chapters/act-*/ch*.md`, sort by filename (ch01, ch02, ...).
4. **For each chapter file**:
   - Read the file content
   - Strip the `### 写作备注` section and everything after it (including the `---` separator before it)
   - The result is the clean chapter prose only
5. **Assemble output**:
   - **md format**: Add a header `# {项目名}`, optional `> 作者: {作者}`, then `---`, then concatenate all cleaned chapters separated by `---`
   - **txt format**: Add a header `{项目名}` with `=` underline, then concatenate all cleaned chapters. Strip markdown formatting (`#`, `**`, `*`) from the text
6. **Write** the assembled content to `{项目名}.md` or `{项目名}.txt` in the project root directory.
7. **Report**: tell the user the output path and total chapter count.

## Chapter Writing Sessions

When the user wants to write chapters:

1. **Check progress**: Read `project.yaml` → `chapters` field, or use Glob to count files in `outline/chapters/` vs `chapters/act-*/`
2. **Read the next chapter outline**: `outline/chapters/chXX.md`
3. **Summarize what the chapter should contain**: scenes, characters, events, weave_notes obligations
4. **Check weave_notes**: What foreshadowing needs to be planted/advanced? What subplots need movement?
5. **Execute Stage 9** (chapter writer agent) for this chapter
6. **Auto-execute Stage 10** (editor agent) to review the chapter
7. **Present both**: the chapter and the review
8. **Help decide**: Address critical issues from the review, suggest confirm or revise

## Workflow: Content Modification (自由修改)

当用户在已有项目中进行自由对话，提出对小说内容的修改意见时（例如："让反派提前出场"、"把第三章的战斗写得更激烈"、"给主角加一条身世伏笔"），遵循本工作流。

**核心原则：先更新设计，再改写章节。** 确保所有上游设计文档与修改意图一致后，才进行章节重写或局部改写。

### Step 1: 分析修改请求

理解用户的修改意图，判断修改的性质和范围。将修改归类为以下类型之一或组合：

| 修改类型 | 说明 | 示例 |
|---------|------|------|
| 结构调整 | 影响卷章划分、节奏曲线、高潮布局 | "把三卷改为四卷"、"大高潮提前到第二卷" |
| 角色变更 | 影响角色性格、能力、关系、成长弧线 | "让主角更果断"、"给反派增加悲情背景" |
| 伏笔/支线变更 | 影响伏笔体系、支线网络、叙事技巧 | "增加一条主角身世暗线"、"这根伏笔改成误导" |
| 情节变更 | 影响某章或数章的事件、场景、冲突 | "第五章增加一场追逐戏"、"删掉第三章的支线" |
| 世界观变更 | 影响设定、规则、时间线 | "修改力量体系等级"、"增加一个新种族" |
| 风格调整 | 影响语言风格、叙事手法 | "对话写得更口语化"、"战斗用短句加速" |
| 局部文字修改 | 仅影响具体措辞和描写，不涉及情节设定 | "这段描写太冗长，精简一下" |

### Step 2: 影响评估

根据修改类型，判断影响哪些设计文档：

| 修改类型 | 架构设计 | 世界观 | 叙事编织(伏笔) | 人物设计 | 故事设计 | 章节 |
|---------|---------|--------|--------------|---------|---------|------|
| 结构调整 | ✓ | | ✓ | | ✓ | ✓ |
| 角色变更 | | | ✓ | ✓ | ✓ | ✓ |
| 伏笔/支线变更 | | | ✓ | | ✓ | ✓ |
| 情节变更 | | | | | ✓ | ✓ |
| 世界观变更 | | ✓ | ✓ | ✓ | ✓ | ✓ |
| 风格调整 | | | | | | ✓ |
| 局部文字修改 | | | | | | ✓ |

**注意**：如果修改同时涉及多个类型（例如"让反派提前到第三章出场并揭示其与主角的关系"），取所有影响类型的并集。

### Step 3: 制定更新计划

按照依赖关系从上游到下游排列更新顺序：

1. **架构设计** (blueprint.md) — 如受影响，最先更新
2. **世界观** (world/) — 如受影响
3. **叙事编织/伏笔** (narrative-weave.md) — 如受影响
4. **人物设计** (characters/) — 如受影响
5. **故事设计/大纲** (outline/) — 如受影响
6. **章节重写/局部改写** — 最后执行

向用户展示更新计划：

> 这个修改会影响以下设计文档：
> - [文档1]：[具体影响说明]
> - [文档2]：[具体影响说明]
>
> 建议按以下顺序更新：
> 1. [文档1] — [更新内容摘要]
> 2. [文档2] — [更新内容摘要]
> 3. 章节重写/局部改写
>
> 是否按此计划执行？还是只更新部分文档？

等待用户确认后再开始执行。

### Step 4: 逐层更新设计文档

按计划顺序，对每个需要更新的设计文档：

1. **读取当前文件**内容
2. **定位修改范围**：只修改与用户请求相关的部分，保持其他内容不变
3. **应用修改**：局部修改用 Edit 工具，大范围变更用 Write 工具重写
4. **展示修改摘要**：告知用户改了什么、为什么这样改
5. **更新 project.yaml**：将对应阶段状态设为 `pending_confirm`

用户可以在任一步骤中提出调整意见，确认后再进入下一步。

### Step 5: 章节重写/局部改写

所有相关设计文档更新并确认后，处理章节：

**局部改写**（修改仅涉及章节的部分段落）：
1. 读取目标章节文件
2. 根据更新后的设计文档，使用 Edit 工具修改相关段落
3. 更新章节末尾的写作备注，反映本次变更内容（新增的伏笔操作、角色状态变化、设定引用等）
4. 展示修改结果供用户确认

**整章重写**（修改涉及章节核心情节或大部分内容）：
1. 读取更新后的该章大纲 (outline/chapters/chXX.md)
2. 执行 Stage 9（章节写作）重写该章
3. 自动执行 Stage 10（编辑审核）审核重写后的章节
4. 展示章节和审核结果

### 快速通道

以下情况可跳过设计文档更新，直接修改章节：
- **纯文字润色**：只涉及措辞、描写调整，不涉及情节、角色、设定变更
- **写作备注修正**：修正章节末尾写作备注中的记录错误
- **格式修复**：修复文件格式问题

即使在快速通道中，也需确认修改不与任何设计文档矛盾。如有疑问，仍应先检查上游设计。

## Important Constraints

- All generated content is in **Chinese**. Summaries for the user can be in their language.
- Respect **pipeline dependencies**. Never run a stage whose prerequisites are not confirmed.
- **Warn about propagation** before suggesting edits to early stages.
- Each agent prompt defines its own **constraints** section — follow them strictly.
- Character files **must** include YAML front-matter (see `references/project-structure.md`).
- Chapter files **must** include the 写作备注 (Writing Notes) section.
- Use `references/context-procedures.md` for context compression procedures.

## Reference Files

For deeper detail, read these files as needed:

- `references/pipeline.md` — Full pipeline dependency graph, propagation rules, status values
- `references/project-structure.md` — Directory tree, project.yaml schema, file formats
- `references/context-procedures.md` — Context compression and extraction procedures
- `references/agents/01-genre-analyst.md` through `references/agents/11-consistency-checker.md` — Agent prompts for each stage

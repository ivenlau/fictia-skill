# Fictia 项目结构参考

## 单本目录结构

```
project-root/
├── project.yaml                    # 项目配置 + 流水线状态
├── genre-analysis.md               # 阶段 1：题材分析
├── blueprint.md                    # 阶段 2：架构设计
├── style-guide.md                  # 阶段 3：风格指南
├── art-design.md                   # 阶段 4：艺术设计
├── narrative-weave.md              # 阶段 5：叙事编织
├── sources/                        # 改写/仿写/续写源文本（由 source import 生成）
│   ├── original.md                 #   epub/txt/md 规范化后的文本
│   └── ...
├── world/                          # 阶段 6：世界观构建
│   ├── setting.md                  #   世界概况、地理、历史、社会
│   ├── rules.md                    #   力量体系、战斗、核心规则
│   └── timeline.md                 #   编年事件表
├── characters/                     # 阶段 7：人物设计
│   ├── protagonist.md              #   主角（含 YAML front-matter）
│   ├── antagonist.md               #   反派（含 YAML front-matter）
│   ├── relationships.md            #   人物关系图谱
│   └── supporting/                 #   配角
│       ├── mentor.md
│       └── ...
├── outline/                        # 阶段 8：故事设计
│   ├── act-1.md                    #   第一幕概要
│   ├── act-2.md                    #   第二幕概要
│   ├── act-3.md                    #   第三幕概要
│   └── chapters/                   #   逐章大纲
│       ├── ch01.md                 #     含 weave_notes
│       ├── ch02.md
│       └── ...
├── chapters/                       # 阶段 9：章节写作
│   ├── act-1/                      #   第一幕章节
│   │   ├── ch01.md                 #     正文 + 写作备注
│   │   ├── ch02.md
│   │   └── ...
│   ├── act-2/
│   └── act-3/
├── notes/                          # 用户笔记（贯穿整个流程，append-only）
│   ├── raw.md                      #   原始记录（verbatim 保留）
│   └── summary.md                  #   蒸馏后的额外上下文（按主题分类）
└── reviews/                        # 阶段 10-11：审核
    ├── ch01-review.md              #   编辑审核
    ├── ch02-review.md
    ├── ...
    └── consistency-report.md       #   里程碑一致性报告（覆写）
```

## 系列目录结构

```
series-root/
├── series.yaml                     # 系列配置（共享世界/角色）
├── shared/
│   ├── world/                      # 跨书共享世界设定
│   └── characters/                 # 跨书共享角色库
└── books/
    ├── book-1/                     # 完整单本结构
    │   ├── project.yaml
    │   └── ...
    └── book-2/
        ├── project.yaml
        └── ...
```

## project.yaml 格式

```yaml
name: "项目名称"
author: "作者名"
description: "项目描述"
created: "2026-05-27T00:00:00Z"
last_modified: "2026-05-27T00:00:00Z"
version: 1
genre: "玄幻"
target_words: 800000
target_volumes: 3
chapter_target_words: 3000               # 每章平均目标字数（由 target_words / 预估章节数 自动计算，或用户指定）

pipeline:
  genre_analysis:
    status: "confirmed"
    confirmedAt: "2026-05-27T10:00:00Z"
    outputFiles: ["genre-analysis.md"]
  architecture:
    status: "not_started"
  # ... 每个阶段一条

pipeline_settings:
  parallel_design: false          # 启用并行模式：故事设计与章节写作可同时进行（见 SKILL.md）
  brainstorm_mode: true           # 头脑风暴模式：设计阶段默认进入探索→共创→产出三段式

chapters:
  total: 30
  written: 5
  confirmed: 3
  outlines:                       # 每章大纲的就绪时间戳（并行模式下使用）
    ch01: "2026-06-17T10:00:00Z"
    ch02: "2026-06-17T11:30:00Z"

consistency:
  last_check_chapter: 5
  last_check_date: "2026-06-04"
  status: confirmed

source_material:
  workflow: rewrite                  # rewrite / imitation / continuation
  files:
    - title: "源文本标题"
      workflow: rewrite
      format: epub                   # epub / txt / md
      original: "C:/path/original.epub"
      text: sources/original.md
      importedAt: "2026-06-11T12:00:00Z"
```

`source_material` 仅在小说改写、仿写、续写流程中出现。源文件统一由 `fictia source import <file> --workflow <mode>` 导入，后续 `ctx assemble` 会自动把 `sources/*.md` 的节选放入写手、编辑和一致性校验上下文。

## 角色文件格式

每个角色文件必须以 YAML front-matter 开头：

```markdown
---
name: "林远"
role: "protagonist"
identity: "落魄世家子弟"
age: 17
traits: ["坚韧", "聪慧", "隐忍"]
relationships:
  - name: "苏瑶"
    relation: "青梅竹马"
    dynamic: "从信任到误解到重修旧好"
growth_arc: "从隐忍求存到主动担当"
language_style: "简洁克制，偶尔锋利"
---

[角色详细描述正文...]
```

## 章节文件格式

章节正文后接写作备注：

```markdown
[章节正文...]

---

### 写作备注

- **字数**: 3200
- **伏笔操作**:
  - 埋设: 伏笔ID-F003 (神秘玉佩的来历)
  - 推进: 伏笔ID-F001 (林远身世线索在第三段提及)
- **副线进度**: 感情线推进 (林远与苏瑶重逢)
- **新增设定**: 无
- **人物状态更新**: 林远左臂受伤 (第12段)
- **下章衔接点**: 本章结尾林远决定前往北域，下章从北域入口开始
```

## 文件命名规范

| 内容 | 路径模式 |
|------|---------|
| 幕章节 | `chapters/act-1/ch01.md`, `ch02.md`, ... |
| 章节大纲 | `outline/chapters/ch01.md`, `ch02.md`, ... |
| 审核报告 | `reviews/ch01-review.md`, `ch02-review.md`, ... |

## 信息定位

| 信息 | 位置 |
|------|------|
| 项目名、题材、目标字数 | `project.yaml` → `name`, `genre`, `target_words` |
| 流水线阶段状态 | `project.yaml` → `pipeline.<stage>.status` |
| 章节进度 | `project.yaml` → `chapters`（或统计文件数） |
| 风格规则 | `style-guide.md` |
| 力量体系 | `world/rules.md` |
| 角色速查 | 角色文件 → YAML front-matter |
| 伏笔追踪 | `narrative-weave.md` → 伏笔表 |
| 章节伏笔指令 | `outline/chapters/chXX.md` → `weave_notes` |
| 编辑评分 | `reviews/chXX-review.md` → 评分表 |
| 一致性问题 | `reviews/consistency-report.md` → 问题列表 |
| 用户笔记原始记录 | `notes/raw.md` |
| 用户笔记蒸馏摘要 | `notes/summary.md`（章节写作时自动加载） |

## Meta Index（产出文件注册表）

项目根目录的 `meta-index.yaml` 声明所有 agent 产出文件的元数据，供向量索引和实体提取器使用。

```bash
fictia meta init      # 首次生成（扫描项目文件）
fictia meta sync      # 增量更新（检测内容变化）
fictia meta status    # 查看注册表状态
fictia meta stale     # 列出需要重新索引的文件
```

文件结构示例：
```yaml
version: 2
last_sync: "2026-07-16T10:00:00Z"
design_files:
  - path: "genre-analysis.md"
    stage: "genre_analysis"
    indexable: true
    chunk_strategy: "section"
    vector_collection: "design"
    content_hash: "sha256:abcdef1234567890"
```

## 标准化表格 Schema

所有 agent 产出文件中的结构化数据表格**必须**使用以下标准列名。提取器（`entity_extractors.py`）按这些列名解析。

### 伏笔表（foreshadowing）
```markdown
| 编号 | 名称 | 类型 | 埋设章节 | 强化章节 | 回收章节 | 描述 |
```
- 编号：格式 `F01`, `F02`...（大写 F + 两位数字）
- 类型：`明伏笔 | 暗伏笔 | 结构性伏笔 | 反向伏笔 | 主题伏笔`
- 埋设/强化/回收章节：格式 `ch03` 或 `ch03, ch08`（多个用逗号分隔）

### 支线表（storylines）
```markdown
| 编号 | 名称 | 类型 | 起始章节 | 结束章节 | 关联角色 | 描述 |
```
- 编号：格式 `S01`, `S02`...
- 类型：`人物 | 世界观 | 情感 | 悬念 | 主题`
- 关联角色：逗号分隔的角色名

### 彩蛋表（easter_eggs）
```markdown
| 编号 | 名称 | 类型 | 位置 | 触发条件 | 描述 |
```
- 编号：格式 `E01`, `E02`...
- 类型：`致敬 | 元叙事 | 细节 | 互文 | 读者互动`

### 时间线表（timeline）
```markdown
| 时间 | 事件 | 影响 | 与故事关联 |
```

### 角色 front-matter relationships 字段
必须使用 dict 格式：
```yaml
relationships:
  - name: "角色名"
    relation: "关系描述"
    dynamic: "关系发展轨迹"
```

### 章节大纲场景格式
场景内定位字段必须使用独立行格式（不混合斜杠）：
```markdown
- **地点**：[具体场所]
- **时间**：[时辰/时间段]
- **POV**：[视角角色名]
- **参与角色**：[角色名列表，逗号分隔]
- **场景目标**：[目标描述]
```

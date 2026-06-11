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

chapters:
  total: 30
  written: 5
  confirmed: 3

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

# Fictia Project Structure Reference

## Single-Book Project Directory Tree

```
project-root/
├── project.yaml                    # Project config + pipeline state
├── genre-analysis.md               # Stage 1: Genre analysis output
├── blueprint.md                    # Stage 2: Architecture blueprint
├── style-guide.md                  # Stage 3: Style guide (global anchor)
├── art-design.md                   # Stage 4: Art design (imagery, emotional beats)
├── narrative-weave.md              # Stage 5: Narrative web (foreshadowing, subplots)
├── world/                          # Stage 6: World building
│   ├── setting.md                  #   World overview, geography, history, society
│   ├── rules.md                    #   Power system, combat, magic, core rules
│   └── timeline.md                 #   Chronological event table
├── characters/                     # Stage 7: Character design
│   ├── protagonist.md              #   Protagonist (with YAML front-matter)
│   ├── antagonist.md               #   Antagonist (with YAML front-matter)
│   ├── relationships.md            #   Relationship network
│   └── supporting/                 #   Supporting characters
│       ├── mentor.md
│       └── ...
├── outline/                        # Stage 8: Story design
│   ├── act-1.md                    #   Act 1 overview
│   ├── act-2.md                    #   Act 2 overview
│   ├── act-3.md                    #   Act 3 overview
│   └── chapters/                   #   Per-chapter outlines
│       ├── ch01.md                 #     Chapter 1 outline (with weave_notes)
│       ├── ch02.md
│       └── ...
├── chapters/                       # Stage 9: Chapter writing
│   ├── act-1/                      #   Act 1 chapters
│   │   ├── ch01.md                 #     Chapter 1 prose + writing notes
│   │   ├── ch02.md
│   │   └── ...
│   ├── act-2/
│   └── act-3/
└── reviews/                        # Stages 10-11: Reviews
    ├── ch01-review.md              #   Chapter 1 editor review
    ├── ch02-review.md
    ├── ...
    └── consistency-report.md       #   Global consistency report
```

## Series Project Directory Tree

```
series-root/
├── series.yaml                     # Series config (shared world/characters)
├── shared/
│   ├── world/                      # Shared world setting across books
│   └── characters/                 # Shared character library
└── books/
    ├── book-1/                     # Full single-book structure
    │   ├── project.yaml
    │   └── ...
    └── book-2/
        ├── project.yaml
        └── ...
```

## project.yaml Schema

```yaml
name: "项目名称"                    # Project name (required)
author: "作者名"                    # Author (optional)
description: "项目描述"             # Description (optional)
created: "2026-05-27T00:00:00Z"    # Creation timestamp
last_modified: "2026-05-27T00:00:00Z"
version: 1                         # Schema version
genre: "玄幻"                       # Genre (optional)
target_words: 800000               # Target total word count (optional)
target_volumes: 3                  # Number of volumes/acts (optional)
chapter_target_words: 3000         # Target words per chapter (optional)

pipeline:                          # Pipeline state per stage
  genre_analysis:
    status: "confirmed"            # not_started | in_progress | pending_confirm | confirmed | needs_update | failed
    confirmedAt: "2026-05-27T10:00:00Z"
    outputFiles: ["genre-analysis.md"]
  architecture:
    status: "not_started"
  # ... (one entry per stage)

chapters:                          # Chapter progress (auto-computed)
  total: 30                        # Total chapters (from outline/chapters/*.md count)
  written: 5                       # Written chapters (from chapters/act-*/*.md count)
  confirmed: 3                     # Confirmed chapters
```

## Character File Format

Every character file MUST start with YAML front-matter:

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

[Detailed character description in narrative form...]
```

## Chapter File Format

Chapter files contain prose followed by a "Writing Notes" section:

```markdown
[Chapter prose in Chinese...]

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

## Chapter Naming Convention

- Act 1 chapters: `chapters/act-1/ch01.md`, `ch02.md`, ...
- Act 2 chapters: `chapters/act-2/ch08.md`, `ch09.md`, ... (continuing numbering)
- Act 3 chapters: `chapters/act-3/ch15.md`, ...
- Chapter outlines: `outline/chapters/ch01.md`, `ch02.md`, ...
- Reviews: `reviews/ch01-review.md`, `ch02-review.md`, ...

## Where to Find Specific Information

| Information | Location |
|-------------|----------|
| Project name, genre, target words | `project.yaml` → `name`, `genre`, `target_words` |
| Pipeline stage status | `project.yaml` → `pipeline.<stage>.status` |
| Chapter progress | `project.yaml` → `chapters` (or count files in `outline/chapters/` vs `chapters/act-*/`) |
| Style rules | `style-guide.md` |
| Power system details | `world/rules.md` |
| Character quick info | Character files → YAML front-matter |
| Foreshadowing tracking | `narrative-weave.md` → foreshadowing table |
| Chapter-specific foreshadowing | `outline/chapters/chXX.md` → `weave_notes` |
| Editor review scores | `reviews/chXX-review.md` → scoring table |
| Consistency issues | `reviews/consistency-report.md` → issue list |

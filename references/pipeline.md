# Fictia Pipeline Reference

## Pipeline Stages

Fictia orchestrates 11 stages in strict dependency order. Each stage has a dedicated AI agent.

| # | Stage Name | Chinese Label | Dependencies | Incremental | Auto-Trigger |
|---|-----------|---------------|-------------|-------------|--------------|
| 1 | `genre_analysis` | 题材分析 | (none) | No | — |
| 2 | `architecture` | 架构设计 | genre_analysis | No | — |
| 3 | `style` | 风格设计 | genre_analysis, architecture | No | — |
| 4 | `art_design` | 艺术设计 | genre_analysis, architecture, style | No | — |
| 5 | `narrative_weave` | 叙事编织 | genre_analysis, architecture, art_design, style | No | — |
| 6 | `world` | 世界观构建 | genre_analysis, architecture, art_design, narrative_weave | Yes | — |
| 7 | `characters` | 人物设计 | world, architecture, style, art_design, narrative_weave | Yes | — |
| 8 | `story` | 故事设计 | architecture, art_design, narrative_weave, world, characters | Yes | — |
| 9 | `chapters` | 章节写作 | style, art_design, narrative_weave, world, characters, story | Yes | — |
| 10 | `editor` | 编辑审核 | chapters, style | Yes | Yes |
| 11 | `consistency` | 一致性校验 | chapters | Yes | — |

## Dependency Diagram

```
genre_analysis
  ├── architecture
  │     ├── style ──────────────────────────────────────┐
  │     │     ├── art_design                            │
  │     │     │     ├── narrative_weave                 │
  │     │     │     │     ├── world                     │
  │     │     │     │     │     ├── characters          │
  │     │     │     │     │     │     ├── story         │
  │     │     │     │     │     │     │     ├── chapters┤
  │     │     │     │     │     │     │     │     ├── editor (auto)
  │     │     │     │     │     │     │     │     └── consistency
```

## Propagation Rules

When a stage is modified, downstream stages are marked `needs_update` via BFS:

| Modified Stage | Affected Downstream Stages |
|---------------|---------------------------|
| `genre_analysis` | architecture, style, art_design, narrative_weave, world, characters, story, chapters |
| `architecture` | narrative_weave, story, chapters |
| `style` | chapters, editor |
| `art_design` | narrative_weave, characters, story, chapters |
| `narrative_weave` | characters, story, chapters |
| `world` | characters, story, chapters |
| `characters` | story, chapters |
| `story` | chapters |
| `chapters` | consistency |
| `editor` | (none) |
| `consistency` | (none) |

**Warning**: Modifying `genre_analysis` invalidates 8 downstream stages — the most expensive change. Modifying `style` affects `chapters` and `editor`. Always warn the user about propagation before suggesting edits to early stages.

## Stage Status Values

| Status | Meaning |
|--------|---------|
| `not_started` | Stage has not been run yet |
| `in_progress` | Stage is currently running (or has more incremental work) |
| `pending_confirm` | Stage output is ready, awaiting user confirmation |
| `confirmed` | User has approved the stage output |
| `needs_update` | An upstream stage was modified; this stage needs re-running |
| `failed` | Stage execution failed (check error details) |

## Incremental Stages

Stages marked "Yes" for incremental support can process one item at a time:
- `world`: Can build world files incrementally
- `characters`: Can design characters one at a time
- `story`: Can outline acts/chapters incrementally
- `chapters`: Writes one chapter at a time (primary use case)
- `editor`: Reviews one chapter at a time (auto-triggers after each chapter)
- `consistency`: Can check incrementally

For incremental stages, after each item is processed, the agent checks `hasMoreWork()`. If more items remain, the stage stays `in_progress` and processes the next item.

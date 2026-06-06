# Fictia 流水线参考

## 流水线阶段

11 个阶段按严格依赖顺序执行，每个阶段有专用 agent。

| # | 阶段 | 中文名 | 依赖 | 增量 | 自动触发 |
|---|------|--------|------|------|---------|
| 1 | `genre_analysis` | 题材分析 | （无） | 否 | — |
| 2 | `architecture` | 架构设计 | genre_analysis | 否 | — |
| 3 | `style` | 风格设计 | genre_analysis, architecture | 否 | — |
| 4 | `art_design` | 艺术设计 | genre_analysis, architecture, style | 否 | — |
| 5 | `narrative_weave` | 叙事编织 | genre_analysis, architecture, art_design, style | 否 | — |
| 6 | `world` | 世界观构建 | genre_analysis, architecture, art_design, narrative_weave | 是 | — |
| 7 | `characters` | 人物设计 | world, architecture, style, art_design, narrative_weave | 是 | — |
| 8 | `story` | 故事设计 | architecture, art_design, narrative_weave, world, characters | 是 | — |
| 9 | `chapters` | 章节写作 | style, art_design, narrative_weave, world, characters, story | 是 | — |
| 10 | `editor` | 编辑审核 | chapters, style | 是 | 是（每章强制，必须通过） |
| 11 | `consistency` | 一致性校验 | chapters | 是 | 是（每 5 章强制，必须通过） |

## 依赖图

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

## 传播规则

某阶段修改后，下游阶段通过 BFS 标记为 `needs_update`：

| 修改阶段 | 受影响下游 |
|---------|-----------|
| `genre_analysis` | architecture, style, art_design, narrative_weave, world, characters, story, chapters |
| `architecture` | narrative_weave, story, chapters |
| `style` | chapters, editor |
| `art_design` | narrative_weave, characters, story, chapters |
| `narrative_weave` | characters, story, chapters |
| `world` | characters, story, chapters |
| `characters` | story, chapters |
| `story` | chapters |
| `chapters` | consistency |
| `editor` | （无） |
| `consistency` | （无） |

**注意**：修改 `genre_analysis` 影响最多（8 个下游），代价最高。修改早期阶段前必须警告用户。

## 阶段状态值

| 状态 | 含义 |
|------|------|
| `not_started` | 未执行 |
| `in_progress` | 执行中（或有更多增量工作） |
| `pending_confirm` | 产出已就绪，等待用户确认 |
| `confirmed` | 用户已确认 |
| `needs_update` | 上游阶段被修改，需重新执行 |
| `failed` | 执行失败 |

## 增量阶段

标记为"是"的阶段可逐项处理：
- `world`：逐个构建世界文件
- `characters`：逐个设计角色
- `story`：逐幕/逐章规划
- `chapters`：逐章写作（主要使用场景）
- `editor`：逐章审核。**强制**：每章写完后必须执行，审核-修复循环必须通过（零严重/一般问题，评分 = A）后章节才能确认。最多 3 轮。
- `consistency`：跨章节校验。**强制**：每确认 5 章（ch05、ch10、ch15...）必须执行，一致性-修复循环必须通过（零严重/一般问题，评分 = A）后才能写作新章节。最多 2 轮。

增量阶段每处理完一项后检查 `hasMoreWork()`，若有更多则保持 `in_progress` 继续处理下一项。

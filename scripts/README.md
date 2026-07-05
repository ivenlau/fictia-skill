# Fictia CLI 工具

把 Fictia 流水线中所有可机械化的环节脚本化，让 LLM 把注意力放在创作而非流程管理上。

## 零依赖

- 纯 Python 3.8+ 标准库
- 无 PyYAML / requests / 任何第三方包
- 跨平台：Windows / macOS / Linux
- Windows 控制台自动启用 UTF-8

## 安装

把 `scripts/` 目录加到 PATH 即可：

**Git Bash / WSL / macOS / Linux：**
```bash
# 已设执行权限
chmod +x scripts/fictia
export PATH="$PWD/scripts:$PATH"
```

**Windows cmd：**
```cmd
set PATH=%CD%\scripts;%PATH%
```
（`scripts/fictia.bat` 是 Windows cmd 的入口，`scripts/fictia` 是 Git Bash / WSL 的入口。）

## 子命令总览

```
fictia init <name>             新建项目
fictia status                  渲染状态面板
fictia stage                   下一个可执行阶段
fictia stage <sub> <stage>     ready / confirm / invalidate / start / fail / reset / show
fictia stage chapter increment 单章进度 +1
fictia stage chapter set       直接设置 total/written/confirmed
fictia words <file>...         统计字数（自动剥离写作备注）
fictia judge <actual> <target> 字数判定
fictia milestone               检查章节里程碑（每 5 章）
fictia consistency confirm     记录一致性校验通过的章节
fictia consistency collect     自动汇总伏笔/支线/角色状态追踪表 → .fictia-cache/
fictia source import <file>    导入改写/仿写/续写源文本（epub/txt/md）
fictia source list             列出已导入源文本
fictia ctx <program> [...]     上下文压缩与组装
fictia verdict review <file>   解析编辑审核报告
fictia verdict consistency <file> 解析一致性校验报告
fictia export <md|txt>         导出整本
fictia lint                    项目结构校验（v1 兼容）
fictia lint <stage> <file>     单文件 v2 schema lint（字数预算 + 污染检测）
```

所有子命令都支持 `--project / -p` 显式指定项目目录；不指定则从当前目录向上查找 `project.yaml`。

## v2 schema lint（单文件模式）

`fictia lint <stage> <file>` 检查单个产出文件是否符合 v2 schema：

- **front-matter 必填字段**：缺失 → warning
- **字数预算**：超出 ±20% → warning
- **数量上限**：严重问题 ≤ 3 条等 → 超出 → warning
- **计数字段一致性**：`severe_count` 与实际表行数不一致 → warning
- **污染检测**：`feedback_*` / `project_*` / `note_*` / `符合 chXX` / `分工如下` 等 internal token → warning
- **front-matter 缺失/格式错**：→ error（exit 1）

支持的 stage key（也可传 file_budget key 如 `character_heavy`）：

| stage key | 用途 | 典型文件 |
|-----------|------|---------|
| `genre_analysis` | 题材分析 | genre-analysis.md |
| `architecture` | 架构设计 | blueprint.md |
| `style` | 风格指南 | style-guide.md |
| `style_samples` | 风格示例库 | style-samples.md |
| `art_design` | 艺术设计 | art-design.md |
| `narrative_weave` | 叙事编织 | narrative-weave.md |
| `world` | 世界观设定 | world/setting.md |
| `world_timeline` | 世界观时间线 | world/timeline.md |
| `characters` | 重角色 | characters/protagonist.md |
| `character_light` | 轻角色 | characters/supporting/*.md |
| `character_relationships` | 角色关系 | characters/relationships.md |
| `story` | 章节大纲 | outline/chapters/chNN.md |
| `outline_act` | 幕设计 | outline/act-N.md |
| `chapters` | 章节正文 | chapters/act-N/chNN.md |
| `editor` | 编辑审核 | reviews/chNN-review.md |
| `consistency` | 一致性报告 | reviews/consistency-report.md |

```bash
fictia lint chapters chapters/act-3/ch86.md
fictia lint editor reviews/ch86-review.md
fictia lint consistency reviews/consistency-report.md
```

软 warn 语义：所有超限问题以 warning 输出，exit 0；仅 front-matter 缺失/未知 stage 才 exit 1。

## consistency collect（自动汇总）

`fictia consistency collect` 扫所有章节 front-matter，与 narrative-weave.md 计划对照，生成：

- 章节摘要表（标题 / 字数 / 埋设 / 回收 / 推进 / 首次出场）
- 伏笔追踪表（计划 + 实际状态 + 出现章节；不在计划的标"未在计划"）
- 支线追踪表（计划 + 实际出现章节）
- 角色首次出场登记
- 各章写作备注原文

产物写入 `.fictia-cache/consistency-context.md`，stage 11 agent 直接读 + 标问题。
`fictia ctx assemble consistency` 会自动嵌入此文件。

```bash
fictia consistency collect
# → .fictia-cache/consistency-context.md
```

v1 章节（无 v2 front-matter）会显示空字段——这是预期行为，agent 应基于写作备注原文校验。

## source 子命令详解

源文本用于小说改写、仿写和续写，导入后统一保存为 `<project>/sources/*.md`，并记录到 `project.yaml` 的 `source_material` 字段。

```bash
fictia source import novel.epub --workflow rewrite
fictia source import sample.txt --workflow imitation --title "参考文本"
fictia source import draft.md --workflow continuation
fictia source list
```

支持格式：`.epub`、`.txt`、`.md`。`ctx assemble writer/editor/consistency` 会自动把已导入源文本摘要加入上下文。

## ctx 子命令详解

实现 `references/context-procedures.md` 的 8 个 build/extract 程序 + 3 个 assemble：

```
fictia ctx character-registry                    角色速查表（500-1000 字）
fictia ctx character-card <名字>                 单角色快速卡（300-500 字）
fictia ctx world-quickref                        世界观速查（1000-2000 字）
fictia ctx chapter-weave <chN>                   本章相关伏笔/支线
fictia ctx chapter-art <chN>                     本章相关情感节拍/意象
fictia ctx style-act <act-1|2|3|prologue|epilogue> 当前幕风格要点
fictia ctx weave-summary                         叙事编织全量压缩（~50%）
fictia ctx art-summary                           艺术设计全量压缩（~50%）
fictia ctx previous-chapter <chN>                前章摘要（写作备注 + 正文）
fictia ctx chapter-act <chN>                     章节→幕映射
fictia ctx assemble writer --chapter <N>         写手上下文 → .fictia-cache/
fictia ctx assemble editor --chapter <N>         编辑上下文 → .fictia-cache/
fictia ctx assemble consistency                  一致性上下文 → .fictia-cache/
```

`assemble` 的产物写入 `<project>/.fictia-cache/`，subagent 可直接 `Read` 该文件。

## LLM 集成

`fictia` 的输出可以直接喂给 subagent prompt，例：

```bash
# 1. 生成写手上下文
fictia ctx assemble writer --chapter 3

# 2. 启动 subagent，prompt 中：
#    "请撰写第 3 章正文。先 Read 项目根目录的
#    .fictia-cache/ch03-writer-context.md 获取完整上下文，
#    然后按 references/agents/09-chapter-writer.md 的要求写作。"
```

## 退出码

- `0`：成功
- `1`：报告未通过（verdict）/ lint 有 error
- `2`：参数错误 / 文件缺失

`stage invalidate` 和 `verdict` 的非零退出码让 LLM 可直接根据退出码分支，无需解析 stdout。

## 测试

在临时目录跑完整端到端：

```bash
cd /tmp && rm -rf test
fictia init test --author "A" --genre "玄幻" --target 300000
cd test
fictia status
fictia stage                          # 应输出 01 题材分析
fictia stage start genre_analysis
fictia stage ready genre_analysis      # 产出已写入，等待用户确认
fictia stage confirm genre_analysis    # 用户确认后
fictia status                         # 题材分析应为 [✓]
```

## 设计原则

1. **LLM 不做机械事**：字数统计、状态推进、面板渲染、BFS 传播——全部脚本化
2. **Token 友好**：assemble 写出缓存文件，subagent 一次 Read 即可，不再 8 次 Read 拼 prompt
3. **可逆可控**：所有写操作都落到 project.yaml / 缓存文件，不修改正文/设定文件
4. **可独立调用**：CLI 设计让用户和 LLM 都能用

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
fictia meta init|sync|status   产出文件注册表管理（meta-index.yaml）
fictia source import <file>    导入改写/仿写/续写源文本（epub/txt/md）
fictia source list             列出已导入源文本
fictia ctx <program> [...]     上下文压缩与组装
fictia vector <sub> [...]      向量检索管理（zvec + embedding，可选 RAG）
fictia entity <sub> [...]      动态写作空间 — 实体管理（8 类有状态实体）
fictia brainstorm-mode <action> 头脑风暴模式开关（on/off/status，默认开启）
fictia verdict review <file>   解析编辑审核报告
fictia verdict consistency <file> 解析一致性校验报告
fictia export <md|txt>         导出整本
fictia lint                    项目结构校验
```

所有子命令都支持 `--project / -p` 显式指定项目目录；不指定则从当前目录向上查找 `project.yaml`。

## source 子命令详解

源文本用于小说改写、仿写和续写，导入后统一保存为 `<project>/sources/*.md`，并记录到 `project.yaml` 的 `source_material` 字段。

```bash
fictia source import novel.epub --workflow rewrite
fictia source import sample.txt --workflow imitation --title "参考文本"
fictia source import draft.md --workflow continuation
fictia source list
```

支持格式：`.epub`、`.txt`、`.md`。`ctx assemble writer/editor/consistency` 会自动把已导入源文本摘要加入上下文。

## meta 子命令详解

产出文件注册表管理（`meta-index.yaml`），供向量索引和实体提取器自动发现文件。

```bash
fictia meta init       # 首次生成（扫描项目目录，创建 meta-index.yaml）
fictia meta sync       # 增量更新（检测文件内容变化，递增 version）
fictia meta status     # 查看注册表状态（各类型文件数量）
fictia meta stale      # 列出需要重新索引的文件（content_hash 不匹配）
```

`meta-index.yaml` 记录每个产出文件的：
- `path`：相对路径
- `stage`：所属流水线阶段
- `indexable`：是否需要向量索引
- `chunk_strategy`：切分策略（section / paragraph / scene / table_row）
- `vector_collection`：写入哪个向量 collection（design / world / outlines / chapters / notes / sources）
- `entity_collections`：涉及哪些实体类型
- `content_hash`：内容摘要（用于增量检测）
- `version`：内容版本号

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

## 向量检索（可选 RAG 能力）

适用场景：长篇创作需要跨章节语义检索（如"找出所有'林远受伤'的场景"）。

### 安装

| 模式 | 命令 | 适用 |
|---|---|---|
| stub（默认） | 无 | 仅跑通工具链，无语义 |
| local | `pip install sentence-transformers` + `export FICTIA_EMBEDDING=local` | 本地离线、中文 SOTA、首次下载 ~2.3GB 模型 |
| api | `pip install httpx` + `export ZHIPUAI_API_KEY=xxx` + `export FICTIA_EMBEDDING=api` | 云端、不想装模型 |

向量库 zvec 单独安装：`pip install zvec`。

### 索引

```bash
fictia vector index-chapter --chapter N    # 手动索引单章
fictia vector index-notes                  # 索引笔记摘要
fictia vector index-source                 # 索引源文本
fictia vector index-design                 # 索引设计文件（genre-analysis/blueprint/style-guide/art-design/narrative-weave/characters）
fictia vector index-world                  # 索引世界观文件（setting/rules/timeline）
fictia vector index-outlines               # 索引大纲文件（act-*.md, chapters/ch*.md）
fictia vector index-all                    # 索引全部（含上述所有）
```

> **自动索引**：执行 `fictia stage chapter outline --chapter N` 与 `fictia consistency confirm --chapter N` 时会自动索引对应章节，无需手动调用。

### 检索

```bash
fictia vector search "<query>" --top-k 5
fictia ctx semantic-search "<query>" --chapter N  # 作为 ctx 输出（markdown 格式）
```

### 管理

```bash
fictia vector status                        # 显示当前 embedding model + dim + 各 collection chunk 数
fictia vector clear --collection chapters   # 清空指定 collection
fictia vector clear --yes                   # 清空全部（需 --yes 确认）
```

### Embedding 切换

- `local` ↔ `api` 都是 1024-dim，**互相切换不需要重建索引**
- `stub` → `local|api` 必须 `fictia vector clear && index-all` 重建

### 数据位置

向量数据存放在 `<project_root>/.fictia/zvec/`，已在 `.gitignore` 中排除。

## entity 子命令详解（动态写作空间）

管理 8 类有状态的实体（characters/locations/items/events/foreshadowing/easter_eggs/storylines/timeline）。

```
fictia entity index-all                          从项目文件批量提取所有实体
fictia entity index <collection>                 提取指定类型的实体
fictia entity status                             各 collection 实体数量统计
fictia entity list <collection> [--state <s>]    列出实体（可按状态过滤）
fictia entity get <collection> <entity_id>       获取单个实体详情（JSON）
fictia entity search "<query>" [--collection X]  语义搜索实体
fictia entity update <col> <id> --state <s> --state-ch <N>  更新实体状态
fictia entity clear [--collection X] [--yes]     清空实体数据
fictia entity outline-hints --chapter <N>        解析大纲线索（调试用）
```

### 写作空间组装

```bash
fictia ctx writing-space --chapter <N>           组装写作空间 → .fictia-cache/
```

写作空间 = 静态设计文档 + 必读动态实体 + 按需检索。大纲解析器自动从大纲中提取角色/地点/伏笔线索，检索对应实体的当前状态。

### 写作备注扩展

章节写作备注支持实体状态变更声明：

```markdown
- **人物状态更新**: 林远左臂受伤 (第12段)
- **地点变更**: 北域冰原 → state: active
- **物品状态**: 神秘玉佩 → state: discovered
- **事件结案**: 北域围猎 → state: concluded
```

### 数据位置

实体数据存放在 `<project_root>/.fictia/zvec/{characters,locations,...}/`，与 chunk-based 全文检索并存。

## 设计原则

1. **LLM 不做机械事**：字数统计、状态推进、面板渲染、BFS 传播——全部脚本化
2. **Token 友好**：assemble 写出缓存文件，subagent 一次 Read 即可，不再 8 次 Read 拼 prompt
3. **可逆可控**：所有写操作都落到 project.yaml / 缓存文件，不修改正文/设定文件
4. **可独立调用**：CLI 设计让用户和 LLM 都能用

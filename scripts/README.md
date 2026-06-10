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
fictia ctx <program> [...]     上下文压缩与组装
fictia verdict review <file>   解析编辑审核报告
fictia verdict consistency <file> 解析一致性校验报告
fictia export <md|txt>         导出整本
fictia lint                    项目结构校验
```

所有子命令都支持 `--project / -p` 显式指定项目目录；不指定则从当前目录向上查找 `project.yaml`。

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

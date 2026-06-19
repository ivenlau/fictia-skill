"""回归测试：parse_review_verdict 报告解析。

涵盖的 bug 场景（见 scripts/lib/context.py 修复记录）：

1. **BUG 1** — section 跨边界匹配：审核员写「严重问题（必须修改）：无」，
   后面跟「细节问题」表格。原 parser 跨过 `### ` 标题去抓下一个表格，把
   细节问题的行数误算成严重问题行数。
2. **BUG 2** — 修复日志表混入：报告末尾追加「### 审核修复日志」表格后，
   原 parser 可能把迭代行数算成问题数。
3. **BUG 3** — 综合评分正则过松：原 ``评分[：:]`` 模式可能误抓
   「评分细项」表里的字母。
4. **f-string 转义** — ``rf"^(#{1,6})..."`` 中的 ``#`` 会触发 f-string 表达式，
   导致模式变成 ``^(#(1, 6))...`` 永远不匹配。

运行方式：
    python3 scripts/tests/test_parse_review_verdict.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 把 scripts/ 加进 path 以便直接 import lib.context
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.context import parse_review_verdict  # noqa: E402


def _v(text: str) -> dict:
    return parse_review_verdict(text)


# ---------- 真实场景 ----------

REPORT_BUG1 = """# 第3章审核报告

## 总体评价
- **综合评分**：A

## 问题清单

### 严重问题（必须修改）
无

### 一般问题（建议修改）
无

### 细节问题（可选修改）
| 序号 | 位置 | 问题类型 | 问题描述 | 修改建议 |
|------|------|---------|---------|---------|
| 1 | 中段 | 措辞 | 某处措辞不够精炼 | 建议改用更准确的词汇 |
| 2 | 末段 | 节奏 | 末段略仓促 | 可适当展开 |

## 亮点
...
"""

REPORT_BUG2 = """# 第3章审核报告

## 总体评价
- **综合评分**：B

## 问题清单

### 严重问题（必须修改）
| 序号 | 位置 | 问题类型 | 问题描述 | 修改建议 |
|------|------|---------|---------|---------|
| 1 | 第1段 | 地名错误 | 开头出现"新兴县"应删除 | 删除"新兴县" |

### 一般问题（建议修改）
无

### 细节问题（可选修改）
| 序号 | 位置 | 问题类型 | 问题描述 | 修改建议 |
|------|------|---------|---------|---------|
| 1 | 中段 | 措辞 | 某处措辞不够精炼 | 建议改用更准确的词汇 |

### 审核修复日志
| 迭代 | 严重问题 | 一般问题 | 评分 | 主要修复内容 |
|------|---------|---------|------|------------|
| 1 | 1 | 5 | B | 开头删新兴县 |
"""

REPORT_USER = """# 第3章审核报告

## 总体评价
- **综合评分**：A

## 评分细项
| 维度 | 评分 | 说明 |
|------|------|------|
| 文学质量 | 9 | 文笔成熟 |
| 风格一致性 | 9 | 与风格指南一致 |

## 字数验证（必填）

| 项目 | 数值 |
|------|------|
| 目标字数 | 3000 |
| 实际字数（约） | 3100 |
| 偏差率 | 3% |
| 字数判定 | ✅ 达标 |

## 问题清单

### 严重问题（必须修改）
（无）

### 一般问题（建议修改）
（无）

### 细节问题（可选修改）
| 序号 | 位置 | 问题类型 | 问题描述 | 修改建议 |
|------|------|---------|---------|---------|
| 1 | 第2段 | 措辞 | 一处"赫然"使用略生硬 | 可考虑替换 |

## 亮点
...

### 审核修复日志
| 迭代 | 严重问题 | 一般问题 | 评分 | 主要修复内容 |
|------|---------|---------|------|------------|
| 1 | 1 | 5 | B | 开头删新兴县 |
| 2 | 0 | 0 | A |  本章通过 |
"""

REPORT_A = """# 第3章审核报告

## 总体评价
- **综合评分**：B

## 问题清单

### 严重问题（必须修改）
| 序号 | 位置 | 问题类型 | 问题描述 | 修改建议 |
|------|------|---------|---------|---------|
| 1 | 第1段 | **地名错误** | 开头出现"新兴县"应删除 | 删除"新兴县" |

### 一般问题（建议修改）
| 序号 | 位置 | 问题类型 | 问题描述 | 修改建议 |
|------|------|---------|---------|---------|
| 1 | 中段 | 用词 | ... | ... |
| 2 | 末段 | 节奏 | ... | ... |

## 亮点
...
"""

REPORT_GRADE = """# 第3章审核报告

## 总体评价
- **综合评分**：B

## 评分细项
| 维度 | 评分 | 说明 |
|------|------|------|
| 文学质量 | 7 | 整体评分尚可，需打磨 |

## 问题清单

### 严重问题（必须修改）
| 序号 | 位置 | 问题类型 | 问题描述 | 修改建议 |
|------|------|---------|---------|---------|
| 1 | ... | ... | ... | ... |

### 审核修复日志
| 迭代 | 严重问题 | 一般问题 | 评分 | 主要修复内容 |
|------|---------|---------|------|------------|
| 1 | 1 | 0 | B | fix1 |
| 2 | 0 | 0 | A | fix2 |
"""

REPORT_PASS_CLEAN = """# 第3章审核报告

## 总体评价
- **综合评分**：A
- **一句话评价**：本章完成度极高

## 亮点
...
"""

REPORT_NONE_SIMPLE = """# 第3章审核报告

## 总体评价
- **综合评分**：A

## 问题清单

### 严重问题（必须修改）
无重大问题。

### 一般问题（建议修改）
无明显问题。

## 亮点
...
"""


CASES = [
    (
        "BUG 1: A + 严重=无 + 细节 table → severe=0 normal=0",
        REPORT_BUG1,
        {"grade": "A", "severe": 0, "normal": 0, "passed": True},
    ),
    (
        "BUG 2: B + 严重=1 + 一般=无 + 细节 + 修复日志 → severe=1 normal=0",
        REPORT_BUG2,
        {"grade": "B", "severe": 1, "normal": 0, "passed": False},
    ),
    (
        "BUG 3 (user case): A + 严重=（无）+ 一般=（无）+ 细节 + 修复日志 → 0/0/A",
        REPORT_USER,
        {"grade": "A", "severe": 0, "normal": 0, "passed": True},
    ),
    (
        "Case A: B + 1 severe + 2 normal (无修复日志)",
        REPORT_A,
        {"grade": "B", "severe": 1, "normal": 2, "passed": False},
    ),
    (
        "Grade robustness: B + 评分细项含『整体评分尚可』+ 严重=1 → grade=B severe=1",
        REPORT_GRADE,
        {"grade": "B", "severe": 1, "normal": 0, "passed": False},
    ),
    (
        "Case C: A + 无问题 sections → grade=A severe=0 normal=0",
        REPORT_PASS_CLEAN,
        {"grade": "A", "severe": 0, "normal": 0, "passed": True},
    ),
    (
        "Case D: A + 严重=『无重大问题』+ 一般=『无明显问题』 → 0/0/A",
        REPORT_NONE_SIMPLE,
        {"grade": "A", "severe": 0, "normal": 0, "passed": True},
    ),
]


def main() -> int:
    failed = 0
    for name, text, expected in CASES:
        actual = _v(text)
        ok = actual == expected
        if not ok:
            failed += 1
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name}")
        if not ok:
            print(f"      expected={expected}")
            print(f"      actual=  {actual}")
    print()
    total = len(CASES)
    print(f"{'PASS' if failed == 0 else 'FAIL'}: {total - failed}/{total} cases passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
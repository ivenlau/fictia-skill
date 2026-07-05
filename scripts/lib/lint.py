"""
项目结构 lint + 单文件 v2 schema lint。

- lint_project(root): 检查 project.yaml、产出文件存在性、写作备注等（v1 兼容）
- lint_file(stage, path): 单文件 v2 schema lint——必填字段、字数预算、数量上限、污染检测
"""

from __future__ import annotations
import re
from pathlib import Path
from . import project as P
from . import budgets as B
from . import context as C
from . import words as W
from .yaml_subset import load as yaml_load


FRONTMATTER_RE = re.compile(r"^---\s*$", re.MULTILINE)
WRITING_NOTES_RE = re.compile(r"^#{1,6}\s*写作备注\s*$", re.MULTILINE)


def _has_frontmatter(text: str) -> bool:
    """判断文件是否以 YAML front-matter 开头。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    # 找到第二个 ---
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return True
    return False


def _has_writing_notes(text: str) -> bool:
    return bool(WRITING_NOTES_RE.search(text))


def _has_weave_notes(text: str) -> bool:
    """outline/chapters/chXX.md 应有 weave_notes 字段。"""
    return bool(re.search(r"^weave_notes\s*:", text, re.MULTILINE))


def lint_project(root: Path) -> list[dict]:
    """返回检查问题列表。每项 = {level, code, message, path}。"""
    issues: list[dict] = []
    yaml_path = root / "project.yaml"
    if not yaml_path.is_file():
        issues.append({"level": "error", "code": "yaml-missing", "message": "project.yaml 不存在", "path": str(yaml_path)})
        return issues

    # yaml 解析
    try:
        data = P.load_project(root)
    except Exception as e:
        issues.append({"level": "error", "code": "yaml-invalid", "message": f"project.yaml 解析失败: {e}", "path": str(yaml_path)})
        return issues

    # 必填字段
    for k in ["name", "author", "genre", "target_words", "target_volumes", "chapter_target_words"]:
        if not data.get(k):
            issues.append({"level": "warning", "code": "field-missing", "message": f"缺少字段: {k}", "path": "project.yaml"})

    # 阶段产出文件存在性
    for _, key, name in P.STAGES:
        outputs = P.STAGE_OUTPUTS.get(key, [])
        for rel in outputs:
            if rel.endswith(".gitkeep"):
                continue
            p = root / rel
            if not p.exists():
                issues.append({
                    "level": "info",
                    "code": "output-missing",
                    "message": f"{name} 产出文件不存在: {rel}",
                    "path": rel,
                })

    # 角色文件 front-matter
    chars_dir = root / "characters"
    if chars_dir.is_dir():
        for md in chars_dir.rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            if not _has_frontmatter(text):
                issues.append({
                    "level": "warning",
                    "code": "frontmatter-missing",
                    "message": "角色文件缺少 YAML front-matter",
                    "path": str(md.relative_to(root)),
                })

    # 章节文件 写作备注
    ch_dir = root / "chapters"
    if ch_dir.is_dir():
        for md in ch_dir.rglob("ch*.md"):
            text = md.read_text(encoding="utf-8")
            if not _has_writing_notes(text):
                issues.append({
                    "level": "warning",
                    "code": "writing-notes-missing",
                    "message": "章节文件缺少 ### 写作备注",
                    "path": str(md.relative_to(root)),
                })

    # 章节大纲 weave_notes
    outline_ch = root / "outline" / "chapters"
    if outline_ch.is_dir():
        for md in outline_ch.glob("ch*.md"):
            text = md.read_text(encoding="utf-8")
            if not _has_weave_notes(text):
                issues.append({
                    "level": "info",
                    "code": "weave-notes-missing",
                    "message": "大纲文件缺少 weave_notes 字段",
                    "path": str(md.relative_to(root)),
                })

    # 并行模式相关检查
    parallel = P.is_parallel_design_enabled(data)
    chapters = data.get("chapters") or {}
    outlines_map = chapters.get("outlines") or {}
    written = int(chapters.get("written") or 0)

    # 1) 大纲标记 ready 但文件不存在 → error
    for cn in outlines_map:
        outline_p = root / "outline" / "chapters" / f"{cn}.md"
        if not outline_p.is_file():
            issues.append({
                "level": "error",
                "code": "outline-marker-file-missing",
                "message": f"大纲已标记就绪但文件不存在: {cn}",
                "path": str(outline_p.relative_to(root)),
            })

    # 2) 并行模式开启但 story 阶段仍未开始 → info
    if parallel and P.get_stage_status(data, "story") == P.STATUS_NOT_STARTED:
        issues.append({
            "level": "info",
            "code": "parallel-without-story",
            "message": "并行模式已开启但 story 阶段未开始；建议先写至少一章大纲再用 `fictia stage chapter outline N` 标记就绪",
            "path": "project.yaml",
        })

    # 3) 章节已写但大纲未标记 ready（数据异常）→ info
    for n in range(1, written + 1):
        cn = f"ch{n:02d}"
        if cn not in outlines_map:
            issues.append({
                "level": "info",
                "code": "chapter-no-outline-marker",
                "message": f"章节 {cn} 已写但大纲未标记 ready（数据异常，可能由串行流程遗留）",
                "path": f"chapters/{cn}.md",
            })

    return issues


# ---------- 单文件 v2 schema lint ----------


def _count_table_rows_in_section(text: str, header: str) -> tuple[int, list[str]]:
    """统计指定 section 内第一个表格的数据行数，并返回每行原文。

    返回 (row_count, data_rows)。无表格返回 (0, [])。
    """
    m = re.search(rf"^(#{{1,6}})\s*{re.escape(header)}[^\n]*\n", text, re.MULTILINE)
    if not m:
        return (0, [])
    marker = m.group(1)
    start = m.end()
    next_section = re.search(rf"^#{{1,{len(marker)}}}\s+", text[start:], re.MULTILINE)
    end = start + next_section.start() if next_section else len(text)
    section_body = text[start:end]
    tbl_m = re.search(r"((?:^\|.*\|\s*\n)+)", section_body, re.MULTILINE)
    if not tbl_m:
        return (0, [])
    tbl = tbl_m.group(1)
    lines = [l for l in tbl.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        return (0, [])
    data_lines = [l for l in lines[2:] if not re.match(r"^\|[\s\-:|]+\|\s*$", l)]
    return (len(data_lines), data_lines)


def _check_pollution(text: str, path: str) -> list[dict]:
    """检测污染模式（仅检查 body，不查 front-matter）。"""
    fm, body = C.parse_frontmatter(text)
    issues: list[dict] = []
    for pat in B.POLLUTION_PATTERNS:
        for m in pat.finditer(body):
            issues.append({
                "level": "warning",
                "code": "pollution",
                "message": f"检测到 internal token / 元说明：{m.group(0)}",
                "path": path,
            })
    return issues


def _check_frontmatter_fields(fm: dict, required: list[str], path: str) -> list[dict]:
    """必填字段检查。"""
    issues: list[dict] = []
    for k in required:
        v = fm.get(k)
        if v is None or v == "":
            issues.append({
                "level": "warning",
                "code": "frontmatter-field-missing",
                "message": f"front-matter 缺少字段：{k}",
                "path": path,
            })
    return issues


def _check_total_chars(text: str, target: int, tolerance: float, path: str) -> list[dict]:
    """全文（含 front-matter）字数预算检查。"""
    if not target:
        return []
    actual = len(text)
    lo = int(target * (1 - tolerance))
    hi = int(target * (1 + tolerance))
    if actual < lo:
        return [{
            "level": "warning",
            "code": "total-chars-under",
            "message": f"字数 {actual} 低于预算下限 {lo}（目标 {target} ±{int(tolerance * 100)}%）",
            "path": path,
        }]
    if actual > hi:
        return [{
            "level": "warning",
            "code": "total-chars-over",
            "message": f"字数 {actual} 超出预算上限 {hi}（目标 {target} ±{int(tolerance * 100)}%）",
            "path": path,
        }]
    return []


def _check_chapter_words(fm: dict, body: str, budget: dict, path: str) -> list[dict]:
    """章节正文字数比例 + 写作备注字数检查。"""
    issues: list[dict] = []
    target = fm.get("target_words")
    actual_fm = fm.get("actual_words")
    if target and actual_fm:
        try:
            t = int(target)
            a = int(actual_fm)
            min_ratio = budget.get("body_min_ratio", 0)
            max_ratio = budget.get("body_max_ratio", 99)
            if a < t * min_ratio:
                issues.append({
                    "level": "warning",
                    "code": "chapter-words-under",
                    "message": f"实际字数 {a} 低于目标 {t} × {min_ratio:.0%} = {int(t * min_ratio)}",
                    "path": path,
                })
            elif a > t * max_ratio:
                issues.append({
                    "level": "warning",
                    "code": "chapter-words-over",
                    "message": f"实际字数 {a} 超出目标 {t} × {max_ratio:.0%} = {int(t * max_ratio)}",
                    "path": path,
                })
        except (ValueError, TypeError):
            issues.append({
                "level": "warning",
                "code": "frontmatter-field-invalid",
                "message": "target_words / actual_words 不是整数",
                "path": path,
            })
    # 写作备注字数
    notes_max = budget.get("writing_notes_max_chars")
    if notes_max:
        m = WRITING_NOTES_RE.search(body)
        if m:
            notes_text = body[m.end():].strip()
            notes_chars = len(re.sub(r"\s+", "", notes_text))
            if notes_chars > notes_max:
                issues.append({
                    "level": "warning",
                    "code": "writing-notes-too-long",
                    "message": f"写作备注 {notes_chars} 字超出上限 {notes_max} 字",
                    "path": path,
                })
    return issues


def _check_review_consistency(fm: dict, body: str, budget: dict, path: str) -> list[dict]:
    """审核报告 / 一致性报告：表行数 + 计数字段一致性 + 单条字数。"""
    issues: list[dict] = []
    count_fields: dict[str, str] = budget.get("count_fields", {})
    max_map = {
        "严重问题": budget.get("severe_max"),
        "一般问题": budget.get("normal_max"),
        "细节问题": budget.get("detail_max"),
    }
    desc_max = budget.get("problem_desc_max")

    for section_name, fm_field in count_fields.items():
        rows_count, data_rows = _count_table_rows_in_section(body, section_name)
        fm_count = fm.get(fm_field)
        # 计数字段一致性
        if fm_count is not None:
            try:
                if int(fm_count) != rows_count:
                    issues.append({
                        "level": "warning",
                        "code": "count-mismatch",
                        "message": f"{section_name} 表行数 {rows_count} 与 front-matter.{fm_field}={fm_count} 不一致",
                        "path": path,
                    })
            except (ValueError, TypeError):
                pass
        # 数量上限
        max_n = max_map.get(section_name)
        if max_n and rows_count > max_n:
            issues.append({
                "level": "warning",
                "code": f"{section_name}-too-many",
                "message": f"{section_name} 表 {rows_count} 行超出上限 {max_n}",
                "path": path,
            })
        # 单条字数（启发式：跳过 ID/类型短单元格，超过 desc_max 的告警）
        if desc_max:
            for row in data_rows:
                cells = [c.strip() for c in row.split("|")[1:-1]]
                for cell in cells:
                    cell_chars = len(re.sub(r"\s+", "", cell))
                    if cell_chars > desc_max and not _is_id_or_type(cell):
                        issues.append({
                            "level": "warning",
                            "code": "problem-cell-too-long",
                            "message": f"问题单元格 {cell_chars} 字超出上限 {desc_max} 字：{cell[:30]}...",
                            "path": path,
                        })
                        break  # 同一行只告警一次
    return issues


def _is_id_or_type(cell: str) -> bool:
    """识别"序号/类型"列（不参与字数检查）。"""
    s = cell.strip()
    if not s:
        return True
    # 纯数字 / 单字母 / 短编号（F01, S02, ch5）
    if re.fullmatch(r"\d+", s):
        return True
    if re.fullmatch(r"[A-Z]+", s) and len(s) <= 4:
        return True
    if re.fullmatch(r"(ch|F|S)\d+", s, re.IGNORECASE):
        return True
    # 设定漂移 / 角色矛盾 等类型标签
    type_keywords = ["设定漂移", "角色矛盾", "时间线冲突", "伏笔遗漏", "设定", "角色", "情节", "节奏",
                     "风格", "文学", "叙事", "通过", "问题", "无", "—", "✅", "⚠️", "❌"]
    if any(s == kw or s.startswith(kw) for kw in type_keywords):
        return True
    if len(s) <= 8:
        return True
    return False


def lint_file(stage: str, path: Path) -> list[dict]:
    """单文件 v2 schema lint。

    参数：
        stage: stage key（chapters / editor / consistency / style / ...）或 file_budget key
        path: 目标文件路径

    返回：issue 列表（每项 = {level, code, message, path}）。软 warn 语义：
    - front-matter 缺失/格式错 → error
    - 其余超限 / 字段缺失 / 污染 → warning
    """
    issues: list[dict] = []

    if not path.is_file():
        return [{
            "level": "error",
            "code": "file-not-found",
            "message": f"文件不存在：{path}",
            "path": str(path),
        }]

    budget_key = B.resolve_budget(stage)
    if budget_key is None:
        return [{
            "level": "error",
            "code": "unknown-stage",
            "message": f"未知 stage：{stage}（支持：chapters / editor / consistency / style / ...）",
            "path": str(path),
        }]
    budget = B.FILE_BUDGETS[budget_key]

    text = path.read_text(encoding="utf-8")

    # 1. front-matter 存在性
    fm_text_m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not fm_text_m:
        issues.append({
            "level": "error",
            "code": "frontmatter-missing",
            "message": "缺少 YAML front-matter",
            "path": str(path),
        })
        return issues  # 没 front-matter 后续检查无意义

    fm, body = C.parse_frontmatter(text)

    # 2. 必填字段
    issues.extend(_check_frontmatter_fields(fm, budget.get("frontmatter_required", []), str(path)))

    # 3. 污染检测
    issues.extend(_check_pollution(text, str(path)))

    # 4. 字数预算（review / consistency_report / outline / 其他）
    target = budget.get("total_chars_target")
    tol = budget.get("total_chars_tolerance")
    if target and tol:
        issues.extend(_check_total_chars(text, target, tol, str(path)))

    # 5. 文件类型特定检查
    if budget_key == "chapter":
        issues.extend(_check_chapter_words(fm, body, budget, str(path)))
    elif budget_key in ("review", "consistency_report"):
        issues.extend(_check_review_consistency(fm, body, budget, str(path)))

    return issues

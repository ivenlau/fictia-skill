"""
Fictia v2 schema lint 预算与污染检测定义。

每个 stage 的字数预算、数量上限、必填 front-matter 字段集中在此模块，
作为 lint 的单一信息源。agent prompt 文件描述规则，本模块执行规则。

设计原则：
- 预算 = agent prompt 中"字数预算"表的镜像
- 必填字段 = agent prompt 中 YAML front-matter 块的字段列表
- 污染模式 = 全 stage 共用，禁止 internal token / 元说明泄露
"""

from __future__ import annotations
import re


# ---------- 共用污染检测模式 ----------

POLLUTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bfeedback_\w+\b"),
    re.compile(r"\bproject_\w+\b"),
    re.compile(r"\bnote_\w+\b"),
    re.compile(r"符合\s*ch\d+"),
    re.compile(r"延续\s*ch\d+\s*模式"),
    re.compile(r"ch\d+\s*模式固化"),
    re.compile(r"分工如下"),
    re.compile(r"本节是[^。\n]{0,20}母本"),
]


# ---------- 各文件类型预算 ----------

# 字段说明：
# - frontmatter_required: YAML front-matter 必填字段列表
# - total_chars_target / tolerance: 全文（含 front-matter）字数预算与浮动比
# - body_min_ratio / body_max_ratio: 正文实际字数 / 目标字数（章节专用）
# - writing_notes_max_chars: 写作备注字数上限（章节专用）
# - severe_max / normal_max / detail_max: 问题表行数上限（评审/校验报告专用）
# - problem_desc_max / problem_fix_max: 单条问题描述/修复方案字数上限
# - count_fields: front-matter 中需与表行数一致的计数字段（评审/校验报告专用）

FILE_BUDGETS: dict[str, dict] = {
    "genre_analysis": {
        "frontmatter_required": ["schema_version", "stage", "genre", "tone", "core_drive", "status"],
        "total_chars_target": 830,
        "total_chars_tolerance": 0.20,
    },
    "architecture": {
        "frontmatter_required": ["schema_version", "stage", "title", "target_words", "target_volumes", "target_chapters", "chapter_target_words", "structure_pattern", "act_count", "status"],
        "total_chars_target": 1900,
        "total_chars_tolerance": 0.20,
    },
    "style_guide": {
        "frontmatter_required": ["schema_version", "stage", "tone", "pov", "density", "status"],
        "total_chars_target": 1030,
        "total_chars_tolerance": 0.20,
    },
    "style_samples": {
        "frontmatter_required": ["schema_version", "stage", "project", "tone", "pov", "status"],
        "total_chars_target": 1500,
        "total_chars_tolerance": 0.20,
    },
    "art_design": {
        "frontmatter_required": ["schema_version", "stage", "core_image", "image_count", "emotion_peak_chapter", "status"],
        "total_chars_target": 1180,
        "total_chars_tolerance": 0.20,
    },
    "narrative_weave": {
        "frontmatter_required": ["schema_version", "stage", "foreshadowing_count", "subline_count", "status"],
        "total_chars_target": 1730,
        "total_chars_tolerance": 0.20,
    },
    "world_setting": {
        "frontmatter_required": ["schema_version", "stage", "file_type", "genre", "power_system", "geography_scale", "history_span", "status"],
        "total_chars_target": 1530,
        "total_chars_tolerance": 0.20,
    },
    "world_timeline": {
        "frontmatter_required": ["schema_version", "stage", "file_type", "anchor_event", "status"],
        "total_chars_target": 400,
        "total_chars_tolerance": 0.20,
    },
    "character_heavy": {
        "frontmatter_required": ["schema_version", "stage", "role", "name", "identity", "age", "traits", "language_style", "debut_chapter", "power_level", "arc_summary", "key_relationships", "growth_arc", "status"],
        "total_chars_target": 800,
        "total_chars_tolerance": 0.30,
    },
    "character_light": {
        "frontmatter_required": ["schema_version", "stage", "role", "name", "identity", "language_style", "debut_chapter", "status"],
        "total_chars_target": 300,
        "total_chars_tolerance": 0.30,
    },
    "character_relationships": {
        "frontmatter_required": ["schema_version", "stage", "type", "status"],
        "total_chars_target": 400,
        "total_chars_tolerance": 0.50,
    },
    "outline_act": {
        "frontmatter_required": ["schema_version", "stage", "act", "chapters", "status"],
        "total_chars_target": 800,
        "total_chars_tolerance": 0.30,
    },
    "outline_chapter": {
        "frontmatter_required": ["schema_version", "stage", "chapter", "act", "title", "target_words", "status"],
        "total_chars_target": 600,
        "total_chars_tolerance": 0.30,
    },
    "chapter": {
        "frontmatter_required": [
            "schema_version", "stage", "act", "chapter", "title",
            "target_words", "actual_words",
            "debut_characters",
            "foreshadowings_planted", "foreshadowings_resolved",
            "sublines_advanced", "status",
        ],
        "body_min_ratio": 0.8,
        "body_max_ratio": 1.2,
        "writing_notes_max_chars": 120,
    },
    "review": {
        "frontmatter_required": [
            "schema_version", "stage", "chapter",
            "target_words", "actual_words", "word_judgment",
            "overall_grade",
            "severe_count", "normal_count", "detail_count",
            "status",
        ],
        "total_chars_target": 850,
        "total_chars_tolerance": 0.20,
        "severe_max": 3, "normal_max": 3, "detail_max": 2,
        "problem_desc_max": 50, "problem_fix_max": 50,
        "count_fields": {
            "严重问题": "severe_count",
            "一般问题": "normal_count",
            "细节问题": "detail_count",
        },
    },
    "consistency_report": {
        "frontmatter_required": [
            "schema_version", "stage",
            "check_range", "check_date", "chapters_checked",
            "overall_grade",
            "severe_count", "normal_count", "detail_count",
            "status",
        ],
        "total_chars_target": 1590,
        "total_chars_tolerance": 0.20,
        "severe_max": 3, "normal_max": 5, "detail_max": 5,
        "problem_desc_max": 50, "problem_fix_max": 30,
        "count_fields": {
            "严重问题": "severe_count",
            "一般问题": "normal_count",
            "细节问题": "detail_count",
        },
    },
}


# ---------- stage key → 默认 file budget 映射 ----------

# 调用 fictia lint <stage_key> <file> 时，stage_key → file_budget key 的默认映射
# 用户也可直接传 file_budget key（如 character_heavy）
STAGE_TO_FILE_BUDGET: dict[str, str] = {
    "genre_analysis": "genre_analysis",
    "architecture": "architecture",
    "style": "style_guide",  # 默认；style-samples.md 用 "style_samples"
    "art_design": "art_design",
    "narrative_weave": "narrative_weave",
    "world": "world_setting",
    "characters": "character_heavy",
    "story": "outline_chapter",
    "chapters": "chapter",
    "editor": "review",
    "consistency": "consistency_report",
}


def resolve_budget(stage_or_alias: str) -> str | None:
    """把用户传入的 stage key / alias / file_budget key 解析为 file_budget key。

    返回 None 表示未知。
    """
    if stage_or_alias in FILE_BUDGETS:
        return stage_or_alias
    if stage_or_alias in STAGE_TO_FILE_BUDGET:
        return STAGE_TO_FILE_BUDGET[stage_or_alias]
    return None

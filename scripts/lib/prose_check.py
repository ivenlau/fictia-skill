"""
AI 模式检测：扫描中文散文中的高风险 AI 腔句式，返回 findings 列表。

检测 18 条规则，blocking 6 条 / advisory 12 条。与 JS 版 check-ai-patterns.js 同源；
阈值、正则、处理流水线保持一致。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

STOP_CHARS = frozenset(["。", "！", "？", "!", "?", "\n"])
SOFT_SEPARATORS = frozenset(["，", ",", "、", "；", ";", "：", ":"])
HARD_SEPARATORS = frozenset(["。", ".", "！", "!", "？", "?"])
MAX_NEGATIVE_SPAN = 80
MAX_POSITIVE_SPAN = 80

# 碎句号
STUTTER_MIN_RUN = 6
STUTTER_MAX_SENTENCE = 5

# 长段落
LONG_PARAGRAPH_CHARS = 200

# 微动作复读
MICRO_TIC_PATTERN = re.compile(r"了(?:[一两三几半])?[下阵圈道声眼口气会]")
MICRO_TIC_MIN_HITS = 5
MICRO_TIC_PER_KILO = 6

# 监控摄像头式动作清单
ACTION_LIST_VERB_PATTERN = re.compile(
    r"伸手|抬手|探手|拿起|拿过|取出|取过|掏出|摸出|抓起|攥住|握住|捏住|按住|推开|拉开|打开|关上|放下|递给|挑开|掀开|扯开|拧开|倒出|端起|转身|回头|抬头|低头|弯腰|俯身|走到|走向|坐下|站起|看向|看着|盯着|扫过"
)
ACTION_LIST_MIN_HITS = 5
ACTION_LIST_MIN_SEPARATORS = 4

# 抽象总结复读
ABSTRACT_SUMMARY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"这一刻[，,]?[^\n。！？!?]{0,24}(?:终于|才)(?:明白|意识到)"),
    re.compile(r"从这一刻开始"),
    re.compile(r"(?:命运|宿命)[^\n。！？!?]{0,28}(?:齿轮|棋局|獠牙|改写|推向|安排)"),
    re.compile(r"早已[^\n。！？!?]{0,8}(?:布好|安排好)[^\n。！？!?]{0,8}(?:棋局|局)"),
    re.compile(r"前所未有的(?:决意|清醒|勇气|力量|恐惧|平静|信念)"),
    re.compile(r"(?:反击|复仇|战争|较量|故事|命运)[^\n。！？!?]{0,12}才刚刚开始"),
    re.compile(r"(?:新的开始|全新的开始)"),
]
ABSTRACT_SUMMARY_MIN_HITS = 3
ABSTRACT_SUMMARY_PER_KILO = 4

# 套词密度
CLICHE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"仿佛|犹如|宛若|如同"),
    re.compile(r"一丝|一抹|些许|几分|隐约"),
    re.compile(r"深吸一口气|缓缓|微微|轻轻|淡淡"),
    re.compile(r"眼中闪过|嘴角勾起|眸光微微一闪|指节泛白|目光锐利|眼神锐利"),
    re.compile(r"心中涌起一股|心头一震|心中一动|心下了然|心中暗道|心中一凛"),
    re.compile(r"不容置疑|不容置喙|不易察觉|显而易见|毫无疑问|不可否认"),
    re.compile(r"声音不大[，,]?却带着|语气平静无波|平静无波|声音平直|听不出情绪"),
    re.compile(r"不知何时|唾手可得|无声翻涌|沉默(?:在[^。！？!?\n]{0,16})?蔓延|难以言说"),
    re.compile(r"散发着一股|冰冷的光|格外刺眼|深邃而冰冷"),
]
CLICHE_DENSITY_MIN_HITS = 8
CLICHE_DENSITY_PER_KILO = 12

# 比喻密度
METAPHOR_MARKER_PATTERN = re.compile(
    r"好像|像是|仿佛|宛如|如同|犹如|(?<![不头图画录摄肖])像(?![头像素])"
)
METAPHOR_LIKE_PHRASE_PATTERN = re.compile(
    r"(?:死|水|冰|火|潮水|石头|木头|机器|纸|铁|鬼|死人|刀|针|网|墙)一样"
)
METAPHOR_DENSITY_MIN_HITS = 7
METAPHOR_DENSITY_PER_KILO = 3

# 解释链密度
REASONING_CHAIN_PATTERNS: list[dict] = [
    {
        "key": "mental",
        "core": True,
        "pattern": re.compile(
            r"(?<![不没未无])(?:他|她|我)?(?:知道|明白|意识到|清楚|判断|确认|分析)"
        ),
    },
    {
        "key": "connector",
        "core": True,
        "pattern": re.compile(
            r"这意味着|也就是说|换句话说|真正的问题(?:在于)?|问题在于|关键在于"
            r"|在这种情况下|按照这个逻辑|只有这样|想到这里"
        ),
    },
    {
        "key": "modal",
        "core": True,
        "pattern": re.compile(
            r"(?:(?<!不)(?:必须|需要|应该|只要|就会|可能|可以|能够|无法)|不能)"
            r"[^。！？!?\n]{0,16}"
            r"(?:判断|确认|承担|维持|稳住|控制|扩大|失控|带来|造成|理解|默认"
            r"|回家|进门|核对|筛选|减少|建立|风险|结果|秩序|责任)"
        ),
    },
    {
        "key": "abstract",
        "core": False,
        "pattern": re.compile(
            r"(?:任务|条件|风险|来源|逻辑|局面|结果|责任|秩序|规则|信息不足|决策能力)"
        ),
    },
]
REASONING_CHAIN_MIN_HITS = 8
REASONING_CHAIN_CORE_MIN_HITS = 4
REASONING_CHAIN_MIN_BUCKETS = 2
REASONING_CHAIN_PER_KILO = 18

# 系统公告公文腔
NOTICE_FORMAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"不得|必须|不可|禁止|严禁|应当|须|需|务必"),
    re.compile(r"当前|本公告|本规则|本系统|提示|任务失败|临时权限|权限|状态|等级"),
    re.compile(r"维持|公共区域|秩序|优先|惩罚|处罚|违规|指令|执行"),
    re.compile(r"被视为|同样计入|计入|承担|责任|单位|撤回|转发|截图"),
]
NOTICE_FORMAL_CORE_PATTERN = re.compile(
    r"不得|必须|不可|禁止|严禁|应当|须|需|务必|被视为|同样计入|计入"
)
NOTICE_FORMAL_MIN_LINES = 4
NOTICE_FORMAL_MIN_HITS = 12
NOTICE_FORMAL_CORE_MIN_HITS = 5
NOTICE_FORMAL_PER_KILO = 60

# 过度精炼短段
OVERCOMPRESSED_PROSE_PARTICLE_PATTERN = re.compile(r"[的了就着过呢吧啊呀嘛]")
OVERCOMPRESSED_PROSE_MIN_CHARS = 1200
OVERCOMPRESSED_PROSE_MIN_PARAS = 45
OVERCOMPRESSED_PROSE_SHORT_MAX_CHARS = 15
OVERCOMPRESSED_PROSE_SHORT_RATIO = 0.58
OVERCOMPRESSED_PROSE_PARTICLE_PER_KILO = 85

# 低连接密度
LOW_CONNECTIVE_FUNCTION_TERMS = [
    "的", "了", "就", "在", "是", "也", "都", "还", "又", "把", "被", "给",
    "这个", "那个", "里面", "以后", "时候", "现在", "因为", "所以", "但是",
    "不过", "然后", "已经", "还是", "起来", "出来", "下去",
]
LOW_CONNECTIVE_PLAIN_TERMS = [
    "的", "了", "就", "也", "还", "又", "这个", "那个", "东西", "事情",
    "时候", "里面", "以后", "一下", "一点", "有点", "还是",
]
LOW_CONNECTIVE_MIN_CHARS = 800
LOW_CONNECTIVE_FUNCTION_PER_KILO = 100
LOW_CONNECTIVE_PLAIN_PER_KILO = 65
LOW_CONNECTIVE_LONG_SENTENCE_CHARS = 30
LOW_CONNECTIVE_LONG_SENTENCE_RATIO = 0.08

# not-is / reverse-not-is 前字排除
COMPACT_EITHER_OR_PREV = frozenset(["不", "就", "也"])
TAG_PARTICLES = frozenset(["吗", "吧", "嘛"])
AFFIRMATION_TAG_PARTICLES = frozenset(["的", "啊", "呀", "呢"])
AFFIRMATION_TAG_BOUNDARY = frozenset(
    ["", "，", ",", "。", ".", "！", "!", "？", "?", "、", "；", ";", "：", ":", "\n", "\r", "\t", " "]
)

# 反序对比前字排除
REVERSE_NOT_IS_PREV_EXCLUDE = frozenset(
    list(COMPACT_EITHER_OR_PREV)
    + ["还", "只", "可", "但", "于", "倒", "像", "若", "要", "正", "便",
       "总", "老", "更", "最", "算", "怕", "凡", "或", "即", "自", "竟",
       "原", "本", "仍", "许", "净", "光", "单", "尽"]
)

# 音量反差腔
VOICE_CONTRAST_PATTERN = re.compile(
    r"声音(?:并)?不[大高响亮][^。！？!?\n]{0,16}[却但偏]"
)

# 否定排比
NEGATION_PARADE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:没有[^。！？!?\n，,]{1,12}[，,]){2}"),
    re.compile(
        r"没(?:有)?[^。！？!?\n，,]{1,12}[，,]\s*没(?:有)?[^。！？!?\n，,]{1,16}"
        r"[，,。.][^。！？!?\n，,]{0,6}只(?:是|会|有)"
    ),
]

# 反序对比
REVERSE_NOT_IS_PATTERN = re.compile(
    r"是([^。！？!?\n，,]{1,12})[，,]\s*(?:而)?不是([^。！？!?\n]{1,20})"
)

# 预告式总结收尾
TRAILER_ENDING_PATTERN = re.compile(
    r"没人知道|谁也不知道|谁也没想到|殊不知"
    r"|(?:这)?才刚刚开(?:始|头)"
    r"|正(?:朝着|向着)[^。！？!?\n]{0,24}(?:压|涌|袭|逼)(?:了?过去|了?过来|来)"
    r"|(?<!正式)拉开(?:序幕|帷幕)"
    r"|即将(?:开始|来临|降临)"
)
TRAILER_ENDING_WINDOW_CHARS = 600

# 引号强调滥用
QUOTE_EMPHASIS_MIN_HITS = 3
QUOTE_EMPHASIS_MAX_VISIBLE = 4
QUOTE_EMPHASIS_SPEECH_VERB_PATTERN = re.compile(r"[说道问喊答念叫回吼骂写读唱嘀咕]")

# 成对引号
QUOTE_PAIRS: list[tuple[str, str]] = [
    ("「", "」"), ("『", "』"), ("【", "】"),
    ("“", "”"), ("‘", "’"),  # "" ''
    ('"', '"'), ("'", "'"),
]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _escape_re(text: str) -> str:
    """转义正则特殊字符。"""
    return re.escape(text)


def _escape_char_class(text: str) -> str:
    """转义字符类内的特殊字符。"""
    return re.sub(r"[\\\]^-]", r"\\\g<0>", text)


def _build_quote_sources() -> list[re.Pattern[str]]:
    """构建引号匹配正则列表。"""
    sources: list[re.Pattern[str]] = []
    for open_ch, close_ch in QUOTE_PAIRS:
        pat = (
            _escape_re(open_ch)
            + r"[^" + _escape_char_class(close_ch) + r"]*"
            + _escape_re(close_ch)
        )
        sources.append(re.compile(pat))
    return sources


_QUOTE_SOURCES = _build_quote_sources()


def _is_divider(trimmed: str) -> bool:
    return bool(re.match(r"^-{3,}$", trimmed)) or bool(re.match(r"^[*_]{3,}$", trimmed))


def _is_structural(trimmed: str) -> bool:
    if re.match(r"^(#{1,6}\s|>\s?|[-*+]\s|\d+[.)]\s|\|)", trimmed):
        return True
    if re.match(r"^第[零一二三四五六七八九十百千万\d]+章(?:\s|_|$)", trimmed):
        return True
    return False


def _is_inline_space(ch: str) -> bool:
    return ch in (" ", "\t", "\r")


def _strip_quoted(text: str) -> str:
    """去掉成对引号内的片段，只留引号外叙述。"""
    out = text
    for pat in _QUOTE_SOURCES:
        out = pat.sub("", out)
    return out


def _mask_quoted(text: str) -> str:
    """把成对引号片段替换为等长句号占位，保偏移量。"""

    def _repl(m: re.Match[str]) -> str:
        return "。" * len(m.group(0))

    out = text
    for pat in _QUOTE_SOURCES:
        out = pat.sub(_repl, out)
    return out


def _quoted_ranges(text: str) -> list[tuple[int, int]]:
    """返回引号内片段的 [start, end) 区间列表。"""
    ranges: list[tuple[int, int]] = []
    for pat in _QUOTE_SOURCES:
        for m in pat.finditer(text):
            ranges.append((m.start(), m.end()))
    return ranges


def _inside_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in ranges)


def _split_sentences(trimmed: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?]", trimmed) if s.strip()]


def _visible_length(sentence: str) -> int:
    """可见字数：中文 + 半角字母数字。"""
    return len(re.findall(r"[一-鿿Ａ-ｚA-Za-z0-9]", sentence))


def _count_terms(text: str, terms: list[str]) -> int:
    count = 0
    for term in terms:
        idx = 0
        while True:
            idx = text.find(term, idx)
            if idx == -1:
                break
            count += 1
            idx += len(term)
    return count


def _sentence_around(text: str, index: int) -> str:
    start = index
    while start > 0 and text[start - 1] not in STOP_CHARS:
        start -= 1
    end = index
    while end < len(text) and text[end] not in STOP_CHARS:
        end += 1
    return _compact(text[start:end].strip())


def _compact(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) > 80:
        return normalized[:77] + "..."
    return normalized


def _trim_trailing_noise(text: str) -> str:
    return re.sub(r"[\s|）)】\]]+$", "", text)


def _starts_with_at(text: str, index: int, needle: str) -> bool:
    return text[index:index + len(needle)] == needle


def _is_affirmation_tag_at(text: str, index: int) -> bool:
    """判断 text[index] 是否为「是的/是啊/是呀/呢」确认语。"""
    if text[index] != "是":
        return False
    if index + 1 >= len(text):
        return False
    particle = text[index + 1]
    if particle not in AFFIRMATION_TAG_PARTICLES:
        return False
    boundary = text[index + 2] if index + 2 < len(text) else ""
    return boundary in AFFIRMATION_TAG_BOUNDARY


def _skip_gap(text: str, index: int) -> int:
    """跳过行内空白与换行，停在下一个实义字符。"""
    while index < len(text) and (_is_inline_space(text[index]) or text[index] == "\n"):
        index += 1
    return index


def _parse_fence_marker(trimmed_line: str) -> dict | None:
    m = re.match(r"(?:```+|~~~+)", trimmed_line)
    if not m:
        return None
    return {"char": m.group()[0], "length": len(m.group())}


def _has_yaml_front_matter(lines: list[str]) -> bool:
    if not lines or lines[0].strip() != "---":
        return False
    saw_field = False
    for i in range(1, min(len(lines), 40)):
        trimmed = lines[i].strip()
        if trimmed == "---":
            return saw_field
        if re.match(r"^[A-Za-z0-9_-]+:\s*", trimmed):
            saw_field = True
    return False


def _position_for_offset(line_starts: list[dict], offset: int) -> dict:
    low, high = 0, len(line_starts) - 1
    while low <= high:
        mid = (low + high) // 2
        current = line_starts[mid]
        nxt = line_starts[mid + 1] if mid + 1 < len(line_starts) else None
        if offset < current["offset"]:
            high = mid - 1
        elif nxt and offset >= nxt["offset"]:
            low = mid + 1
        else:
            return {"line": current["lineNo"], "column": offset - current["offset"] + 1}
    return {"line": line_starts[0]["lineNo"], "column": 1}


# ---------------------------------------------------------------------------
# not-is-comparison（跨行 block 级检测）
# ---------------------------------------------------------------------------

def _find_positive_flip_end(candidate: str) -> int:
    """在 '不是' 之后寻找肯定翻转标记，返回偏移量或 -1。"""
    index = 2  # 跳过 '不是'
    scanned = 0
    crossed_separator = False

    while index < len(candidate) and scanned <= MAX_NEGATIVE_SPAN:
        ch = candidate[index]

        if _starts_with_at(candidate, index, "而是"):
            return index + 2

        if ch in SOFT_SEPARATORS:
            nxt = _skip_gap(candidate, index + 1)
            if _starts_with_at(candidate, nxt, "而是"):
                return nxt + 2
            if (
                nxt < len(candidate)
                and candidate[nxt] == "是"
                and (nxt + 1 >= len(candidate) or candidate[nxt + 1] not in TAG_PARTICLES)
                and not _is_affirmation_tag_at(candidate, nxt)
            ):
                return nxt + 1
            crossed_separator = True

        if ch in HARD_SEPARATORS:
            nxt = _skip_gap(candidate, index + 1)
            if (
                nxt < len(candidate)
                and candidate[nxt] == "是"
                and (nxt + 1 >= len(candidate) or candidate[nxt + 1] not in TAG_PARTICLES)
                and not _is_affirmation_tag_at(candidate, nxt)
            ):
                return nxt + 1
            if ch != ".":
                break
            crossed_separator = True

        if ch in STOP_CHARS:
            break

        # Compact forms: 不是A是B (before any separator)
        if (
            ch == "是"
            and index > 0
            and candidate[index - 1] not in COMPACT_EITHER_OR_PREV
            and not crossed_separator
        ):
            return index + 1

        index += 1
        scanned += 1

    return -1


def _extract_finding(candidate: str, marker_end: int) -> str:
    end = marker_end
    limit = min(len(candidate), marker_end + MAX_POSITIVE_SPAN)
    while end < limit:
        if candidate[end] in STOP_CHARS:
            break
        end += 1
    return candidate[:end]


def _find_not_is_comparisons(text: str, get_position) -> list[dict]:
    """扫描 block 级文本中的 not-is 对比句式。"""
    findings: list[dict] = []
    quoted = _quoted_ranges(text)
    offset = 0

    while offset < len(text):
        start = text.find("不是", offset)
        if start == -1:
            break

        # 引号内豁免
        if _inside_ranges(start, quoted):
            offset = start + 2
            continue

        # 排除「是不是」
        if start > 0 and text[start - 1] == "是":
            offset = start + 2
            continue

        candidate = text[start:]
        marker_end = _find_positive_flip_end(candidate)

        if marker_end == -1:
            offset = start + 2
            continue

        raw = _trim_trailing_noise(_extract_finding(candidate, marker_end))
        if len(raw) >= 4:
            pos = get_position(start)
            findings.append({
                "line": pos["line"],
                "column": pos["column"],
                "type": "not-is-comparison",
                "severity": "blocking",
                "message": "高频 AI 对比句式；删掉否定铺垫，直接写后项，或改成动作/细节呈现。",
                "excerpt": _compact(raw),
            })

        offset = start + max(len(raw), 2)

    return findings


# ---------------------------------------------------------------------------
# 逐行检测函数
# ---------------------------------------------------------------------------

def _find_voice_contrast(prose_lines: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for entry in prose_lines:
        text = entry["text"]
        line_no = entry["lineNo"]
        trimmed = text.strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        masked = _mask_quoted(text)
        for m in VOICE_CONTRAST_PATTERN.finditer(masked):
            findings.append({
                "line": line_no,
                "column": m.start() + 1,
                "type": "voice-contrast",
                "severity": "blocking",
                "message": (
                    "音量反差腔：「声音不大/不高…却/但…」是 AI 高频反差模板；"
                    "删掉音量铺垫，直接写声音落进场子的具体效果（谁停了手、哪排安静了）。"
                ),
                "excerpt": _compact(text[m.start():m.start() + len(m.group())]),
            })
    return findings


def _find_negation_parade(prose_lines: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for entry in prose_lines:
        text = entry["text"]
        line_no = entry["lineNo"]
        trimmed = text.strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        masked = _mask_quoted(text)

        spans: list[tuple[int, int]] = []
        for pat in NEGATION_PARADE_PATTERNS:
            for m in pat.finditer(masked):
                spans.append((m.start(), m.end()))
        spans.sort()

        last_end = -1
        for start, end in spans:
            if start < last_end:
                last_end = max(last_end, end)
                continue
            last_end = end
            findings.append({
                "line": line_no,
                "column": start + 1,
                "type": "negation-parade",
                "severity": "blocking",
                "message": (
                    "否定排比：「没有X，没有Y…」/「没X，没有Y，只是Z」是 AI 高频排比模板；"
                    "删掉否定清单，直接写现场实际有什么，最多留一个最有信息量的否定。"
                ),
                "excerpt": _compact(text[start:end]),
            })
    return findings


def _find_reverse_not_is(prose_lines: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for entry in prose_lines:
        text = entry["text"]
        line_no = entry["lineNo"]
        trimmed = text.strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        masked = _mask_quoted(text)
        for m in REVERSE_NOT_IS_PATTERN.finditer(masked):
            start = m.start()
            # 前字合成词排除
            if start > 0 and masked[start - 1] in REVERSE_NOT_IS_PREV_EXCLUDE:
                continue
            # 「是不是…」问句
            if start + 1 < len(masked) and masked[start + 1] == "不":
                continue
            # 「是的，…不是…」确认语
            if _is_affirmation_tag_at(masked, start):
                continue
            # 反问尾巴
            if m.group(2) and re.match(r"^[吗么吧]", m.group(2)):
                continue
            findings.append({
                "line": line_no,
                "column": start + 1,
                "type": "reverse-not-is",
                "severity": "blocking",
                "message": (
                    "反序对比腔：「是A，不是B」与「不是A，是B」同族；"
                    "删掉后置否定，直接写 A 的具体表现，或用细节让读者自己对比。"
                ),
                "excerpt": _compact(text[start:start + len(m.group())]),
            })
    return findings


def _find_trailer_ending(prose_lines: list[dict]) -> list[dict]:
    # 从文末往回收集窗口行
    window_lines: list[dict] = []
    accumulated = 0
    for entry in reversed(prose_lines):
        trimmed = entry["text"].strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        if accumulated >= TRAILER_ENDING_WINDOW_CHARS:
            break
        window_lines.insert(0, entry)
        accumulated += _visible_length(_strip_quoted(trimmed))

    findings: list[dict] = []
    for entry in window_lines:
        text = entry["text"]
        line_no = entry["lineNo"]
        masked = _mask_quoted(text)
        for m in TRAILER_ENDING_PATTERN.finditer(masked):
            findings.append({
                "line": line_no,
                "column": m.start() + 1,
                "type": "trailer-ending",
                "severity": "blocking",
                "message": (
                    "预告式总结收尾：「没人知道/才刚刚开始/正朝着…压了过去」是 AI 章尾预告腔；"
                    "结尾停在具体动作、画面或一句台词上，悬念让事件自己挂住，别替读者预告下一章。"
                ),
                "excerpt": _compact(text[m.start():m.start() + len(m.group())]),
            })
    return findings


def _find_quote_emphasis_tic(prose_lines: list[dict]) -> list[dict]:
    hits = 0
    first_line: int | None = None
    samples: list[str] = []

    for entry in prose_lines:
        text = entry["text"]
        line_no = entry["lineNo"]
        trimmed = text.strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        if _visible_length(_strip_quoted(trimmed)) == 0:
            continue
        ranges = _quoted_ranges(text)

        for start, end in ranges:
            if text[start] == "【":
                continue
            # 引号套引号排除
            if any(s2 <= start and end <= e2 and (s2 != start or e2 != e2)
                   for s2, e2 in ranges if s2 <= start and end <= e2 and (s2, e2) != (start, end)):
                continue
            # More precise nested check
            nested = False
            for s2, e2 in ranges:
                if s2 <= start and end <= e2 and (s2, e2) != (start, end):
                    nested = True
                    break
            if nested:
                continue

            inner = text[start + 1:end - 1]
            visible = _visible_length(inner)
            if visible < 1 or visible > QUOTE_EMPHASIS_MAX_VISIBLE:
                continue
            if re.search(r"[。！？!?…，,；;：:]", inner):
                continue
            before = text[max(0, start - 6):start]
            after = text[end:end + 3]
            if QUOTE_EMPHASIS_SPEECH_VERB_PATTERN.search(before) or QUOTE_EMPHASIS_SPEECH_VERB_PATTERN.search(after):
                continue
            hits += 1
            if first_line is None:
                first_line = line_no
            if len(samples) < 6 and inner not in samples:
                samples.append(inner)

    if hits < QUOTE_EMPHASIS_MIN_HITS:
        return []

    return [{
        "line": first_line or 1,
        "column": 1,
        "type": "quote-emphasis-tic",
        "severity": "advisory",
        "message": (
            f"引号强调滥用：叙述里 1-4 字短词加引号强调 {hits} 处；"
            "只留真正反讽/转述必要的一两处，其余去掉引号直接写，或换成具体动作让读者自己品。"
        ),
        "excerpt": _compact(" ".join(samples)),
    }]


def _find_micro_action_tic(prose_lines: list[dict]) -> list[dict]:
    hits = 0
    narrative_chars = 0
    first_line: int | None = None
    samples: list[str] = []

    for entry in prose_lines:
        trimmed = entry["text"].strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        narrative = _strip_quoted(trimmed)
        narrative_chars += _visible_length(narrative)
        for m in MICRO_TIC_PATTERN.finditer(narrative):
            hits += 1
            if first_line is None:
                first_line = entry["lineNo"]
            if len(samples) < 6 and m.group() not in samples:
                samples.append(m.group())

    if narrative_chars == 0 or hits < MICRO_TIC_MIN_HITS:
        return []
    per_kilo = (hits / narrative_chars) * 1000
    if per_kilo < MICRO_TIC_PER_KILO:
        return []

    return [{
        "line": first_line or 1,
        "column": 1,
        "type": "micro-action-tic",
        "severity": "advisory",
        "message": (
            f"微动作复读：「了下/了一下」式轻量补语 {hits} 处（{per_kilo:.1f}/千字）；"
            "同一反应模板高密度复现是机械指纹，合并动作 beat、换具体细节，"
            "别每个动作都补一个轻反应尾巴。"
        ),
        "excerpt": _compact(" ".join(samples)),
    }]


def _find_action_list_tic(prose_lines: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for entry in prose_lines:
        text = entry["text"]
        line_no = entry["lineNo"]
        trimmed = text.strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        narrative = _strip_quoted(trimmed).strip()
        if not narrative:
            continue

        verbs = [m.group() for m in ACTION_LIST_VERB_PATTERN.finditer(narrative)]
        if len(verbs) < ACTION_LIST_MIN_HITS:
            continue
        separators = len(re.findall(r"[，、；;]", narrative))
        if separators < ACTION_LIST_MIN_SEPARATORS:
            continue

        findings.append({
            "line": line_no,
            "column": 1,
            "type": "action-list-tic",
            "severity": "advisory",
            "message": (
                f"监控摄像头式动作清单：同段连续动作动词 {len(verbs)} 个、分隔符 {separators} 个；"
                "合并琐碎步骤，只保留有情绪/情节功能的动作，"
                "必要时用角色犹豫、误判或环境反馈做缓冲。"
            ),
            "excerpt": _compact(" ".join(verbs[:8])),
        })
    return findings


def _find_cliche_density_tic(prose_lines: list[dict]) -> list[dict]:
    hits = 0
    narrative_chars = 0
    first_line: int | None = None
    samples: list[str] = []

    for entry in prose_lines:
        trimmed = entry["text"].strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        narrative = _strip_quoted(trimmed)
        narrative_chars += _visible_length(narrative)

        for pat in CLICHE_PATTERNS:
            for m in pat.finditer(narrative):
                hits += 1
                if first_line is None:
                    first_line = entry["lineNo"]
                if len(samples) < 8 and m.group() not in samples:
                    samples.append(m.group())

    if narrative_chars == 0 or hits < CLICHE_DENSITY_MIN_HITS:
        return []
    per_kilo = (hits / narrative_chars) * 1000
    if per_kilo < CLICHE_DENSITY_PER_KILO:
        return []

    return [{
        "line": first_line or 1,
        "column": 1,
        "type": "cliche-density-tic",
        "severity": "advisory",
        "message": (
            f"套词密度过高：高危 AI 套词 {hits} 处（{per_kilo:.1f}/千字）；"
            "不要同义词轮换，改成角色当下可见的动作、物件、对话和具体后果。"
        ),
        "excerpt": _compact(" ".join(samples)),
    }]


def _find_metaphor_density_tic(prose_lines: list[dict]) -> list[dict]:
    hits = 0
    narrative_chars = 0
    first_line: int | None = None
    samples: list[str] = []

    for entry in prose_lines:
        trimmed = entry["text"].strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        narrative = _strip_quoted(trimmed)
        narrative_chars += _visible_length(narrative)

        for m in METAPHOR_MARKER_PATTERN.finditer(narrative):
            hits += 1
            if first_line is None:
                first_line = entry["lineNo"]
            sample = _sentence_around(narrative, m.start())
            if len(samples) < 6 and sample and sample not in samples:
                samples.append(sample)

        for m in METAPHOR_LIKE_PHRASE_PATTERN.finditer(narrative):
            prefix = narrative[max(0, m.start() - 8):m.start()]
            if re.search(r"好像|像是|像|仿佛|宛如|如同|犹如", prefix):
                continue
            hits += 1
            if first_line is None:
                first_line = entry["lineNo"]
            sample = _sentence_around(narrative, m.start())
            if len(samples) < 6 and sample and sample not in samples:
                samples.append(sample)

    if narrative_chars == 0 or hits < METAPHOR_DENSITY_MIN_HITS:
        return []
    per_kilo = (hits / narrative_chars) * 1000
    if per_kilo < METAPHOR_DENSITY_PER_KILO:
        return []

    return [{
        "line": first_line or 1,
        "column": 1,
        "type": "metaphor-density-tic",
        "severity": "advisory",
        "message": (
            f"比喻密度过高：像/好像/仿佛/如同等比喻标记 {hits} 处（{per_kilo:.1f}/千字）；"
            "保留最有叙事功能的少数比喻，其余回到具体动作、物件、声音或后果，不要换成新比喻。"
        ),
        "excerpt": _compact(" | ".join(samples)),
    }]


def _find_reasoning_chain_tic(prose_lines: list[dict]) -> list[dict]:
    hits = 0
    core_hits = 0
    narrative_chars = 0
    first_line: int | None = None
    samples: list[str] = []
    buckets: set[str] = set()

    for entry in prose_lines:
        trimmed = entry["text"].strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        narrative = _strip_quoted(trimmed)
        narrative_chars += _visible_length(narrative)

        for item in REASONING_CHAIN_PATTERNS:
            for m in item["pattern"].finditer(narrative):
                hits += 1
                if item["core"]:
                    core_hits += 1
                buckets.add(item["key"])
                if first_line is None:
                    first_line = entry["lineNo"]
                sample = _compact(m.group())
                if len(samples) < 8 and sample not in samples:
                    samples.append(sample)

    if narrative_chars == 0 or hits < REASONING_CHAIN_MIN_HITS:
        return []
    if core_hits < REASONING_CHAIN_CORE_MIN_HITS or len(buckets) < REASONING_CHAIN_MIN_BUCKETS:
        return []
    per_kilo = (hits / narrative_chars) * 1000
    if per_kilo < REASONING_CHAIN_PER_KILO:
        return []

    return [{
        "line": first_line or 1,
        "column": 1,
        "type": "reasoning-chain-tic",
        "severity": "advisory",
        "message": (
            f"解释链密度过高：知道/明白/这意味着/必须/需要等判断链 {hits} 处（{per_kilo:.1f}/千字）；"
            "像逻辑报告时，把判断落到角色当下可见的动作、物件、对话和现场反馈。"
        ),
        "excerpt": _compact(" | ".join(samples)),
    }]


def _find_notice_formality_tic(prose_lines: list[dict]) -> list[dict]:
    hits = 0
    notice_chars = 0
    notice_lines = 0
    core_hits = 0
    first_line: int | None = None
    samples: list[str] = []

    for entry in prose_lines:
        trimmed = entry["text"].strip()
        if not re.match(r"^【[^】]+】$", trimmed):
            continue
        notice_lines += 1
        notice_chars += _visible_length(trimmed)

        for cm in NOTICE_FORMAL_CORE_PATTERN.finditer(trimmed):
            core_hits += 1

        for pat in NOTICE_FORMAL_PATTERNS:
            for m in pat.finditer(trimmed):
                hits += 1
                if first_line is None:
                    first_line = entry["lineNo"]
                sample = _compact(m.group())
                if len(samples) < 8 and sample not in samples:
                    samples.append(sample)

    if (notice_lines < NOTICE_FORMAL_MIN_LINES or notice_chars == 0
            or hits < NOTICE_FORMAL_MIN_HITS or core_hits < NOTICE_FORMAL_CORE_MIN_HITS):
        return []
    per_kilo = (hits / notice_chars) * 1000
    if per_kilo < NOTICE_FORMAL_PER_KILO:
        return []

    return [{
        "line": first_line or 1,
        "column": 1,
        "type": "system-notice-formality-tic",
        "severity": "advisory",
        "message": (
            f"系统公告公文腔过密：方括号规则行中硬规则词 {hits} 处（{per_kilo:.1f}/千字）；"
            "保留为角色看见的屏幕/公告/规则载体，只在载体内部白话化部分硬词，"
            "或补角色当场看懂的具体后果，不改成叙述者解释。"
        ),
        "excerpt": _compact(" | ".join(samples)),
    }]


def _find_overcompressed_prose_tic(prose_lines: list[dict]) -> list[dict]:
    narrative_chars = 0
    narrative_paras = 0
    short_paras = 0
    particles = 0
    first_line: int | None = None
    samples: list[str] = []

    for entry in prose_lines:
        trimmed = entry["text"].strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        if re.match(r"^【[^】]+】$", trimmed):
            continue
        narrative = _strip_quoted(trimmed).strip()
        length = _visible_length(narrative)
        if length == 0:
            continue

        if first_line is None:
            first_line = entry["lineNo"]
        narrative_paras += 1
        narrative_chars += length
        if length <= OVERCOMPRESSED_PROSE_SHORT_MAX_CHARS:
            short_paras += 1
            if len(samples) < 6:
                samples.append(narrative)

        for _ in OVERCOMPRESSED_PROSE_PARTICLE_PATTERN.finditer(narrative):
            particles += 1

    if narrative_chars < OVERCOMPRESSED_PROSE_MIN_CHARS or narrative_paras < OVERCOMPRESSED_PROSE_MIN_PARAS:
        return []
    short_ratio = short_paras / narrative_paras
    if short_ratio < OVERCOMPRESSED_PROSE_SHORT_RATIO:
        return []
    particle_per_kilo = (particles / narrative_chars) * 1000
    if particle_per_kilo >= OVERCOMPRESSED_PROSE_PARTICLE_PER_KILO:
        return []

    return [{
        "line": first_line or 1,
        "column": 1,
        "type": "overcompressed-prose-tic",
        "severity": "advisory",
        "message": (
            f"过度精炼短段：叙述段 {narrative_paras} 个，"
            f"其中 {short_paras} 个≤{OVERCOMPRESSED_PROSE_SHORT_MAX_CHARS}字"
            f"（{short_ratio * 100:.0f}%），自然连接 {particle_per_kilo:.1f}/千字偏少；"
            "先通读判断，确有提纲感再补断裂处和必要结构虚词，有意短镜头可留，别机械注水。"
        ),
        "excerpt": _compact(" | ".join(samples)),
    }]


def _find_low_connective_density_tic(prose_lines: list[dict]) -> list[dict]:
    body_chars = 0
    function_hits = 0
    plain_hits = 0
    first_line: int | None = None
    sentences: list[int] = []
    samples: list[str] = []

    for entry in prose_lines:
        trimmed = entry["text"].strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        narrative = _strip_quoted(trimmed).strip()
        narrative_len = _visible_length(narrative)
        if narrative_len == 0:
            continue

        if first_line is None:
            first_line = entry["lineNo"]
        body_chars += narrative_len
        function_hits += _count_terms(narrative, LOW_CONNECTIVE_FUNCTION_TERMS)
        plain_hits += _count_terms(narrative, LOW_CONNECTIVE_PLAIN_TERMS)

        for sentence in _split_sentences(narrative):
            length = _visible_length(sentence)
            if length == 0:
                continue
            sentences.append(length)
            if length <= 12 and len(samples) < 6:
                samples.append(sentence)

    if body_chars < LOW_CONNECTIVE_MIN_CHARS or not sentences:
        return []
    function_per_kilo = (function_hits / body_chars) * 1000
    if function_per_kilo >= LOW_CONNECTIVE_FUNCTION_PER_KILO:
        return []
    plain_per_kilo = (plain_hits / body_chars) * 1000
    if plain_per_kilo >= LOW_CONNECTIVE_PLAIN_PER_KILO:
        return []
    long_count = sum(1 for s in sentences if s >= LOW_CONNECTIVE_LONG_SENTENCE_CHARS)
    long_ratio = long_count / len(sentences)
    if long_ratio >= LOW_CONNECTIVE_LONG_SENTENCE_RATIO:
        return []

    return [{
        "line": first_line or 1,
        "column": 1,
        "type": "low-connective-density-tic",
        "severity": "advisory",
        "message": (
            f"低连接密度：引号外叙述功能词 {function_per_kilo:.1f}/千字、"
            f"白话连接 {plain_per_kilo:.1f}/千字，"
            f"且≥{LOW_CONNECTIVE_LONG_SENTENCE_CHARS}字承接句仅 {long_ratio * 100:.0f}%；"
            "容易像提纲/电报体。通读后补必要连接和中长句群，别机械注水。"
        ),
        "excerpt": _compact(" | ".join(samples)),
    }]


def _find_abstract_summary_tic(prose_lines: list[dict]) -> list[dict]:
    hits = 0
    narrative_chars = 0
    first_line: int | None = None
    samples: list[str] = []

    for entry in prose_lines:
        trimmed = entry["text"].strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue
        narrative = _strip_quoted(trimmed)
        narrative_chars += _visible_length(narrative)

        for pat in ABSTRACT_SUMMARY_PATTERNS:
            for m in pat.finditer(narrative):
                hits += 1
                if first_line is None:
                    first_line = entry["lineNo"]
                sample = _compact(m.group())
                if len(samples) < 6 and sample not in samples:
                    samples.append(sample)

    if narrative_chars == 0 or hits < ABSTRACT_SUMMARY_MIN_HITS:
        return []
    per_kilo = (hits / narrative_chars) * 1000
    if per_kilo < ABSTRACT_SUMMARY_PER_KILO:
        return []

    return [{
        "line": first_line or 1,
        "column": 1,
        "type": "abstract-summary-tic",
        "severity": "advisory",
        "message": (
            f"抽象总结复读：命运/棋局/这一刻终于明白/才刚刚开始等作者总结 {hits} 处"
            f"（{per_kilo:.1f}/千字）；"
            "回到角色当下可见的文件、动作、对话或物理后果，别替读者盖章。"
        ),
        "excerpt": _compact(" | ".join(samples)),
    }]


def _find_period_stutter(prose_lines: list[dict]) -> list[dict]:
    findings: list[dict] = []
    run_len = 0
    run_start_line: int | None = None
    run_sample: list[str] = []

    def _flush() -> None:
        nonlocal run_len, run_start_line, run_sample
        if run_len >= STUTTER_MIN_RUN:
            findings.append({
                "line": run_start_line or 1,
                "column": 1,
                "type": "period-stutter",
                "severity": "advisory",
                "message": (
                    f"碎句号：连续 {run_len} 个短句无呼吸；"
                    "按目标句长把碎句合并成中长句、补回画面与连接（见本 skill 句长/疏密节奏规则）。"
                ),
                "excerpt": _compact(" ".join(run_sample)),
            })
        run_len = 0
        run_start_line = None
        run_sample = []

    for entry in prose_lines:
        text = entry["text"]
        line_no = entry["lineNo"]
        trimmed = text.strip()
        if not trimmed:
            continue
        if _is_divider(trimmed) or _is_structural(trimmed):
            _flush()
            continue
        narrative = _strip_quoted(trimmed)
        if _visible_length(narrative) == 0:
            _flush()
            continue
        for sentence in _split_sentences(narrative):
            if _visible_length(sentence) <= STUTTER_MAX_SENTENCE:
                if run_len == 0:
                    run_start_line = line_no
                run_len += 1
                if len(run_sample) < 6:
                    run_sample.append(sentence)
            else:
                _flush()

    _flush()
    return findings


# ---------------------------------------------------------------------------
# 段落级 prose 检测（em-dash + long-paragraph + 所有逐行/全文规则）
# ---------------------------------------------------------------------------

def _scan_prose_patterns(prose_lines: list[dict]) -> list[dict]:
    findings: list[dict] = []

    # em-dash + long-paragraph 逐行
    for entry in prose_lines:
        text = entry["text"]
        line_no = entry["lineNo"]
        trimmed = text.strip()
        if not trimmed or _is_divider(trimmed) or _is_structural(trimmed):
            continue

        dash_pattern = re.compile(r"——|—|--+")
        for dash in dash_pattern.finditer(text):
            findings.append({
                "line": line_no,
                "column": dash.start() + 1,
                "type": "em-dash",
                "severity": "blocking",
                "message": (
                    "破折号按功能改写：打断→动作 beat/短句，拖长音→省略或动作，"
                    "插入说明→逗号/冒号；勿一律改句号。"
                ),
                "excerpt": _compact(
                    text[max(0, dash.start() - 8):dash.start() + len(dash.group()) + 8]
                ),
            })

        if len(trimmed) > LONG_PARAGRAPH_CHARS:
            findings.append({
                "line": line_no,
                "column": 1,
                "type": "long-paragraph",
                "severity": "advisory",
                "message": (
                    f"段落过长（{len(trimmed)} 字）："
                    "按镜头/新动作/新线索/视线切换断段，别一段到底。"
                ),
                "excerpt": _compact(trimmed[:40]),
            })

    # 全文/逐行规则
    findings.extend(_find_voice_contrast(prose_lines))
    findings.extend(_find_negation_parade(prose_lines))
    findings.extend(_find_reverse_not_is(prose_lines))
    findings.extend(_find_trailer_ending(prose_lines))
    findings.extend(_find_quote_emphasis_tic(prose_lines))
    findings.extend(_find_period_stutter(prose_lines))
    findings.extend(_find_micro_action_tic(prose_lines))
    findings.extend(_find_action_list_tic(prose_lines))
    findings.extend(_find_abstract_summary_tic(prose_lines))
    findings.extend(_find_cliche_density_tic(prose_lines))
    findings.extend(_find_metaphor_density_tic(prose_lines))
    findings.extend(_find_reasoning_chain_tic(prose_lines))
    findings.extend(_find_notice_formality_tic(prose_lines))
    findings.extend(_find_overcompressed_prose_tic(prose_lines))
    findings.extend(_find_low_connective_density_tic(prose_lines))
    return findings


# ---------------------------------------------------------------------------
# Block 扫描（not-is-comparison 跨行检测）
# ---------------------------------------------------------------------------

def _scan_block(block: list[dict]) -> list[dict]:
    text = "\n".join(entry["text"] for entry in block)
    line_starts: list[dict] = []
    cursor = 0
    for entry in block:
        line_starts.append({"offset": cursor, "lineNo": entry["lineNo"]})
        cursor += len(entry["text"]) + 1

    def get_position(offset: int) -> dict:
        return _position_for_offset(line_starts, offset)

    return _find_not_is_comparisons(text, get_position)


# ---------------------------------------------------------------------------
# 主扫描流水线
# ---------------------------------------------------------------------------

def scan_text(text: str) -> list[dict]:
    """扫描文本，返回所有 findings。"""
    lines = text.split("\r\n") if "\r\n" in text else text.split("\n")
    findings: list[dict] = []
    fence: dict | None = None
    in_front_matter = _has_yaml_front_matter(lines)
    block: list[dict] = []
    prose_lines: list[dict] = []

    def flush_block() -> None:
        nonlocal block
        if block:
            findings.extend(_scan_block(block))
            block = []

    for index, line in enumerate(lines):
        trimmed = line.strip()

        if in_front_matter:
            if index > 0 and trimmed == "---":
                in_front_matter = False
            continue

        fence_marker = _parse_fence_marker(trimmed)
        if fence:
            if (fence_marker and fence_marker["char"] == fence["char"]
                    and fence_marker["length"] >= fence["length"]):
                fence = None
            continue

        if fence_marker:
            flush_block()
            fence = fence_marker
            continue

        block.append({"text": line, "lineNo": index + 1})
        prose_lines.append({"text": line, "lineNo": index + 1})

    flush_block()
    findings.extend(_scan_prose_patterns(prose_lines))
    findings.sort(key=lambda f: (f["line"], f["column"]))
    return findings


def scan_file(path: Path) -> list[dict]:
    """扫描文件，返回所有 findings。"""
    text = path.read_text(encoding="utf-8")
    return scan_text(text)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

USAGE = """\
Usage: python -m scripts.lib.prose_check [--json] [--fail-on=blocking|all] <file...>

Detect high-risk AI-flavor prose patterns that need human rewrite.
See check-ai-patterns.js for full rule documentation."""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect high-risk AI-flavor prose patterns.",
        usage=USAGE,
    )
    parser.add_argument("files", nargs="+", help="Files to scan")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument(
        "--fail-on",
        choices=["blocking", "all"],
        default="all",
        help="Exit 1 on blocking findings only, or all findings (default: all)",
    )
    args = parser.parse_args()

    all_findings: list[dict] = []
    failed = False

    for file_arg in args.files:
        path = Path(file_arg)
        if not path.is_file():
            failed = True
            if not args.json:
                print(f"{file_arg}: unable to read (file not found)", file=sys.stderr)
            continue

        try:
            findings = scan_file(path)
        except Exception as exc:
            failed = True
            if not args.json:
                print(f"{file_arg}: unable to read ({exc})", file=sys.stderr)
            continue

        for f in findings:
            f["file"] = str(path)
        all_findings.extend(findings)

    if args.json:
        json.dump({"findings": all_findings}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for f in all_findings:
            print(
                f"{f['file']}:{f['line']}:{f['column']}: [{f['severity']}] "
                f"{f['type']}: {f['message']} ({f['excerpt']})"
            )

    if failed:
        sys.exit(2)

    has_blocking = any(f["severity"] == "blocking" for f in all_findings)
    if args.fail_on == "blocking":
        should_fail = has_blocking
    else:
        should_fail = len(all_findings) > 0

    if should_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

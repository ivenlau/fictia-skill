"""
极简 YAML 解析器（仅支持 project.yaml 用到的语法子集）。

支持的语法：
- 缩进表示嵌套（空格缩进，2 空格为基本单位）
- 字符串（裸字符串、单引号、双引号）
- 整数、浮点数、布尔（true/false）、null
- 列表（- item）
- 映射（key: value）
- 注释（#）
- 多行字符串（| 保留 / > 折叠；本解析器对 `| value` 形式作简化处理）

不支持：锚点（&/*）、标签（!!str）、流式语法（{a: b}）、引用。
这些都不在 project.yaml 中使用。
"""

from __future__ import annotations
from typing import Any


class YAMLError(ValueError):
    pass


def _parse_scalar(text: str) -> Any:
    """把字符串 token 解析为 Python 值。"""
    s = text.strip()
    if s == "" or s.lower() in ("null", "~"):
        return None
    if s == "{}":
        return {}
    if s == "[]":
        return []
    if s.startswith("[") and s.endswith("]"):
        return _parse_inline_list(s)
    if s.startswith("{") and s.endswith("}"):
        return _parse_inline_dict(s)
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    # 去掉引号
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        inner = s[1:-1]
        # 仅当字符串包含反斜杠转义时才做 unicode_escape 处理
        if "\\" in inner:
            return inner.encode("utf-8").decode("unicode_escape")
        return inner
    # 数字
    try:
        if "." in s or "e" in s or "E" in s:
            return float(s)
        return int(s)
    except ValueError:
        pass
    return s


def _parse_inline_list(s: str) -> list:
    """解析 inline list：[a, b, "c d", 1]"""
    inner = s[1:-1].strip()
    if not inner:
        return []
    items = _split_top_level_commas(inner)
    return [_parse_scalar(item.strip()) for item in items]


def _parse_inline_dict(s: str) -> dict:
    """解析 inline dict：{a: 1, b: "c d"}"""
    inner = s[1:-1].strip()
    if not inner:
        return {}
    result = {}
    for item in _split_top_level_commas(inner):
        if ":" not in item:
            continue
        k, _, v = item.partition(":")
        result[k.strip()] = _parse_scalar(v.strip())
    return result


def _split_top_level_commas(s: str) -> list[str]:
    """按顶层逗号切分（忽略引号内和方括号内的逗号）。"""
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    bracket = 0
    brace = 0
    for ch in s:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "[" and not in_single and not in_double:
            bracket += 1
        elif ch == "]" and not in_single and not in_double:
            bracket -= 1
        elif ch == "{" and not in_single and not in_double:
            brace += 1
        elif ch == "}" and not in_single and not in_double:
            brace -= 1
        elif ch == "," and not in_single and not in_double and bracket == 0 and brace == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _strip_comment(line: str) -> str:
    """去掉行末注释（不在引号内的 #）。"""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i].rstrip()
    return line.rstrip()


class _Parser:
    def __init__(self, text: str):
        # 保留原始行用于错误信息
        self.raw_lines = text.splitlines()
        # 预处理：去注释、跳过空行/纯注释
        self.lines: list[tuple[int, int, str]] = []
        for i, raw in enumerate(self.raw_lines):
            stripped_comment = _strip_comment(raw)
            if not stripped_comment.strip():
                continue
            indent = len(stripped_comment) - len(stripped_comment.lstrip(" "))
            content = stripped_comment[indent:]
            self.lines.append((i + 1, indent, content))
        self.pos = 0

    def _peek(self) -> tuple[int, int, str] | None:
        if self.pos >= len(self.lines):
            return None
        return self.lines[self.pos]

    def _advance(self) -> tuple[int, int, str]:
        item = self.lines[self.pos]
        self.pos += 1
        return item

    def parse(self) -> Any:
        result = self._parse_block(0)
        return result

    def _parse_block(self, parent_indent: int) -> Any:
        """在指定缩进层级解析一个块（dict 或 list）。"""
        first = self._peek()
        if first is None:
            return None
        line_no, indent, content = first
        if indent < parent_indent:
            return None
        if content.startswith("- "):
            return self._parse_list(indent)
        return self._parse_dict(indent)

    def _parse_dict(self, indent: int) -> dict:
        result: dict[str, Any] = {}
        while True:
            cur = self._peek()
            if cur is None:
                break
            line_no, ind, content = cur
            if ind < indent:
                break
            if ind > indent:
                # 缩进跳级，忽略
                self._advance()
                continue
            if content.startswith("- "):
                break
            if ":" not in content:
                # 不是合法键，跳过
                self._advance()
                continue
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            self._advance()
            if value == "":
                # 嵌套结构
                nxt = self._peek()
                if nxt is None:
                    result[key] = None
                else:
                    nxt_line, nxt_indent, nxt_content = nxt
                    if nxt_indent <= indent:
                        result[key] = None
                    else:
                        result[key] = self._parse_block(nxt_indent)
            else:
                result[key] = _parse_scalar(value)
        return result

    def _parse_list(self, indent: int) -> list:
        result: list[Any] = []
        while True:
            cur = self._peek()
            if cur is None:
                break
            line_no, ind, content = cur
            if ind < indent:
                break
            if ind > indent:
                self._advance()
                continue
            if not content.startswith("- "):
                break
            rest = content[2:].strip()
            self._advance()
            if rest == "":
                nxt = self._peek()
                if nxt is None or nxt[1] <= indent:
                    result.append(None)
                else:
                    result.append(self._parse_block(nxt[1]))
            elif ":" in rest and not (rest.startswith('"') or rest.startswith("'")):
                # 列表项是 inline dict：- key: value
                # 把该项视作一个 dict，从当前缩进 + 2 开始
                inline_indent = indent + 2
                # 先把当前行作为 dict 的首项
                first_dict: dict[str, Any] = {}
                key, _, value = rest.partition(":")
                first_dict[key.strip()] = _parse_scalar(value.strip()) if value.strip() else None
                result.append(first_dict)
                # 继续读后续同级（inline_indent）缩进的键作为这个 dict 的字段
                while True:
                    nxt = self._peek()
                    if nxt is None:
                        break
                    nl, ni, nc = nxt
                    if ni < inline_indent:
                        break
                    if ni > inline_indent:
                        self._advance()
                        continue
                    if nc.startswith("- ") or ":" not in nc:
                        break
                    k2, _, v2 = nc.partition(":")
                    self._advance()
                    v2 = v2.strip()
                    if v2 == "":
                        nn = self._peek()
                        if nn is None or nn[1] <= ni:
                            first_dict[k2.strip()] = None
                        else:
                            first_dict[k2.strip()] = self._parse_block(nn[1])
                    else:
                        first_dict[k2.strip()] = _parse_scalar(v2)
            else:
                result.append(_parse_scalar(rest))
        return result


def load(text: str) -> Any:
    """从字符串加载 YAML。"""
    if not text.strip():
        return None
    parser = _Parser(text)
    return parser.parse()


def dump(data: Any, indent: int = 0) -> str:
    """把 Python 对象序列化为 YAML（最小子集）。

    支持：dict、list、str、int、float、bool、None。
    """
    lines: list[str] = []
    pad = " " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{pad}{k}: {{}}")
                else:
                    lines.append(f"{pad}{k}:")
                    lines.append(dump(v, indent + 2))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{pad}{k}: []")
                else:
                    lines.append(f"{pad}{k}:")
                    lines.append(dump(v, indent + 2))
            elif v is None:
                lines.append(f"{pad}{k}: null")
            elif isinstance(v, bool):
                lines.append(f"{pad}{k}: {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{pad}{k}: {v}")
            else:
                s = str(v)
                if any(c in s for c in [":", "#", '"', "'", "\n", "-"]) or s.strip() != s:
                    s_escaped = s.replace("\\", "\\\\").replace('"', '\\"')
                    lines.append(f'{pad}{k}: "{s_escaped}"')
                else:
                    lines.append(f"{pad}{k}: {s}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                # 第一个 key 写为 "- key: value"，其余 key 续行
                items = list(item.items())
                if not items:
                    lines.append(f"{pad}- {{}}")
                    continue
                first_k, first_v = items[0]
                if isinstance(first_v, (dict, list)) and first_v:
                    lines.append(f"{pad}- {first_k}:")
                    lines.append(dump(first_v, indent + 4))
                elif first_v is None:
                    lines.append(f"{pad}- {first_k}: null")
                elif isinstance(first_v, bool):
                    lines.append(f"{pad}- {first_k}: {'true' if first_v else 'false'}")
                elif isinstance(first_v, (int, float)):
                    lines.append(f"{pad}- {first_k}: {first_v}")
                else:
                    s = str(first_v)
                    if any(c in s for c in [":", "#", '"', "'", "\n", "-"]) or s.strip() != s:
                        s_escaped = s.replace("\\", "\\\\").replace('"', '\\"')
                        lines.append(f'{pad}- {first_k}: "{s_escaped}"')
                    else:
                        lines.append(f"{pad}- {first_k}: {s}")
                for k2, v2 in items[1:]:
                    sub_pad = " " * (indent + 2)
                    if isinstance(v2, (dict, list)) and v2:
                        lines.append(f"{sub_pad}{k2}:")
                        lines.append(dump(v2, indent + 4))
                    elif v2 is None:
                        lines.append(f"{sub_pad}{k2}: null")
                    elif isinstance(v2, bool):
                        lines.append(f"{sub_pad}{k2}: {'true' if v2 else 'false'}")
                    elif isinstance(v2, (int, float)):
                        lines.append(f"{sub_pad}{k2}: {v2}")
                    else:
                        s = str(v2)
                        if any(c in s for c in [":", "#", '"', "'", "\n", "-"]) or s.strip() != s:
                            s_escaped = s.replace("\\", "\\\\").replace('"', '\\"')
                            lines.append(f'{sub_pad}{k2}: "{s_escaped}"')
                        else:
                            lines.append(f"{sub_pad}{k2}: {s}")
            elif isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}-")
                lines.append(dump(item, indent + 2))
            elif item is None:
                lines.append(f"{pad}- null")
            elif isinstance(item, bool):
                lines.append(f"{pad}- {'true' if item else 'false'}")
            elif isinstance(item, (int, float)):
                lines.append(f"{pad}- {item}")
            else:
                s = str(item)
                if any(c in s for c in [":", "#", '"', "'", "\n"]) or s.strip() != s:
                    s_escaped = s.replace("\\", "\\\\").replace('"', '\\"')
                    lines.append(f'{pad}- "{s_escaped}"')
                else:
                    lines.append(f"{pad}- {s}")
    return "\n".join(lines)

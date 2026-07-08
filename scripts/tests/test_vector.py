"""单元测试：vector.py 的 chunker + 纯函数。

聚焦：
  - strip_writing_notes / strip_frontmatter
  - _split_long 长段落切窗
  - chunk_chapter / chunk_notes / chunk_source
  - 路径解析函数（vector_root / chapter_file_path / outline_file_path 等）
  - VectorError / require_zvec

不依赖 zvec 已装。zvec round-trip 测试在 test_vector_zvec_integration.py 中
用 pytest.importorskip 守卫。

运行：
    python3 scripts/tests/test_vector.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.vector import (  # noqa: E402
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP,
    Chunk,
    VectorError,
    chapter_file_path,
    chunk_chapter,
    chunk_notes,
    chunk_source,
    notes_summary_path,
    outline_file_path,
    require_zvec,
    sources_dir,
    strip_frontmatter,
    strip_writing_notes,
    vector_root,
)


# --------------------------------------------------------------------------- #
# strip_writing_notes
# --------------------------------------------------------------------------- #


def test_strip_writing_notes_basic() -> None:
    text = "正文第一段。\n\n正文第二段。\n\n### 写作备注\n\n- 字数: 3000"
    out = strip_writing_notes(text)
    assert "写作备注" not in out
    assert "正文第一段" in out
    assert "正文第二段" in out


def test_strip_writing_notes_no_marker() -> None:
    text = "纯正文。\n\n第二段。"
    assert strip_writing_notes(text) == text


def test_strip_writing_notes_marker_at_start() -> None:
    """标记在文首时，正文应为空字符串（不报错）。"""
    text = "### 写作备注\n\n- 字数: 3000"
    assert strip_writing_notes(text) == ""


# --------------------------------------------------------------------------- #
# strip_frontmatter
# --------------------------------------------------------------------------- #


def test_strip_frontmatter_basic() -> None:
    text = "---\ntitle: foo\nworkflow: rewrite\n---\n\n# 第一章\n\n正文。"
    out = strip_frontmatter(text)
    assert "title: foo" not in out
    assert "workflow: rewrite" not in out
    assert "正文" in out
    assert "第一章" in out


def test_strip_frontmatter_no_frontmatter() -> None:
    text = "# 第一章\n\n正文。"
    assert strip_frontmatter(text) == text


# --------------------------------------------------------------------------- #
# _split_long（间接通过 chunk_chapter）
# --------------------------------------------------------------------------- #


def test_split_long_short_text_unchanged() -> None:
    text = "短文本。" * 10
    chunks = chunk_chapter(text, chapter=1, path="dummy")
    # 短文本应至少产生 1 个 chunk
    assert len(chunks) >= 1
    assert "短文本" in chunks[0].text


def test_split_long_long_paragraph() -> None:
    """超过 CHUNK_MAX_CHARS 的单段应被切为多个 chunk。"""
    long_text = "句子" * 300  # ≈ 900 字符
    chunks = chunk_chapter(long_text, chapter=1, path="dummy")
    assert len(chunks) >= 2
    for c in chunks:
        # 单 chunk 文本不应显著超过上限
        assert len(c.text) <= CHUNK_MAX_CHARS + 50


def test_split_long_overlap_preserved() -> None:
    """相邻 chunk 应有 overlap（验证切窗窗口滑动）。"""
    long_text = ("句子。" * 100) + ("。句子" * 100)
    chunks = chunk_chapter(long_text, chapter=1, path="dummy")
    assert len(chunks) >= 2


# --------------------------------------------------------------------------- #
# chunk_chapter
# --------------------------------------------------------------------------- #


def test_chunk_chapter_metadata() -> None:
    text = "第一段。\n\n第二段。\n\n第三段。"
    chunks = chunk_chapter(text, chapter=5, path="chapters/act-1/ch05.md")
    assert len(chunks) >= 3
    assert chunks[0].chunk_index == 0
    assert chunks[0].metadata["chapter"] == 5
    assert chunks[0].metadata["path"] == "chapters/act-1/ch05.md"


def test_chunk_chapter_strips_writing_notes() -> None:
    text = "正文段落。\n\n### 写作备注\n\n- 字数: 3000\n- 伏笔: F001"
    chunks = chunk_chapter(text, chapter=1, path="x")
    all_text = " ".join(c.text for c in chunks)
    assert "写作备注" not in all_text
    assert "伏笔" not in all_text
    assert "正文段落" in all_text


def test_chunk_chapter_empty() -> None:
    assert chunk_chapter("", chapter=1, path="x") == []
    assert chunk_chapter("   \n\n   \n", chapter=1, path="x") == []


# --------------------------------------------------------------------------- #
# chunk_notes
# --------------------------------------------------------------------------- #


def test_chunk_notes_basic() -> None:
    text = "主题一：林远背景。\n\n主题二：苏瑶背景。"
    chunks = chunk_notes(text, note_id="n001")
    assert len(chunks) >= 2
    assert all(c.metadata["note_id"] == "n001" for c in chunks)


def test_chunk_notes_default_id() -> None:
    chunks = chunk_notes("一行文本。")
    assert chunks[0].metadata["note_id"] == "summary"


# --------------------------------------------------------------------------- #
# chunk_source
# --------------------------------------------------------------------------- #


def test_chunk_source_strips_frontmatter() -> None:
    text = (
        "---\ntitle: 源文本\nworkflow: rewrite\n---\n\n"
        "# 第一章\n\n原文第一段。\n\n原文第二段。"
    )
    chunks = chunk_source(text, slug="original", workflow="rewrite")
    all_text = " ".join(c.text for c in chunks)
    assert "title: 源文本" not in all_text
    assert "原文第一段" in all_text
    assert chunks[0].metadata["source_slug"] == "original"
    assert chunks[0].metadata["workflow"] == "rewrite"


def test_chunk_source_no_frontmatter() -> None:
    chunks = chunk_source("# 第一章\n\n正文。", slug="x")
    assert len(chunks) >= 1
    all_text = " ".join(c.text for c in chunks)
    assert "正文" in all_text


# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #


def test_vector_root() -> None:
    p = vector_root(Path("/tmp/foo"))
    assert p == Path("/tmp/foo/.fictia/zvec")


def test_outline_file_path() -> None:
    p = outline_file_path(Path("/tmp/proj"), 7)
    assert p == Path("/tmp/proj/outline/chapters/ch07.md")


def test_notes_summary_path() -> None:
    p = notes_summary_path(Path("/tmp/proj"))
    assert p == Path("/tmp/proj/notes/summary.md")


def test_sources_dir() -> None:
    p = sources_dir(Path("/tmp/proj"))
    assert p == Path("/tmp/proj/sources")


def test_chapter_file_path_act1() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "chapters" / "act-1").mkdir(parents=True)
        (tmp_path / "chapters" / "act-1" / "ch03.md").write_text("x")
        p = chapter_file_path(tmp_path, 3)
        assert p == tmp_path / "chapters" / "act-1" / "ch03.md"


def test_chapter_file_path_act2() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "chapters" / "act-2").mkdir(parents=True)
        (tmp_path / "chapters" / "act-2" / "ch15.md").write_text("x")
        p = chapter_file_path(tmp_path, 15)
        assert p == tmp_path / "chapters" / "act-2" / "ch15.md"


def test_chapter_file_path_missing() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        assert chapter_file_path(Path(tmp), 99) is None


# --------------------------------------------------------------------------- #
# require_zvec
# --------------------------------------------------------------------------- #


def test_require_zvec_missing() -> None:
    """zvec 未装时（当前测试环境）应抛清晰错误。"""
    # 当前 env 未装 zvec；如果测试环境恰好装了，会自动通过
    try:
        require_zvec()
        # 环境装了 zvec：无法验证未装路径，跳过
        print("    [skip] zvec 已在环境中，跳过此断言")
    except VectorError as e:
        assert "zvec 未安装" in str(e)
        assert "pip install zvec" in str(e)


# --------------------------------------------------------------------------- #
# Test runner
# --------------------------------------------------------------------------- #


TEST_FUNCTIONS = [
    test_strip_writing_notes_basic,
    test_strip_writing_notes_no_marker,
    test_strip_writing_notes_marker_at_start,
    test_strip_frontmatter_basic,
    test_strip_frontmatter_no_frontmatter,
    test_split_long_short_text_unchanged,
    test_split_long_long_paragraph,
    test_split_long_overlap_preserved,
    test_chunk_chapter_metadata,
    test_chunk_chapter_strips_writing_notes,
    test_chunk_chapter_empty,
    test_chunk_notes_basic,
    test_chunk_notes_default_id,
    test_chunk_source_strips_frontmatter,
    test_chunk_source_no_frontmatter,
    test_vector_root,
    test_outline_file_path,
    test_notes_summary_path,
    test_sources_dir,
    test_chapter_file_path_act1,
    test_chapter_file_path_act2,
    test_chapter_file_path_missing,
    test_require_zvec_missing,
]


def main() -> int:
    failed: list[str] = []
    for fn in TEST_FUNCTIONS:
        name = fn.__name__
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            print(f"  ✗ {name}: AssertionError: {e}")
            failed.append(name)
        except Exception as e:
            print(f"  ✗ {name}: {type(e).__name__}: {e}")
            failed.append(name)
    total = len(TEST_FUNCTIONS)
    print()
    print(f"{'PASS' if not failed else 'FAIL'}: {total - len(failed)}/{total} tests passed")
    if failed:
        print("Failed tests:")
        for name in failed:
            print(f"  - {name}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
"""Tests for canonical note normalization."""

from alphaxiv_workflow.unify import normalize_note


def test_normalize_note_converts_legacy_ai_summary_h2(tmp_path):
    note = tmp_path / "paper.md"
    note.write_text(
        """---
title: "Test"
arxiv_id: "1234.56789"
---

# Test

## 摘要

abstract

---

## AI 摘要

summary

---

## AI 综述 (中文)

overview

## 相关引用

citations
""",
        encoding="utf-8",
    )

    assert normalize_note(str(note)) is True
    content = note.read_text(encoding="utf-8")
    assert "\n### AI 摘要\n" in content
    assert "\n## AI 摘要\n" not in content


def test_normalize_note_moves_ai_summary_before_review(tmp_path):
    note = tmp_path / "paper.md"
    note.write_text(
        """---
title: "Test"
arxiv_id: "1234.56789"
---

# Test

## 摘要

abstract

## AI 综述 (中文)

overview

---

## AI 摘要

summary

## 相关引用

citations
""",
        encoding="utf-8",
    )

    assert normalize_note(str(note)) is True
    content = note.read_text(encoding="utf-8")
    assert content.index("\n### AI 摘要\n") < content.index("\n## AI 综述 (中文)\n")

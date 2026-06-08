"""
Tests for backfill_overviews.py — scan_pending, update_note, get_overview_with_retry.
"""
import os
import sys
import re
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from backfill_overviews import scan_pending, update_note, get_overview_with_retry


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

PENDING_NOTE = """---
title: "Attention Is All You Need"
arxiv_id: "1706.03762"
version: "v7"
tags: [paper, transformer, attention]
blog_status: pending
authors:
  - Vaswani et al.
---

# Attention Is All You Need

## 摘要

abstract content

---

## AI 摘要

summary content

---

## AI 综述 (中文)

*AI 综述正在生成中（blog_status: pending）...*

---

## 相关引用

*暂无相关引用*

---

*Fetched from AlphaXiv*
"""


def write_note(path: str, content: str = PENDING_NOTE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


# ──────────────────────────────────────────────────────────────────
# scan_pending
# ──────────────────────────────────────────────────────────────────

class TestScanPending:
    def test_finds_pending_paper(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'))
        monkeypatch.setattr('backfill_overviews.PAPERS_DIR', refs)
        results = scan_pending()
        assert len(results) == 1
        assert results[0]['arxiv_id'] == '1706.03762'
        assert 'Attention Is All You Need' in results[0]['title']

    def test_skips_non_pending(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        content = PENDING_NOTE.replace('blog_status: pending', 'blog_status: done')
        write_note(os.path.join(refs, 'paper1.md'), content)
        monkeypatch.setattr('backfill_overviews.PAPERS_DIR', refs)
        results = scan_pending()
        assert len(results) == 0

    def test_handles_missing_dir(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), 'nonexistent')
        monkeypatch.setattr('backfill_overviews.PAPERS_DIR', refs)
        results = scan_pending()
        assert results == []

    def test_skips_non_markdown(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'))
        write_note(os.path.join(refs, 'notes.txt'),
                   'blog_status: pending\narxiv_id: "1234.56789"')
        monkeypatch.setattr('backfill_overviews.PAPERS_DIR', refs)
        results = scan_pending()
        assert len(results) == 1

    def test_handles_unquoted_title(self, tmp_path, monkeypatch):
        """yaml.safe_load handles unquoted titles — regex-based parsing would fail."""
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        content = """---
title: Simple Title Without Quotes
arxiv_id: "2301.12345"
tags: [paper]
blog_status: pending
---

# Simple Title Without Quotes

## 摘要
abstract

## AI 摘要
summary

## AI 综述 (中文)
pending

## 相关引用
citations
"""
        write_note(os.path.join(refs, 'paper1.md'), content)
        monkeypatch.setattr('backfill_overviews.PAPERS_DIR', refs)
        results = scan_pending()
        assert len(results) == 1
        assert results[0]['title'] == 'Simple Title Without Quotes'

    def test_handles_unquoted_arxiv_id(self, tmp_path, monkeypatch):
        """yaml.safe_load handles numeric-looking arxiv_id without quotes."""
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        content = """---
title: "Test Paper"
arxiv_id: 2301.12345
tags: [paper]
blog_status: pending
---

# Test Paper

## 摘要
abstract

## AI 摘要
summary

## AI 综述 (中文)
pending

## 相关引用
citations
"""
        write_note(os.path.join(refs, 'paper1.md'), content)
        monkeypatch.setattr('backfill_overviews.PAPERS_DIR', refs)
        results = scan_pending()
        assert len(results) == 1
        # YAML parses 2301.12345 as float — str conversion needed for arxiv_id
        assert str(results[0]['arxiv_id']) == '2301.12345'

    def test_skips_invalid_yaml(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        content = """---
\tbad: : yaml
blog_status: pending
---

# Test
"""
        write_note(os.path.join(refs, 'paper1.md'), content)
        monkeypatch.setattr('backfill_overviews.PAPERS_DIR', refs)
        results = scan_pending()
        assert len(results) == 0

    def test_handles_multiple_pending(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'))
        content2 = PENDING_NOTE.replace('1706.03762', '2301.12345').replace(
            'Attention Is All You Need', 'Another Paper')
        write_note(os.path.join(refs, 'paper2.md'), content2)
        monkeypatch.setattr('backfill_overviews.PAPERS_DIR', refs)
        results = scan_pending()
        assert len(results) == 2
        ids = {r['arxiv_id'] for r in results}
        assert ids == {'1706.03762', '2301.12345'}


# ──────────────────────────────────────────────────────────────────
# update_note
# ──────────────────────────────────────────────────────────────────

ZH_OVERVIEW = """这是Transformer架构的论文，提出了全新的注意力机制。

## 相关引用

1. Bahdanau et al. Neural Machine Translation
2. Kim et al. Character-Aware Neural Language Models"""

EN_OVERVIEW = """This paper introduces the Transformer architecture with self-attention.

## References

1. Bahdanau et al. Neural Machine Translation"""


class TestUpdateNote:
    def test_replaces_ai_section_with_zh(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        update_note(fpath, ZH_OVERVIEW, 'zh')

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '## AI 综述 (中文)' in content
        assert '> *由 AlphaXiv 生成*' in content
        assert '提出了全新的注意力机制' in content
        assert 'blog_status: pending' not in content

    def test_replaces_ai_section_with_en(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        update_note(fpath, EN_OVERVIEW, 'en')

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '## AI 综述 (English)' in content
        assert '> *Generated by AlphaXiv*' in content
        assert 'self-attention' in content

    def test_removes_blog_status(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        update_note(fpath, ZH_OVERVIEW, 'zh')

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'blog_status: pending' not in content

    def test_extracts_citations_from_overview(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        update_note(fpath, ZH_OVERVIEW, 'zh')

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '## 相关引用' in content
        assert 'Bahdanau et al.' in content

    def test_handles_overview_without_citations(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        update_note(fpath, 'Just a simple overview without references.', 'zh')

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        # Old placeholder is removed; no new citation section added
        assert '暂无相关引用' not in content

    def test_overview_boundary_stops_at_next_h2(self, tmp_path):
        """Verify that AI section replacement stops at the next H2 heading,
        not consuming content beyond."""
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        update_note(fpath, ZH_OVERVIEW, 'zh')

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        # The ## 摘要 section before AI should still exist
        assert '## 摘要' in content
        assert 'abstract content' in content
        # The ## AI 摘要 section should still exist
        assert '## AI 摘要' in content

    def test_no_footer_boundary_safe(self, tmp_path):
        """When note has no ---\\n*Fetched footer, replacement still works safely."""
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
title: "Test"
arxiv_id: "1234.56789"
tags: [paper]
blog_status: pending
---

# Test

## 摘要
abstract

## AI 摘要
summary

## AI 综述 (中文)
pending overview...

## 相关引用
citations
"""
        write_note(fpath, content)
        update_note(fpath, ZH_OVERVIEW, 'zh')

        with open(fpath, 'r', encoding='utf-8') as f:
            result = f.read()
        assert '提出了全新的注意力机制' in result
        assert '## 相关引用' in result
        # The citations from overview are inserted, existing ones remain
        assert 'Bahdanau et al.' in result


# ──────────────────────────────────────────────────────────────────
# get_overview_with_retry
# ──────────────────────────────────────────────────────────────────

class TestGetOverviewWithRetry:
    def test_returns_on_first_success(self):
        mock = MagicMock(return_value=MagicMock())
        with patch('backfill_overviews.get_overview', mock):
            result = get_overview_with_retry('v1', 'zh')
            assert result is not None
            assert mock.call_count == 1

    def test_retries_on_failure(self):
        mock = MagicMock(side_effect=[Exception('timeout'), Exception('timeout'), MagicMock()])
        with patch('backfill_overviews.get_overview', mock):
            result = get_overview_with_retry('v1', 'zh', max_retries=3)
            assert result is not None
            assert mock.call_count == 3

    def test_returns_none_after_max_retries(self):
        mock = MagicMock(side_effect=Exception('timeout'))
        with patch('backfill_overviews.get_overview', mock):
            result = get_overview_with_retry('v1', 'zh', max_retries=3)
            assert result is None
            assert mock.call_count == 3

    def test_retries_with_default_count(self):
        """Default max_retries=3: 3 attempts, then None."""
        mock = MagicMock(side_effect=Exception('error'))
        with patch('backfill_overviews.get_overview', mock):
            result = get_overview_with_retry('v1', 'en')
            assert result is None
            assert mock.call_count == 3

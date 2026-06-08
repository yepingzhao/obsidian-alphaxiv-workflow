"""
Tests for literature_analyzer.py — vault scanning, topic/author search,
paper summary extraction, and synthesis note building.
"""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from literature_analyzer import (
    _scan_vault_papers,
    find_notes_by_topic,
    find_notes_by_author,
    extract_paper_summary,
    build_synthesis_note,
)


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

FULL_NOTE = """---
title: "Attention Is All You Need"
arxiv_id: "1706.03762"
version: "v7"
tags: [paper, alphaxiv, nlp, transformer, attention]
authors:
  - Vaswani, Ashish
  - Shazeer, Noam
published_venue: "NeurIPS 2017"
ccf: "A"
published_date: 2017-12-01
---

# Attention Is All You Need

## 摘要

The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...

## AI 摘要

### 要点
- Self-attention replaces recurrence for sequence modeling
- Achieves state-of-the-art on WMT 2014 translation tasks

### 问题背景
Sequence models were dominated by RNNs and CNNs with attention mechanisms.

---

## AI 综述 (中文)

Transformer 提出了全新的自注意力机制，摒弃了传统的循环和卷积结构，
在机器翻译任务上取得了显著的性能提升。

---

## 相关引用

1. **Related Paper**
   - [AlphaXiv](https://alphaxiv.org/paper/1234)

---

*Fetched from AlphaXiv*
"""

PENDING_NOTE = """---
title: "New Paper"
arxiv_id: "2301.12345"
tags: [paper, alphaxiv, nlp]
blog_status: pending
authors:
  - Smith, John
---

# New Paper

## 摘要

This is a pending paper abstract.

## AI 摘要

*AI 摘要正在生成中（blog_status: pending）...*

## AI 综述 (中文)

*AI 综述正在生成中（blog_status: pending）...*

## 相关引用

*暂无相关引用*

---
*Fetched from AlphaXiv*
"""

SUMMARY_NOTE = """---
title: "Ego Summary Paper"
arxiv_id: "2301.99999"
tags: [paper, alphaxiv, computer-vision]
authors:
  - Doe, Jane
---
# Ego Summary Paper

## AI 摘要

### 核心总结
This paper uses egocentric video for 3D scene understanding.
"""

GHOST_NOTE = """---
title: "Ghost Title"
arxiv_id: "2301.88888"
tags: [paper, alphaxiv, nlp]
authors:
  - Ghost, Author
---
# Ghost Title

## 摘要
A paper about unrelated natural language processing topics.
"""


def write_note(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


# ──────────────────────────────────────────────────────────────────
# _scan_vault_papers
# ──────────────────────────────────────────────────────────────────

class TestScanVaultPapers:
    def test_scans_all_papers(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = _scan_vault_papers(str(tmp_path))
        assert len(results) == 1
        assert results[0]['arxiv_id'] == '1706.03762'
        assert results[0]['title'] == 'Attention Is All You Need'
        assert results[0]['published_venue'] == 'NeurIPS 2017'
        assert results[0]['ccf'] == 'A'

    def test_handles_missing_dir(self, tmp_path):
        results = _scan_vault_papers(os.path.join(str(tmp_path), 'nonexistent'))
        assert results == []

    def test_skips_non_md_files(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        write_note(os.path.join(refs, 'notes.txt'), 'not markdown')
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = _scan_vault_papers(str(tmp_path))
        assert len(results) == 1

    def test_skips_invalid_yaml(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'bad.md'), '---\n\tbad: : yaml\n---\n# Test')
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = _scan_vault_papers(str(tmp_path))
        assert len(results) == 0

    def test_scans_multiple_papers(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        write_note(os.path.join(refs, 'paper2.md'),
                   FULL_NOTE.replace('1706.03762', '2301.12345').replace(
                       'Attention Is All You Need', 'Another Paper'))
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = _scan_vault_papers(str(tmp_path))
        assert len(results) == 2


# ──────────────────────────────────────────────────────────────────
# find_notes_by_topic
# ──────────────────────────────────────────────────────────────────

class TestFindNotesByTopic:
    def test_matches_title_keyword(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_topic('attention', str(tmp_path))
        assert len(results) == 1

    def test_matches_tag_keyword(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_topic('transformer', str(tmp_path))
        assert len(results) == 1

    def test_no_match_returns_empty(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_topic('quantum computing', str(tmp_path))
        assert results == []

    def test_multi_keyword_any_match(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_topic('quantum attention', str(tmp_path))
        assert len(results) == 1

    def test_matches_abstract_content(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        write_note(os.path.join(refs, 'paper2.md'), SUMMARY_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_topic('egocentric', str(tmp_path))
        assert len(results) == 1
        assert results[0]['arxiv_id'] == '2301.99999'

    def test_result_has_relevance_scores(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_topic('attention', str(tmp_path))
        assert len(results) == 1
        assert 'relevance' in results[0]
        assert results[0]['relevance'] == 'high'

    def test_relevance_medium_for_tags_only(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_topic('transformer', str(tmp_path))
        assert len(results) == 1
        assert results[0]['relevance'] == 'medium'

    def test_ghost_keyword_no_match(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), GHOST_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_topic('nonexistent_keyword_xyz', str(tmp_path))
        assert results == []


# ──────────────────────────────────────────────────────────────────
# find_notes_by_author
# ──────────────────────────────────────────────────────────────────

class TestFindNotesByAuthor:
    def test_matches_full_name(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_author('Vaswani', str(tmp_path))
        assert len(results) == 1

    def test_case_insensitive(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_author('vaswani', str(tmp_path))
        assert len(results) == 1

    def test_no_match_returns_empty(self, tmp_path, monkeypatch):
        refs = os.path.join(str(tmp_path), '300 Resources', '320 References')
        write_note(os.path.join(refs, 'paper1.md'), FULL_NOTE)
        monkeypatch.setattr('literature_analyzer.VAULT_REFERENCES',
                           os.path.relpath(refs, str(tmp_path)))
        results = find_notes_by_author('Einstein', str(tmp_path))
        assert results == []


# ──────────────────────────────────────────────────────────────────
# extract_paper_summary
# ──────────────────────────────────────────────────────────────────

class TestExtractPaperSummary:
    def test_extracts_abstract(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, FULL_NOTE)
        result = extract_paper_summary(fpath)
        assert 'dominant sequence transduction' in result

    def test_extracts_key_insights(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, FULL_NOTE)
        result = extract_paper_summary(fpath)
        assert 'Self-attention replaces' in result

    def test_handles_pending_note(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, PENDING_NOTE)
        result = extract_paper_summary(fpath)
        assert 'pending paper abstract' in result.lower()

    def test_handles_missing_file(self, tmp_path):
        result = extract_paper_summary(os.path.join(str(tmp_path), 'nonexistent.md'))
        assert result == ''

    def test_handles_empty_note(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, '---\ntitle: "Empty"\n---\n# Empty')
        result = extract_paper_summary(fpath)
        assert isinstance(result, str)


# ──────────────────────────────────────────────────────────────────
# build_synthesis_note
# ──────────────────────────────────────────────────────────────────

class TestBuildSynthesisNote:
    def test_builds_topic_synthesis(self, tmp_path):
        papers = [{
            'filepath': os.path.join(str(tmp_path), 'test.md'),
            'title': 'Attention Is All You Need',
            'arxiv_id': '1706.03762',
            'authors': ['Vaswani, Ashish'],
            'published_venue': 'NeurIPS 2017',
            'ccf': 'A',
            'presentation_type': '',
            'published_date': '2017-12-01',
        }]
        write_note(papers[0]['filepath'], FULL_NOTE)

        content, filepath = build_synthesis_note('Transformer', papers, 'topic', str(tmp_path))
        assert '文献综述' in filepath
        assert 'Transformer' in content
        assert 'Attention Is All You Need' in content
        assert 'NeurIPS 2017' in content
        assert 'CCF-A' in content
        assert '交叉引用与演进' in content

    def test_builds_author_synthesis(self, tmp_path):
        papers = [{
            'filepath': os.path.join(str(tmp_path), 'test.md'),
            'title': 'Attention Is All You Need',
            'arxiv_id': '1706.03762',
            'authors': ['Vaswani, Ashish'],
            'published_venue': '',
            'ccf': '',
            'presentation_type': '',
            'published_date': '',
        }]
        write_note(papers[0]['filepath'], FULL_NOTE)

        content, filepath = build_synthesis_note('Ashish Vaswani', papers, 'author', str(tmp_path))
        assert '文献分析' in filepath
        assert 'Ashish Vaswani' in content

    def test_sanitizes_topic_in_filename(self, tmp_path):
        papers = [{
            'filepath': os.path.join(str(tmp_path), 'test.md'),
            'title': 'Test', 'arxiv_id': '1234.56789',
            'authors': [], 'published_venue': '', 'ccf': '',
            'presentation_type': '', 'published_date': '',
        }]
        write_note(papers[0]['filepath'], '---\ntitle: "Test"\n---\n# Test')

        content, filepath = build_synthesis_note(
            'Topic with: illegal "chars" ?', papers, 'topic', str(tmp_path))
        assert ':' not in os.path.basename(filepath)
        assert '"' not in os.path.basename(filepath)
        assert '?' not in os.path.basename(filepath)

    def test_handles_pending_paper(self, tmp_path):
        papers = [{
            'filepath': os.path.join(str(tmp_path), 'test.md'),
            'title': 'Pending Paper', 'arxiv_id': '2301.12345',
            'authors': ['Smith, John'],
            'published_venue': '', 'ccf': '', 'presentation_type': '',
            'published_date': '',
        }]
        write_note(papers[0]['filepath'], PENDING_NOTE)

        content, filepath = build_synthesis_note('Test', papers, 'topic', str(tmp_path))
        assert 'Pending Paper' in content

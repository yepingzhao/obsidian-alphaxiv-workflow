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
    build_synthesis_prompt,
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

### 核心总结
Self-attention replaces recurrence for sequence modeling, achieving SOTA on WMT 2014.

### 关键洞察
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

STRUCTURED_NOTE = """---
title: "Structured Paper"
arxiv_id: "2301.11111"
tags: [paper, alphaxiv]
authors:
  - Alice, Researcher
---

# Structured Paper

## 摘要

Original English abstract here.

## AI 摘要

### 核心总结
This paper introduces a novel method for 3D reconstruction from single images.

### 关键洞察
- Uses neural radiance fields for implicit representation
- Achieves state-of-the-art on DTU benchmark
- Requires only a single GPU for training

### 问题背景
3D reconstruction is a fundamental problem in computer vision.

### 方法
The method combines NeRF with monocular depth estimation.

### 结果
Outperforms previous methods by 12% on PSNR metric.

## AI 综述 (中文)

3D 重建是计算机视觉领域的核心问题。本文提出了一种从单张图片进行
3D 重建的新方法，结合了神经辐射场和单目深度估计技术。
该方法在 DTU 基准上取得了最先进的结果，同时只需要单 GPU 训练。

---

## 相关引用

1. **NeRF**
   - Mildenhall et al., ECCV 2020

---

*Fetched from AlphaXiv*
"""

OVERVIEW_ONLY_NOTE = """---
title: "Overview Only Paper"
arxiv_id: "2301.22222"
tags: [paper, alphaxiv]
authors:
  - Bob, Author
---

# Overview Only Paper

## 摘要

This paper studies multimodal learning for video understanding.

## AI 摘要

*AI 摘要正在生成中...*

## AI 综述 (中文)

多模态视频理解是近年来的研究热点。本文提出了一个新颖的跨模态注意力机制，
能够有效融合视觉和文本信息。通过在多个基准数据集上的实验验证，
该方法在视频问答和视频描述任务上都取得了显著的性能提升。
与现有方法相比，本方法在计算效率上也有明显优势，适合大规模部署。

---

*Fetched from AlphaXiv*
"""

ABSTRACT_ONLY_NOTE = """---
title: "Abstract Only Paper"
arxiv_id: "2301.33333"
tags: [paper, alphaxiv]
blog_status: pending
authors:
  - Charlie, Author
---

# Abstract Only Paper

## 摘要

A brief abstract about video diffusion models.

## AI 摘要

*AI 摘要正在生成中（blog_status: pending）...*

## AI 综述 (中文)

*AI 综述正在生成中（blog_status: pending）...*

## 相关引用

*暂无相关引用*

---

*Fetched from AlphaXiv*
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
        assert 'Self-attention replaces' in result

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

    def test_extracts_core_summary_tier1(self, tmp_path):
        """Tier 1: 核心总结 + 关键洞察."""
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, STRUCTURED_NOTE)
        result = extract_paper_summary(fpath)
        assert 'novel method for 3D reconstruction' in result
        assert 'neural radiance fields' in result
        assert 'Original English abstract' not in result

    def test_extracts_overview_fallback_tier2(self, tmp_path):
        """Tier 2: 核心总结 missing, falls back to AI 综述 first paragraphs."""
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, OVERVIEW_ONLY_NOTE)
        result = extract_paper_summary(fpath)
        assert '多模态视频理解' in result
        assert '跨模态注意力机制' in result

    def test_extracts_abstract_fallback_tier3(self, tmp_path):
        """Tier 3: No structured summary or overview, falls back to abstract."""
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, ABSTRACT_ONLY_NOTE)
        result = extract_paper_summary(fpath)
        assert 'video diffusion models' in result

    def test_pending_paper_marked_warning(self, tmp_path):
        """blog_status: pending papers get warning marker."""
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, ABSTRACT_ONLY_NOTE)
        result = extract_paper_summary(fpath)
        assert '⚠️' in result

    def test_extraction_stays_within_token_budget(self, tmp_path):
        """Extracted content under ~600 tokens (~2400 chars)."""
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, STRUCTURED_NOTE)
        result = extract_paper_summary(fpath)
        assert len(result) <= 2500, f'Extracted {len(result)} chars, expected <= 2500'


# ──────────────────────────────────────────────────────────────────
# build_synthesis_prompt
# ──────────────────────────────────────────────────────────────────


class TestBuildSynthesisPrompt:
    def test_includes_all_papers(self):
        papers = [
            {'title': 'Paper A', 'arxiv_id': '1111.00001', 'authors': ['A'], 'published_date': '2024', 'summary': 'Summary A', 'ccf': 'A', 'published_venue': 'NeurIPS 2024', 'relevance': 'high'},
            {'title': 'Paper B', 'arxiv_id': '2222.00002', 'authors': ['B'], 'published_date': '2023', 'summary': 'Summary B', 'ccf': '', 'published_venue': '', 'relevance': 'medium'},
        ]
        prompt = build_synthesis_prompt('MyTopic', papers, 'topic')
        assert 'MyTopic' in prompt
        assert 'Paper A' in prompt
        assert 'Paper B' in prompt
        assert '1111.00001' in prompt
        assert '2222.00002' in prompt
        assert 'Summary A' in prompt
        assert 'Summary B' in prompt

    def test_includes_five_chapter_headings(self):
        papers = [{'title': 'T', 'arxiv_id': '1', 'authors': ['A'], 'published_date': '', 'summary': 'S', 'ccf': '', 'published_venue': '', 'relevance': 'high'}]
        prompt = build_synthesis_prompt('Test', papers, 'topic')
        assert '方法分类与对比' in prompt
        assert '演进脉络' in prompt
        assert '共识与矛盾' in prompt
        assert '空白与机会' in prompt
        assert '关键论文推荐' in prompt

    def test_includes_output_format_constraints(self):
        papers = [{'title': 'T', 'arxiv_id': '1', 'authors': ['A'], 'published_date': '', 'summary': 'S', 'ccf': '', 'published_venue': '', 'relevance': 'high'}]
        prompt = build_synthesis_prompt('Test', papers, 'topic')
        assert 'wikilink' in prompt or '[[' in prompt
        assert '中文' in prompt

    def test_handles_empty_summary_paper(self):
        papers = [{'title': 'Empty', 'arxiv_id': '1', 'authors': ['X'], 'published_date': '', 'summary': '⚠️ *无可用摘要信息*', 'ccf': '', 'published_venue': '', 'relevance': 'low'}]
        prompt = build_synthesis_prompt('Test', papers, 'topic')
        assert 'Empty' in prompt
        assert '⚠️' in prompt

    def test_author_mode_uses_different_instructions(self):
        papers = [{'title': 'T', 'arxiv_id': '1', 'authors': ['Vaswani, Ashish'], 'published_date': '', 'summary': 'S', 'ccf': '', 'published_venue': '', 'relevance': 'high'}]
        prompt = build_synthesis_prompt('Ashish Vaswani', papers, 'author')
        assert '学者' in prompt or 'author' in prompt.lower()


# ──────────────────────────────────────────────────────────────────
# build_synthesis_note
# ──────────────────────────────────────────────────────────────────

class TestBuildSynthesisNote:
    def test_builds_topic_synthesis_scaffold(self, tmp_path):
        papers = [{
            'filepath': os.path.join(str(tmp_path), 'test.md'),
            'title': 'Attention Is All You Need',
            'arxiv_id': '1706.03762',
            'authors': ['Vaswani, Ashish'],
            'published_venue': 'NeurIPS 2017',
            'ccf': 'A',
            'presentation_type': '',
            'published_date': '2017-12-01',
            'summary': 'Core contribution: self-attention mechanism.',
            'relevance': 'high',
        }]
        write_note(papers[0]['filepath'], FULL_NOTE)

        content, filepath = build_synthesis_note('Transformer', papers, 'topic', str(tmp_path))
        assert '文献综述' in filepath
        assert 'Transformer' in content
        assert 'Attention Is All You Need' in content
        assert 'LLM_SYNTHESIS_PLACEHOLDER' in content
        assert '## 论文列表' in content
        assert '## 论文分析' in content
        assert '## AI 综述生成' in content

    def test_builds_author_synthesis_scaffold(self, tmp_path):
        papers = [{
            'filepath': os.path.join(str(tmp_path), 'test.md'),
            'title': 'Attention Is All You Need',
            'arxiv_id': '1706.03762',
            'authors': ['Vaswani, Ashish'],
            'published_venue': '',
            'ccf': '',
            'presentation_type': '',
            'published_date': '',
            'summary': 'Self-attention mechanism.',
            'relevance': 'high',
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
            'summary': 'S', 'relevance': 'high',
        }]
        write_note(papers[0]['filepath'], '---\ntitle: "Test"\n---\n# Test')

        content, filepath = build_synthesis_note(
            'Topic with: illegal "chars" ?', papers, 'topic', str(tmp_path))
        assert ':' not in os.path.basename(filepath)
        assert '"' not in os.path.basename(filepath)
        assert '?' not in os.path.basename(filepath)

    def test_generated_by_notice(self, tmp_path):
        papers = [{
            'filepath': os.path.join(str(tmp_path), 'test.md'),
            'title': 'T', 'arxiv_id': '1',
            'authors': [], 'published_venue': '', 'ccf': '',
            'presentation_type': '', 'published_date': '',
            'summary': 'S', 'relevance': 'high',
        }]
        write_note(papers[0]['filepath'], '---\ntitle: "T"\n---\n# T')
        content, _ = build_synthesis_note('Test', papers, 'topic', str(tmp_path))
        assert 'alphaxiv-to-obsidian' in content

    def test_includes_relevance_label(self, tmp_path):
        papers = [{
            'filepath': os.path.join(str(tmp_path), 'test.md'),
            'title': 'T', 'arxiv_id': '1',
            'authors': [], 'published_venue': '', 'ccf': '',
            'presentation_type': '', 'published_date': '',
            'summary': 'S', 'relevance': 'low',
        }]
        write_note(papers[0]['filepath'], '---\ntitle: "T"\n---\n# T')
        content, _ = build_synthesis_note('Test', papers, 'topic', str(tmp_path))
        assert '弱相关' in content

    def test_handles_pending_paper_scaffold(self, tmp_path):
        papers = [{
            'filepath': os.path.join(str(tmp_path), 'test.md'),
            'title': 'Pending Paper', 'arxiv_id': '2301.12345',
            'authors': ['Smith, John'],
            'published_venue': '', 'ccf': '', 'presentation_type': '',
            'published_date': '',
            'summary': 'A pending paper abstract.',
            'relevance': 'medium',
        }]
        write_note(papers[0]['filepath'], PENDING_NOTE)

        content, filepath = build_synthesis_note('Test', papers, 'topic', str(tmp_path))
        assert 'Pending Paper' in content

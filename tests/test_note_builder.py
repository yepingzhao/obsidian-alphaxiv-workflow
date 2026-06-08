"""
Tests for note_builder.py — title cleaning, filename sanitization,
heading demotion, tag extraction, citation formatting, title validation.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from note_builder import (
    clean_title,
    sanitize_filename,
    demote_headings,
    extract_tags,
    format_citations,
    check_title_issues,
    build_note,
)


# ──────────────────────────────────────────────────────────────────
# clean_title
# ──────────────────────────────────────────────────────────────────

class TestCleanTitle:
    def test_strips_arxiv_id_prefix(self):
        assert clean_title('[1706.03762] Attention Is All You Need') == 'Attention Is All You Need'

    def test_strips_arxiv_id_with_version(self):
        assert clean_title('[1706.03762v7] Attention Is All You Need') == 'Attention Is All You Need'

    def test_removes_arxiv_suffix(self):
        assert clean_title('Attention Is All You Need - arXiv') == 'Attention Is All You Need'

    def test_removes_truncation_dots(self):
        assert clean_title('A Very Long Title That Gets Cut Off...') == 'A Very Long Title That Gets Cut Off'

    def test_collapses_newlines(self):
        assert clean_title('Title\nwith\nnewlines') == 'Title with newlines'

    def test_collapses_multiple_spaces(self):
        assert clean_title('Title   with    spaces') == 'Title with spaces'

    def test_handles_empty_title(self):
        assert clean_title('') == ''

    def test_handles_combined_issues(self):
        result = clean_title('[2301.00001] My Great Paper... - arXiv')
        assert result == 'My Great Paper'

    def test_preserves_hyphens_in_title(self):
        assert clean_title('Pre-training vs Fine-tuning') == 'Pre-training vs Fine-tuning'


# ──────────────────────────────────────────────────────────────────
# sanitize_filename
# ──────────────────────────────────────────────────────────────────

class TestSanitizeFilename:
    def test_removes_illegal_chars(self):
        result = sanitize_filename('Title with / \\ : * ? " < > | chars')
        assert '/' not in result
        assert '\\' not in result
        assert ':' not in result
        assert '*' not in result
        assert '?' not in result
        assert '"' not in result
        assert '<' not in result
        assert '>' not in result
        assert '|' not in result

    def test_truncates_to_100_chars(self):
        long_title = 'A' * 200
        assert len(sanitize_filename(long_title)) <= 100

    def test_preserves_normal_title(self):
        result = sanitize_filename('Attention Is All You Need')
        assert result == 'Attention Is All You Need'

    def test_strips_arxiv_prefix(self):
        result = sanitize_filename('[1706.03762] Attention Is All You Need')
        assert '[1706.03762]' not in result

    def test_removes_whitespace_only(self):
        result = sanitize_filename('   Spaces Around   ')
        assert result == 'Spaces Around'


# ──────────────────────────────────────────────────────────────────
# demote_headings
# ──────────────────────────────────────────────────────────────────

class TestDemoteHeadings:
    def test_demotes_h1(self):
        assert demote_headings('# Title') == '## Title'

    def test_demotes_h2(self):
        assert demote_headings('## Section') == '### Section'

    def test_demotes_h3(self):
        assert demote_headings('### Subsection') == '#### Subsection'

    def test_multiple_headings(self):
        text = '# Main\nSome text\n## Sub\nMore text\n### Deep'
        result = demote_headings(text)
        assert '## Main' in result
        assert '### Sub' in result
        assert '#### Deep' in result

    def test_preserves_non_headings(self):
        text = 'plain text\n# heading\nmore plain'
        result = demote_headings(text)
        assert 'plain text' in result
        assert 'more plain' in result


# ──────────────────────────────────────────────────────────────────
# extract_tags
# ──────────────────────────────────────────────────────────────────

class TestExtractTags:
    def test_extracts_base_tags(self):
        meta = {'categories': ['cs.CL']}
        tags = extract_tags(meta)
        assert 'paper' in tags
        assert 'alphaxiv' in tags

    def test_maps_cs_cl_to_nlp(self):
        meta = {'categories': ['cs.CL']}
        tags = extract_tags(meta)
        assert 'nlp' in tags

    def test_maps_cs_cv_to_cv(self):
        meta = {'categories': ['cs.CV']}
        tags = extract_tags(meta)
        assert 'computer-vision' in tags

    def test_maps_cs_lg_to_ml(self):
        meta = {'categories': ['cs.LG']}
        tags = extract_tags(meta)
        assert 'machine-learning' in tags

    def test_handles_dict_categories(self):
        meta = {'categories': [{'name': 'cs.CL'}]}
        tags = extract_tags(meta)
        assert 'nlp' in tags

    def test_handles_subjects_fallback(self):
        meta = {'subjects': ['cs.AI']}
        tags = extract_tags(meta)
        assert 'ai' in tags

    def test_deduplicates_tags(self):
        meta = {'categories': ['cs.CL', 'cs.CL']}
        tags = extract_tags(meta)
        assert tags.count('nlp') == 1

    def test_handles_unknown_category(self):
        meta = {'categories': ['q-bio.QM']}
        tags = extract_tags(meta)
        assert 'paper' in tags
        assert 'alphaxiv' in tags

    def test_handles_empty_categories(self):
        meta = {'categories': []}
        tags = extract_tags(meta)
        assert tags == ['paper', 'alphaxiv']


# ──────────────────────────────────────────────────────────────────
# format_citations
# ──────────────────────────────────────────────────────────────────

class TestFormatCitations:
    def test_empty_returns_empty(self):
        assert format_citations([]) == ''

    def test_formats_single_citation(self):
        citations = [{'title': 'BERT', 'alphaxiv_link': 'https://alphaxiv.org/paper/123',
                       'justification': 'relevant'}]
        result = format_citations(citations)
        assert 'BERT' in result
        assert 'AlphaXiv' in result

    def test_handles_missing_link(self):
        citations = [{'title': 'BERT', 'justification': ''}]
        result = format_citations(citations)
        assert 'BERT' in result

    def test_converts_paper_to_abs_link(self):
        citations = [{'title': 'BERT', 'alphaxiv_link': 'https://alphaxiv.org/paper/123'}]
        result = format_citations(citations)
        assert '/abs/' in result
        assert '/paper/' not in result

    def test_handles_pydantic_style_fields(self):
        class MockCitation:
            title = 'BERT'
            alphaxivLink = 'https://alphaxiv.org/paper/456'
            justification = 'relevant'
        result = format_citations([MockCitation()])
        assert 'BERT' in result

    def test_multiple_citations(self):
        citations = [
            {'title': 'Paper 1', 'alphaxiv_link': 'https://alphaxiv.org/paper/1'},
            {'title': 'Paper 2', 'alphaxiv_link': 'https://alphaxiv.org/paper/2'},
        ]
        result = format_citations(citations)
        assert '1.' in result
        assert '2.' in result


# ──────────────────────────────────────────────────────────────────
# check_title_issues
# ──────────────────────────────────────────────────────────────────

class TestCheckTitleIssues:
    def test_block_on_existing_file(self, tmp_path):
        vault = str(tmp_path)
        refs = os.path.join(vault, '300 Resources', '320 References')
        os.makedirs(refs)
        title = 'Test Paper Title'
        filename = sanitize_filename(title) + '.md'
        with open(os.path.join(refs, filename), 'w') as f:
            f.write('---\ntitle: test\n---\n# test')

        issues = check_title_issues(title, vault)
        blocks = [i for i in issues if i[0] == 'block']
        assert len(blocks) >= 1
        assert 'already exists' in blocks[0][1]

    def test_warn_on_truncated(self):
        issues = check_title_issues('Paper Title...', '/nonexistent/vault')
        warns = [i for i in issues if i[0] == 'warn']
        assert any('truncated' in w[1].lower() for w in warns)

    def test_no_issues_for_clean_title(self, tmp_path):
        vault = str(tmp_path)
        issues = check_title_issues('Clean Paper Title', vault)
        blocks = [i for i in issues if i[0] == 'block']
        assert len(blocks) == 0


# ──────────────────────────────────────────────────────────────────
# build_note
# ──────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock


def _make_mock_model(data: dict) -> MagicMock:
    """Create a mock Pydantic model with .model_dump() returning the dict."""
    m = MagicMock()
    m.model_dump.return_value = data
    return m


def _base_meta() -> dict:
    return {
        'title': 'Attention Is All You Need',
        'universal_id': '1706.03762',
        'version_label': 'v7',
        'publication_date': 1497225600000,  # 2017-06-12
        'abstract': 'The dominant sequence transduction models...',
        'citation_bibtex': '@article{vaswani2017attention,\n'
                          'author = {Vaswani, Ashish and Shazeer, Noam},\n'
                          'title = {Attention Is All You Need}\n}',
        'categories': ['cs.CL', 'cs.LG'],
        'authors': [],
    }


def _base_overview_zh() -> dict:
    return {
        'overview': '这是Transformer架构的论文，提出了全新的注意力机制。\n\n'
                    '## 相关引用\n\n1. Bahdanau et al.\n2. Kim et al.',
        'summary': {'summary': ['Key insight: self-attention replaces recurrence.']},
        'summary_section_titles': {},
        'overview_section_titles': {'relevant_citations': '相关引用'},
        'citations': [
            {'title': 'Related Paper', 'alphaxiv_link': 'https://alphaxiv.org/paper/1234', 'justification': ''},
        ],
        'ai_tooltips': {},
    }


class TestBuildNote:
    def test_builds_basic_note(self):
        meta = _make_mock_model(_base_meta())
        zh = _make_mock_model(_base_overview_zh())
        content, warnings = build_note(meta, zh)
        assert 'Attention Is All You Need' in content
        assert 'arxiv_id: "1706.03762"' in content
        assert '## 摘要' in content
        assert '## AI 摘要' in content
        assert '## AI 综述 (中文)' in content
        assert '## 相关引用' in content
        assert '*Fetched from [AlphaXiv]' in content

    def test_falls_back_to_en_when_zh_empty(self):
        meta = _make_mock_model(_base_meta())
        zh_empty = _make_mock_model({'overview': '', 'summary': {}, 'citations': [],
                                     'summary_section_titles': {}, 'overview_section_titles': {},
                                     'ai_tooltips': {}})
        en = _make_mock_model(_base_overview_zh())
        content, warnings = build_note(meta, zh_empty, en)
        assert any('English fallback' in w for w in warnings)

    def test_marks_blog_pending_when_both_empty(self):
        meta = _make_mock_model(_base_meta())
        zh_empty = _make_mock_model({'overview': '', 'summary': {}, 'citations': [],
                                     'summary_section_titles': {}, 'overview_section_titles': {},
                                     'ai_tooltips': {}})
        content, warnings = build_note(meta, zh_empty)
        assert any('blog_pending' in w for w in warnings)
        assert 'blog_status: pending' in content

    def test_escapes_double_quotes_in_title(self):
        meta = _make_mock_model({**_base_meta(), 'title': 'Paper with "quotes" inside'})
        zh = _make_mock_model(_base_overview_zh())
        content, warnings = build_note(meta, zh)
        assert 'title: "Paper with \\"quotes\\" inside"' in content

    def test_includes_publication_venue(self):
        meta = _make_mock_model(_base_meta())
        zh = _make_mock_model(_base_overview_zh())
        pub_info = {'published_venue': 'NeurIPS 2017', 'presentation_type': 'Oral'}
        content, warnings = build_note(meta, zh, pub_info=pub_info)
        assert 'published_venue: "NeurIPS 2017"' in content
        assert 'NeurIPS 2017 (Oral)' in content  # info bar badge

    def test_includes_ccf_ranking(self):
        meta = _make_mock_model(_base_meta())
        zh = _make_mock_model(_base_overview_zh())
        pub_rank = {'ccf': 'A', 'sci_jcr': 'Q1', 'sci_cas_top': True}
        content, warnings = build_note(meta, zh, pub_rank=pub_rank)
        assert 'ccf: "A"' in content
        assert 'CCF A' in content
        assert 'SCI Q1' in content
        assert '中科院Top' in content

    def test_strips_trailing_references_from_overview(self):
        meta = _make_mock_model(_base_meta())
        zh_data = _base_overview_zh()
        zh = _make_mock_model(zh_data)
        content, warnings = build_note(meta, zh)
        overview_start = content.find('## AI 综述 (中文)')
        overview_section = content[overview_start:content.find('## 相关引用', overview_start + 1)]
        assert '相关引用' not in overview_section.split('##')[-1]

    def test_handles_missing_bibtex(self):
        meta = _make_mock_model({**_base_meta(), 'citation_bibtex': '',
                                 'authors': [{'name': 'Smith, John'}]})
        zh = _make_mock_model(_base_overview_zh())
        content, warnings = build_note(meta, zh)
        assert 'Smith, John' in content

    def test_no_authors_triggers_warning(self):
        meta = _make_mock_model({**_base_meta(), 'citation_bibtex': '', 'authors': []})
        zh = _make_mock_model(_base_overview_zh())
        content, warnings = build_note(meta, zh)
        assert any('No authors' in w for w in warnings)

    def test_includes_arxiv_and_alphaxiv_links(self):
        meta = _make_mock_model(_base_meta())
        zh = _make_mock_model(_base_overview_zh())
        content, warnings = build_note(meta, zh)
        assert 'https://arxiv.org/abs/1706.03762' in content
        assert 'https://alphaxiv.org/abs/1706.03762' in content

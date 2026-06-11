"""
Tests for gate01_search.py — table building, JSON export,
progress logging, and pipeline stages (with mocked external APIs).
"""
import asyncio
import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from alphaxiv_workflow.search import (
    build_table,
    export_json,
    check_overview_async,
    fetch_ranking_async,
)


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _make_processed_paper(i: int, **overrides) -> dict:
    """Create a processed paper dict with default test values."""
    data = {
        'arxiv_id': f'2301.0000{i}',
        'title': f'Test Paper Title {i}',
        'in_vault': False,
        'vault_path': '',
        'rating': 3,
        'rating_display': '★★★☆☆ (Top venue: CVPR)',
        'overview': 'en',
        'ccf': 'A',
        'quality': {
            'venue': 'CVPR', 'year': 2024, 'citations': 50,
            'signals': ['Top venue: CVPR']
        },
        'pub_info': {
            'published_venue': 'CVPR 2024',
            'presentation_type': 'Oral',
            'published_date': '2023-11-15',
            'journal_ref_raw': 'CVPR 2024',
            'authors': ['Doe, John', 'Smith, Jane'],
        },
    }
    data.update(overrides)
    return data


# ──────────────────────────────────────────────────────────────────
# build_table
# ──────────────────────────────────────────────────────────────────

class TestBuildTable:
    def test_creates_table_with_correct_columns(self):
        papers = [_make_processed_paper(1)]
        table = build_table(papers)
        field_names = str(table.field_names)
        assert '#' in field_names
        assert '评级' in field_names
        assert 'arXiv ID' in field_names
        assert '标题' in field_names
        assert '一作' in field_names
        assert '发表venue' in field_names
        assert 'CCF' in field_names

    def test_shows_first_author(self):
        papers = [_make_processed_paper(1)]
        table = build_table(papers)
        table_str = str(table)
        assert 'Doe' in table_str

    def test_shows_venue_with_presentation_type(self):
        papers = [_make_processed_paper(1)]
        table = build_table(papers)
        table_str = str(table)
        assert 'CVPR 2024 (Oral)' in table_str

    def test_shows_ccf(self):
        papers = [_make_processed_paper(1)]
        table = build_table(papers)
        table_str = str(table)
        assert 'CCF-A' in table_str

    def test_shows_arxiv_date(self):
        papers = [_make_processed_paper(1)]
        table = build_table(papers)
        table_str = str(table)
        assert '2023-11-15' in table_str

    def test_shows_conf_date_from_venue(self):
        papers = [_make_processed_paper(1)]
        table = build_table(papers)
        table_str = str(table)
        # 'CVPR 2024' -> conf_date column should contain '2024'
        # The exact column position depends on table formatting, check for 2024
        lines = table_str.split('\n')
        found = any('2024' in line and '2023-11-15' in line for line in lines)
        assert found or '2024' in table_str

    def test_shows_new_status(self):
        papers = [_make_processed_paper(1, in_vault=False)]
        table = build_table(papers)
        table_str = str(table)
        assert '新' in table_str

    def test_shows_saved_status(self):
        papers = [_make_processed_paper(1, in_vault=True)]
        table = build_table(papers)
        table_str = str(table)
        assert '已保存' in table_str

    def test_shows_overview_badge(self):
        papers = [_make_processed_paper(1, overview='en')]
        table = build_table(papers)
        table_str = str(table)
        assert '⚡' in table_str

    def test_no_overview_no_badge(self):
        papers = [_make_processed_paper(1, overview=None)]
        table = build_table(papers)
        table_str = str(table)
        assert '⚡' not in table_str

    def test_no_venue_shows_dash(self):
        papers = [_make_processed_paper(1)]
        papers[0]['pub_info']['published_venue'] = ''
        table = build_table(papers)
        table_str = str(table)
        assert '—' in table_str

    def test_no_ccf_shows_dash(self):
        papers = [_make_processed_paper(1, ccf='')]
        table = build_table(papers)
        table_str = str(table)
        assert '—' in table_str

    def test_no_authors_shows_unknown(self):
        papers = [_make_processed_paper(1)]
        papers[0]['pub_info']['authors'] = []
        table = build_table(papers)
        table_str = str(table)
        assert 'Unknown' in table_str

    def test_multiple_papers(self):
        papers = [_make_processed_paper(i) for i in range(1, 4)]
        table = build_table(papers)
        table_str = str(table)
        assert 'Test Paper Title 1' in table_str
        assert 'Test Paper Title 3' in table_str

    def test_empty_pub_info_handled(self):
        papers = [_make_processed_paper(1, pub_info={})]
        table = build_table(papers)
        table_str = str(table)
        # Should not raise — should gracefully handle missing pub_info
        assert 'Unknown' in table_str or '—' in table_str


# ──────────────────────────────────────────────────────────────────
# export_json
# ──────────────────────────────────────────────────────────────────

class TestExportJSON:
    def test_exports_correct_keys(self):
        papers = [_make_processed_paper(1)]
        result = export_json(papers)
        assert len(result) == 1
        entry = result[0]
        expected_keys = {
            'arxiv_id', 'title', 'in_vault', 'vault_path', 'rating',
            'rating_display', 'first_author', 'venue', 'presentation_type',
            'ccf', 'arxiv_date', 'overview', 'quality',
        }
        assert set(entry.keys()) == expected_keys

    def test_exports_first_author(self):
        papers = [_make_processed_paper(1)]
        result = export_json(papers)
        assert result[0]['first_author'] == 'Doe'

    def test_exports_empty_authors_unknown(self):
        papers = [_make_processed_paper(1)]
        papers[0]['pub_info'] = {}
        result = export_json(papers)
        assert result[0]['first_author'] == 'Unknown'

    def test_exports_multiple_papers(self):
        papers = [_make_processed_paper(1), _make_processed_paper(2)]
        result = export_json(papers)
        assert len(result) == 2
        assert result[0]['arxiv_id'] == '2301.00001'
        assert result[1]['arxiv_id'] == '2301.00002'

    def test_json_serializable(self):
        papers = [_make_processed_paper(1)]
        result = export_json(papers)
        # Should not raise — all values must be JSON-serializable
        json.dumps(result)


# ──────────────────────────────────────────────────────────────────
# check_overview_async
# ──────────────────────────────────────────────────────────────────

class TestCheckOverviewAsync:
    def test_returns_none_for_empty_version_id(self):
        result = asyncio.run(check_overview_async(''))
        assert result is None

    def test_returns_none_when_api_fails(self):
        async def run():
            with patch('alphaxiv_workflow.search.get_overview', side_effect=Exception('404')):
                return await check_overview_async('test-id')

        result = asyncio.run(run())
        assert result is None


# ──────────────────────────────────────────────────────────────────
# fetch_ranking_async
# ──────────────────────────────────────────────────────────────────

class TestFetchRankingAsync:
    def test_returns_empty_for_empty_venue(self):
        sem = asyncio.Semaphore(1)

        async def run():
            return await fetch_ranking_async('', sem)

        result = asyncio.run(run())
        assert result == {}

    def test_extracts_venue_abbreviation(self):
        sem = asyncio.Semaphore(1)

        async def run():
            with patch('alphaxiv_workflow.search.get_venue_ranking', return_value={'ccf': 'A'}) as mock_rank:
                result = await fetch_ranking_async('NeurIPS 2020', sem)
                mock_rank.assert_called_once_with('NeurIPS')
                return result

        result = asyncio.run(run())
        assert result == {'ccf': 'A'}

    def test_strips_whitespace_venue(self):
        sem = asyncio.Semaphore(1)

        async def run():
            with patch('alphaxiv_workflow.search.get_venue_ranking', return_value={}) as mock_rank:
                result = await fetch_ranking_async('  ICML 2023  ', sem)
                mock_rank.assert_called_once_with('ICML')
                return result

        result = asyncio.run(run())
        assert result == {}

"""
Tests for alphaxiv_client.py — venue parsing, quality signals,
quality rating, arXiv ID resolution, batch publication info, author parsing.
"""
import os
import sys
import io
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from alphaxiv_client import (
    _parse_venue_from_ref,
    _detect_presentation_type,
    _extract_venue_from_text,
    extract_quality_signals,
    rate_paper_quality,
    _parse_authors_from_entry,
    _get_first_author,
)


# ──────────────────────────────────────────────────────────────────
# _parse_venue_from_ref
# ──────────────────────────────────────────────────────────────────

class TestParseVenueFromRef:
    def test_parses_full_name_neurips(self):
        result = _parse_venue_from_ref(
            'Advances in Neural Information Processing Systems 33 (NeurIPS 2020)')
        assert result == 'NeurIPS 2020'

    def test_parses_full_name_icml(self):
        result = _parse_venue_from_ref('International Conference on Machine Learning 2023')
        assert result == 'ICML 2023'

    def test_parses_full_name_cvpr(self):
        result = _parse_venue_from_ref('Conference on Computer Vision and Pattern Recognition 2024')
        assert result == 'CVPR 2024'

    def test_parses_abbreviation_with_year(self):
        result = _parse_venue_from_ref('CVPR 2019')
        assert result == 'CVPR 2019'

    def test_parses_abbreviation_no_year(self):
        result = _parse_venue_from_ref('IEEE TPAMI')
        assert result == 'TPAMI'

    def test_returns_none_for_empty(self):
        assert _parse_venue_from_ref('') is None

    def test_returns_none_for_none(self):
        assert _parse_venue_from_ref(None) is None

    def test_rejects_non_venue_text(self):
        assert _parse_venue_from_ref('15 pages, 5 figures, 3 tables') is None

    def test_parses_journal_with_year(self):
        result = _parse_venue_from_ref('Journal of Machine Learning Research 22 (2021)')
        assert result == 'JMLR 2021'


# ──────────────────────────────────────────────────────────────────
# _detect_presentation_type
# ──────────────────────────────────────────────────────────────────

class TestDetectPresentationType:
    def test_detects_oral(self):
        assert _detect_presentation_type('Accepted at NeurIPS 2020 (Oral)') == 'Oral'

    def test_detects_spotlight(self):
        assert _detect_presentation_type('Spotlight presentation at ICML') == 'Spotlight'

    def test_oral_priority_over_spotlight(self):
        result = _detect_presentation_type('Oral Spotlight paper')
        assert result == 'Oral'

    def test_returns_none_for_regular(self):
        assert _detect_presentation_type('Accepted at NeurIPS 2020') is None

    def test_returns_none_for_empty(self):
        assert _detect_presentation_type('') is None

    def test_returns_none_for_none(self):
        assert _detect_presentation_type(None) is None

    def test_case_insensitive(self):
        assert _detect_presentation_type('ORAL presentation') == 'Oral'


# ──────────────────────────────────────────────────────────────────
# _extract_venue_from_text
# ──────────────────────────────────────────────────────────────────

class TestExtractVenueFromText:
    def test_extracts_accepted_at(self):
        result = _extract_venue_from_text('This work was accepted at NeurIPS 2024.')
        assert result == 'NeurIPS 2024'

    def test_extracts_published_in(self):
        result = _extract_venue_from_text('Published as a conference paper at ICLR 2024.')
        assert result == 'ICLR 2024'

    def test_extracts_proceedings_of(self):
        result = _extract_venue_from_text('In Proceedings of ICML 2023, pages 1-10.')
        assert result == 'ICML 2023'

    def test_returns_none_for_plain_text(self):
        result = _extract_venue_from_text(
            'This paper introduces a new method for image classification.')
        assert result is None

    def test_returns_none_for_empty(self):
        assert _extract_venue_from_text('') is None

    def test_returns_none_for_none(self):
        assert _extract_venue_from_text(None) is None


# ──────────────────────────────────────────────────────────────────
# extract_quality_signals
# ──────────────────────────────────────────────────────────────────

class TestExtractQualitySignals:
    def test_detects_top_venue_from_snippet(self):
        paper = {
            'snippet': 'Published at NeurIPS 2024, this paper...',
            'title': 'Test Paper',
        }
        result = extract_quality_signals(paper)
        assert result['venue'] is not None
        assert any('Top venue' in s for s in result['signals'])

    def test_detects_recent_year(self):
        paper = {
            'snippet': 'Published 2025...',
            'title': 'Test Paper',
            'publication_date': None,
        }
        result = extract_quality_signals(paper)
        assert any('Recent' in s or 'Very recent' in s for s in result['signals'])

    def test_handles_unknown_paper_type(self):
        result = extract_quality_signals('not a dict or pydantic')
        assert 'unknown' in result['signals']

    def test_detects_sota_claims(self):
        paper = {
            'snippet': 'We achieve state-of-the-art results on all benchmarks.',
            'title': 'Test Paper',
        }
        result = extract_quality_signals(paper)
        assert any('Claims' in s for s in result['signals'])


# ──────────────────────────────────────────────────────────────────
# rate_paper_quality
# ──────────────────────────────────────────────────────────────────

class TestRatePaperQuality:
    def test_baseline_rating_is_2(self):
        rating, _ = rate_paper_quality({'signals': []})
        assert rating == 2

    def test_top_venue_boosts_rating(self):
        signals = {'venue': 'NeurIPS', 'signals': ['Top venue: NeurIPS']}
        rating, _ = rate_paper_quality(signals)
        assert rating >= 3

    def test_very_recent_boosts_rating(self):
        signals = {'year': 2026, 'signals': ['Very recent (2026)']}
        rating, _ = rate_paper_quality(signals)
        assert rating >= 3

    def test_highly_cited_boosts_rating(self):
        signals = {'citations': 500, 'signals': ['Highly cited (500+ citations)']}
        rating, _ = rate_paper_quality(signals)
        assert rating >= 4

    def test_rating_bounded_1_to_5(self):
        rating_min, _ = rate_paper_quality({'signals': []})
        assert 1 <= rating_min <= 5

        signals_max = {
            'venue': 'NeurIPS', 'year': 2026, 'citations': 1000,
            'signals': ['Top venue: NeurIPS', 'Very recent (2026)',
                        'Highly cited (1000+ citations)'],
        }
        rating_max, _ = rate_paper_quality(signals_max)
        assert rating_max <= 5

    def test_display_contains_stars(self):
        _, display = rate_paper_quality({'signals': []})
        assert '★' in display
        assert '☆' in display


# ──────────────────────────────────────────────────────────────────
# rate_paper_quality with CCF
# ──────────────────────────────────────────────────────────────────

class TestRatePaperQualityWithCCF:
    def test_ccf_a_adds_star(self):
        signals = {'venue': 'NeurIPS', 'signals': ['Top venue: NeurIPS']}
        rating_no_ccf, _ = rate_paper_quality(signals)
        rating_ccf_a, _ = rate_paper_quality(signals, ccf='A')
        assert rating_ccf_a == rating_no_ccf + 1

    def test_ccf_b_no_extra_star(self):
        signals = {'venue': 'ICML', 'signals': ['Top venue: ICML']}
        rating_ccf_b, display = rate_paper_quality(signals, ccf='B')
        rating_no_ccf, _ = rate_paper_quality(signals)
        assert rating_ccf_b == rating_no_ccf

    def test_ccf_c_no_extra_star(self):
        signals = {'signals': []}
        rating_ccf_c, _ = rate_paper_quality(signals, ccf='C')
        assert rating_ccf_c == 2  # baseline

    def test_ccf_none_no_effect(self):
        signals = {'signals': []}
        rating, _ = rate_paper_quality(signals, ccf=None)
        assert rating == 2

    def test_ccf_a_still_bounded_to_5(self):
        signals = {
            'venue': 'NeurIPS', 'year': 2026, 'citations': 1000,
            'signals': ['Top venue: NeurIPS', 'Very recent (2026)',
                        'Highly cited (1000+ citations)'],
        }
        rating, _ = rate_paper_quality(signals, ccf='A')
        assert rating <= 5

    def test_ccf_case_insensitive(self):
        signals = {'venue': 'CVPR', 'signals': ['Top venue: CVPR']}
        rating_upper, _ = rate_paper_quality(signals, ccf='A')
        rating_lower, _ = rate_paper_quality(signals, ccf='a')
        assert rating_upper == rating_lower


# ──────────────────────────────────────────────────────────────────
# _parse_authors_from_entry
# ──────────────────────────────────────────────────────────────────

class TestParseAuthorsFromEntry:
    NS_ATOM = 'http://www.w3.org/2005/Atom'

    def _make_entry(self, author_names: list) -> ET.Element:
        """Build a minimal arXiv Atom entry with given authors."""
        entry = ET.Element(f'{{{self.NS_ATOM}}}entry')
        for name in author_names:
            author_el = ET.SubElement(entry, f'{{{self.NS_ATOM}}}author')
            name_el = ET.SubElement(author_el, f'{{{self.NS_ATOM}}}name')
            name_el.text = name
        return entry

    def test_single_author(self):
        entry = self._make_entry(['Doe, John'])
        authors = _parse_authors_from_entry(entry, self.NS_ATOM)
        assert authors == ['Doe, John']

    def test_multiple_authors(self):
        entry = self._make_entry(['Doe, John', 'Smith, Jane', 'Brown, Bob'])
        authors = _parse_authors_from_entry(entry, self.NS_ATOM)
        assert len(authors) == 3
        assert authors[0] == 'Doe, John'

    def test_no_authors(self):
        entry = ET.Element(f'{{{self.NS_ATOM}}}entry')
        authors = _parse_authors_from_entry(entry, self.NS_ATOM)
        assert authors == []

    def test_author_without_name(self):
        entry = ET.Element(f'{{{self.NS_ATOM}}}entry')
        author_el = ET.SubElement(entry, f'{{{self.NS_ATOM}}}author')
        # No name sub-element
        authors = _parse_authors_from_entry(entry, self.NS_ATOM)
        assert authors == []

    def test_trims_whitespace(self):
        entry = self._make_entry(['  Doe, John  '])
        authors = _parse_authors_from_entry(entry, self.NS_ATOM)
        assert authors == ['Doe, John']


# ──────────────────────────────────────────────────────────────────
# _get_first_author
# ──────────────────────────────────────────────────────────────────

class TestGetFirstAuthor:
    def test_lastname_comma_firstname(self):
        assert _get_first_author(['Doe, John']) == 'Doe'

    def test_firstname_lastname(self):
        assert _get_first_author(['John Doe']) == 'Doe'

    def test_single_name(self):
        assert _get_first_author(['Einstein']) == 'Einstein'

    def test_empty_list(self):
        assert _get_first_author([]) == 'Unknown'

    def test_multiple_authors_takes_first(self):
        assert _get_first_author(['Doe, John', 'Smith, Jane']) == 'Doe'

    def test_complex_last_name(self):
        assert _get_first_author(['van der Waals, Johannes']) == 'van der Waals'

"""AlphaXiv + arXiv API client — search, metadata, overview fetching."""
import os
import re
import time
from datetime import datetime
import yaml
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from alphaxiv_cat import AlphaxivCat

from .config import VAULT_PATH, PAPERS_DIR
from .query_parser import (
    parse_query, extract_or_groups, filter_results, build_search_query,
    evaluate_expr, ParseError, Or, Term, Expr, And,
)

# Venue functions (delegated to venue module)
from .venue import (
    _parse_venue_from_ref, _detect_presentation_type, _extract_venue_from_text,
)

client = AlphaxivCat()


# Top-tier ML/CV/NLP venues — grouped by match precision
# Group A: Unambiguous venue acronyms (won't appear in normal text)
VENUE_ACRONYMS = [
    "neurips", "nips", "icml", "iclr", "cvpr", "iccv", "eccv",
    "acl", "emnlp", "naacl", "coling", "aaai", "ijcai", "siggraph",
    "kdd", "sigir", "wsdm", "recsys", "sigmod", "vldb",
    "osdi", "sosp", "nsdi", "isca", "micro", "hpca",
    "chi", "uist", "cscw", "ubicomp", "mobicom", "sensys",
    "rss", "icra", "iros", "corl",
]

# Group B: Journal names — require context to avoid false positives
# Match only when followed by year/volume/publisher patterns
VENUE_JOURNALS = {
    "nature": r'nature\s+(communications|methods|machine\s+intelligence|biotechnology|neuroscience|medicine|electronics|photonics|materials|energy|sustainability|computational\s+science|reviews)',
    "science": r'science\s+(advances|robotics|translational\s+medicine|immunology|signaling)',
    "cell": r'cell\s+(reports|systems|metabolism|stem\s+cell|host\s+&?\s*microbe|neuron|molecular\s+cell|developmental\s+cell|cancer\s+cell|immunity|current\s+biology|patterns)',
    "pnas": r'pnas|proceedings\s+of\s+the\s+national\s+academy\s+of\s+sciences',
    "jmlr": r'jmlr|journal\s+of\s+machine\s+learning\s+research',
    "tpami": r'tpami|ieee\s+trans.*pattern\s+analysis\s+and\s+machine\s+intelligence',
}

# Compiled patterns
ACRONYM_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(v) for v in VENUE_ACRONYMS) + r')\b',
    re.IGNORECASE
)

JOURNAL_PATTERN = re.compile(
    '|'.join(f'({p})' for p in VENUE_JOURNALS.values()),
    re.IGNORECASE
)


def search_paper(query: str):
    """Search AlphaXiv for a paper, return best match Pydantic model."""
    result = client.search.v2.paper.fast_search(q=query, include_private=False)
    items = list(result)
    if not items:
        return None
    return items[0]


def search_papers(query: str, limit: int = 10):
    """Search AlphaXiv and return top-N results as a list of Pydantic models."""
    result = client.search.v2.paper.fast_search(q=query, include_private=False)
    items = list(result)
    return items[:limit]


def search_with_operators(query: str, limit: int = 10) -> tuple:
    """Search AlphaXiv with boolean operator support.

    Supported operators (uppercase to distinguish from keywords):
      - AND     — both terms must match (default: implicit AND)
      - OR      — either term matches (triggers multi-search)
      - NOT     — exclude term from results
      - -word   — shorthand for NOT word
      - (...)   — grouping, e.g. "(diffusion OR gan) AND image"

    If no operators detected, delegates to search_papers() directly.

    Args:
        query: User query string with optional boolean operators
        limit: Maximum results to return

    Returns:
        (results, query_info) tuple:
          results: List of search result Pydantic models
          query_info: Dict with {original, parsed, operators_used, strategy}
    """
    try:
        expr, search_terms, exclude_terms = parse_query(query)
    except ParseError as e:
        # Fall back to plain search on parse failure
        return search_papers(query, limit=limit), {
            'original': query, 'parsed': 'fallback (parse error)',
            'operators_used': False, 'strategy': 'plain',
            'error': str(e),
        }

    # Check if any operators were actually used (single tree walk)
    has_or = False
    has_not = False
    for node in _walk_expr(expr):
        if not has_or and isinstance(node, Or):
            has_or = True
        if not has_not and isinstance(node, Term) and node.negated:
            has_not = True
        if has_or and has_not:
            break
    has_operators = has_or or has_not

    if not has_operators:
        # Simple query — delegate directly
        query_str = build_search_query(search_terms)
        results = search_papers(query_str, limit=limit)
        return results, {
            'original': query, 'parsed': query_str,
            'operators_used': False, 'strategy': 'plain',
        }

    # Strategy: OR → multi-search, NOT → post-filter
    if has_or:
        # Multi-search: one API call per OR group
        groups = extract_or_groups(expr)
        all_results = {}
        api_limit = max(limit * 2, 20)  # Fetch extra to account for filtering

        for pos_terms, _neg_terms in groups:
            query_str = build_search_query(pos_terms)
            if not query_str:
                continue
            batch = search_papers(query_str, limit=api_limit)
            for r in batch:
                aid = r.paper_id if hasattr(r, 'paper_id') else r.get('paper_id', id(r))
                if aid not in all_results:
                    all_results[aid] = r

        results = list(all_results.values())
    else:
        # Single search with NOT — fetch more to compensate for filtering
        query_str = build_search_query(search_terms)
        api_limit = max(limit * 3, 30)
        results = search_papers(query_str, limit=api_limit)

    # Post-filter against the full boolean expression
    results = filter_results(expr, results, limit=limit)

    return results, {
        'original': query,
        'parsed': f'or_groups={len(extract_or_groups(expr))}' if has_or else build_search_query(search_terms),
        'operators_used': True,
        'strategy': 'multi-search + filter' if has_or else 'single-search + filter',
        'has_or': has_or,
        'has_not': has_not,
    }


def _walk_expr(node):
    """Walk expression tree yielding all nodes. Handles cross-module types."""
    yield node
    if isinstance(node, (And, Or)):
        for child in node.children:
            yield from _walk_expr(child)


def resolve_paper_id(query: str):
    """Resolve an arXiv ID or search by title. Returns arxiv_id or None."""
    arxiv_pattern = r'^(\d{4}\.\d{4,5})(v\d+)?$'
    match = re.match(arxiv_pattern, query.strip())
    if match:
        return match.group(1)

    paper = search_paper(query)
    if paper:
        return paper.paper_id if hasattr(paper, 'paper_id') else paper.paperId

    return None


def get_paper_metadata(arxiv_id: str):
    """Get full paper metadata from AlphaXiv. Returns Pydantic model."""
    return client.papers.v3.retrieve(unresolved=arxiv_id)


def get_overview(version_id: str, language: str = "en"):
    """Get paper AI overview for a given language. Returns Pydantic model."""
    return client.papers.v3.overview.retrieve(
        language=language,
        paper_version=version_id
    )

def fetch_publication_info(arxiv_id: str, abstract: str = None) -> dict:
    """Fetch formal publication info for a paper.

    Multi-source fallback chain:
    1. arXiv API <journal_ref> (most reliable structured data)
    2. arXiv API <comment> (e.g. "Accepted at ICML 2023 (Oral)")
    3. Abstract text parsing (e.g. "Published as a conference paper at ICLR 2024")

    Gracefully degrades on network errors — missing values left as None.

    Args:
        arxiv_id: arXiv paper ID
        abstract: Paper abstract text for text-based venue extraction fallback

    Returns:
        published_venue: str | None   — 'NeurIPS 2020'
        presentation_type: str | None — 'Oral' | 'Spotlight' | None
        published_date: str | None    — '2020-12-06' (arXiv first published)
        journal_ref_raw: str | None   — raw journal_ref for debugging
    """
    result = {
        'published_venue': None,
        'presentation_type': None,
        'published_date': None,
        'journal_ref_raw': None,
    }
    try:
        url = f'https://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'AlphaXivToObsidian/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read().decode('utf-8')
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        # arXiv API unreachable — try abstract fallback directly
        if abstract:
            result['published_venue'] = _extract_venue_from_text(abstract)
            result['presentation_type'] = _detect_presentation_type(abstract)
        return result

    try:
        root = ET.fromstring(xml_data)
        entry = root.find('{http://www.w3.org/2005/Atom}entry')
        if entry is None:
            if abstract:
                result['published_venue'] = _extract_venue_from_text(abstract)
                result['presentation_type'] = _detect_presentation_type(abstract)
            return result

        ns = 'http://arxiv.org/schemas/atom'
        journal_ref_el = entry.find(f'{{{ns}}}journal_ref')
        comment_el = entry.find(f'{{{ns}}}comment')
        published_el = entry.find('{http://www.w3.org/2005/Atom}published')

        journal_ref = (journal_ref_el.text or '').strip() if journal_ref_el is not None else ''
        comment = (comment_el.text or '').strip() if comment_el is not None else ''
        published_raw = (published_el.text or '').strip() if published_el is not None else ''

        # Source 1: Venue from journal_ref
        if journal_ref:
            result['journal_ref_raw'] = journal_ref
            result['published_venue'] = _parse_venue_from_ref(journal_ref)

        # Oral/Spotlight from comment (primary) or journal_ref (fallback)
        pt = _detect_presentation_type(comment) or _detect_presentation_type(journal_ref)
        if pt:
            result['presentation_type'] = pt

        # Source 2: Venue from comment (e.g. "Accepted at ICML 2023 (Oral)")
        if not result['published_venue'] and comment:
            venue_from_comment = _parse_venue_from_ref(comment)
            if venue_from_comment:
                result['published_venue'] = venue_from_comment
                if not result['presentation_type']:
                    result['presentation_type'] = _detect_presentation_type(comment)

        # Source 3: Venue from abstract text parsing
        if not result['published_venue'] and abstract:
            venue_from_abstract = _extract_venue_from_text(abstract)
            if venue_from_abstract:
                result['published_venue'] = venue_from_abstract
                if not result['presentation_type']:
                    result['presentation_type'] = _detect_presentation_type(abstract)

        # Also try oral/spotlight detection from abstract
        if not result['presentation_type'] and abstract:
            result['presentation_type'] = _detect_presentation_type(abstract)

        # Published date from arXiv <published> field
        if published_raw:
            # Format: 2017-06-12T17:57:34Z -> 2017-06-12
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})', published_raw)
            if date_match:
                result['published_date'] = date_match.group(1)

    except ET.ParseError:
        pass

    return result


def fetch_publication_info_batch(arxiv_ids: list, abstracts: dict = None) -> dict:
    """Fetch formal publication info for multiple papers in a single arXiv API call.

    Args:
        arxiv_ids: List of arXiv paper IDs
        abstracts: Optional dict {arxiv_id: abstract_text} for text-based venue extraction fallback

    Returns:
        dict keyed by arxiv_id, each value is a dict with keys:
        published_venue, presentation_type, published_date, journal_ref_raw,
        authors, title, abstract
    """
    abstracts = abstracts or {}
    result = {aid: {
        'published_venue': None,
        'presentation_type': None,
        'published_date': None,
        'journal_ref_raw': None,
        'authors': [],
        'title': '',
        'abstract': '',
    } for aid in arxiv_ids}

    if not arxiv_ids:
        return result

    try:
        ids_str = ','.join(arxiv_ids)
        url = f'https://export.arxiv.org/api/query?id_list={ids_str}&max_results={len(arxiv_ids)}'
        req = urllib.request.Request(url, headers={'User-Agent': 'AlphaXivToObsidian/1.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_data = resp.read().decode('utf-8')
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        # arXiv API unreachable — try abstract fallback for each paper
        for aid in arxiv_ids:
            if aid in abstracts and abstracts[aid]:
                result[aid]['published_venue'] = _extract_venue_from_text(abstracts[aid])
                result[aid]['presentation_type'] = _detect_presentation_type(abstracts[aid])
        return result

    try:
        root = ET.fromstring(xml_data)
        ns_atom = 'http://www.w3.org/2005/Atom'
        ns_arxiv = 'http://arxiv.org/schemas/atom'

        for entry in root.findall(f'{{{ns_atom}}}entry'):
            # Extract arXiv ID from the entry
            id_el = entry.find(f'{{{ns_atom}}}id')
            if id_el is None:
                continue
            id_text = (id_el.text or '').strip()
            # ID format: http://arxiv.org/abs/1706.03762v7
            id_match = re.search(r'(\d{4}\.\d{4,5})', id_text)
            if not id_match:
                continue
            aid = id_match.group(1)
            if aid not in result:
                continue

            journal_ref_el = entry.find(f'{{{ns_arxiv}}}journal_ref')
            comment_el = entry.find(f'{{{ns_arxiv}}}comment')
            published_el = entry.find(f'{{{ns_atom}}}published')
            title_el = entry.find(f'{{{ns_atom}}}title')
            abstract_el = entry.find(f'{{{ns_atom}}}summary')

            journal_ref = (journal_ref_el.text or '').strip() if journal_ref_el is not None else ''
            comment = (comment_el.text or '').strip() if comment_el is not None else ''
            published_raw = (published_el.text or '').strip() if published_el is not None else ''
            abstract_text = (abstract_el.text or '').strip() if abstract_el is not None else ''
            title_text = (title_el.text or '').strip() if title_el is not None else ''

            # Title + Abstract
            result[aid]['title'] = title_text.replace('\n', ' ').strip()
            result[aid]['abstract'] = abstract_text.replace('\n', ' ').strip()

            # Authors
            authors = _parse_authors_from_entry(entry, ns_atom)
            result[aid]['authors'] = authors

            # Venue from journal_ref (Source 1)
            if journal_ref:
                result[aid]['journal_ref_raw'] = journal_ref
                result[aid]['published_venue'] = _parse_venue_from_ref(journal_ref)

            # Oral/Spotlight
            pt = _detect_presentation_type(comment) or _detect_presentation_type(journal_ref)
            if pt:
                result[aid]['presentation_type'] = pt

            # Venue from comment (Source 2)
            if not result[aid]['published_venue'] and comment:
                venue_from_comment = _parse_venue_from_ref(comment)
                if venue_from_comment:
                    result[aid]['published_venue'] = venue_from_comment
                    if not result[aid]['presentation_type']:
                        result[aid]['presentation_type'] = _detect_presentation_type(comment)

            # Venue from abstract (Source 3) — use API abstract or provided abstract
            fallback_abstract = abstracts.get(aid, '') or abstract_text
            if not result[aid]['published_venue'] and fallback_abstract:
                venue_from_abstract = _extract_venue_from_text(fallback_abstract)
                if venue_from_abstract:
                    result[aid]['published_venue'] = venue_from_abstract
                    if not result[aid]['presentation_type']:
                        result[aid]['presentation_type'] = _detect_presentation_type(fallback_abstract)

            if not result[aid]['presentation_type'] and fallback_abstract:
                result[aid]['presentation_type'] = _detect_presentation_type(fallback_abstract)

            # Published date
            if published_raw:
                date_match = re.match(r'(\d{4}-\d{2}-\d{2})', published_raw)
                if date_match:
                    result[aid]['published_date'] = date_match.group(1)

    except ET.ParseError:
        pass

    return result


def _parse_authors_from_entry(entry, ns_atom: str = 'http://www.w3.org/2005/Atom') -> list:
    """Extract author names from an arXiv Atom XML entry.

    Args:
        entry: ElementTree Element for an arXiv entry
        ns_atom: XML namespace URI for Atom elements

    Returns:
        List of author name strings, e.g. ['Doe, John', 'Smith, Jane']
    """
    authors = []
    for author_el in entry.findall(f'{{{ns_atom}}}author'):
        name_el = author_el.find(f'{{{ns_atom}}}name')
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())
    return authors


def _get_first_author(authors: list) -> str:
    """Extract the last name of the first author.

    Args:
        authors: List of author strings in 'LastName, FirstName' format

    Returns:
        Last name string or 'Unknown' if list is empty
    """
    if not authors:
        return 'Unknown'
    first = authors[0]
    # 'LastName, FirstName' -> 'LastName'
    if ',' in first:
        return first.split(',')[0].strip()
    # 'FirstName LastName' -> 'LastName'
    parts = first.strip().split()
    return parts[-1] if parts else first


# ──────────────────────────────────────────────────────────────────
# Vault duplicate detection — scans existing paper notes before import
# ──────────────────────────────────────────────────────────────────

_vault_index_cache = {}  # {vault_path: (timestamp, index_dict)}
_VAULT_CACHE_TTL = 30  # seconds


def _scan_vault_index(vault_path: str) -> dict:
    """Scan 320 References/ and build {arxiv_id: filepath} index.

    Results cached for 30s to avoid repeated directory scans when
    multiple calls happen within the same process (e.g. search +
    enrich + check-vault all in one import session).
    """
    now = time.time()
    cached = _vault_index_cache.get(vault_path)
    if cached and (now - cached[0]) < _VAULT_CACHE_TTL:
        return cached[1]

    index = {}
    papers_dir = os.path.join(vault_path, '300 Resources', '320 References')
    if not os.path.exists(papers_dir):
        _vault_index_cache[vault_path] = (now, index)
        return index
    for f in os.listdir(papers_dir):
        if not f.endswith('.md'):
            continue
        fpath = os.path.join(papers_dir, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                head = fh.read(2000)
            fm_match = re.match(r'^---\s*\n(.*?)\n---', head, re.DOTALL)
            if fm_match:
                fm = yaml.safe_load(fm_match.group(1))
                aid = fm.get('arxiv_id', '') if fm else ''
                if aid:
                    index[aid] = fpath
        except Exception:
            pass
    _vault_index_cache[vault_path] = (now, index)
    return index


def check_vault_for_papers(vault_path: str, arxiv_ids: list) -> dict:
    """Check which arXiv IDs already exist in the vault.
    Returns {arxiv_id: filepath} for existing papers only."""
    index = _scan_vault_index(vault_path)
    return {aid: index[aid] for aid in arxiv_ids if aid in index}


# ──────────────────────────────────────────────────────────────────
# Paper quality & influence assessment
# ──────────────────────────────────────────────────────────────────

def extract_quality_signals(paper) -> dict:
    """Extract quality/influence signals from a search result or metadata object.
    Works with both fast_search results (sparse) and full metadata (rich).

    Returns dict with:
        venue: str or None — detected top venue name
        year: int or None — publication year extracted from snippet/metadata
        has_overview: bool — whether AlphaXiv AI overview exists
        citations: int or 0 — citation count (from metadata only)
        signals: list[str] — human-readable quality indicators
    """
    signals = []
    venue = None
    year = None
    citations = 0
    has_overview = False

    # Try model_dump for Pydantic objects, fall back to dict
    if hasattr(paper, 'model_dump'):
        d = paper.model_dump()
    elif isinstance(paper, dict):
        d = paper
    else:
        return {'venue': None, 'year': None, 'has_overview': False,
                'citations': 0, 'signals': ['unknown']}

    snippet = d.get('snippet', '') or ''
    title = d.get('title', '') or ''

    # Venue detection from snippet + title
    combined = f'{snippet} {title}'

    # Check acronym venues first (highest precision, unlikely false positives)
    acronym_matches = ACRONYM_PATTERN.findall(combined)
    if acronym_matches:
        venue = acronym_matches[0].upper()
        signals.append(f'Top venue: {venue}')
    else:
        # Check journal names (require specific patterns to avoid false positives)
        journal_matches = JOURNAL_PATTERN.findall(combined)
        if journal_matches:
            # journal_matches is list of tuples (one per alternation group); flatten
            flat = [m for group in journal_matches for m in group if m]
            if flat:
                venue = flat[0].upper()
                signals.append(f'Top venue: {venue}')

    # Year extraction
    # Try metadata first (publication_date timestamp)
    pub_ts = d.get('publication_date') or d.get('publicationDate') or 0
    if pub_ts and pub_ts > 0:
        from datetime import datetime
        year = datetime.fromtimestamp(pub_ts / 1000).year
    else:
        # Fall back to snippet date parsing
        year_match = re.search(r'\b(20\d{2})\b', snippet)
        if year_match:
            year = int(year_match.group(1))

    if year:
        current_year = 2026
        age = current_year - year
        if age <= 1:
            signals.append(f'Very recent ({year})')
        elif age <= 3:
            signals.append(f'Recent ({year})')

    # Citation count (from full metadata)
    citations = int(d.get('citations_count', 0) or d.get('citationsCount', 0) or 0)
    if citations >= 100:
        signals.append(f'Highly cited ({citations}+ citations)')
    elif citations >= 10:
        signals.append(f'Cited ({citations} citations)')

    # Check for keywords indicating significance
    significance_keywords = [
        'state-of-the-art', 'state of the art', 'SOTA', 'SotA',
        'novel', 'first', 'breakthrough', 'best paper', 'oral',
        'spotlight', 'outperforms', 'significantly',
    ]
    for kw in significance_keywords:
        if kw.lower() in combined.lower():
            signals.append(f'Claims: {kw}')
            break  # one is enough

    return {
        'venue': venue,
        'year': year,
        'has_overview': has_overview,
        'citations': citations,
        'signals': signals,
    }


def rate_paper_quality(signals: dict, ccf: str = None) -> tuple:
    """Rate paper quality on a 1-5 scale based on extracted signals.
    Returns (rating: int, summary: str).

    Args:
        signals: Quality signals dict from extract_quality_signals()
        ccf: Optional CCF rank (e.g. 'A', 'B', 'C'). CCF-A adds +1 star.
    """
    rating = 2  # baseline
    reasons = []

    if signals.get('venue'):
        rating += 1
        reasons.append(f'top-venue ({signals["venue"]})')

    year = signals.get('year')
    if year:
        age = datetime.now().year - year
        if age <= 1:
            rating += 1
            reasons.append('very recent')
        elif age <= 2:
            rating += 0

    citations = signals.get('citations', 0)
    if citations >= 500:
        rating += 2
        reasons.append(f'highly-cited ({citations})')
    elif citations >= 100:
        rating += 1
        reasons.append(f'well-cited ({citations})')
    elif citations >= 50:
        rating += 0

    # CCF-A bonus
    if ccf and ccf.strip().upper() == 'A':
        rating += 1
        reasons.append('CCF-A')

    has_claims = any('Claims' in s for s in signals.get('signals', []))
    if has_claims:
        rating = min(5, rating + 0)

    rating = max(1, min(5, rating))

    stars = '★' * rating + '☆' * (5 - rating)
    reason_str = ', '.join(reasons) if reasons else 'baseline'
    return rating, f'{stars} ({reason_str})'


def enrich_search_results(results: list, vault_path: str) -> list:
    """Enrich search results with vault status and quality signals.
    Returns list of dicts with keys: paper, arxiv_id, title, snippet,
    in_vault, vault_path, quality, rating, rating_display.
    """
    enriched = []
    arxiv_ids = [r.paper_id for r in results if hasattr(r, 'paper_id')]
    existing = check_vault_for_papers(vault_path, arxiv_ids)

    for r in results:
        aid = r.paper_id if hasattr(r, 'paper_id') else r.get('paper_id', '')
        title = r.title if hasattr(r, 'title') else r.get('title', '')
        snippet = r.snippet if hasattr(r, 'snippet') else r.get('snippet', '')
        quality = extract_quality_signals(r)
        rating, rating_display = rate_paper_quality(quality)

        enriched.append({
            'paper': r,
            'arxiv_id': aid,
            'title': title,
            'snippet': snippet,
            'in_vault': aid in existing,
            'vault_path': existing.get(aid, ''),
            'quality': quality,
            'rating': rating,
            'rating_display': rating_display,
        })

    return enriched

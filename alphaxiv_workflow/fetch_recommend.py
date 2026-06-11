"""
Fetch recommended papers from AlphaXiv Recommended page.
Scrapes arxiv IDs from the server-rendered HTML, then enriches via batch arXiv API.

Usage:
    python fetch_recommend_papers.py                    # PrettyTable display
    python fetch_recommend_papers.py --json             # JSON output for piping
    python fetch_recommend_papers.py --limit 10         # Top N only
    python fetch_recommend_papers.py /path/to/vault     # With vault duplicate detection
    python fetch_recommend_papers.py /path/to/vault --data-file /tmp/recommend_papers.json
"""
import asyncio
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime

from prettytable import PrettyTable

from .api import (
    fetch_publication_info_batch,
    rate_paper_quality,
    _get_first_author,
    check_vault_for_papers,
)
from .note_builder import clean_title


# ──────────────────────────────────────────────────────────────────
# Scraping
# ──────────────────────────────────────────────────────────────────

ALPHAXIV_RECOMMEND_URL = 'https://www.alphaxiv.org/?sort=Recommended'
ARXIV_ID_RE = re.compile(r'(\d{4}\.\d{4,5})')


def fetch_recommend_ids() -> list:
    """Scrape arxiv IDs from AlphaXiv Recommended page HTML.

    The Recommended page is server-rendered and contains paper IDs in the HTML.
    Returns deduplicated, sorted list of arxiv IDs.
    """
    req = urllib.request.Request(
        ALPHAXIV_RECOMMEND_URL,
        headers={'User-Agent': 'AlphaXivToObsidian/1.0 (recommend-papers)'}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8')
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f'❌ Failed to fetch {ALPHAXIV_RECOMMEND_URL}: {e}', file=sys.stderr)
        sys.exit(1)

    ids = sorted(set(ARXIV_ID_RE.findall(html)))
    if not ids:
        print('❌ No arxiv IDs found on AlphaXiv Recommended page.', file=sys.stderr)
        sys.exit(1)

    return ids


# ──────────────────────────────────────────────────────────────────
# Enrichment (reuses alphaxiv_client batch pipeline)
# ──────────────────────────────────────────────────────────────────

def enrich_recommend_papers(arxiv_ids: list, vault_path: str = None) -> list:
    """Enrich recommended paper IDs with arXiv metadata.

    Returns list of dicts with keys matching gate01_search export format:
    arxiv_id, title, first_author, venue, ccf, arxiv_date, overview, etc.
    """
    if not arxiv_ids:
        return []

    # Batch fetch from arXiv API
    abstracts = {}
    pub_infos = fetch_publication_info_batch(arxiv_ids, abstracts)

    # Vault check
    existing = {}
    if vault_path and os.path.exists(vault_path):
        existing = check_vault_for_papers(vault_path, arxiv_ids)

    results = []
    for aid in arxiv_ids:
        pi = pub_infos.get(aid, {})
        venue = pi.get('published_venue', '') or ''
        authors = pi.get('authors', [])
        first_author = _get_first_author(authors) if authors else 'Unknown'

        # Quality rating without CCF (no EasyScholar calls for recommend page — fast display)
        quality = {}
        rating, rating_display = rate_paper_quality(quality)

        # Conference date from venue
        if venue:
            ym = re.search(r'\b(20\d{2})\b', venue)
            conf_date = ym.group(1) if ym else '—'
        else:
            conf_date = '—'

        results.append({
            'arxiv_id': aid,
            'title': clean_title(pi.get('title', '') or ''),
            'first_author': first_author,
            'venue': venue,
            'presentation_type': pi.get('presentation_type', '') or '',
            'ccf': '',
            'arxiv_date': pi.get('published_date', '') or '',
            'conf_date': conf_date,
            'rating': rating,
            'rating_display': rating_display,
            'in_vault': aid in existing,
            'vault_path': existing.get(aid, ''),
            'overview': None,
            'quality': quality,
            'pub_info': pi,
        })

    return results


# ──────────────────────────────────────────────────────────────────
# Table rendering
# ──────────────────────────────────────────────────────────────────

def build_table(results: list) -> PrettyTable:
    """Build PrettyTable for recommended papers display."""
    table = PrettyTable()
    table.field_names = [
        '#', '评级', '状态', 'arXiv ID', '标题', '一作',
        '发表venue', 'CCF', '会议日期', 'arXiv日期',
    ]
    table.align = 'l'
    table.align['#'] = 'r'
    table.max_width['标题'] = 55
    table.max_width['发表venue'] = 28
    table.max_width['arXiv ID'] = 12

    for i, p in enumerate(results, 1):
        aid = p['arxiv_id']
        title = p.get('title', '') or ''
        stars = p['rating_display']

        # Status
        status_parts = ['新'] if not p.get('in_vault') else ['已保存 ✓']
        status = ' '.join(status_parts)

        # Venue display
        venue = p.get('venue', '') or ''
        pres_type = p.get('presentation_type', '') or ''
        venue_display = f'{venue} ({pres_type})' if venue and pres_type else (venue or '—')

        table.add_row([
            i, stars, status, aid, title,
            p.get('first_author', '—'), venue_display, '—',
            p.get('conf_date', '—'), p.get('arxiv_date', '—'),
        ])

    return table


def export_json(results: list) -> list:
    """Export recommended papers as JSON-serializable list for AI handoff."""
    output = []
    for p in results:
        pi = p.get('pub_info', {}) or {}
        authors = pi.get('authors', []) if pi else []
        output.append({
            'arxiv_id': p['arxiv_id'],
            'title': p.get('title', ''),
            'in_vault': p.get('in_vault', False),
            'vault_path': p.get('vault_path', ''),
            'rating': p['rating'],
            'rating_display': p['rating_display'],
            'first_author': _get_first_author(authors),
            'venue': pi.get('published_venue', '') or '',
            'presentation_type': pi.get('presentation_type', '') or '',
            'ccf': p.get('ccf', '') or '',
            'arxiv_date': pi.get('published_date', '') or '',
            'overview': p.get('overview'),
        })
    return output


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Fetch recommended papers from AlphaXiv Recommended page'
    )
    parser.add_argument(
        'vault_path', nargs='?', default=None,
        help='Obsidian vault root path (for duplicate detection)'
    )
    parser.add_argument(
        '--limit', type=int, default=0,
        help='Limit to top N papers (0 = all)'
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Output JSON instead of table'
    )
    parser.add_argument(
        '--data-file',
        help='Save processed data as JSON (for AI handoff)'
    )
    parser.add_argument(
        '--ids-only', action='store_true',
        help='Output only arxiv IDs (one per line) for piping'
    )
    args = parser.parse_args()

    # Step 1: Scrape IDs
    print('🎯 获取 AlphaXiv 推荐论文...', file=sys.stderr)
    ids = fetch_recommend_ids()
    if args.limit and args.limit > 0:
        ids = ids[:args.limit]
    print(f'🎯 获取到 {len(ids)} 篇推荐论文', file=sys.stderr)

    # IDs-only mode: simple output for piping to other scripts
    if args.ids_only:
        for aid in ids:
            print(aid)
        return

    # Step 2: Enrich with arXiv metadata
    print(f'📄 批量获取 arXiv 元数据 ({len(ids)} 篇)...', file=sys.stderr)
    results = enrich_recommend_papers(ids, args.vault_path)

    # JSON mode
    if args.json:
        print(json.dumps(export_json(results), ensure_ascii=False, indent=2))
        return

    # Save data file if requested
    if args.data_file:
        with open(args.data_file, 'w', encoding='utf-8') as f:
            json.dump(export_json(results), f, ensure_ascii=False, indent=2)

    # Table output
    table = build_table(results)
    print(table)
    print()
    print('🎯 AlphaXiv 推荐论文 — 基于个性化推荐算法排序')
    print('标记: 已保存 ✓ = vault 中已存在')
    print()
    print('评级说明: ★ = 基准预印本, ★★-★★★ = 有发表信号, ★★★★-★★★★★ = 顶会+高引用')
    print()


if __name__ == '__main__':
    main()

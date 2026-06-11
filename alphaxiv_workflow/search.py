"""
Gate 1: Search & Disambiguate — standalone script for paper search with
publication info display. Outputs PrettyTable with venue, CCF, dates, first author.

Usage:
    python gate01_search.py "diffusion models" /path/to/vault
    python gate01_search.py "diffusion models" /path/to/vault --limit 5
    python gate01_search.py "diffusion models" /path/to/vault --json  # machine output

Handoff: use --data-file to save processed results for AI consumption.
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime

from prettytable import PrettyTable

from .api import (
    search_papers,
    search_with_operators,
    enrich_search_results,
    fetch_publication_info_batch,
    rate_paper_quality,
    get_paper_metadata,
    get_overview,
    _get_first_author,
)
from .note_builder import clean_title
from .venue import get_venue_ranking


# ──────────────────────────────────────────────────────────────────
# Progress logging
# ──────────────────────────────────────────────────────────────────

_log_stream = sys.stdout


def log(msg: str):
    """Print progress message with flush for real-time output.
    Redirects to stderr when --json mode is active to keep stdout clean.
    """
    print(msg, flush=True, file=_log_stream)


# ──────────────────────────────────────────────────────────────────
# Async helpers
# ──────────────────────────────────────────────────────────────────

async def check_overview_async(version_id: str) -> str | None:
    """Check if any language overview exists for a paper version.

    Returns 'en', 'zh', 'enzh', or None (no overview found).
    """
    if not version_id:
        return None
    has_en = False
    has_zh = False
    try:
        en = await asyncio.to_thread(get_overview, version_id, 'en')
        if en is not None and hasattr(en, 'model_dump'):
            d = en.model_dump()
            has_en = bool(d.get('overview', '') and len(d['overview']) > 50)
    except Exception:
        pass
    try:
        zh = await asyncio.to_thread(get_overview, version_id, 'zh')
        if zh is not None and hasattr(zh, 'model_dump'):
            d = zh.model_dump()
            has_zh = bool(d.get('overview', '') and len(d['overview']) > 50)
    except Exception:
        pass
    if has_en and has_zh:
        return 'enzh'
    elif has_en:
        return 'en'
    elif has_zh:
        return 'zh'
    return None


async def fetch_ranking_async(venue: str, sem: asyncio.Semaphore) -> dict:
    """Async wrapper for EasyScholar ranking with rate limiting.

    Args:
        venue: Normalized venue name (e.g. 'NeurIPS')
        sem: Semaphore to serialize EasyScholar API calls (0.6s rate limit)

    Returns:
        Ranking dict from extract_ranking_fields()
    """
    venue_abbrev = venue.strip().split()[0] if venue and venue.strip() else ''
    if not venue_abbrev:
        return {}
    async with sem:
        return await asyncio.to_thread(get_venue_ranking, venue_abbrev)


# ──────────────────────────────────────────────────────────────────
# Pipeline stages
# ──────────────────────────────────────────────────────────────────

async def process_paper(
    paper: dict,
    pub_info: dict,
    sem: asyncio.Semaphore,
    idx: int,
    total: int,
) -> dict:
    """Process a single paper through metadata → overview → ranking pipeline.

    Args:
        paper: Enriched search result dict
        pub_info: Pre-fetched publication info from batch arXiv call
        sem: Semaphore for EasyScholar rate limiting
        idx: 1-based index for progress display
        total: Total paper count
    """
    aid = paper['arxiv_id']
    result = {**paper, 'pub_info': pub_info, 'ccf': '', 'overview': None}

    try:
        # Step 1: Metadata (for version_id + citations)
        meta = await asyncio.to_thread(get_paper_metadata, aid)
        paper['meta'] = meta

        # Update citations from full metadata
        citations = 0
        if hasattr(meta, 'model_dump'):
            citations = meta.model_dump().get('citations_count', 0) or 0
        elif isinstance(meta, dict):
            citations = meta.get('citations_count', 0) or 0
        if citations:
            quality = paper.get('quality', {})
            quality['citations'] = citations

        # Step 2: Overview check
        version_id = (
            meta.version_id if hasattr(meta, 'version_id')
            else meta.get('version_id', '')
        )
        result['overview'] = await check_overview_async(version_id)

        # Step 3: EasyScholar ranking (rate-limited by semaphore)
        venue = pub_info.get('published_venue', '') or ''
        if venue:
            try:
                rank = await fetch_ranking_async(venue, sem)
                result['ccf'] = (rank or {}).get('ccf', '') or ''
            except Exception as e:
                log(f'  ⚠️ [{idx}/{total}] {aid} ranking: {e}')

        # Progress
        ov_tag = '⚡' if result['overview'] else '  '
        ccf_tag = f'CCF-{result["ccf"]}' if result['ccf'] else '—'
        log(f'  ✅ [{idx}/{total}] {aid} {ov_tag} {ccf_tag}')

    except Exception as e:
        log(f'  ⚠️ [{idx}/{total}] {aid} — {e}')

    return result


async def main_async(query: str, vault_path: str, limit: int = 10):
    """Main async pipeline: search → batch arXiv → parallel pipeline → table output.

    Returns list of processed paper dicts, or None if no results found.
    """
    # ── Phase 1: Search (with boolean operator support) ──
    log(f'🔍 搜索中: "{query}"')
    t0 = datetime.now()
    results, qinfo = search_with_operators(query, limit=limit)
    if qinfo.get('error'):
        log(f'  ⚠️  布尔检索解析失败: {qinfo["error"]}')
        log(f'  ℹ️  已回退至普通搜索')
    if not results:
        if qinfo.get('operators_used'):
            log(f'  ℹ️  布尔检索解析: {qinfo.get("parsed", "")}')
        log('❌ 未找到结果。请尝试更短的查询或直接输入 arXiv ID。')
        return None
    if qinfo.get('operators_used'):
        log(f'  🔣 布尔检索: {qinfo.get("strategy", "")}')
    log(f'🔍 搜索到 {len(results)} 条结果 ({_elapsed(t0)})')

    # ── Phase 2: Enrich (vault status + snippet quality) ──
    enriched = enrich_search_results(results, vault_path)
    arxiv_ids = [e['arxiv_id'] for e in enriched]
    abstracts = {e['arxiv_id']: e.get('snippet', '') for e in enriched}

    # ── Phase 3: Batch arXiv API ──
    log(f'📄 批量获取 arXiv 元数据 ({len(arxiv_ids)} 篇)...')
    t1 = datetime.now()
    pub_infos = await asyncio.to_thread(fetch_publication_info_batch, arxiv_ids, abstracts)
    log(f'📄 arXiv 批量获取完成 ({_elapsed(t1)})')

    # ── Phase 4: Parallel pipeline ──
    log(f'🔄 论文处理中...')
    t2 = datetime.now()
    sem = asyncio.Semaphore(1)  # Serialize EasyScholar calls

    tasks = []
    for i, e in enumerate(enriched):
        aid = e['arxiv_id']
        pi = pub_infos.get(aid, {})
        tasks.append(process_paper(e, pi, sem, i + 1, len(enriched)))

    processed = await asyncio.gather(*tasks)
    log(f'🔄 处理完成 ({_elapsed(t2)})')

    # ── Phase 5: Re-rate with CCF + updated citations ──
    for p in processed:
        quality = p.get('quality', {})
        ccf = p.get('ccf', '') or ''
        rating, rating_display = rate_paper_quality(quality, ccf=ccf)
        p['rating'] = rating
        p['rating_display'] = rating_display

    return processed


# ──────────────────────────────────────────────────────────────────
# Table rendering
# ──────────────────────────────────────────────────────────────────

def build_table(processed: list) -> PrettyTable:
    """Build PrettyTable from processed paper data."""
    table = PrettyTable()
    table.field_names = [
        '#', '评级', '状态', 'arXiv ID', '标题', '一作',
        '发表venue', 'CCF', '会议日期', 'arXiv日期',
    ]
    table.align = 'l'
    table.align['#'] = 'r'

    # Column sizing
    table.max_width['标题'] = 55
    table.max_width['发表venue'] = 28
    table.max_width['arXiv ID'] = 12

    for i, p in enumerate(processed, 1):
        aid = p['arxiv_id']
        title = clean_title(p['title'])[:80]
        stars = p['rating_display']

        # Status column
        status_parts = []
        if p.get('in_vault'):
            status_parts.append('已保存 ✓')
        else:
            status_parts.append('新')
        ov = p.get('overview')
        if ov:
            status_parts.append('⚡')
        status = ' '.join(status_parts)

        # First author
        authors = p.get('pub_info', {}).get('authors', []) if p.get('pub_info') else []
        first_author = _get_first_author(authors)

        # Venue
        pub_info = p.get('pub_info', {}) or {}
        venue = pub_info.get('published_venue', '') or ''
        pres_type = pub_info.get('presentation_type', '') or ''
        if venue:
            venue_display = f'{venue} ({pres_type})' if pres_type else venue
        else:
            venue_display = '—'

        # CCF
        ccf = p.get('ccf', '') or ''
        ccf_display = f'CCF-{ccf}' if ccf else '—'

        # Conference date (year from venue)
        if venue:
            ym = re.search(r'\b(20\d{2})\b', venue)
            conf_date = ym.group(1) if ym else '—'
        else:
            conf_date = '—'

        # arXiv date
        arxiv_date = pub_info.get('published_date', '') or '—'

        table.add_row([
            i, stars, status, aid, title,
            first_author, venue_display, ccf_display,
            conf_date, arxiv_date,
        ])

    return table


def print_legend():
    """Print rating legend and status key."""
    print()
    print('评级说明 (1-5 ★):')
    print('  ★★★★★  卓越 — 顶会发表 + CCF-A + 高引用 + 近期')
    print('  ★★★★☆  优秀 — 多项正面信号')
    print('  ★★★☆☆  良好 — 至少一项显著信号')
    print('  ★★☆☆☆  基准 — 标准预印本')
    print('  ★☆☆☆☆  低信号 — 较旧、无发表、无引用')
    print()
    print('标记: 已保存 ✓ = vault 中已存在, ⚡ = AlphaXiv AI overview 可用')
    print()


def export_json(processed: list) -> list:
    """Export processed papers as JSON-serializable dicts."""
    output = []
    for p in processed:
        pub_info = p.get('pub_info', {}) or {}
        authors = pub_info.get('authors', []) if pub_info else []
        output.append({
            'arxiv_id': p['arxiv_id'],
            'title': p['title'],
            'in_vault': p.get('in_vault', False),
            'vault_path': p.get('vault_path', ''),
            'rating': p['rating'],
            'rating_display': p['rating_display'],
            'first_author': _get_first_author(authors),
            'venue': pub_info.get('published_venue', '') or '',
            'presentation_type': pub_info.get('presentation_type', '') or '',
            'ccf': p.get('ccf', '') or '',
            'arxiv_date': pub_info.get('published_date', '') or '',
            'overview': p.get('overview'),
            'quality': p.get('quality', {}),
        })
    return output


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────

def _elapsed(t: datetime) -> str:
    """Format elapsed time from start timestamp."""
    return f'{(datetime.now() - t).total_seconds():.1f}s'


def main():
    """CLI entry point for Gate 1 search."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Gate 1: Search papers with publication info (venue, CCF, dates)'
    )
    parser.add_argument('query', help='Search query or arXiv ID')
    parser.add_argument('vault_path', help='Obsidian vault root path')
    parser.add_argument(
        '--limit', type=int, default=10,
        help='Maximum results (default: 10)'
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Output JSON instead of table'
    )
    parser.add_argument(
        '--data-file',
        help='Save processed data as JSON to this file (for AI handoff)'
    )
    args = parser.parse_args()

    # JSON mode: redirect progress logs to stderr to keep stdout clean
    if args.json:
        global _log_stream
        _log_stream = sys.stderr

    processed = asyncio.run(main_async(args.query, args.vault_path, args.limit))

    if processed is None:
        sys.exit(1)

    if args.json:
        print(json.dumps(export_json(processed), ensure_ascii=False, indent=2))
        return

    # Save data file if requested
    if args.data_file:
        with open(args.data_file, 'w', encoding='utf-8') as f:
            json.dump(export_json(processed), f, ensure_ascii=False, indent=2)

    # Print table
    table = build_table(processed)
    print(table)
    print_legend()


if __name__ == '__main__':
    main()

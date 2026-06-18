"""
Note builder - constructs structured Obsidian markdown notes from AlphaXiv data.
Handles title validation, citation formatting, degradation, and all markdown rendering.
"""
import re
import os
from datetime import datetime

from .venue import classify_venue_type, extract_pub_year


def parse_bibtex_pub_fields(bibtex: str) -> dict:
    """Parse BibTeX for publication info fields not covered by arXiv API.

    Extracts: booktitle, journal, year, publisher, school, volume, number, pages.
    These serve as Source 5 fallback when arXiv API provides no venue.

    Returns dict with: bib_booktitle, bib_journal, bib_year, bib_publisher,
        bib_school, bib_volume, bib_number, bib_pages.
    All None when BibTeX is empty or unparseable.
    """
    result = {
        'bib_booktitle': None, 'bib_journal': None, 'bib_year': None,
        'bib_publisher': None, 'bib_school': None,
        'bib_volume': None, 'bib_number': None, 'bib_pages': None,
    }
    if not bibtex:
        return result
    for key in result:
        field = key.removeprefix('bib_')
        m = re.search(rf'{field}\s*=\s*\{{(.+?)\}}', bibtex)
        if m:
            result[key] = m.group(1).strip()
    return result


# arXiv category mapping for readable tags
CATEGORY_MAP = {
    "cs.CL": "nlp", "cs.AI": "ai", "cs.LG": "machine-learning",
    "cs.CV": "computer-vision", "cs.RO": "robotics", "cs.HC": "hci",
    "cs.IR": "information-retrieval", "cs.NE": "neural-networks",
    "cs.SE": "software-engineering", "cs.DB": "databases",
    "cs.CR": "security", "cs.SD": "systems", "cs.DC": "distributed-systems",
    "cs.DS": "data-structures", "cs.GT": "game-theory", "cs.CC": "complexity",
    "cs.IT": "information-theory", "cs.MA": "multi-agent",
    "cs.MM": "multimedia", "cs.NI": "networking", "cs.OS": "operating-systems",
    "cs.PL": "programming-languages", "cs.SI": "social-networks",
    "stat.ML": "statistics", "math.OC": "optimization",
    "q-bio": "biology", "q-fin": "finance", "physics": "physics",
    "eess": "engineering",
}

TITLE_SUFFIX_PATTERNS = [
    r'\s*-\s*arXiv$',
    r'\s*\.\.\.\s*$',
    r'\s*\.\.\.\s*-\s*arXiv$',
]


def clean_title(title: str) -> str:
    """Clean API title: collapse newlines, remove [arxiv_id] prefix, -arXiv suffix, truncation dots."""
    cleaned = re.sub(r'[\n\r]+', ' ', title)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    cleaned = re.sub(r'^\[\d{4}\.\d{4,5}(v\d+)?\]\s*', '', cleaned)
    for pattern in TITLE_SUFFIX_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned)
    return cleaned.strip()


def sanitize_filename(title: str) -> str:
    """Create safe filename from paper title: safe chars, normalized whitespace, <=100 chars."""
    safe = clean_title(title)
    safe = re.sub(r'[\\/:*?"<>|]', '', safe)
    safe = re.sub(r'[\n\r\t]', ' ', safe)
    safe = safe.strip()
    return safe[:100].strip()


def check_title_issues(title: str, vault_path: str) -> list:
    """Check title compliance. Returns list of (severity, message)."""
    issues = []
    cleaned = clean_title(title)
    if title.endswith('...') or '... - arXiv' in title:
        issues.append(('warn', f'Title appears truncated: "{title[:80]}..."'))
    if re.match(r'^\[\d{4}\.\d{4,5}\]', cleaned):
        issues.append(('warn', 'Title still contains arXiv ID prefix after cleaning'))
    filename = sanitize_filename(title) + '.md'
    target_path = os.path.join(vault_path, '300 Resources', '320 References', filename)
    if os.path.exists(target_path):
        issues.append(('block', f'File already exists: {filename}'))
    if len(filename) > 100:
        issues.append(('info', f'Filename truncated from {len(title)} to 100 chars'))
    return issues


def format_citations(citations: list) -> str:
    """Format citations as markdown. Safely handles None field values."""
    if not citations:
        return ''
    lines = []
    for i, c in enumerate(citations, 1):
        if isinstance(c, dict):
            title = c.get('title', 'Untitled')
            raw_link = c.get('alphaxiv_link') or c.get('alphaxivLink') or ''
            justification = c.get('justification', '')
        else:
            title = getattr(c, 'title', 'Untitled')
            raw_link = getattr(c, 'alphaxiv_link', None) or getattr(c, 'alphaxivLink', None) or ''
            justification = getattr(c, 'justification', '')
        link = raw_link.replace('/paper/', '/abs/') if raw_link else ''
        lines.append(f'{i}. **{title}**')
        if link:
            lines.append(f'   - [AlphaXiv]({link})')
        if justification:
            lines.append(f'   - {justification}')
        lines.append('')
    return '\n'.join(lines)


def extract_tags(meta: dict) -> list:
    """Extract base tags from arXiv categories. Content tags added by LLM in Gate 3."""
    tags = ['paper', 'alphaxiv']
    categories = meta.get('categories', []) or meta.get('subjects', [])
    if categories:
        if isinstance(categories[0], dict):
            categories = [c.get('name', c.get('code', '')) for c in categories]
        for cat in categories:
            if cat in CATEGORY_MAP:
                tags.append(CATEGORY_MAP[cat])
            elif '.' not in str(cat):
                tags.append(str(cat).lower().replace(' ', '-'))
    return list(dict.fromkeys(tags))


def demote_headings(text: str, under_level: int = 2) -> str:
    """Demote headings to nest properly under a parent section.

    Finds the highest (shallowest) heading level in the text, then adds
    enough '#' to push the shallowest heading to `under_level + 1`.

    Example: text has '# H1' and '## H2', under_level=2 (parent is H2)
      → shallowest = 1, need to add (2+1-1) = 2 levels
      → '# H1' → '### H3', '## H2' → '#### H4'

    Example: text has '## H2' only, under_level=2
      → shallowest = 2, need to add (2+1-2) = 1 level
      → '## H2' → '### H3'

    Args:
        text: Markdown text with headings to demote.
        under_level: Heading level of the parent section (default 2 for H2).
    """
    if not text:
        return text

    # Find the minimum heading level in the text
    headings = re.findall(r'^(#+) ', text, re.MULTILINE)
    if not headings:
        return text

    min_level = min(len(h) for h in headings)
    target_level = under_level + 1
    add_levels = target_level - min_level

    if add_levels <= 0:
        return text  # Already deep enough

    prefix = '#' * add_levels
    return re.sub(r'^(#+) ', prefix + r'\1 ', text, flags=re.MULTILINE)


def resolve_authors(meta: dict, bibtex: str) -> list:
    """Resolve authors from BibTeX, fallback to metadata authors."""
    authors = []
    author_match = re.search(r'author\s*=\s*\{(.+?)\}', bibtex)
    if author_match:
        authors = [a.strip() for a in author_match.group(1).split(' and ')]
    if not authors:
        meta_authors = meta.get('authors', [])
        if meta_authors:
            if isinstance(meta_authors[0], dict):
                authors = [a.get('name', '') for a in meta_authors]
            else:
                authors = [str(a) for a in meta_authors]
    return authors


def build_summary_sections(summary: dict, titles: dict) -> str:
    """Build AI summary sections from API summary data."""
    if not isinstance(summary, dict):
        return ''
    field_order = [
        ('summary', titles.get('summary', 'AI 摘要'), True),
        ('key_insights', titles.get('takeaways', '关键洞察'), False),
        ('original_problem', titles.get('problem', '问题背景'), False),
        ('solution', titles.get('method', '方法'), False),
        ('results', titles.get('results', '结果'), False),
    ]
    parts = []
    for field, label, is_main in field_order:
        val = summary.get(field, [])
        if isinstance(val, list):
            val = [v for v in val if v]
        if not val:
            continue
        heading = '###'  # always H3 — nested under ## 摘要
        parts.append(f'{heading} {label}')
        if isinstance(val, list):
            for item in val:
                parts.append(f'- {item}')
        else:
            parts.append(str(val))
        parts.append('')
    return '\n'.join(parts)


def format_ai_summary_from_model(overview_model) -> str:
    """Convert AlphaXiv OverviewRetrieveResponse Pydantic model to AI 摘要 markdown.

    Safety wrapper: handles both Pydantic models and pre-dumped dicts.
    CRITICAL: NEVER call str() or f-string on overview_model.summary directly —
    the Pydantic Summary.__repr__() produces unreadable 'Summary(key_insights=[...])' text.

    NOTE: This is a documented utility for LLM agents following SKILL.md instructions.
    It is not called by any production Python pipeline — scripts that need summary
    formatting currently do so inline. Consolidating callers to use this wrapper is
    tracked as a future cleanup.
    """
    if overview_model is None:
        return ''
    # Accept both Pydantic model and dict
    if hasattr(overview_model, 'model_dump'):
        d = overview_model.model_dump()
    elif isinstance(overview_model, dict):
        d = overview_model
    else:
        return ''
    return build_summary_sections(d.get('summary', {}), d.get('summary_section_titles', {}) or {})


def build_note(metadata, overview_zh, overview_en=None, pub_info=None, pub_rank=None) -> tuple:
    """
    Build complete Obsidian markdown note.
    Returns (note_content: str, warnings: list).
    Degradation: CN empty -> fallback EN -> mark incomplete.

    pub_info: dict from fetch_publication_info() with keys:
        published_venue, presentation_type, published_date, journal_ref_raw
    pub_rank: dict from fetch_publication_rank() with keys:
        ccf, sci_jcr, sci_cas, sci_cas_small, sci_cas_top,
        fms, utd24, ft50, swufe, pku, cssci, cscd, eii, custom_ranks
    """
    meta = metadata.model_dump()
    zh = overview_zh.model_dump() if overview_zh else {}
    en = overview_en.model_dump() if overview_en else {}
    pub = pub_info or {}
    rank = pub_rank or {}
    warnings = []

    title = meta.get('title', 'Unknown')
    title_clean = clean_title(title)
    title_escaped = title_clean.replace('"', '\\"')  # prevent YAML injection
    arxiv_id = meta.get('universal_id', meta.get('universalId', ''))
    version = meta.get('version_label', meta.get('versionLabel', ''))
    pub_date_ts = meta.get('publication_date', meta.get('publicationDate', 0))
    pub_date = datetime.fromtimestamp(pub_date_ts / 1000).strftime('%Y-%m-%d') if pub_date_ts else 'Unknown'
    arxiv_url = f'https://arxiv.org/abs/{arxiv_id}'
    alphaxiv_url = f'https://alphaxiv.org/abs/{arxiv_id}'
    abstract = re.sub(r'\s+', ' ', meta.get('abstract', '')).strip()

    bibtex = meta.get('citation_bibtex', meta.get('citationBibtex', ''))
    authors = resolve_authors(meta, bibtex)
    if not authors:
        warnings.append('No authors found in BibTeX or metadata')
    authors_yaml = '\n  - '.join(authors)

    tags = extract_tags(meta)

    zh_overview = zh.get('overview', '')
    zh_summary = zh.get('summary', {})
    zh_citations = zh.get('citations', [])

    summary_titles = zh.get('summary_section_titles', {}) or {}
    overview_titles = zh.get('overview_section_titles', {}) or {}
    ai_tooltips = zh.get('ai_tooltips', {}) or {}
    ai_disclaimer = ai_tooltips.get('ai_generated_content', ai_tooltips.get('aiGeneratedContent', ''))

    # Publication info from arXiv API
    published_venue = pub.get('published_venue') or ''
    presentation_type = pub.get('presentation_type') or ''
    formal_pub_date = pub.get('published_date') or ''

    # BibTeX fallback for missing venue (Source 5)
    bib_fields = parse_bibtex_pub_fields(bibtex)
    if not published_venue:
        bib_venue = bib_fields.get('bib_booktitle') or bib_fields.get('bib_journal')
        if bib_venue:
            bib_year = bib_fields.get('bib_year')
            published_venue = f'{bib_venue} {bib_year}'.strip() if bib_year else bib_venue
        elif bib_fields.get('bib_school'):
            published_venue = bib_fields.get('bib_school')

    # Venue type classification
    venue_type = classify_venue_type(published_venue) if published_venue else None

    # Extract pub year from venue (NeurIPS 2020 → 2020) — fallback for formal_pub_date
    venue_pub_year = extract_pub_year(published_venue) if published_venue else None
    if not formal_pub_date and venue_pub_year:
        formal_pub_date = venue_pub_year

    # Degradation: Chinese overview empty -> try English
    blog_pending = False
    overview_text = zh_overview
    if not overview_text and en:
        en_overview = en.get('overview', '')
        if en_overview:
            overview_text = en_overview
            warnings.append('Chinese overview empty, using English fallback')
        else:
            blog_pending = True
            warnings.append('blog_pending: No overview available (both CN and EN empty)')
    elif not overview_text:
        blog_pending = True
        warnings.append('blog_pending: No Chinese overview available')

    if not zh_summary and en:
        zh_summary = en.get('summary', {})
        summary_titles = en.get('summary_section_titles', {}) or {}
        if zh_summary:
            warnings.append('Chinese summary empty, using English fallback')

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    blog_status_line = 'blog_status: pending\n' if blog_pending else ''

    # Build publication YAML lines (only when data exists)
    pub_yaml_lines = ''
    if published_venue:
        pub_yaml_lines += f'published_venue: "{published_venue}"\n'
    if presentation_type:
        pub_yaml_lines += f'presentation_type: "{presentation_type}"\n'
    if formal_pub_date:
        pub_yaml_lines += f'published_date: {formal_pub_date}\n'
    if venue_type:
        pub_yaml_lines += f'venue_type: {venue_type}\n'

    # Build ranking YAML lines (only when data exists)
    rank_yaml_lines = ''
    if rank.get('ccf'):
        rank_yaml_lines += f'ccf: "{rank["ccf"]}"\n'
    if rank.get('sci_jcr'):
        rank_yaml_lines += f'sci_jcr: "{rank["sci_jcr"]}"\n'
    if rank.get('sci_cas'):
        rank_yaml_lines += f'sci_cas: "{rank["sci_cas"]}"\n'
    if rank.get('sci_cas_top'):
        rank_yaml_lines += 'sci_cas_top: true\n'
    if rank.get('fms'):
        rank_yaml_lines += f'fms: "{rank["fms"]}"\n'
    if rank.get('utd24'):
        rank_yaml_lines += 'utd24: true\n'
    if rank.get('ft50'):
        rank_yaml_lines += 'ft50: true\n'
    if rank.get('swufe'):
        rank_yaml_lines += f'swufe: "{rank["swufe"]}"\n'

    parts = [f'''---
title: "{title_escaped}"
arxiv_id: "{arxiv_id}"
version: "{version}"
date: {pub_date}
tags: [{', '.join(tags)}]
source: "{alphaxiv_url}"
authors:
  - {authors_yaml}
aliases:
  - {title_escaped}
created: {now_str}
{pub_yaml_lines}{rank_yaml_lines}{blog_status_line}---

# {title_clean}

> **arXiv**: [{arxiv_id}]({arxiv_url}) | **Version**: {version} | **Published**: {pub_date}''']

    # Build info bar with optional venue + ranking badges
    info_bar = parts[-1]  # last element is the arXiv info line
    if published_venue:
        pub_badge = f'{published_venue}'
        if presentation_type:
            pub_badge += f' ({presentation_type})'
        if venue_type and venue_type not in str(pub_badge).lower():
            pub_badge += f' [{venue_type}]'
        info_bar += f' | **Venue**: {pub_badge}'

    # Ranking badges (CCF + SCI/CAS)
    rank_badges = []
    if rank.get('ccf'):
        rank_badges.append(f'CCF {rank["ccf"]}')
    if rank.get('sci_jcr'):
        rank_badges.append(f'SCI {rank["sci_jcr"]}')
    if rank.get('sci_cas_top'):
        rank_badges.append('中科院Top')
    if rank.get('fms'):
        rank_badges.append(f'FMS {rank["fms"]}')
    if rank.get('utd24'):
        rank_badges.append('UTD24')
    if rank.get('ft50'):
        rank_badges.append('FT50')
    if rank_badges:
        info_bar += f' | **Rank**: {" · ".join(rank_badges)}'

    info_bar += '\n'
    parts[-1] = info_bar

    parts.append(f'''## 摘要

{abstract}

---''')

    summary_sections = build_summary_sections(zh_summary, summary_titles)
    if summary_sections:
        parts.append(summary_sections)
    else:
        parts.append('### AI 摘要\n\n*AI 摘要正在生成中（blog_status: pending）...*\n')
    parts.append('---\n')

    parts.append('## AI 综述 (中文)\n')
    if ai_disclaimer:
        parts.append(f'> {ai_disclaimer}\n')
    if overview_text:
        # Strip trailing references section from overview before demoting headings.
        # AlphaXiv overview text often ends with "## 相关引用" / "## References" which
        # should NOT be demoted -- we add our own formatted citations section separately.
        overview_text = re.sub(
            r'\n#{1,}\s*(?:相关引[用文]|Reference|参考文献?).*$',
            '', overview_text, flags=re.DOTALL
        ).strip()
        parts.append(f'{demote_headings(overview_text)}\n')
    else:
        parts.append('*AI 综述正在生成中（blog_status: pending）...*\n')
    parts.append('---\n')

    citations_label = overview_titles.get('relevant_citations',
                                          overview_titles.get('relevantCitations', '相关引用'))
    if zh_citations:
        parts.append(f'## {citations_label}\n\n{format_citations(zh_citations)}\n\n---\n')
    else:
        parts.append(f'## {citations_label}\n\n*暂无相关引用*\n\n---\n')

    parts.append(f'*Fetched from [AlphaXiv]({alphaxiv_url}) on {now_str}*\n')
    return '\n'.join(parts), warnings

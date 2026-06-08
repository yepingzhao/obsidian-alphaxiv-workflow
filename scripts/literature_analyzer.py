"""
Literature Analyzer - search and synthesize saved paper notes in the Obsidian vault.
Supports topic-based and author-based analysis. Outputs to 200 Areas/.
"""
import os
import re
import yaml
from datetime import datetime

VAULT_REFERENCES = '300 Resources/320 References'
VAULT_OUTPUT_AREA = '200 Areas/深度学习'


def _scan_vault_papers(vault_path: str) -> list:
    """Scan vault and return all paper frontmatter dicts with filepath."""
    papers_dir = os.path.join(vault_path, VAULT_REFERENCES)
    if not os.path.exists(papers_dir):
        return []
    results = []
    for f in os.listdir(papers_dir):
        if not f.endswith('.md'):
            continue
        fpath = os.path.join(papers_dir, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                content = fh.read()
        except Exception:
            continue
        fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        if not fm_match:
            continue
        try:
            fm = yaml.safe_load(fm_match.group(1))
        except yaml.YAMLError:
            continue
        if not fm:
            continue
        authors = fm.get('authors', [])
        results.append({
            'filepath': fpath, 'title': fm.get('title', ''), 'tags': fm.get('tags', []),
            'arxiv_id': fm.get('arxiv_id', ''),
            'authors': authors,
            'first_author': (authors[0] if authors else ''),
            'published_venue': fm.get('published_venue', ''),
            'presentation_type': fm.get('presentation_type', ''),
            'ccf': fm.get('ccf', ''),
            'published_date': fm.get('published_date', ''),
        })
    return results


def _read_body_content(filepath: str) -> str:
    """Read body content of a note (after frontmatter) for keyword matching."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        fm_end = content.find('---', 4)
        if fm_end == -1:
            return content.lower()
        return content[fm_end + 3:].lower()
    except Exception:
        return ''


def find_notes_by_topic(topic: str, vault_path: str) -> list:
    """Search vault paper notes by topic with weighted relevance.

    Relevance levels:
        high   — keyword matches title
        medium — keyword matches tags
        low    — keyword matches abstract or AI overview body

    Results are sorted by relevance (high → medium → low).
    """
    keywords = topic.lower().split()
    all_papers = _scan_vault_papers(vault_path)

    scored = []
    for p in all_papers:
        title_lower = p['title'].lower()
        tags_lower = [t.lower() for t in p['tags']]

        for kw in keywords:
            if kw in title_lower:
                p['relevance'] = 'high'
                p['_match_kw'] = kw
                scored.append(p)
                break
            elif any(kw in t for t in tags_lower):
                p['relevance'] = 'medium'
                p['_match_kw'] = kw
                scored.append(p)
                break
            else:
                body = _read_body_content(p['filepath'])
                if kw in body:
                    p['relevance'] = 'low'
                    p['_match_kw'] = kw
                    scored.append(p)
                    break

    relevance_order = {'high': 0, 'medium': 1, 'low': 2}
    scored.sort(key=lambda x: relevance_order.get(x.get('relevance', 'low'), 2))

    return scored


def find_notes_by_author(author: str, vault_path: str) -> list:
    """Search vault paper notes by author name."""
    author_lower = author.lower()
    return [
        p for p in _scan_vault_papers(vault_path)
        if any(author_lower in a.lower() for a in p['authors'])
    ]


def extract_paper_summary(filepath: str) -> str:
    """Extract abstract and key insights from a paper note."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return ''
    parts = []
    has_blog_pending = 'blog_status: pending' in content

    # Extract abstract
    abstract_match = re.search(r'## 摘要\s*\n\n(.*?)(?:\n---|\n##)', content, re.DOTALL)
    abstract_text = abstract_match.group(1).strip()[:500] if abstract_match else ''

    if abstract_text:
        parts.append(abstract_text)

    # Extract key insights from AI summary (### 要点, Chinese)
    insights_match = re.search(r'### 要点\s*\n(.*?)(?:\n###|\n##)', content, re.DOTALL)
    if insights_match:
        parts.append('**关键洞察**:\n' + insights_match.group(1).strip()[:500])
    else:
        # Fallback: extract from Chinese overview section
        zh_match = re.search(
            r'## AI 综述 \(中文\)\s*\n\n(.*?)(?:\n---|\n##)', content, re.DOTALL)
        zh_text = zh_match.group(1).strip() if zh_match else ''
        has_real_zh = (zh_text and '正在生成中' not in zh_text
                       and len(zh_text) > 50)
        if has_real_zh:
            # Use first meaningful paragraph from Chinese overview
            zh_para = re.sub(r'> .*?\n', '', zh_text).strip()[:400]
            parts.append('**关键洞察**:\n' + zh_para)
        elif has_blog_pending and abstract_text:
            parts.append(
                '**关键洞察**: ⏳ 中文综述生成中，请运行 `backfill-overviews` 获取。\n\n'
                f'*英文摘要参考*: {abstract_text[:300]}')
        elif abstract_text:
            parts.append(
                '**关键洞察**: 暂无结构化摘要。\n\n'
                f'*摘要*: {abstract_text[:300]}')
        else:
            parts.append('**关键洞察**: 暂不可用。')
    return '\n\n'.join(parts)


def build_synthesis_note(topic: str, papers: list, dimension: str, vault_path: str) -> tuple:
    """Build a literature synthesis note. Returns (content, filepath)."""
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    clean_topic = re.sub(r'[\\/:*?"<>|]', '', topic)[:60]
    output_dir = os.path.join(vault_path, VAULT_OUTPUT_AREA)
    suffix = '文献分析' if dimension == 'author' else '文献综述'
    filename = f'{clean_topic} {suffix}.md'
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    paper_refs = '\n'.join(
        f'- [[{os.path.splitext(os.path.basename(p["filepath"]))[0]}]]'
        for p in papers
    )
    source_links = '[' + ', '.join(
        f'"[[{os.path.splitext(os.path.basename(p["filepath"]))[0]}]]"'
        for p in papers[:5]
    ) + ']'

    paper_details = []
    for p in papers:
        summary = extract_paper_summary(p['filepath'])
        # Build publication info line
        pub_badges = []
        if p.get('published_venue'):
            pub_badges.append(p['published_venue'])
        if p.get('ccf'):
            pub_badges.append(f'CCF-{p["ccf"]}')
        if p.get('presentation_type'):
            pub_badges.append(p['presentation_type'])
        pub_info = ' | '.join(pub_badges) if pub_badges else ''
        # Format authors (up to 5, first author bold)
        authors = p.get('authors', [])
        if authors:
            author_str = ', '.join(authors[:5])
            if len(authors) > 5:
                author_str += f' et al. ({len(authors)} authors)'
        else:
            author_str = 'TBD'
        # Assemble paper detail block
        detail = f'### {p["title"]}\n\n'
        if pub_info:
            detail += f'> 🏷️ {pub_info}\n\n'
        detail += (f'- **arXiv**: [{p["arxiv_id"]}](https://arxiv.org/abs/{p["arxiv_id"]})\n'
                   f'- **作者**: {author_str}\n')
        if p.get('published_date'):
            detail += f'- **日期**: {p["published_date"]}\n'
        detail += f'\n{summary}\n'
        paper_details.append(detail)

    dimension_label = f'汇总了学者 **{topic}** 的相关论文' if dimension == 'author' else f'围绕主题 **{topic}** 检索相关论文'

    note = f'''---
title: "{clean_topic} - {suffix}"
tags: [literature-review, deep-learning, area]
created: "{now_str}"
source: {source_links}
---

# {clean_topic} - {suffix}

## 概述

本笔记由 AlphaXiv 文献分析工具自动生成，{dimension_label}。

共找到 {len(papers)} 篇相关论文。

## 论文列表

{paper_refs}

## 论文分析

{'\n'.join(paper_details)}

## 交叉引用与演进

*此部分建议手动补充论文之间的演进关系和对比分析。*

---

*Generated by alphaxiv-to-obsidian on {now_str}*
'''
    return note, filepath

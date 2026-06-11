"""
Literature Synthesis - search and synthesize saved paper notes in the Obsidian vault.
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


EXTRACTION_MAX_CHARS = 2400  # ~600 tokens for LLM input


def _extract_section(content: str, heading: str, max_chars: int = 800) -> str:
    """Extract plain text from a markdown section by heading name. Returns '' if not found."""
    pattern = rf'^#{{2,3}}\s*{re.escape(heading)}\s*\n(.*?)(?=\n#{{2,3}}\s|\n---|\Z)'
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
    if not match:
        return ''
    text = match.group(1).strip()
    text = re.sub(r'^> .*?\n', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n\*[^*]+\*$', '', text)
    return text[:max_chars]


def _has_real_content(text: str) -> bool:
    """Check if extracted text has substantive content (not pending/placeholder)."""
    if not text or len(text) < 30:
        return False
    placeholders = ['正在生成中', 'blog_status', '暂无', '暂不可用']
    return not any(p in text for p in placeholders)


def extract_paper_summary(filepath: str) -> str:
    """Extract structured paper data for LLM synthesis input.

    Three-tier priority with ~400-600 token budget:
      Tier 1: 核心总结 (<=3 sentences) + 关键洞察 (3-5 bullet points)
      Tier 2: AI 综述 (中文) first 2 paragraphs (<=400 chars)
      Tier 3: English abstract (<=300 chars)

    blog_status: pending papers get warning marker, included with abstract.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return ''

    has_blog_pending = re.search(r'blog_status:\s*"?pending"?', content) is not None

    # Tier 1: 核心总结 + 关键洞察 (structured AI summary)
    core_summary = _extract_section(content, '核心总结', max_chars=400)
    key_insights = _extract_section(content, '关键洞察', max_chars=600)

    if _has_real_content(core_summary) or _has_real_content(key_insights):
        parts = []
        if _has_real_content(core_summary):
            parts.append(f'**核心贡献**: {core_summary}')
        if _has_real_content(key_insights):
            parts.append(f'**关键洞察**:\n{key_insights}')
        result = '\n\n'.join(parts)
        if has_blog_pending:
            result = '⚠️ *AI 综述尚未生成*\n\n' + result
        return result[:EXTRACTION_MAX_CHARS]

    # Tier 2: AI 综述 (Chinese overview) first 2 paragraphs
    zh_overview = _extract_section(content, 'AI 综述 (中文)', max_chars=800)
    if _has_real_content(zh_overview):
        paragraphs = [p.strip() for p in zh_overview.split('\n\n') if p.strip()]
        first_two = '\n\n'.join(paragraphs[:2])
        result = first_two[:400]
        if has_blog_pending:
            result = '⚠️ *AI 综述尚未生成*\n\n' + result
        return result[:EXTRACTION_MAX_CHARS]

    # Tier 3: English abstract
    abstract = _extract_section(content, '摘要', max_chars=500)
    if _has_real_content(abstract):
        result = f'**摘要**: {abstract[:300]}'
        if has_blog_pending:
            result = '⚠️ *AI 综述尚未生成，仅英文摘要可用*\n\n' + result
        return result[:EXTRACTION_MAX_CHARS]

    return '⚠️ *无可用摘要信息*'


def _format_paper_entry(p: dict, index: int) -> str:
    """Format a single paper for the LLM prompt."""
    badges = []
    if p.get('published_venue'):
        badges.append(p['published_venue'])
    if p.get('ccf'):
        badges.append(f'CCF-{p["ccf"]}')
    if p.get('relevance'):
        badges.append(f'相关度: {p["relevance"]}')

    authors = p.get('authors', [])
    author_str = ', '.join(authors[:3])
    if len(authors) > 3:
        author_str += f' et al. ({len(authors)} 位作者)'

    lines = [
        f'### {index}. {p["title"]}',
        f'- **arXiv**: {p["arxiv_id"]}',
        f'- **作者**: {author_str}',
    ]
    if p.get('published_date'):
        lines.append(f'- **日期**: {p["published_date"]}')
    if badges:
        lines.append(f'- **标签**: {" | ".join(badges)}')
    lines.append('')
    lines.append(p.get('summary', '⚠️ *无摘要*'))
    lines.append('')
    return '\n'.join(lines)


def build_synthesis_prompt(topic: str, papers: list, dimension: str) -> str:
    """Build the LLM prompt for five-chapter literature synthesis.

    Returns the complete prompt string ready for Claude.
    """
    is_author = dimension == 'author'

    paper_entries = '\n'.join(
        _format_paper_entry(p, i) for i, p in enumerate(papers, 1)
    )

    if is_author:
        intro = f'以下是学者 **{topic}** 的 {len(papers)} 篇论文的结构化摘要。'
    else:
        intro = f'以下是主题 **{topic}** 相关的 {len(papers)} 篇论文的结构化摘要。'

    prompt = f'''{intro}请基于这些论文撰写一份学术文献综述。

{paper_entries}

## 写作要求

请生成以下五个章节。每章 2-5 段，中文输出，专业术语保留英文。

### 一、方法分类与对比
按技术路线或子领域将论文分组。每组列出代表论文（使用 `[[论文标题]]` wikilink），对比优缺点。
**重要**: 如果论文分属完全不同的子领域，不要牵强统一分组。承认差异，分为「子领域 A（X篇）」「子领域 B（Y篇）」分别分析。

### 二、演进脉络
按时间线梳理关键突破节点，标注论文之间的承继关系（谁改进了谁）。
无法确定时间或承继关系的论文，归入「独立工作」段落。

### 三、共识与矛盾
列出社区已达成共识的结论（被多篇论文独立验证）和仍存在的争议或矛盾。
如果该领域尚未形成明确共识，请如实声明。

### 四、空白与机会
识别论文中明确提出的未解决问题，以及你从论文空白中推断的潜在研究方向。
**重要**: 区分「论文明确提出」（标注出处）和「综述推断」两个来源。

### 五、关键论文推荐
推荐 3-5 篇必读论文，说明每篇的核心贡献和推荐理由。
允许多选 1 篇不在上述列表中的重要相关论文（标注为「扩展阅读」）。

## 格式约束

- 所有论文引用使用 `[[论文完整标题]]` wikilink 格式
- 中文撰写，专业术语保留英文原文
- 每篇被引用的论文至少出现一次 wikilink 引用
- 不确定的信息标注「推测」或「待验证」
'''

    return prompt


def build_synthesis_note(topic: str, papers: list, dimension: str, vault_path: str) -> tuple:
    """Build a literature synthesis note scaffold with LLM placeholder.

    Returns (content, filepath). The actual five-chapter synthesis is generated
    by Claude inline using the prompt from build_synthesis_prompt().
    """
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    date_str = datetime.now().strftime('%Y-%m-%d')
    clean_topic = re.sub(r'[\\/:*?"<>|]', '', topic)[:60]
    output_dir = os.path.join(vault_path, VAULT_OUTPUT_AREA)
    dim_suffix = '文献分析' if dimension == 'author' else '文献综述'
    filename = f'AI 综述 {clean_topic} ({dim_suffix}) {date_str}.md'
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    # Paper list with wikilinks
    paper_refs = '\n'.join(
        f'- [[{os.path.splitext(os.path.basename(p["filepath"]))[0]}]]'
        for p in papers
    )

    # Source links (frontmatter, up to 10 papers)
    source_links = '[' + ', '.join(
        f'"[[{os.path.splitext(os.path.basename(p["filepath"]))[0]}]]"'
        for p in papers[:10]
    ) + ']'

    # Paper details (title + meta; summary handled by LLM synthesis)
    paper_details = []
    for p in papers:
        authors = p.get('authors', [])
        author_str = ', '.join(authors[:3])
        if len(authors) > 3:
            author_str += f' et al. ({len(authors)} authors)'
        elif not author_str:
            author_str = 'TBD'

        detail = f'### {p["title"]}\n\n'
        detail += f'- **arXiv**: [{p["arxiv_id"]}](https://arxiv.org/abs/{p["arxiv_id"]})\n'
        detail += f'- **作者**: {author_str}\n'
        if p.get('published_venue'):
            detail += f'- **发表**: {p["published_venue"]}'
            if p.get('ccf'):
                detail += f' (CCF-{p["ccf"]})'
            detail += '\n'
        if p.get('published_date'):
            detail += f'- **日期**: {p["published_date"]}\n'
        if p.get('relevance'):
            relevance_label = {
                'high': '高相关 (标题匹配)',
                'medium': '中相关 (标签匹配)',
                'low': '弱相关 (内容匹配)'
            }
            detail += f'- **相关度**: {relevance_label.get(p["relevance"], p["relevance"])}\n'
        detail += f'\n{p.get("summary", "⚠️ 无摘要")}\n'
        paper_details.append(detail)

    dimension_label = (
        f'汇总了学者 **{topic}** 的相关论文'
        if dimension == 'author'
        else f'围绕主题 **{topic}** 检索相关论文'
    )

    note = f'''---
title: "AI 综述 {clean_topic} ({dim_suffix}) {date_str}"
tags: [literature-review, area]
created: "{now_str}"
source: {source_links}
---

# AI 综述 {clean_topic} ({dim_suffix}) {date_str}

## 概述

本笔记由 AlphaXiv 文献分析工具生成，{dimension_label}。

共找到 {len(papers)} 篇相关论文。

## 论文列表

{paper_refs}

## AI 综述生成

> 以下五章综述通过 LLM 生成。

<!-- LLM_SYNTHESIS_PLACEHOLDER -->

## 论文分析

{chr(10).join(paper_details)}

---

*Generated by alphaxiv-to-obsidian on {now_str}*
'''
    return note, filepath


# --- CLI entry point ---
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Search and synthesize saved paper notes in Obsidian vault')
    sub = parser.add_subparsers(dest='mode', required=True)

    topic_p = sub.add_parser('topic', help='Search by topic/keyword')
    topic_p.add_argument('query', help='Topic or keyword to search')
    topic_p.add_argument('vault', help='Path to Obsidian vault')

    author_p = sub.add_parser('author', help='Search by author name')
    author_p.add_argument('name', help='Author name to search')
    author_p.add_argument('vault', help='Path to Obsidian vault')

    args = parser.parse_args()

    if args.mode == 'topic':
        papers = find_notes_by_topic(args.query, args.vault)
        dimension = 'topic'
        label = args.query
    else:
        papers = find_notes_by_author(args.name, args.vault)
        dimension = 'author'
        label = args.name

    print(f'Found {len(papers)} papers for {dimension}: {label}')
    for i, p in enumerate(papers, 1):
        rel = p.get('relevance', '?')
        mark = ' [weak]' if rel == 'low' else ''
        print(f'  {i}. [{p["arxiv_id"]}] {p["title"]} ({rel}){mark}')

    if not papers:
        print('No papers found. Try a different query or check vault path.')
    else:
        print(f'\nTo generate synthesis: run Claude inline with the prompt from build_synthesis_prompt()')

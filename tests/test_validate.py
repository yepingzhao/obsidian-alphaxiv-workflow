"""
Tests for validator.py — frontmatter validation, heading hierarchy,
duplicate detection, tag merging.
"""
import os
import sys
import re

import pytest

from alphaxiv_workflow.validate import (
    validate_frontmatter,
    check_heading_hierarchy,
    check_duplicates,
    merge_tags,
)


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

SAMPLE_NOTE = """---
title: "Attention Is All You Need"
arxiv_id: "1706.03762"
version: "v7"
date: 2017-06-12
tags: [paper, alphaxiv, nlp]
source: "https://alphaxiv.org/abs/1706.03762"
authors:
  - Vaswani et al.
created: 2024-01-01 12:00
---

# Attention Is All You Need

> **arXiv**: [1706.03762](https://arxiv.org/abs/1706.03762)

## 摘要

The dominant sequence transduction models...

---

### AI 摘要

Key insights from the paper...

---

## AI 综述 (中文)

This is the Chinese AI overview...

---

## 相关引用

1. **Related Paper**
   - [AlphaXiv](https://alphaxiv.org/abs/1234.56789)

---

*Fetched from AlphaXiv*
"""


def write_note(path: str, content: str = SAMPLE_NOTE):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


# ──────────────────────────────────────────────────────────────────
# validate_frontmatter
# ──────────────────────────────────────────────────────────────────

class TestValidateFrontmatter:
    def test_passes_valid_note(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = SAMPLE_NOTE.replace(
            'tags: [paper, alphaxiv, nlp]',
            'tags: [paper, alphaxiv, nlp, transformer, attention]')
        write_note(fpath, content)
        result = validate_frontmatter(fpath)
        assert result['status'] == 'pass'

    def test_blocks_missing_file(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'nonexistent.md')
        result = validate_frontmatter(fpath)
        assert result['status'] == 'block'

    def test_blocks_missing_title(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
arxiv_id: "1706.03762"
tags: [paper]
---

# Title

## 摘要

abstract

## AI 摘要

summary

## AI 综述 (中文)

overview

## 相关引用

citations
"""
        write_note(fpath, content)
        result = validate_frontmatter(fpath)
        assert any('title' in issue[1].lower()
                   for issue in result['issues'] if issue[0] == 'block')

    def test_blocks_missing_arxiv_id(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
title: "Test"
tags: [paper]
---

# Test

## 摘要

abstract

## AI 摘要

summary

## AI 综述 (中文)

overview

## 相关引用

citations
"""
        write_note(fpath, content)
        result = validate_frontmatter(fpath)
        assert any('arxiv_id' in issue[1].lower()
                   for issue in result['issues'] if issue[0] == 'block')

    def test_warns_on_few_tags(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
title: "Test"
arxiv_id: "1234.56789"
tags: [paper]
---

# Test

## 摘要

abstract

## AI 摘要

summary

## AI 综述 (中文)

overview

## 相关引用

citations
"""
        write_note(fpath, content)
        result = validate_frontmatter(fpath)
        warns = [i for i in result['issues'] if i[0] == 'warn']
        assert any('tags' in w[1].lower() for w in warns)

    def test_blocks_on_yaml_parse_error(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, '---\n\tbad: : yaml\n---\n# Test')
        result = validate_frontmatter(fpath)
        assert result['status'] == 'block'

    def test_info_missing_publication_venue(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        result = validate_frontmatter(fpath)
        infos = [i for i in result['issues'] if i[0] == 'info']
        assert any('published_venue' in i[1].lower() for i in infos)


# ──────────────────────────────────────────────────────────────────
# check_heading_hierarchy
# ──────────────────────────────────────────────────────────────────

class TestCheckHeadingHierarchy:
    def test_passes_valid_hierarchy(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        result = check_heading_hierarchy(fpath)
        assert result['status'] == 'pass'

    def test_blocks_ai_summary_at_h2(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath, SAMPLE_NOTE.replace('### AI 摘要', '## AI 摘要'))
        result = check_heading_hierarchy(fpath)
        assert any('must be H3' in issue[1]
                   for issue in result['issues'] if issue[0] == 'block')

    def test_blocks_no_h1(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
title: "Test"
---

## 摘要

abstract

## AI 摘要

summary

## AI 综述 (中文)

overview

## 相关引用

citations
"""
        write_note(fpath, content)
        result = check_heading_hierarchy(fpath)
        assert any('No H1' in issue[1]
                   for issue in result['issues'] if issue[0] == 'block')

    def test_blocks_multiple_h1(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
title: "Test"
---

# Title One

text

# Title Two

## 摘要

abstract

## AI 摘要

summary

## AI 综述 (中文)

overview

## 相关引用

citations
"""
        write_note(fpath, content)
        result = check_heading_hierarchy(fpath)
        assert any('Multiple H1' in issue[1]
                   for issue in result['issues'] if issue[0] == 'block')

    def test_blocks_missing_required_section(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
title: "Test"
arxiv_id: "1234.56789"
tags: [paper]
---

# Test

## 摘要

abstract
"""
        write_note(fpath, content)
        result = check_heading_hierarchy(fpath)
        assert result['status'] == 'block'
        assert any('Missing required H2' in issue[1]
                   for issue in result['issues'] if issue[0] == 'block')

    def test_warns_skipped_level(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
title: "Test"
---

# Title

## 摘要

abstract

## AI 摘要

#### Skipped H3

content

## AI 综述 (中文)

overview

## 相关引用

citations
"""
        write_note(fpath, content)
        result = check_heading_hierarchy(fpath)
        warns = [i for i in result['issues'] if i[0] == 'warn']
        assert any('skip' in w[1].lower() for w in warns)

    def test_warns_deep_heading(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
title: "Test"
---

# Title

## 摘要

abstract

## AI 摘要

##### Too Deep

content

## AI 综述 (中文)

overview

## 相关引用

citations
"""
        write_note(fpath, content)
        result = check_heading_hierarchy(fpath)
        warns = [i for i in result['issues'] if i[0] == 'warn']
        assert any('deep' in w[1].lower() for w in warns)

    def test_blocks_missing_file(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'nonexistent.md')
        result = check_heading_hierarchy(fpath)
        assert result['status'] == 'block'

    def test_warns_citation_not_h2(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        content = """---
title: "Test"
---

# Title

## 摘要

abstract

## AI 摘要

summary

## AI 综述 (中文)

overview

### 相关引用

citations
"""
        write_note(fpath, content)
        result = check_heading_hierarchy(fpath)
        warns = [i for i in result['issues'] if i[0] == 'warn']
        assert any('相关引用' in w[1] for w in warns)


# ──────────────────────────────────────────────────────────────────
# check_duplicates
# ──────────────────────────────────────────────────────────────────

class TestCheckDuplicates:
    def test_finds_duplicate(self, tmp_path):
        vault = str(tmp_path)
        refs = os.path.join(vault, '300 Resources', '320 References')
        os.makedirs(refs)
        write_note(os.path.join(refs, 'paper1.md'))
        dups = check_duplicates('1706.03762', vault)
        assert len(dups) == 1

    def test_no_duplicate_for_new_id(self, tmp_path):
        vault = str(tmp_path)
        refs = os.path.join(vault, '300 Resources', '320 References')
        os.makedirs(refs)
        write_note(os.path.join(refs, 'paper1.md'))
        dups = check_duplicates('9999.99999', vault)
        assert len(dups) == 0

    def test_empty_for_missing_vault(self, tmp_path):
        dups = check_duplicates('1706.03762', str(tmp_path))
        assert dups == []


# ──────────────────────────────────────────────────────────────────
# merge_tags
# ──────────────────────────────────────────────────────────────────

class TestMergeTags:
    def test_adds_new_tags(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        result = merge_tags(fpath, ['transformer', 'attention'])
        assert result is True

    def test_no_change_for_existing_tags(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        result = merge_tags(fpath, ['paper', 'alphaxiv'])
        assert result is False

    def test_deduplicates_tags(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        merge_tags(fpath, ['paper', 'nlp'])

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        assert fm_match is not None
        tags_section = fm_match.group(1)
        assert tags_section.count('nlp') == 1

    def test_preserves_existing_tags(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'test.md')
        write_note(fpath)
        merge_tags(fpath, ['new-tag'])

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'paper' in content
        assert 'alphaxiv' in content
        assert 'new-tag' in content

    def test_returns_false_for_nonexistent_file(self, tmp_path):
        fpath = os.path.join(str(tmp_path), 'nonexistent.md')
        result = merge_tags(fpath, ['tag'])
        assert result is False

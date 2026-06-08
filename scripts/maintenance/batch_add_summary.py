"""
Batch supplement AI 摘要 (AI Summary) for existing papers that already have AI 综述 but missing AI 摘要.
Fetches summary data from AlphaXiv API and inserts it before the AI 综述 section.
"""
import os
import re
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from alphaxiv_client import get_paper_metadata, get_overview
from note_builder import build_summary_sections

VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", "")
if not VAULT_PATH:
    config_path = os.path.join(os.path.expanduser("~"), ".alphaxiv-to-obsidian.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                VAULT_PATH = json.load(f).get("vault_path", "")
        except (json.JSONDecodeError, OSError):
            pass
REFERENCES_DIR = os.path.join(VAULT_PATH, "300 Resources", "320 References") if VAULT_PATH else ""

# 11 papers missing AI 摘要
PAPERS = [
    ("DeepSeek LLM Scaling Open-Source Language Models with Longtermism.md", "2401.02954"),
    ("DeepSeek-Coder When the Large Language Model Meets Programming -- The Rise of Code Intelligence.md", "2401.14196"),
    ("DeepSeek-Prover Advancing Theorem Proving in LLMs through Large-Scale Synthetic Data.md", "2405.14333"),
    ("DeepSeek-Prover-V1.5 Harnessing Proof Assistant Feedback for Reinforcement Learning and Monte-Carlo .md", "2408.08152"),
    ("DeepSeek-Prover-V2 Advancing Formal Mathematical Reasoning via Reinforcement Learning for Subgoal De.md", "2504.21801"),
    ("DeepSeek-R1 Incentivizing Reasoning Capability in LLMs via Reinforcement Learning.md", "2501.12948"),
    ("DeepSeek-V2 A Strong, Economical, and Efficient Mixture-of-Experts Language Model.md", "2405.04434"),
    ("DeepSeek-V3 Technical Report.md", "2412.19437"),
    ("DeepSeek-VL Towards Real-World Vision-Language Understanding.md", "2403.05525"),
    ("LLaVA-Interactive An All-in-One Demo for Image Chat, Segmentation, Generation and Editing.md", "2311.00571"),
    ("LLaVA-MoLE Sparse Mixture of LoRA Experts for Mitigating Data Conflicts in Instruction Finetuning ML.md", "2401.16160"),
]


def fetch_zh_summary(arxiv_id: str):
    """Fetch Chinese summary data from AlphaXiv. Fallback to EN if CN is empty."""
    try:
        meta = get_paper_metadata(arxiv_id)
    except Exception as e:
        print(f"  ERROR: Failed to get metadata for {arxiv_id}: {e}")
        return None, None

    zh_summary = {}
    zh_titles = {}

    try:
        zh_overview = get_overview(meta.version_id, 'zh')
        if zh_overview:
            d = zh_overview.model_dump()
            zh_summary = d.get('summary', {})
            zh_titles = d.get('summary_section_titles', {}) or {}
    except Exception as e:
        print(f"  WARN: CN overview fetch failed: {e}")

    # Fallback to EN if CN summary is empty
    if not zh_summary:
        try:
            en_overview = get_overview(meta.version_id, 'en')
            if en_overview:
                d = en_overview.model_dump()
                zh_summary = d.get('summary', {})
                zh_titles = d.get('summary_section_titles', {}) or {}
                if zh_summary:
                    print(f"  NOTE: Using EN summary as fallback")
        except Exception as e:
            print(f"  WARN: EN overview fetch also failed: {e}")

    return zh_summary, zh_titles


def insert_summary_section(content: str, summary_md: str) -> str:
    """
    Insert AI 摘要 section after the abstract (## 摘要 block) and before ## AI 综述.
    """
    # Case 1: abstract block ends with --- before ## AI 综述
    pattern = r'(\n---\n+)(## AI 综述)'
    if re.search(pattern, content):
        return re.sub(pattern, f'\n---\n\n## AI 摘要\n\n{summary_md}\n---\n\n\\2', content, count=1)

    # Case 2: no --- separator, ## 摘要 directly to ## AI 综述
    pattern2 = r'(## 摘要\n.+?)(## AI 综述)'
    if re.search(pattern2, content, re.DOTALL):
        return re.sub(pattern2, f'\\1\n---\n\n## AI 摘要\n\n{summary_md}\n---\n\n\\2', content, count=1, flags=re.DOTALL)

    print("  ERROR: Could not find insertion point!")
    return content


def main():
    success = 0
    fail = 0
    empty_summary = 0

    for filename, arxiv_id in PAPERS:
        filepath = os.path.join(REFERENCES_DIR, filename)
        print(f"\n{'='*60}")
        print(f"Processing: {filename}")
        print(f"  arXiv ID: {arxiv_id}")

        if not os.path.exists(filepath):
            print(f"  ERROR: File not found!")
            fail += 1
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        if '## AI 摘要' in content:
            print(f"  SKIP: AI 摘要 already exists")
            continue

        zh_summary, zh_titles = fetch_zh_summary(arxiv_id)

        if not zh_summary:
            print(f"  WARN: No summary data available from AlphaXiv (both CN and EN empty)")
            empty_summary += 1
            continue

        summary_md = build_summary_sections(zh_summary, zh_titles)
        if not summary_md:
            print(f"  WARN: build_summary_sections returned empty")
            empty_summary += 1
            continue

        new_content = insert_summary_section(content, summary_md)
        if new_content == content:
            print(f"  ERROR: Content unchanged after insertion attempt")
            fail += 1
            continue

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print(f"  OK: AI 摘要 added successfully")
        success += 1
        time.sleep(1)

    print(f"\n{'='*60}")
    print(f"SUMMARY: {success} success, {empty_summary} empty/no-summary, {fail} failed")
    return 0


if __name__ == '__main__':
    sys.exit(main())

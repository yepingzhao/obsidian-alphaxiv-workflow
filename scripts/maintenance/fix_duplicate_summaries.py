"""
Fix duplicate AI 摘要 headings in papers where batch_add_summary.py
incorrectly inserted an extra ## AI 摘要 before build_summary_sections output.
"""
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import PAPERS_DIR
REFERENCES_DIR = PAPERS_DIR

if __name__ == '__main__':
    PAPERS = [
        "DeepSeek LLM Scaling Open-Source Language Models with Longtermism.md",
        "DeepSeek-Coder When the Large Language Model Meets Programming -- The Rise of Code Intelligence.md",
        "DeepSeek-Prover Advancing Theorem Proving in LLMs through Large-Scale Synthetic Data.md",
        "DeepSeek-Prover-V1.5 Harnessing Proof Assistant Feedback for Reinforcement Learning and Monte-Carlo .md",
        "DeepSeek-Prover-V2 Advancing Formal Mathematical Reasoning via Reinforcement Learning for Subgoal De.md",
        "DeepSeek-R1 Incentivizing Reasoning Capability in LLMs via Reinforcement Learning.md",
        "DeepSeek-V2 A Strong, Economical, and Efficient Mixture-of-Experts Language Model.md",
        "DeepSeek-V3 Technical Report.md",
        "DeepSeek-VL Towards Real-World Vision-Language Understanding.md",
    ]

    for filename in PAPERS:
        filepath = os.path.join(REFERENCES_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Pattern: ## AI 摘要\n\n## 总结 -> ## AI 摘要
        if '## AI 摘要\n\n## 总结' in content:
            content = content.replace('## AI 摘要\n\n## 总结', '## AI 摘要')
            print(f"Fixed (总结->AI摘要): {filename}")
        # Pattern: ## AI 摘要\n\n## AI 摘要\n -> ## AI 摘要\n
        elif re.search(r'## AI 摘要\n\n## AI 摘要\n', content):
            content = re.sub(r'## AI 摘要\n\n## AI 摘要\n', '## AI 摘要\n', content, count=1)
            print(f"Fixed (duplicate heading): {filename}")
        else:
            print(f"No fix needed: {filename}")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    print("Done!")

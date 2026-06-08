"""
Shared configuration for the alphaxiv-to-obsidian pipeline.
Resolves vault path from: env var -> config file.
"""
import os
import json

VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", "")
if not VAULT_PATH:
    config_path = os.path.join(os.path.expanduser("~"), ".alphaxiv-to-obsidian.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                VAULT_PATH = json.load(f).get("vault_path", "")
        except (json.JSONDecodeError, OSError):
            pass

PAPERS_DIR = os.path.join(VAULT_PATH, '300 Resources', '320 References') if VAULT_PATH else ""

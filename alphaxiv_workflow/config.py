"""
Unified configuration for the alphaxiv-workflow pipeline.
Resolves vault path and API keys from: env var -> config file.
"""
import os
import json

_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".alphaxiv-to-obsidian.json")

def _load_config():
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}

_config = _load_config()

VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", "") or _config.get("vault_path", "")
PAPERS_DIR = os.path.join(VAULT_PATH, '300 Resources', '320 References') if VAULT_PATH else ""
EASYSCHOLAR_SECRET_KEY = os.environ.get("EASYSCHOLAR_SECRET_KEY", "") or _config.get("easyscholar_secret_key", "")

"""
EasyScholar publication ranking API client.
Queries journal/conference rankings: CCF, SCI, CAS, FMS, UTD24, FT50, etc.
"""
import time
import json
import os
import urllib.request
import urllib.parse
import urllib.error

# Rate limiting: max 2 requests/second per EasyScholar API docs
_last_request_time = 0
_REQUEST_INTERVAL = 0.6


def _rate_limit():
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _REQUEST_INTERVAL:
        time.sleep(_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _load_secret_key() -> str | None:
    """Load EasyScholar secret key from config file."""
    config_path = os.path.expanduser('~/.alphaxiv-to-obsidian.json')
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            return cfg.get('easyscholar_secret_key')
    except (json.JSONDecodeError, OSError):
        pass
    return None


# ──────────────────────────────────────────────────────────────────
# Venue abbreviation -> EasyScholar-recognized publication name
# ──────────────────────────────────────────────────────────────────

VENUE_TO_EASYSCHOLAR = {
    # AI / ML
    'NeurIPS': 'Advances in Neural Information Processing Systems',
    'ICML': 'International Conference on Machine Learning',
    'ICLR': 'International Conference on Learning Representations',
    'AAAI': 'AAAI Conference on Artificial Intelligence',
    'IJCAI': 'International Joint Conference on Artificial Intelligence',
    'AISTATS': 'International Conference on Artificial Intelligence and Statistics',
    'UAI': 'Conference on Uncertainty in Artificial Intelligence',
    'AAMAS': 'International Conference on Autonomous Agents and Multiagent Systems',
    # CV
    'CVPR': 'IEEE/CVF Conference on Computer Vision and Pattern Recognition',
    'ICCV': 'IEEE/CVF International Conference on Computer Vision',
    'ECCV': 'European Conference on Computer Vision',
    # NLP
    'ACL': 'Annual Meeting of the Association for Computational Linguistics',
    'EMNLP': 'Conference on Empirical Methods in Natural Language Processing',
    'NAACL': 'North American Chapter of the Association for Computational Linguistics',
    'COLING': 'International Conference on Computational Linguistics',
    # Data / IR / DB
    'KDD': 'International Conference on Knowledge Discovery and Data Mining',
    'SIGIR': 'International Conference on Research and Development in Information Retrieval',
    'WSDM': 'International Conference on Web Search and Data Mining',
    'WWW': 'The Web Conference',
    'RecSys': 'ACM Conference on Recommender Systems',
    'SIGMOD': 'International Conference on Management of Data',
    'VLDB': 'International Conference on Very Large Data Bases',
    'ICDE': 'International Conference on Data Engineering',
    'ICDM': 'International Conference on Data Mining',
    # Systems
    'OSDI': 'USENIX Symposium on Operating Systems Design and Implementation',
    'NSDI': 'USENIX Symposium on Networked Systems Design and Implementation',
    'SOSP': 'ACM Symposium on Operating Systems Principles',
    # Architecture
    'ISCA': 'International Symposium on Computer Architecture',
    'MICRO': 'IEEE/ACM International Symposium on Microarchitecture',
    'HPCA': 'International Symposium on High Performance Computer Architecture',
    # HCI
    'CHI': 'ACM Conference on Human Factors in Computing Systems',
    'UIST': 'ACM Symposium on User Interface Software and Technology',
    'CSCW': 'ACM Conference on Computer-Supported Cooperative Work and Social Computing',
    'Ubicomp': 'Proceedings of the ACM on Interactive Mobile Wearable and Ubiquitous Technologies',
    # Mobile / Networks
    'MobiCom': 'International Conference on Mobile Computing and Networking',
    'SenSys': 'ACM Conference on Embedded Networked Sensor Systems',
    # Robotics
    'ICRA': 'IEEE International Conference on Robotics and Automation',
    'IROS': 'IEEE/RSJ International Conference on Intelligent Robots and Systems',
    'RSS': 'Robotics: Science and Systems',
    'CoRL': 'Conference on Robot Learning',
    # Journals
    'TPAMI': 'IEEE Transactions on Pattern Analysis and Machine Intelligence',
    'JMLR': 'Journal of Machine Learning Research',
    'PNAS': 'Proceedings of the National Academy of Sciences of the United States of America',
    # Graphics
    'SIGGRAPH': 'ACM Transactions on Graphics',
}


def query_easyscholar(publication_name: str, secret_key: str = None) -> dict | None:
    """Query EasyScholar API for publication ranking information.

    Args:
        publication_name: Journal/conference name to query
        secret_key: EasyScholar API secret key (loads from config if None)

    Returns:
        Parsed API response data dict, or None on error/not found
    """
    key = secret_key or _load_secret_key()
    if not key:
        return None

    _rate_limit()
    encoded_name = urllib.parse.quote(publication_name, safe='')
    url = (
        'https://www.easyscholar.cc/open/getPublicationRank'
        f'?secretKey={key}&publicationName={encoded_name}'
    )

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AlphaXivToObsidian/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            ValueError, json.JSONDecodeError):
        return None

    if data.get('code') != 200 or not data.get('data'):
        return None

    return data['data']


def extract_ranking_fields(data: dict | None) -> dict:
    """Extract relevant ranking fields from EasyScholar API response.

    Converts raw API response into a clean dict for Obsidian note frontmatter.

    Args:
        data: Parsed response from query_easyscholar(), or None

    Returns:
        Dict with fields: ccf, sci_jcr, sci_cas, sci_cas_small, sci_cas_top,
            fms, utd24, ft50, swufe, pku, cssci, cscd, eii, custom_ranks.
        All None when no data available.
    """
    result = {
        'ccf': None,
        'sci_jcr': None,
        'sci_cas': None,
        'sci_cas_small': None,
        'sci_cas_top': None,
        'fms': None,
        'utd24': None,
        'ft50': None,
        'swufe': None,
        'pku': None,
        'cssci': None,
        'cscd': None,
        'eii': None,
        'custom_ranks': None,
    }

    if not data:
        return result

    official = data.get('officialRank', {})
    all_ranks = official.get('all', {})

    # String-valued rankings
    _str_fields = {
        'ccf': 'ccf', 'sci': 'sci_jcr', 'sciUp': 'sci_cas',
        'sciUpSmall': 'sci_cas_small', 'fms': 'fms', 'swufe': 'swufe',
        'pku': 'pku', 'cssci': 'cssci', 'cscd': 'cscd', 'eii': 'eii',
    }
    for src, dest in _str_fields.items():
        if src in all_ranks:
            result[dest] = all_ranks[src]

    # Boolean / presence-valued rankings
    # sciUpTop returns values like "计算机科学TOP" or "是" — truthy = Top
    # utd24/ft50 return "UTD24"/"FT50" or "是" — truthy = included
    if 'sciUpTop' in all_ranks:
        val = all_ranks['sciUpTop']
        result['sci_cas_top'] = bool(val) and str(val).strip().lower() != '否'
    if 'utd24' in all_ranks:
        result['utd24'] = True
    if 'ft50' in all_ranks:
        result['ft50'] = True

    # Custom rankings
    custom = data.get('customRank', {})
    rank_info = custom.get('rankInfo', [])
    ranks = custom.get('rank', [])
    if ranks and rank_info:
        uuid_to_info = {ri.get('uuid', ''): ri for ri in rank_info}
        level_keys = [
            'oneRankText', 'twoRankText', 'threeRankText',
            'fourRankText', 'fiveRankText',
        ]
        custom_parts = []
        for entry in ranks:
            parts = entry.split('&&&')
            if len(parts) != 2:
                continue
            rid, level_str = parts
            info = uuid_to_info.get(rid)
            if not info:
                continue
            abb = info.get('abbName', rid)
            try:
                level = int(level_str)
            except ValueError:
                continue
            if 1 <= level <= 5:
                rank_text = info.get(level_keys[level - 1], str(level))
            else:
                rank_text = str(level)
            custom_parts.append(f'{abb} {rank_text}')
        if custom_parts:
            result['custom_ranks'] = ', '.join(custom_parts)

    return result


def get_venue_ranking(normalized_venue: str, secret_key: str = None) -> dict:
    """Query EasyScholar for a normalized venue abbreviation.

    Tries the full official name from VENUE_TO_EASYSCHOLAR first,
    then falls back to the abbreviation itself.

    Args:
        normalized_venue: e.g. "NeurIPS", "TPAMI"
        secret_key: EasyScholar API key (loads from config if None)

    Returns:
        Dict from extract_ranking_fields() — all None when unknown/unavailable
    """
    if not normalized_venue:
        return extract_ranking_fields(None)

    key = secret_key or _load_secret_key()
    if not key:
        return extract_ranking_fields(None)

    # Primary: try mapped official name
    pub_name = VENUE_TO_EASYSCHOLAR.get(normalized_venue, normalized_venue)
    data = query_easyscholar(pub_name, key)

    # Fallback: if mapped name differs and failed, try the abbreviation
    if not data and pub_name != normalized_venue:
        data = query_easyscholar(normalized_venue, key)

    return extract_ranking_fields(data)

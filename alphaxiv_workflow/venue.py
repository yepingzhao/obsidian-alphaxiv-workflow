"""Venue extraction and publication ranking (EasyScholar API)."""
import time
import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error

from .config import EASYSCHOLAR_SECRET_KEY

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
    key = secret_key or EASYSCHOLAR_SECRET_KEY
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

    # or {} fixes the None crash (key exists with value None causes
    # AttributeError downstream). Tradeoff: also replaces falsy values
    # (0, False, [], "") with {} — safe here since EasyScholar API returns
    # either a dict or null for these fields, never 0/False/[]/"".
    official = data.get('officialRank') or {}
    all_ranks = official.get('all') or {}

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

    key = secret_key or EASYSCHOLAR_SECRET_KEY
    if not key:
        return extract_ranking_fields(None)

    # Primary: try mapped official name
    pub_name = VENUE_TO_EASYSCHOLAR.get(normalized_venue, normalized_venue)
    data = query_easyscholar(pub_name, key)

    # Fallback: if mapped name differs and failed, try the abbreviation
    if not data and pub_name != normalized_venue:
        data = query_easyscholar(normalized_venue, key)

    return extract_ranking_fields(data)


# Venue name normalization: arXiv journal_ref full names -> abbreviations
VENUE_NORMALIZE = {
    "advances in neural information processing systems": "NeurIPS",
    "neural information processing systems": "NeurIPS",
    "international conference on machine learning": "ICML",
    "international conference on learning representations": "ICLR",
    "conference on computer vision and pattern recognition": "CVPR",
    "international conference on computer vision": "ICCV",
    "european conference on computer vision": "ECCV",
    "annual meeting of the association for computational linguistics": "ACL",
    "conference on empirical methods in natural language processing": "EMNLP",
    "aaai conference on artificial intelligence": "AAAI",
    "international joint conference on artificial intelligence": "IJCAI",
    "conference on knowledge discovery and data mining": "KDD",
    "international conference on research and development in information retrieval": "SIGIR",
    "international world wide web conference": "WWW",
    "the web conference": "WWW",
    "international conference on robotics and automation": "ICRA",
    "conference on robot learning": "CoRL",
    "ieee transactions on pattern analysis and machine intelligence": "TPAMI",
    "journal of machine learning research": "JMLR",
    "proceedings of the national academy of sciences": "PNAS",
    "international conference on artificial intelligence and statistics": "AISTATS",
    "conference on uncertainty in artificial intelligence": "UAI",
    "international conference on autonomous agents and multiagent systems": "AAMAS",
    "international conference on data mining": "ICDM",
    "international conference on data engineering": "ICDE",
    # NLP extras
    "north american chapter of the association for computational linguistics": "NAACL",
    "international conference on computational linguistics": "COLING",
    # Data / IR / DB extras
    "international conference on web search and data mining": "WSDM",
    "acm conference on recommender systems": "RecSys",
    "international conference on management of data": "SIGMOD",
    "international conference on very large data bases": "VLDB",
    # Systems
    "usenix symposium on operating systems design and implementation": "OSDI",
    "usenix symposium on networked systems design and implementation": "NSDI",
    "acm symposium on operating systems principles": "SOSP",
    # Architecture
    "international symposium on computer architecture": "ISCA",
    "ieee/acm international symposium on microarchitecture": "MICRO",
    "international symposium on high performance computer architecture": "HPCA",
    # HCI
    "acm conference on human factors in computing systems": "CHI",
    "acm symposium on user interface software and technology": "UIST",
    "acm conference on computer-supported cooperative work and social computing": "CSCW",
    "proceedings of the acm on interactive mobile wearable and ubiquitous technologies": "Ubicomp",
    # Mobile / Networks
    "international conference on mobile computing and networking": "MobiCom",
    "acm conference on embedded networked sensor systems": "SenSys",
    # Robotics extras
    "ieee/rsj international conference on intelligent robots and systems": "IROS",
    "robotics: science and systems": "RSS",
    # Graphics
    "acm transactions on graphics": "SIGGRAPH",
}


def _parse_venue_from_ref(journal_ref: str) -> str | None:
    """Parse arXiv journal_ref to extract normalized venue + year.

    Input:  'Advances in Neural Information Processing Systems 33 (NeurIPS 2020)'
    Output: 'NeurIPS 2020'
    """
    if not journal_ref or not journal_ref.strip():
        return None
    jr_lower = journal_ref.strip().lower()
    # Try full-name match first
    for full_name, abbrev in VENUE_NORMALIZE.items():
        if full_name in jr_lower:
            year_match = re.search(r'\b(20\d{2})\b', journal_ref)
            year = year_match.group(1) if year_match else ''
            return f'{abbrev} {year}'.strip() if year else abbrev
    # Fallback: check for acronyms with year
    for abbrev in set(VENUE_NORMALIZE.values()):
        pattern = re.compile(r'\b' + re.escape(abbrev) + r'\b', re.IGNORECASE)
        if pattern.search(journal_ref):
            year_match = re.search(r'\b(20\d{2})\b', journal_ref)
            year = year_match.group(1) if year_match else ''
            return f'{abbrev} {year}'.strip() if year else abbrev
    # Last resort: return raw text only if it looks like a venue reference
    # Must contain a year (20XX) OR venue-indicator words to avoid false
    # positives from non-venue comment text like "15 pages, 5 figures"
    venue_indicators = [
        r'\b20\d{2}\b', r'conference', r'proceedings', r'journal',
        r'transactions', r'symposium', r'workshop', r'accepted',
        r'published', r'press', r'springer', r'elsevier', r'ieee',
        r'acm\b', r'annual', r'international',
    ]
    raw = journal_ref.strip()
    looks_like_venue = any(re.search(ind, raw, re.IGNORECASE) for ind in venue_indicators)
    if looks_like_venue:
        return raw[:120] if len(raw) > 120 else raw
    return None

def _detect_presentation_type(text: str) -> str | None:
    """Detect Oral / Spotlight from arXiv comment or journal_ref text."""
    if not text:
        return None
    t = text.lower()
    # Oral patterns (check first — "oral spotlight" counts as Oral)
    if re.search(r'\boral\b', t):
        return 'Oral'
    if re.search(r'\bspotlight\b', t):
        return 'Spotlight'
    return None

# Patterns to extract venue mentions from abstract/text
# Matches: "accepted at NeurIPS 2024", "published in ICML 2023", "to appear at CVPR 2024", etc.
_VENUE_TEXT_PATTERNS = [
    # "Accepted/Presented/Published ... at/in/to VENUE YEAR"
    # Handles: "Accepted at NeurIPS 2024", "Published as a conference paper at ICLR 2024"
    re.compile(
        r'(?:accepted|published|appear(?:ing|s)?|presented)'
        r'\s+(?:.*?\s)?(?:at|to|in)'
        r'\s+((?:the\s+)?[\w\s&()\-]+?(?:\d{4}))',
        re.IGNORECASE
    ),
    # "In Proceedings of VENUE YEAR" / "Proceedings of the ..."
    re.compile(
        r'(?:in\s+)?proceedings\s+of\s+(?:the\s+)?([\w\s&()\-,/]+?(?:\d{4}))',
        re.IGNORECASE
    ),
    # "In VENUE_FULL_NAME volume (YEAR)" — e.g. "In Advances in Neural Information Processing Systems 33 (2020)"
    re.compile(
        r'(?:in\s+)?(' + '|'.join(re.escape(k) for k in VENUE_NORMALIZE.keys()) + r')'
        r'\s+\d+\s*\(?(\d{4})\)?',
        re.IGNORECASE
    ),
    # "VENUE_ACRONYM YEAR" standalone — e.g. "NeurIPS 2024"
    re.compile(
        r'\b(' + '|'.join(re.escape(v) for v in sorted(set(VENUE_NORMALIZE.values()), key=len, reverse=True))
        + r')\s+(\d{4})\b',
        re.IGNORECASE
    ),
]



def _extract_venue_from_text(text: str) -> str | None:
    """Extract venue + year from unstructured text (abstract, snippet, etc.).

    Matches patterns like:
    - "Accepted at NeurIPS 2024"
    - "Published in Proceedings of ICML 2023"
    - "In Advances in Neural Information Processing Systems 33 (NeurIPS 2020)"
    - "CVPR 2023" (from known venue list)
    """
    if not text:
        return None
    # Normalize whitespace and collapse newlines
    text = re.sub(r'\s+', ' ', text)
    for pattern in _VENUE_TEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            groups = match.groups()
            # Pattern 4 (acronym + year split across two groups)
            if len(groups) == 2 and groups[1].isdigit():
                venue_candidate = f'{groups[0]} {groups[1]}'
            else:
                venue_candidate = groups[0].strip()
            parsed = _parse_venue_from_ref(venue_candidate)
            if parsed:
                return parsed
    return None

# ──────────────────────────────────────────────────────────────────
# Publication ranking — EasyScholar integration
# ──────────────────────────────────────────────────────────────────


def fetch_publication_rank(published_venue: str) -> dict:
    """Fetch journal/conference rankings from EasyScholar for a venue.

    Extracts the venue abbreviation from the formatted venue string
    (e.g. "NeurIPS 2020" -> "NeurIPS"), then queries EasyScholar
    for CCF, SCI, CAS, FMS, UTD24, FT50 rankings.

    Args:
        published_venue: Formatted venue from fetch_publication_info()
                          e.g. "NeurIPS 2020", "TPAMI"

    Returns:
        Dict with: ccf, sci_jcr, sci_cas, sci_cas_small, sci_cas_top,
            fms, utd24, ft50, swufe, pku, cssci, cscd, eii, custom_ranks.
        All None when venue unknown or EasyScholar unavailable.
    """
    if not published_venue or get_venue_ranking is None:
        return (extract_ranking_fields or (lambda d: {}))(None)

    # published_venue format: "ABBREV YEAR" or "ABBREV"
    normalized = published_venue.strip().split()[0] if published_venue.strip() else None
    if not normalized:
        return extract_ranking_fields(None) if extract_ranking_fields else {}

    return get_venue_ranking(normalized)

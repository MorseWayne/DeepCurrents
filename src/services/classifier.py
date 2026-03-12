import re
from typing import List, Dict, Any, Optional, Literal, Set
from dataclasses import dataclass

ThreatLevel = Literal['critical', 'high', 'medium', 'low', 'info']
EventCategory = Literal[
    'conflict', 'protest', 'disaster', 'diplomatic', 'economic',
    'terrorism', 'cyber', 'health', 'environmental', 'military',
    'crime', 'infrastructure', 'tech', 'general'
]

@dataclass
class ThreatClassification:
    level: ThreatLevel
    category: EventCategory
    confidence: float
    matched_keyword: Optional[str] = None

THREAT_PRIORITY: Dict[ThreatLevel, int] = {
    'critical': 5,
    'high': 4,
    'medium': 3,
    'low': 2,
    'info': 1,
}

THREAT_LABELS: Dict[ThreatLevel, str] = {
    'critical': '🔴 CRIT',
    'high': '🟠 HIGH',
    'medium': '🟡 MED',
    'low': '🟢 LOW',
    'info': '🔵 INFO',
}

# ── 关键词定义 ──

CRITICAL_KEYWORDS: Dict[str, EventCategory] = {
    'nuclear strike': 'military', 'nuclear attack': 'military', 'nuclear war': 'military',
    'declaration of war': 'conflict', 'declares war': 'conflict', 'all-out war': 'conflict',
    'full-scale war': 'conflict', 'martial law': 'military', 'coup': 'military',
    'coup attempt': 'military', 'genocide': 'conflict', 'chemical attack': 'terrorism',
    'biological attack': 'terrorism', 'pandemic declared': 'health', 'health emergency': 'health',
    'nato article 5': 'military', 'meltdown': 'disaster', 'nuclear meltdown': 'disaster',
    'invasion': 'conflict', 'massive strikes': 'military', 'declared war': 'conflict',
}

HIGH_KEYWORDS: Dict[str, EventCategory] = {
    'war': 'conflict', 'armed conflict': 'conflict', 'airstrike': 'conflict',
    'airstrikes': 'conflict', 'drone strike': 'conflict', 'missile': 'military',
    'missile launch': 'military', 'troops deployed': 'military', 'military escalation': 'military',
    'military operation': 'military', 'ground offensive': 'military', 'bombing': 'conflict',
    'bombardment': 'conflict', 'shelling': 'conflict', 'casualties': 'conflict',
    'hostage': 'terrorism', 'terrorist': 'terrorism', 'terror attack': 'terrorism',
    'assassination': 'crime', 'cyber attack': 'cyber', 'ransomware': 'cyber',
    'data breach': 'cyber', 'sanctions': 'economic', 'embargo': 'economic',
    'earthquake': 'disaster', 'tsunami': 'disaster', 'hurricane': 'disaster',
    'typhoon': 'disaster', 'retaliatory strike': 'military', 'preemptive strike': 'military',
    'ballistic missile': 'military', 'cruise missile': 'military',
}

MEDIUM_KEYWORDS: Dict[str, EventCategory] = {
    'protest': 'protest', 'protests': 'protest', 'riot': 'protest', 'riots': 'protest',
    'unrest': 'protest', 'demonstration': 'protest', 'military exercise': 'military',
    'naval exercise': 'military', 'arms deal': 'military', 'diplomatic crisis': 'diplomatic',
    'ambassador recalled': 'diplomatic', 'trade war': 'economic', 'tariff': 'economic',
    'recession': 'economic', 'inflation': 'economic', 'market crash': 'economic',
    'flood': 'disaster', 'flooding': 'disaster', 'wildfire': 'disaster',
    'volcano': 'disaster', 'outbreak': 'health', 'epidemic': 'health',
    'oil spill': 'environmental', 'pipeline explosion': 'infrastructure', 'blackout': 'infrastructure',
    'power outage': 'infrastructure', 'interest rate hike': 'economic', 'rate cut': 'economic',
    'supply chain disruption': 'economic', 'currency crisis': 'economic', 'debt ceiling': 'economic',
    'sovereign default': 'economic',
}

LOW_KEYWORDS: Dict[str, EventCategory] = {
    'election': 'diplomatic', 'vote': 'diplomatic', 'referendum': 'diplomatic',
    'summit': 'diplomatic', 'treaty': 'diplomatic', 'agreement': 'diplomatic',
    'negotiation': 'diplomatic', 'ceasefire': 'diplomatic', 'climate change': 'environmental',
    'emissions': 'environmental', 'deforestation': 'environmental', 'drought': 'environmental',
    'vaccine': 'health', 'disease': 'health', 'virus': 'health', 'interest rate': 'economic',
    'gdp': 'economic', 'unemployment': 'economic', 'regulation': 'economic',
    'fed meeting': 'economic', 'ecb decision': 'economic', 'central bank': 'economic',
    'trade deal': 'economic', 'ipo': 'economic',
}

EXCLUSIONS = [
    'protein', 'couples', 'relationship', 'dating', 'diet', 'fitness',
    'recipe', 'cooking', 'shopping', 'fashion', 'celebrity', 'movie',
    'tv show', 'sports', 'game', 'concert', 'festival', 'wedding',
    'vacation', 'travel tips', 'life hack', 'self-care', 'wellness',
    'strikes deal', 'strikes agreement', 'strikes partnership',
]

SHORT_KEYWORDS = {'war', 'coup', 'riot', 'riots', 'vote', 'gdp', 'ipo', 'virus', 'disease', 'flood'}

ESCALATION_ACTIONS = re.compile(r'\b(attack|attacks|attacked|strike|strikes|struck|bomb|bombs|bombed|bombing|shell|shelled|missile|missiles|retaliates|killed|casualties|offensive|invaded|invades|airstrike|airstrikes|drone strike)\b', re.IGNORECASE)
ESCALATION_TARGETS = re.compile(r'\b(iran|tehran|russia|moscow|china|beijing|taiwan|taipei|north korea|pyongyang|nato|us base|us forces|middle east)\b', re.IGNORECASE)

_regex_cache = {}

def get_keyword_regex(kw: str) -> re.Pattern:
    if kw not in _regex_cache:
        escaped = re.escape(kw)
        if kw in SHORT_KEYWORDS:
            _regex_cache[kw] = re.compile(fr'\b{escaped}\b', re.IGNORECASE)
        else:
            _regex_cache[kw] = re.compile(escaped, re.IGNORECASE)
    return _regex_cache[kw]

def match_keywords(text: str, keywords: Dict[str, EventCategory]):
    for kw, cat in keywords.items():
        if get_keyword_regex(kw).search(text):
            return {"keyword": kw, "category": cat}
    return None

def should_escalate(text: str, category: EventCategory) -> bool:
    if category not in ('conflict', 'military'): return False
    return bool(ESCALATION_ACTIONS.search(text) and ESCALATION_TARGETS.search(text))

def classify_threat(title: str, content: str = "") -> ThreatClassification:
    title_lower = title.lower()
    content_snippet = content[:3000].lower() if content else ""

    if any(ex in title_lower for ex in EXCLUSIONS):
        return ThreatClassification(level='info', category='general', confidence=0.3)

    def run_match(text: str):
        m = match_keywords(text, CRITICAL_KEYWORDS)
        if m: return 'critical', m
        
        m = match_keywords(text, HIGH_KEYWORDS)
        if m:
            if should_escalate(text, m['category']):
                return 'critical', m
            return 'high', m
            
        m = match_keywords(text, MEDIUM_KEYWORDS)
        if m: return 'medium', m
        
        m = match_keywords(text, LOW_KEYWORDS)
        if m: return 'low', m
        
        return None

    title_res = run_match(title_lower)
    content_res = run_match(content_snippet) if content_snippet else None

    if content_res and (not title_res or THREAT_PRIORITY[content_res[0]] > THREAT_PRIORITY[title_res[0]]):
        return ThreatClassification(
            level=content_res[0],
            category=content_res[1]['category'],
            confidence=0.75,
            matched_keyword=content_res[1]['keyword']
        )
    
    if title_res:
        return ThreatClassification(
            level=title_res[0],
            category=title_res[1]['category'],
            confidence=0.9,
            matched_keyword=title_res[1]['keyword']
        )

    return ThreatClassification(level='info', category='general', confidence=0.3)

def aggregate_threats(items: List[Dict[str, Any]]) -> ThreatClassification:
    if not items:
        return ThreatClassification(level='info', category='general', confidence=0.3)

    max_level = 'info'
    max_priority = 0
    cat_counts = {}
    
    weighted_sum = 0.0
    weight_total = 0.0

    for item in items:
        threat = item['threat']
        p = THREAT_PRIORITY[threat.level]
        if p > max_priority:
            max_priority = p
            max_level = threat.level
        
        cat = threat.category
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        
        weight = 6 - min(item.get('tier', 4), 5)
        weighted_sum += threat.confidence * weight
        weight_total += weight

    top_cat = max(cat_counts, key=cat_counts.get) if cat_counts else 'general'
    
    return ThreatClassification(
        level=max_level,
        category=top_cat,
        confidence=weighted_sum / weight_total if weight_total > 0 else 0.5
    )

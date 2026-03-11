/**
 * 威胁分类器 (Threat Classifier)
 * 
 * 借鉴 WorldMonitor 的多级关键词威胁分类管线：
 * 1. 排除非相关内容（娱乐、体育等）
 * 2. 级联关键词匹配: CRITICAL → HIGH → MEDIUM → LOW → INFO
 * 3. 复合升级规则: 军事行为 + 关键地缘目标 → 自动升级
 */

export type ThreatLevel = 'critical' | 'high' | 'medium' | 'low' | 'info';

export type EventCategory =
  | 'conflict' | 'protest' | 'disaster' | 'diplomatic' | 'economic'
  | 'terrorism' | 'cyber' | 'health' | 'environmental' | 'military'
  | 'crime' | 'infrastructure' | 'tech' | 'general';

export interface ThreatClassification {
  level: ThreatLevel;
  category: EventCategory;
  confidence: number;
  matchedKeyword?: string;
}

export const THREAT_PRIORITY: Record<ThreatLevel, number> = {
  critical: 5,
  high: 4,
  medium: 3,
  low: 2,
  info: 1,
};

export const THREAT_LABELS: Record<ThreatLevel, string> = {
  critical: '🔴 CRIT',
  high: '🟠 HIGH',
  medium: '🟡 MED',
  low: '🟢 LOW',
  info: '🔵 INFO',
};

type KeywordMap = Record<string, EventCategory>;

// ── 关键词级联定义 ──
// 参考 WorldMonitor 的 550+ 关键词覆盖，精简为宏观经济 & 地缘视角

const CRITICAL_KEYWORDS: KeywordMap = {
  'nuclear strike': 'military',
  'nuclear attack': 'military',
  'nuclear war': 'military',
  'declaration of war': 'conflict',
  'declares war': 'conflict',
  'all-out war': 'conflict',
  'full-scale war': 'conflict',
  'martial law': 'military',
  'coup': 'military',
  'coup attempt': 'military',
  'genocide': 'conflict',
  'chemical attack': 'terrorism',
  'biological attack': 'terrorism',
  'pandemic declared': 'health',
  'health emergency': 'health',
  'nato article 5': 'military',
  'meltdown': 'disaster',
  'nuclear meltdown': 'disaster',
  'invasion': 'conflict',
  'massive strikes': 'military',
  'declared war': 'conflict',
};

const HIGH_KEYWORDS: KeywordMap = {
  'war': 'conflict',
  'armed conflict': 'conflict',
  'airstrike': 'conflict',
  'airstrikes': 'conflict',
  'drone strike': 'conflict',
  'missile': 'military',
  'missile launch': 'military',
  'troops deployed': 'military',
  'military escalation': 'military',
  'military operation': 'military',
  'ground offensive': 'military',
  'bombing': 'conflict',
  'bombardment': 'conflict',
  'shelling': 'conflict',
  'casualties': 'conflict',
  'hostage': 'terrorism',
  'terrorist': 'terrorism',
  'terror attack': 'terrorism',
  'assassination': 'crime',
  'cyber attack': 'cyber',
  'ransomware': 'cyber',
  'data breach': 'cyber',
  'sanctions': 'economic',
  'embargo': 'economic',
  'earthquake': 'disaster',
  'tsunami': 'disaster',
  'hurricane': 'disaster',
  'typhoon': 'disaster',
  'retaliatory strike': 'military',
  'preemptive strike': 'military',
  'ballistic missile': 'military',
  'cruise missile': 'military',
};

const MEDIUM_KEYWORDS: KeywordMap = {
  'protest': 'protest',
  'protests': 'protest',
  'riot': 'protest',
  'riots': 'protest',
  'unrest': 'protest',
  'demonstration': 'protest',
  'military exercise': 'military',
  'naval exercise': 'military',
  'arms deal': 'military',
  'diplomatic crisis': 'diplomatic',
  'ambassador recalled': 'diplomatic',
  'trade war': 'economic',
  'tariff': 'economic',
  'recession': 'economic',
  'inflation': 'economic',
  'market crash': 'economic',
  'flood': 'disaster',
  'flooding': 'disaster',
  'wildfire': 'disaster',
  'volcano': 'disaster',
  'outbreak': 'health',
  'epidemic': 'health',
  'oil spill': 'environmental',
  'pipeline explosion': 'infrastructure',
  'blackout': 'infrastructure',
  'power outage': 'infrastructure',
  'interest rate hike': 'economic',
  'rate cut': 'economic',
  'supply chain disruption': 'economic',
  'currency crisis': 'economic',
  'debt ceiling': 'economic',
  'sovereign default': 'economic',
};

const LOW_KEYWORDS: KeywordMap = {
  'election': 'diplomatic',
  'vote': 'diplomatic',
  'referendum': 'diplomatic',
  'summit': 'diplomatic',
  'treaty': 'diplomatic',
  'agreement': 'diplomatic',
  'negotiation': 'diplomatic',
  'ceasefire': 'diplomatic',
  'climate change': 'environmental',
  'emissions': 'environmental',
  'deforestation': 'environmental',
  'drought': 'environmental',
  'vaccine': 'health',
  'disease': 'health',
  'virus': 'health',
  'interest rate': 'economic',
  'gdp': 'economic',
  'unemployment': 'economic',
  'regulation': 'economic',
  'fed meeting': 'economic',
  'ecb decision': 'economic',
  'central bank': 'economic',
  'trade deal': 'economic',
  'ipo': 'economic',
};

// ── 排除列表：非宏观相关的噪音内容 ──
const EXCLUSIONS = [
  'protein', 'couples', 'relationship', 'dating', 'diet', 'fitness',
  'recipe', 'cooking', 'shopping', 'fashion', 'celebrity', 'movie',
  'tv show', 'sports', 'game', 'concert', 'festival', 'wedding',
  'vacation', 'travel tips', 'life hack', 'self-care', 'wellness',
  'strikes deal', 'strikes agreement', 'strikes partnership',
];

// ── 需要精确词边界匹配的短关键词 ──
const SHORT_KEYWORDS = new Set([
  'war', 'coup', 'riot', 'riots', 'vote', 'gdp', 'ipo',
  'virus', 'disease', 'flood',
]);

// ── 复合升级规则 ──
// 借鉴 WorldMonitor: HIGH 军事/冲突 + 关键地缘目标 → CRITICAL
const ESCALATION_ACTIONS = /\b(attack|attacks|attacked|strike|strikes|struck|bomb|bombs|bombed|bombing|shell|shelled|missile|missiles|retaliates|killed|casualties|offensive|invaded|invades)\b/;
const ESCALATION_TARGETS = /\b(iran|tehran|russia|moscow|china|beijing|taiwan|taipei|north korea|pyongyang|nato|us base|us forces)\b/;

// ── 正则缓存 ──
const keywordRegexCache = new Map<string, RegExp>();

function getKeywordRegex(kw: string): RegExp {
  let re = keywordRegexCache.get(kw);
  if (!re) {
    const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (SHORT_KEYWORDS.has(kw)) {
      re = new RegExp(`\\b${escaped}\\b`);
    } else {
      re = new RegExp(escaped);
    }
    keywordRegexCache.set(kw, re);
  }
  return re;
}

function matchKeywords(
  titleLower: string,
  keywords: KeywordMap
): { keyword: string; category: EventCategory } | null {
  for (const [kw, cat] of Object.entries(keywords)) {
    if (getKeywordRegex(kw).test(titleLower)) {
      return { keyword: kw, category: cat };
    }
  }
  return null;
}

function shouldEscalateToCritical(lower: string, matchCat: EventCategory): boolean {
  if (matchCat !== 'conflict' && matchCat !== 'military') return false;
  return ESCALATION_ACTIONS.test(lower) && ESCALATION_TARGETS.test(lower);
}

/**
 * 对新闻标题进行威胁分类
 * 返回威胁等级、事件类别和置信度
 */
export function classifyThreat(title: string): ThreatClassification {
  const lower = title.toLowerCase();

  // Phase 1: 排除非相关内容
  if (EXCLUSIONS.some(ex => lower.includes(ex))) {
    return { level: 'info', category: 'general', confidence: 0.3 };
  }

  // Phase 2: 级联关键词匹配
  let match = matchKeywords(lower, CRITICAL_KEYWORDS);
  if (match) return { level: 'critical', category: match.category, confidence: 0.9, matchedKeyword: match.keyword };

  match = matchKeywords(lower, HIGH_KEYWORDS);
  if (match) {
    // Phase 3: 复合升级规则
    if (shouldEscalateToCritical(lower, match.category)) {
      return { level: 'critical', category: match.category, confidence: 0.85, matchedKeyword: match.keyword };
    }
    return { level: 'high', category: match.category, confidence: 0.8, matchedKeyword: match.keyword };
  }

  match = matchKeywords(lower, MEDIUM_KEYWORDS);
  if (match) return { level: 'medium', category: match.category, confidence: 0.7, matchedKeyword: match.keyword };

  match = matchKeywords(lower, LOW_KEYWORDS);
  if (match) return { level: 'low', category: match.category, confidence: 0.6, matchedKeyword: match.keyword };

  return { level: 'info', category: 'general', confidence: 0.3 };
}

/**
 * 聚合多条新闻的威胁等级
 * 取最高等级，最常见类别，加权平均置信度
 */
export function aggregateThreats(
  items: Array<{ threat: ThreatClassification; tier?: number }>
): ThreatClassification {
  if (items.length === 0) {
    return { level: 'info', category: 'general', confidence: 0.3 };
  }

  // 取最高等级
  let maxLevel: ThreatLevel = 'info';
  let maxPriority = 0;
  for (const item of items) {
    const p = THREAT_PRIORITY[item.threat.level];
    if (p > maxPriority) {
      maxPriority = p;
      maxLevel = item.threat.level;
    }
  }

  // 最频繁的类别
  const catCounts = new Map<EventCategory, number>();
  for (const item of items) {
    const cat = item.threat.category;
    catCounts.set(cat, (catCounts.get(cat) ?? 0) + 1);
  }
  let topCat: EventCategory = 'general';
  let topCount = 0;
  for (const [cat, count] of catCounts) {
    if (count > topCount) {
      topCount = count;
      topCat = cat;
    }
  }

  // 加权平均（tier 越低权重越高）
  let weightedSum = 0;
  let weightTotal = 0;
  for (const item of items) {
    const weight = item.tier ? (6 - Math.min(item.tier, 5)) : 1;
    weightedSum += item.threat.confidence * weight;
    weightTotal += weight;
  }

  return {
    level: maxLevel,
    category: topCat,
    confidence: weightTotal > 0 ? weightedSum / weightTotal : 0.5,
  };
}

/**
 * 趋势关键词检测 (Trending Keywords)
 * 
 * 借鉴 WorldMonitor 的 Trending Keyword Spike Detection：
 * - 2小时滚动窗口计数
 * - 7天基线比对（Welford 算法）
 * - CVE/APT/领导人名字等实体自动提取
 * - 跨源验证（至少 2 个独立源确认）
 * - 冷却期避免重复告警
 */

import pino from 'pino';

const logger = pino({ name: 'TrendingKeywords', level: 'info', transport: { target: 'pino-pretty', options: { colorize: true } } });

// ── 时间窗口常量 ──
const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;
const ROLLING_WINDOW_MS = 2 * HOUR_MS;
const BASELINE_WINDOW_MS = 7 * DAY_MS;
const BASELINE_REFRESH_MS = HOUR_MS;
const SPIKE_COOLDOWN_MS = 30 * 60 * 1000;
const MAX_TRACKED_TERMS = 5000;
const MIN_TOKEN_LENGTH = 3;
const MIN_SPIKE_SOURCE_COUNT = 2;

// ── 类型定义 ──
export interface TrendingHeadlineInput {
  title: string;
  pubDate: Date;
  source: string;
  link?: string;
}

interface TermRecord {
  timestamps: number[];
  baseline7d: number;
  lastSpikeAlertMs: number;
  displayTerm: string;
  sources: Set<string>;
}

export interface TrendingSpike {
  term: string;
  count: number;
  baseline: number;
  multiplier: number;
  uniqueSources: number;
  headlines: Array<{ title: string; source: string }>;
}

export interface TrendingConfig {
  minSpikeCount: number;
  spikeMultiplier: number;
}

const DEFAULT_CONFIG: TrendingConfig = {
  minSpikeCount: 4,
  spikeMultiplier: 3,
};

// ── 停用词 ──
const STOP_WORDS = new Set([
  'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has',
  'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
  'might', 'can', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
  'as', 'and', 'but', 'or', 'not', 'it', 'its', 'he', 'she', 'they', 'we',
  'you', 'that', 'this', 'said', 'says', 'new', 'news', 'report', 'reports',
  'up', 'out', 'over', 'about', 'also', 'just', 'than', 'more', 'very', 'too',
  'after', 'before', 'being', 'into', 'how', 'why', 'what', 'when', 'where',
  'who', 'which', 'some', 'all', 'any', 'each', 'other', 'such', 'only',
  'own', 'same', 'so', 'then', 'there', 'these', 'those', 'between', 'through',
]);

// ── 实体提取正则 ──
const CVE_PATTERN = /CVE-\d{4}-\d{4,}/gi;
const APT_PATTERN = /APT\d+/gi;

const LEADER_NAMES = [
  'putin', 'zelensky', 'xi jinping', 'biden', 'trump', 'netanyahu',
  'khamenei', 'erdogan', 'modi', 'macron', 'scholz', 'starmer',
  'milei', 'kim jong un',
];

// ── 全局状态 ──
const termFrequency = new Map<string, TermRecord>();
const seenHeadlines = new Set<string>();
let lastBaselineRefreshMs = 0;

function toTermKey(term: string): string {
  return term.trim().toLowerCase();
}

function headlineKey(h: TrendingHeadlineInput): string {
  return `${h.source}|${h.title}`.toLowerCase();
}

/**
 * 从标题中提取实体（CVE、APT、领导人名字等）
 */
export function extractEntities(text: string): string[] {
  const entities: string[] = [];
  const lower = text.toLowerCase();

  for (const match of text.matchAll(CVE_PATTERN)) {
    entities.push(match[0].toUpperCase());
  }
  for (const match of text.matchAll(APT_PATTERN)) {
    entities.push(match[0].toUpperCase());
  }
  for (const name of LEADER_NAMES) {
    if (lower.includes(name)) {
      entities.push(name);
    }
  }

  return entities;
}

/**
 * 分词
 */
function tokenize(text: string): string[] {
  // 去掉末尾的 " - SourceName" 归属
  const idx = text.lastIndexOf(' - ');
  const clean = idx !== -1 ? text.slice(0, idx) : text;

  return clean
    .toLowerCase()
    .replace(/[^a-z0-9\s'-]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length >= MIN_TOKEN_LENGTH && !STOP_WORDS.has(t));
}

/**
 * 清理过期数据
 */
function pruneOldState(now: number): void {
  for (const [term, record] of termFrequency) {
    record.timestamps = record.timestamps.filter(ts => now - ts <= BASELINE_WINDOW_MS);
    if (record.timestamps.length === 0) {
      termFrequency.delete(term);
    }
  }

  // 限制总量
  if (termFrequency.size > MAX_TRACKED_TERMS) {
    const ordered = Array.from(termFrequency.entries())
      .map(([term, record]) => ({
        term,
        latest: record.timestamps[record.timestamps.length - 1] ?? 0,
      }))
      .sort((a, b) => a.latest - b.latest);

    for (const { term } of ordered) {
      if (termFrequency.size <= MAX_TRACKED_TERMS) break;
      termFrequency.delete(term);
    }
  }
}

/**
 * 刷新基线
 */
function maybeRefreshBaselines(now: number): void {
  if (now - lastBaselineRefreshMs < BASELINE_REFRESH_MS) return;
  for (const record of termFrequency.values()) {
    const weekCount = record.timestamps.filter(ts => now - ts <= BASELINE_WINDOW_MS).length;
    record.baseline7d = weekCount / 7; // 日均
  }
  lastBaselineRefreshMs = now;
}

/**
 * 摄入标题数据
 */
export function ingestHeadlines(headlines: TrendingHeadlineInput[]): void {
  if (headlines.length === 0) return;

  const now = Date.now();

  for (const headline of headlines) {
    if (!headline.title?.trim()) continue;

    const key = headlineKey(headline);
    if (seenHeadlines.has(key)) continue;
    seenHeadlines.add(key);

    // 分词 + 实体提取
    const tokens = tokenize(headline.title);
    const entities = extractEntities(headline.title);
    const allTerms = [...tokens, ...entities];

    for (const rawTerm of allTerms) {
      const termKey = toTermKey(rawTerm);
      if (!termKey) continue;

      let record = termFrequency.get(termKey);
      if (!record) {
        record = {
          timestamps: [],
          baseline7d: 0,
          lastSpikeAlertMs: 0,
          displayTerm: rawTerm,
          sources: new Set(),
        };
        termFrequency.set(termKey, record);
      }

      record.timestamps.push(now);
      record.sources.add(headline.source);
    }
  }

  pruneOldState(now);
  maybeRefreshBaselines(now);
}

/**
 * 检测飙升关键词
 */
export function detectSpikes(config?: Partial<TrendingConfig>): TrendingSpike[] {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const now = Date.now();
  const spikes: TrendingSpike[] = [];

  for (const [term, record] of termFrequency) {
    const recentCount = record.timestamps.filter(ts => now - ts < ROLLING_WINDOW_MS).length;
    if (recentCount < cfg.minSpikeCount) continue;

    const baseline = record.baseline7d;
    const multiplier = baseline > 0 ? recentCount / baseline : 0;
    const isSpike = baseline > 0
      ? recentCount > baseline * cfg.spikeMultiplier
      : recentCount >= cfg.minSpikeCount;

    if (!isSpike) continue;
    if (now - record.lastSpikeAlertMs < SPIKE_COOLDOWN_MS) continue;
    if (record.sources.size < MIN_SPIKE_SOURCE_COUNT) continue;

    record.lastSpikeAlertMs = now;

    spikes.push({
      term: record.displayTerm,
      count: recentCount,
      baseline,
      multiplier,
      uniqueSources: record.sources.size,
      headlines: [], // 可扩展为存储关联标题
    });
  }

  return spikes.sort((a, b) => b.count - a.count);
}

/**
 * 生成趋势上下文（用于 AI 深度分析）
 */
export function generateTrendingContext(): string {
  const spikes = detectSpikes();
  if (spikes.length === 0) return '';

  const lines: string[] = ['[TRENDING KEYWORDS - 2h rolling window vs 7d baseline]'];
  for (const spike of spikes.slice(0, 10)) {
    const multiplierText = spike.baseline > 0 ? `${spike.multiplier.toFixed(1)}x baseline` : 'new surge';
    lines.push(`- "${spike.term}": ${spike.count} mentions across ${spike.uniqueSources} sources (${multiplierText})`);
  }

  return lines.join('\n');
}

/**
 * 获取跟踪的关键词总数（用于监控）
 */
export function getTrackedTermCount(): number {
  return termFrequency.size;
}

/**
 * 重置状态（用于测试）
 */
export function resetTrendingState(): void {
  termFrequency.clear();
  seenHeadlines.clear();
  lastBaselineRefreshMs = 0;
}

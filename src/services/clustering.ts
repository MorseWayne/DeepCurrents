/**
 * 新闻聚类服务 (News Clustering)
 * 
 * 借鉴 WorldMonitor 的 Jaccard 相似度聚类：
 * - 词袋交集/并集计算相似度
 * - 同一事件被多个源报道时合并为一个"聚类事件"
 * - 按源 tier 和时新性排序
 * 
 * 核心策略：将碎片化的新闻条目聚合为"宏观事件"，
 * 帮助 AI 在更高层面进行分析。
 */

import { ThreatClassification, aggregateThreats, THREAT_PRIORITY } from './classifier';

export interface NewsItemForClustering {
  id: string;
  title: string;
  url: string;
  content: string;
  source: string;
  sourceTier: number;
  timestamp: string;
  threat: ThreatClassification;
}

export interface ClusteredEvent {
  id: string;
  primaryTitle: string;
  primaryUrl: string;
  primarySource: string;
  sourceCount: number;
  sources: Array<{ name: string; tier: number; title: string; url: string }>;
  allItems: NewsItemForClustering[];
  firstSeen: Date;
  lastUpdated: Date;
  threat: ThreatClassification;
}

// ── 停用词列表（不参与相似度计算）──
const STOP_WORDS = new Set([
  'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
  'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
  'should', 'may', 'might', 'can', 'shall', 'must', 'to', 'of', 'in',
  'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
  'during', 'before', 'after', 'above', 'below', 'between', 'and',
  'but', 'or', 'nor', 'not', 'so', 'yet', 'both', 'either', 'neither',
  'each', 'every', 'all', 'any', 'few', 'more', 'most', 'other',
  'some', 'such', 'no', 'only', 'own', 'same', 'than', 'too', 'very',
  'just', 'about', 'also', 'then', 'that', 'this', 'these', 'those',
  'it', 'its', 'he', 'she', 'they', 'we', 'you', 'who', 'what',
  'which', 'when', 'where', 'how', 'why', 'if', 'up', 'out', 'over',
  'says', 'said', 'new', 'news', 'report', 'reports', 'according',
]);

/**
 * 分词提取关键 token
 */
function tokenize(text: string): Set<string> {
  const tokens = text
    .toLowerCase()
    .replace(/[^a-z0-9\s'-]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length >= 3 && !STOP_WORDS.has(t));
  return new Set(tokens);
}

/**
 * Jaccard 相似度计算
 */
function jaccardSimilarity(setA: Set<string>, setB: Set<string>): number {
  if (setA.size === 0 || setB.size === 0) return 0;
  let intersection = 0;
  for (const item of setA) {
    if (setB.has(item)) intersection++;
  }
  const union = setA.size + setB.size - intersection;
  return union > 0 ? intersection / union : 0;
}

/**
 * 去除标题末尾的新闻源归属（如 " - Reuters"）
 */
function stripSourceAttribution(title: string): string {
  const idx = title.lastIndexOf(' - ');
  if (idx === -1) return title;
  const after = title.slice(idx + 3).trim();
  if (after.length > 0 && after.length <= 60 && !/[.!?]/.test(after)) {
    return title.slice(0, idx).trim();
  }
  return title;
}

/**
 * 对新闻列表执行聚类
 * 
 * @param items 待聚类的新闻条目
 * @param similarityThreshold Jaccard 相似度阈值（默认 0.3）
 * @returns 聚类后的事件列表，按 threat 优先级和时新性排序
 */
export function clusterNews(
  items: NewsItemForClustering[],
  similarityThreshold: number = 0.3
): ClusteredEvent[] {
  if (items.length === 0) return [];

  // 预计算各标题的 token 集合
  const tokenSets = items.map(item => ({
    item,
    tokens: tokenize(stripSourceAttribution(item.title)),
  }));

  // 并查集分组
  const parent: number[] = tokenSets.map((_, i) => i);
  function find(x: number): number {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]!]!;
      x = parent[x]!;
    }
    return x;
  }
  function union(a: number, b: number): void {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[ra] = rb;
  }

  // O(n²) 两两比较（新闻条目通常 < 500，可接受）
  for (let i = 0; i < tokenSets.length; i++) {
    for (let j = i + 1; j < tokenSets.length; j++) {
      const sim = jaccardSimilarity(tokenSets[i]!.tokens, tokenSets[j]!.tokens);
      if (sim >= similarityThreshold) {
        union(i, j);
      }
    }
  }

  // 按组收集
  const groups = new Map<number, NewsItemForClustering[]>();
  for (let i = 0; i < items.length; i++) {
    const root = find(i);
    const group = groups.get(root) || [];
    group.push(items[i]!);
    groups.set(root, group);
  }

  // 构建聚类事件
  const clusters: ClusteredEvent[] = [];
  for (const members of groups.values()) {
    // 选择 tier 最低（最权威）的作为主标题
    const sorted = [...members].sort((a, b) => {
      if (a.sourceTier !== b.sourceTier) return a.sourceTier - b.sourceTier;
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    });

    const primary = sorted[0]!;
    const dates = members.map(m => new Date(m.timestamp).getTime());
    const firstSeen = new Date(Math.min(...dates));
    const lastUpdated = new Date(Math.max(...dates));

    // 聚合威胁评估
    const threat = aggregateThreats(
      members.map(m => ({ threat: m.threat, tier: m.sourceTier }))
    );

    // 去重源列表
    const sourceMap = new Map<string, { name: string; tier: number; title: string; url: string }>();
    for (const m of sorted) {
      if (!sourceMap.has(m.source)) {
        sourceMap.set(m.source, { name: m.source, tier: m.sourceTier, title: m.title, url: m.url });
      }
    }

    clusters.push({
      id: `cluster-${primary.id}`,
      primaryTitle: primary.title,
      primaryUrl: primary.url,
      primarySource: primary.source,
      sourceCount: sourceMap.size,
      sources: Array.from(sourceMap.values()).slice(0, 5),
      allItems: members,
      firstSeen,
      lastUpdated,
      threat,
    });
  }

  // 按威胁优先级 → 时新性排序
  clusters.sort((a, b) => {
    const pa = THREAT_PRIORITY[a.threat.level];
    const pb = THREAT_PRIORITY[b.threat.level];
    if (pa !== pb) return pb - pa;
    return b.lastUpdated.getTime() - a.lastUpdated.getTime();
  });

  return clusters;
}

/**
 * 生成聚类摘要（用于 AI 上下文）
 */
export function generateClusterContext(clusters: ClusteredEvent[]): string {
  if (clusters.length === 0) return '';

  const lines: string[] = ['[CLUSTERED EVENTS]'];
  const top = clusters.slice(0, 15);

  for (const cluster of top) {
    const sourceInfo = cluster.sourceCount > 1 ? ` (${cluster.sourceCount} sources)` : '';
    const threatTag = cluster.threat.level !== 'info' ? ` [${cluster.threat.level.toUpperCase()}]` : '';
    lines.push(`- ${cluster.primaryTitle}${threatTag}${sourceInfo} via ${cluster.primarySource}`);
  }

  return lines.join('\n');
}

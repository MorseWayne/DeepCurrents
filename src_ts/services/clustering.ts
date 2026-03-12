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
import { tokenize, stripSourceAttribution } from '../utils/tokenizer';
import { CONFIG } from '../config/settings';

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
 * 对新闻列表执行聚类
 * 
 * @param items 待聚类的新闻条目
 * @param similarityThreshold Jaccard 相似度阈值
 * @returns 聚类后的事件列表，按 threat 优先级和时新性排序
 */
export function clusterNews(
  items: NewsItemForClustering[],
  similarityThreshold: number = CONFIG.CLUSTER_SIMILARITY_THRESHOLD
): ClusteredEvent[] {
  if (items.length === 0) return [];

  const tokenSets = items.map(item => ({
    item,
    tokens: tokenize(stripSourceAttribution(item.title)),
  }));

  // 并查集
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

  for (let i = 0; i < tokenSets.length; i++) {
    for (let j = i + 1; j < tokenSets.length; j++) {
      const sim = jaccardSimilarity(tokenSets[i]!.tokens, tokenSets[j]!.tokens);
      if (sim >= similarityThreshold) {
        union(i, j);
      }
    }
  }

  const groups = new Map<number, NewsItemForClustering[]>();
  for (let i = 0; i < items.length; i++) {
    const root = find(i);
    const group = groups.get(root) || [];
    group.push(items[i]!);
    groups.set(root, group);
  }

  const clusters: ClusteredEvent[] = [];
  for (const members of groups.values()) {
    const sorted = [...members].sort((a, b) => {
      if (a.sourceTier !== b.sourceTier) return a.sourceTier - b.sourceTier;
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    });

    const primary = sorted[0]!;
    const dates = members.map(m => new Date(m.timestamp).getTime());
    const firstSeen = new Date(Math.min(...dates));
    const lastUpdated = new Date(Math.max(...dates));

    const threat = aggregateThreats(
      members.map(m => ({ threat: m.threat, tier: m.sourceTier }))
    );

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
 *
 * 增强版：除标题外还附带信源细节和正文摘要，
 * 帮助 AI 在事件级别做更深入的分析。
 */
export function generateClusterContext(clusters: ClusteredEvent[]): string {
  if (clusters.length === 0) return '';

  const lines: string[] = ['[CLUSTERED EVENTS — Multi-source confirmed macro events]'];
  const top = clusters.slice(0, 15);

  for (const [i, cluster] of top.entries()) {
    const idx = i + 1;
    const sourceInfo = cluster.sourceCount > 1 ? ` (${cluster.sourceCount} independent sources)` : '';
    const threatTag = cluster.threat.level !== 'info' ? ` [${cluster.threat.level.toUpperCase()}]` : '';
    lines.push(`${idx}. ${cluster.primaryTitle}${threatTag}${sourceInfo}`);

    if (cluster.sources.length > 1) {
      const sourceNames = cluster.sources.slice(0, 5).map(s => `${s.name}(T${s.tier})`).join(', ');
      lines.push(`   Sources: ${sourceNames}`);
    }

    // 提取正文摘要（如果存在），增强 AI 因果推断能力
    const primaryItem = cluster.allItems[0];
    if (primaryItem?.content && primaryItem.content.length > 80) {
      const excerpt = primaryItem.content.substring(0, 350).replace(/\s+/g, ' ').trim();
      lines.push(`   ▸ ${excerpt}`);
    }
  }

  return lines.join('\n');
}

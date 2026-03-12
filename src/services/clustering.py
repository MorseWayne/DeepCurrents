from typing import List, Set, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
from ..config.settings import CONFIG
from ..utils.tokenizer import tokenize, strip_source_attribution
from .classifier import ThreatClassification, aggregate_threats, THREAT_PRIORITY

@dataclass
class NewsItemForClustering:
    id: str
    title: str
    url: str
    content: str
    source: str
    sourceTier: int
    timestamp: str
    threat: ThreatClassification

@dataclass
class ClusteredEvent:
    id: str
    primaryTitle: str
    primaryUrl: str
    primarySource: str
    sourceCount: int
    sources: List[Dict[str, Any]]
    allItems: List[NewsItemForClustering]
    firstSeen: datetime
    lastUpdated: datetime
    threat: ThreatClassification

def jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    if not set_a or not set_b: return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0

def cluster_news(
    items: List[NewsItemForClustering],
    similarity_threshold: float = None
) -> List[ClusteredEvent]:
    similarity_threshold = similarity_threshold or CONFIG.cluster_similarity_threshold
    if not items: return []

    token_sets = [
        {"item": item, "tokens": tokenize(strip_source_attribution(item.title))}
        for item in items
    ]

    # 并查集
    n = len(items)
    parent = list(range(n))
    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: int, b: int):
        root_a = find(a)
        root_b = find(b)
        if root_a != root_b:
            parent[root_a] = root_b

    for i in range(n):
        for j in range(i + 1, n):
            if jaccard_similarity(token_sets[i]["tokens"], token_sets[j]["tokens"]) >= similarity_threshold:
                union(i, j)

    groups = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(items[i])

    clusters = []
    for members in groups.values():
        # 排序：tier 越低越优先，其次时间最新
        sorted_members = sorted(
            members, 
            key=lambda m: (m.sourceTier, -datetime.fromisoformat(m.timestamp.replace('Z', '+00:00')).timestamp())
        )
        
        primary = sorted_members[0]
        timestamps = [datetime.fromisoformat(m.timestamp.replace('Z', '+00:00')) for m in members]
        
        threat = aggregate_threats([{"threat": m.threat, "tier": m.sourceTier} for m in members])
        
        source_map = {}
        for m in sorted_members:
            if m.source not in source_map:
                source_map[m.source] = {
                    "name": m.source, "tier": m.sourceTier, "title": m.title, "url": m.url
                }

        clusters.append(ClusteredEvent(
            id=f"cluster-{primary.id}",
            primaryTitle=primary.title,
            primaryUrl=primary.url,
            primarySource=primary.source,
            sourceCount=len(source_map),
            sources=list(source_map.values())[:5],
            allItems=members,
            firstSeen=min(timestamps),
            lastUpdated=max(timestamps),
            threat=threat
        ))

    # 最终排序：威胁等级最高，其次时间最新
    clusters.sort(
        key=lambda c: (THREAT_PRIORITY[c.threat.level], c.lastUpdated.timestamp()),
        reverse=True
    )

    return clusters

def generate_cluster_context(clusters: List[ClusteredEvent]) -> str:
    if not clusters: return ""

    lines = ["[CLUSTERED EVENTS — Multi-source confirmed macro events]"]
    for i, cluster in enumerate(clusters[:15]):
        idx = i + 1
        source_info = f" ({cluster.sourceCount} independent sources)" if cluster.sourceCount > 1 else ""
        threat_tag = f" [{cluster.threat.level.upper()}]" if cluster.threat.level != 'info' else ""
        lines.append(f"{idx}. {cluster.primaryTitle}{threat_tag}{source_info}")

        if len(cluster.sources) > 1:
            source_names = ", ".join([f"{s['name']}(T{s['tier']})" for s in cluster.sources[:5]])
            lines.append(f"   Sources: {source_names}")

        primary_item = cluster.allItems[0]
        if primary_item.content and len(primary_item.content) > 80:
            excerpt = re.sub(r'\s+', ' ', primary_item.content[:350]).strip()
            lines.append(f"   ▸ {excerpt}")

    return "\n".join(lines)

import re

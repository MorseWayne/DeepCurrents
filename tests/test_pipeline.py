import pytest
from src.services.classifier import classify_threat
from src.services.clustering import cluster_news, NewsItemForClustering

def test_classify_threat_critical():
    title = "Nuclear war declared between major powers"
    res = classify_threat(title)
    assert res.level == 'critical'
    assert res.category == 'military' # 对齐 CRITICAL_KEYWORDS 中的定义

def test_classify_threat_escalation():
    # HIGH 行为 + 关键地缘目标 -> CRITICAL
    title = "Airstrikes hit moscow targets"
    res = classify_threat(title)
    assert res.level == 'critical'
    assert res.category == 'conflict'

def test_classify_threat_exclusion():
    title = "New diet recipe for healthy living"
    res = classify_threat(title)
    assert res.level == 'info'

def test_news_clustering():
    items = [
        NewsItemForClustering(
            id='1', title='Gold prices surge amid tensions', url='u1', content='C1', 
            source='Reuters', sourceTier=1, timestamp='2026-03-12T10:00:00',
            threat=classify_threat('Gold prices surge amid tensions')
        ),
        NewsItemForClustering(
            id='2', title='Global tensions push gold higher', url='u2', content='C2', 
            source='Bloomberg', sourceTier=1, timestamp='2026-03-12T10:05:00',
            threat=classify_threat('Global tensions push gold higher')
        ),
        NewsItemForClustering(
            id='3', title='Oil prices stable today', url='u3', content='C3', 
            source='CNBC', sourceTier=2, timestamp='2026-03-12T10:10:00',
            threat=classify_threat('Oil prices stable today')
        )
    ]
    
    clusters = cluster_news(items, similarity_threshold=0.2)
    # 应有 2 个聚类：黄金相关 (1, 2) 和 原油相关 (3)
    assert len(clusters) == 2
    
    # 查找黄金聚类
    gold_cluster = next(c for c in clusters if 'gold' in c.primaryTitle.lower())
    assert gold_cluster.sourceCount == 2
    
if __name__ == "__main__":
    pytest.main([__file__])

import re
import jieba
from typing import Set, List

# CJK 统一表意文字正则
CJK_PATTERN = re.compile(r'[\u2e80-\u9fff\uf900-\ufaff\ufe30-\ufe4f\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]')

EN_STOP_WORDS = {
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
}

ZH_STOP_WORDS = {
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
    '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '看', '好',
    '自己', '这', '他', '她', '它', '们', '那', '把', '给', '让', '被',
    '与', '对', '而', '但', '以', '又', '从', '或', '其', '已', '为', '等',
    '之', '更', '能', '将', '可以', '可', '中', '及', '该', '所', '据',
    '没有', '还', '个', '来', '过', '没', '多', '做', '当', '用', '下',
}

ALL_STOP_WORDS = EN_STOP_WORDS | ZH_STOP_WORDS

def contains_cjk(text: str) -> bool:
    return bool(CJK_PATTERN.search(text))

def strip_source_attribution(title: str) -> str:
    """去除标题末尾的媒体归属（' - Reuters'、' | BBC News'）"""
    for sep in [' - ', ' | ']:
        if sep in title:
            parts = title.rsplit(sep, 1)
            after = parts[1].strip()
            # 如果分隔符后的内容较短且不像一个句子，则认为是归属标注
            if 0 < len(after) <= 60 and not any(c in after for c in '.!?'):
                return parts[0].strip()
    return title

def tokenize(text: str, min_length: int = 2) -> Set[str]:
    """多语言分词 → 去重 Set"""
    lower = text.lower()
    tokens = set()

    if contains_cjk(lower):
        # 使用 jieba 分词
        for word in jieba.cut(lower):
            word = word.strip()
            if not word or len(word) < min_length:
                continue
            if word in ALL_STOP_WORDS:
                continue
            tokens.add(word)
    else:
        # 英文分词逻辑
        words = re.sub(r'[^a-z0-9\s\'-]', ' ', lower).split()
        for w in words:
            if len(w) >= max(min_length, 3) and w not in ALL_STOP_WORDS:
                tokens.add(w)
    
    return tokens

def tokenize_to_array(text: str, min_length: int = 3) -> List[str]:
    """多语言分词 → 列表（保留重复，用于频率统计）"""
    lower = text.lower()
    tokens = []

    if contains_cjk(lower):
        for word in jieba.cut(lower):
            word = word.strip()
            if not word or len(word) < min_length:
                continue
            if word in ALL_STOP_WORDS:
                continue
            tokens.append(word)
    else:
        words = re.sub(r'[^a-z0-9\s\'-]', ' ', lower).split()
        for w in words:
            if len(w) >= min_length and w not in ALL_STOP_WORDS:
                tokens.append(w)
    
    return tokens

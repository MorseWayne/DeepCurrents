/**
 * 多语言分词器
 *
 * - 英文：空格分词 + 停用词过滤
 * - CJK（中日韩）：Intl.Segmenter 词级分词（Node 18+）
 * - 混合文本：一次遍历同时处理两类字符
 * - 降级方案：若 Segmenter 不可用，CJK 部分使用字符 bigram
 */

// CJK 统一表意文字 + 扩展 A/B + 兼容 + 日文假名 + 韩文
const CJK_REGEX = /[\u2e80-\u9fff\uf900-\ufaff\ufe30-\ufe4f\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]/;
const CJK_CHAR_CLASS = '[\\u2e80-\\u9fff\\uf900-\\ufaff\\ufe30-\\ufe4f\\u3040-\\u309f\\u30a0-\\u30ff\\uac00-\\ud7af]';
const CJK_ONLY = new RegExp(CJK_CHAR_CLASS, 'g');
const NON_CJK = new RegExp(CJK_CHAR_CLASS, 'g');

export const EN_STOP_WORDS = new Set([
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

export const ZH_STOP_WORDS = new Set([
  '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
  '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '看', '好',
  '自己', '这', '他', '她', '它', '们', '那', '把', '给', '让', '被',
  '与', '对', '而', '但', '以', '又', '从', '或', '其', '已', '为', '等',
  '之', '更', '能', '将', '可以', '可', '中', '及', '该', '所', '据',
  '没有', '还', '个', '来', '过', '没', '多', '做', '当', '用', '下',
]);

export const ALL_STOP_WORDS = new Set([...EN_STOP_WORDS, ...ZH_STOP_WORDS]);

export function containsCJK(text: string): boolean {
  return CJK_REGEX.test(text);
}

let _segmenter: Intl.Segmenter | null | undefined;
function getSegmenter(): Intl.Segmenter | null {
  if (_segmenter !== undefined) return _segmenter;
  _segmenter = (typeof Intl !== 'undefined' && typeof Intl.Segmenter === 'function')
    ? new Intl.Segmenter(undefined, { granularity: 'word' })
    : null;
  return _segmenter;
}

/**
 * 去除标题末尾的媒体归属（" - Reuters"、" | BBC News"）
 */
export function stripSourceAttribution(title: string): string {
  const idx = title.lastIndexOf(' - ');
  if (idx !== -1) {
    const after = title.slice(idx + 3).trim();
    if (after.length > 0 && after.length <= 60 && !/[.!?]/.test(after)) {
      return title.slice(0, idx).trim();
    }
  }
  return title;
}

/**
 * 多语言分词 → 去重 Set
 *
 * 用于聚类和去重等需要集合运算的场景。
 */
export function tokenize(text: string, minLength: number = 2): Set<string> {
  const lower = text.toLowerCase();
  const tokens = new Set<string>();
  const segmenter = getSegmenter();

  if (containsCJK(lower) && segmenter) {
    for (const { segment, isWordLike } of segmenter.segment(lower)) {
      if (!isWordLike) continue;
      const word = segment.trim();
      if (!word || word.length < minLength) continue;
      if (ALL_STOP_WORDS.has(word)) continue;
      tokens.add(word);
    }
  } else if (containsCJK(lower)) {
    // 降级：英文走空格分词，CJK 走字符 bigram
    const enText = lower.replace(new RegExp(CJK_CHAR_CLASS, 'g'), ' ');
    for (const w of enText.split(/\s+/)) {
      if (w.length >= 3 && !ALL_STOP_WORDS.has(w)) tokens.add(w);
    }
    const cjk = lower.replace(new RegExp(`[^${CJK_CHAR_CLASS.slice(1)}`, 'g'), '');
    for (let i = 0; i < cjk.length - 1; i++) {
      const bi = cjk.slice(i, i + 2);
      if (!ALL_STOP_WORDS.has(bi)) tokens.add(bi);
    }
  } else {
    for (const w of lower.replace(/[^a-z0-9\s'-]/g, ' ').split(/\s+/)) {
      if (w.length >= Math.max(minLength, 3) && !ALL_STOP_WORDS.has(w)) tokens.add(w);
    }
  }

  return tokens;
}

/**
 * 多语言分词 → 数组（保留重复，用于频率统计）
 */
export function tokenizeToArray(text: string, minLength: number = 3): string[] {
  const lower = text.toLowerCase();
  const tokens: string[] = [];
  const segmenter = getSegmenter();

  if (containsCJK(lower) && segmenter) {
    for (const { segment, isWordLike } of segmenter.segment(lower)) {
      if (!isWordLike) continue;
      const word = segment.trim();
      if (!word || word.length < minLength) continue;
      if (ALL_STOP_WORDS.has(word)) continue;
      tokens.push(word);
    }
  } else if (containsCJK(lower)) {
    const enText = lower.replace(new RegExp(CJK_CHAR_CLASS, 'g'), ' ');
    for (const w of enText.split(/\s+/)) {
      if (w.length >= 3 && !ALL_STOP_WORDS.has(w)) tokens.push(w);
    }
    const cjk = lower.replace(new RegExp(`[^${CJK_CHAR_CLASS.slice(1)}`, 'g'), '');
    for (let i = 0; i < cjk.length - 1; i++) {
      const bi = cjk.slice(i, i + 2);
      if (!ALL_STOP_WORDS.has(bi)) tokens.push(bi);
    }
  } else {
    for (const w of lower.replace(/[^a-z0-9\s'-]/g, ' ').split(/\s+/)) {
      if (w.length >= minLength && !ALL_STOP_WORDS.has(w)) tokens.push(w);
    }
  }

  return tokens;
}

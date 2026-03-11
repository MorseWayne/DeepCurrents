import axios from 'axios';
import { JSDOM } from 'jsdom';
import { Readability } from '@mozilla/readability';

/**
 * 全文提取工具 (Full-text Extractor)
 * 
 * 使用 Mozilla Readability 算法从网页中提取纯净正文。
 * 解决 RSS 摘要信息量不足的问题。
 */
export class Extractor {
  private static readonly USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36';

  /**
   * 从 URL 提取正文内容
   */
  public static async extract(url: string, timeoutMs = 10000): Promise<{ content: string; excerpt: string; title: string } | null> {
    try {
      // 1. 获取 HTML 源代码
      const response = await axios.get(url, {
        timeout: timeoutMs,
        headers: {
          'User-Agent': this.USER_AGENT,
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        },
      });

      const html = response.data;

      // 2. 使用 JSDOM 构造虚拟 DOM
      const dom = new JSDOM(html, { url });
      
      // 3. 使用 Readability 提取正文
      const reader = new Readability(dom.window.document);
      const article = reader.parse();

      if (!article) {
        return null;
      }

      // 4. 清洗内容：去除过长的空行和无意义的空格
      const cleanContent = (article.textContent ?? '')
        .replace(/\n\s*\n/g, '\n\n')
        .trim();

      return {
        content: cleanContent,
        excerpt: article.excerpt || '',
        title: article.title || '',
      };
    } catch (error: any) {
      console.error(`[Extractor] 抓取全文失败 ${url}: ${error.message}`);
      return null;
    }
  }
}

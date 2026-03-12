import Parser from 'rss-parser';
import pino from 'pino';
import { SOURCES, resolveSourceUrl } from './config/sources';

const logger = pino({ 
  name: 'SourceVerifier', 
  level: 'info', 
  transport: { target: 'pino-pretty', options: { colorize: true, destination: 2 } } 
});

/**
 * 信息源验证工具 (Source Verification Tool)
 * 
 * 专门用于检查：
 * 1. RSS 源的联通性
 * 2. 是否有有效条目
 * 3. 针对 RSSHub 源，检查 description/content 是否为空（防止爬虫被封）
 */
async function verifySources() {
  const parser = new Parser({ timeout: 15000 });
  logger.info(`--- 开始验证 ${SOURCES.length} 个信息源 ---`);

  const results = {
    total: SOURCES.length,
    passed: 0,
    failed: 0,
    empty: 0,
  };

  for (const source of SOURCES) {
    const url = resolveSourceUrl(source);
    const typeLabel = source.isRssHub ? '[RSSHub]' : '[RSS]';
    
    try {
      const feed = await parser.parseURL(url);
      
      if (!feed.items || feed.items.length === 0) {
        logger.warn(`⚠️ ${typeLabel} ${source.name}: 联通成功但无条目`);
        results.empty++;
        continue;
      }

      // 验证内容完整性
      const firstItem = feed.items[0];
      if (!firstItem) {
        logger.warn(`⚠️ ${typeLabel} ${source.name}: 联通成功但首条内容为空`);
        results.empty++;
        continue;
      }

      const hasContent = !!(firstItem.contentSnippet || firstItem.content || (firstItem as any).description);
      
      if (!hasContent) {
        logger.error(`❌ ${typeLabel} ${source.name}: ⚠️ 内容缺失 (Description Empty)`);
        results.failed++;
      } else {
        logger.info(`✅ ${typeLabel} ${source.name}: 正常 (${feed.items.length} 条)`);
        results.passed++;
      }
    } catch (e: any) {
      const message = e instanceof Error ? e.message : String(e);
      if (message.includes('403')) {
        logger.warn(`⏸️ ${typeLabel} ${source.name}: 联通受阻 (403 Forbidden). 建议使用自建 RSSHub 或配置代理。`);
        results.empty++; // 计入空/跳过，不计入失败
      } else {
        logger.error(`❌ ${typeLabel} ${source.name}: 失败 - ${message}`);
        results.failed++;
      }
    }
  }

  logger.info("--- 验证报告 ---");
  logger.info(`总计: ${results.total} | 通过: ${results.passed} | 失败: ${results.failed} | 无内容: ${results.empty}`);
  
  if (results.failed > 0) {
    process.exit(1);
  }
}

// 立即运行
verifySources().catch(err => {
  console.error("验证脚本崩溃:", err);
  process.exit(1);
});

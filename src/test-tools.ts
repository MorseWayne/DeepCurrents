import Parser from 'rss-parser';
import axios from 'axios';
import * as dotenv from 'dotenv';
import pino from 'pino';
import { SOURCES } from './config/sources';

dotenv.config();

const logger = pino({ 
  name: 'DeepCurrents-Tester', 
  level: 'info', 
  transport: { target: 'pino-pretty' } 
});

export class TestSuite {
  private parser = new Parser({ timeout: 10000 });

  /**
   * 测试 RSS 源联通性
   */
  public async testRSS() {
    logger.info("--- 开始测试 RSS 信息源 ---");
    const sampleSources = SOURCES.slice(0, 5); // 选取前5个作为样本
    for (const source of sampleSources) {
      try {
        const feed = await this.parser.parseURL(source.url);
        logger.info(`✅ [RSS] ${source.name}: 成功抓取到 ${feed.items.length} 条新闻`);
      } catch (e) {
        logger.error(`❌ [RSS] ${source.name} 失败: ${e.message}`);
      }
    }
  }

  /**
   * 测试 LLM (AI) 联通性与格式返回
   */
  public async testLLM() {
    logger.info("--- 开始测试 LLM (AI) 服务 ---");
    const apiUrl = process.env.AI_API_URL;
    const apiKey = process.env.AI_API_KEY;

    if (!apiUrl || !apiKey) {
      logger.error("❌ [AI] 未配置 AI_API_URL 或 AI_API_KEY");
      return;
    }

    try {
      const response = await axios.post(apiUrl, {
        model: process.env.AI_MODEL || "gpt-4o-mini",
        messages: [{ role: "user", content: "Say hello and return a JSON object with a 'status' field." }],
        response_format: { type: "json_object" }
      }, {
        headers: { 'Authorization': `Bearer ${apiKey}` },
        timeout: 15000
      });
      logger.info(`✅ [AI] 响应成功: ${JSON.stringify(response.data.choices[0].message.content)}`);
    } catch (e) {
      logger.error(`❌ [AI] 失败: ${e.message}`);
    }
  }

  /**
   * 测试飞书 Webhook
   */
  public async testFeishu() {
    logger.info("--- 开始测试飞书推送 ---");
    const webhookUrl = process.env.FEISHU_WEBHOOK;
    if (!webhookUrl) {
      logger.warn("⚠️ [Feishu] 未配置 FEISHU_WEBHOOK");
      return;
    }

    try {
      await axios.post(webhookUrl, {
        msg_type: "text",
        content: { text: "🌊 DeepCurrents 测试消息: 飞书推送联通性正常。" }
      });
      logger.info("✅ [Feishu] 测试消息已发送");
    } catch (e) {
      logger.error(`❌ [Feishu] 失败: ${e.message}`);
    }
  }

  /**
   * 测试 Telegram Bot
   */
  public async testTelegram() {
    logger.info("--- 开始测试 Telegram 推送 ---");
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const chatId = process.env.TELEGRAM_CHAT_ID;

    if (!token || !chatId) {
      logger.warn("⚠️ [Telegram] 未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID");
      return;
    }

    try {
      const url = `https://api.telegram.org/bot${token}/sendMessage`;
      await axios.post(url, {
        chat_id: chatId,
        text: "🌊 *DeepCurrents* 测试消息\nTelegram 推送联通性正常。",
        parse_mode: "Markdown"
      });
      logger.info("✅ [Telegram] 测试消息已发送");
    } catch (e) {
      logger.error(`❌ [Telegram] 失败: ${e.message}`);
    }
  }

  public async runAll() {
    await this.testRSS();
    console.log("\n");
    await this.testLLM();
    console.log("\n");
    await this.testFeishu();
    console.log("\n");
    await this.testTelegram();
    logger.info("--- 集成测试完成 ---");
  }
}

// 可用测试类别映射
const TEST_CATEGORIES: Record<string, (tester: TestSuite) => Promise<void>> = {
  rss: (t) => t.testRSS(),
  llm: (t) => t.testLLM(),
  feishu: (t) => t.testFeishu(),
  telegram: (t) => t.testTelegram(),
};

const AVAILABLE_CATEGORIES = Object.keys(TEST_CATEGORIES);

function printUsage() {
  console.log(`
用法: npx ts-node src/test-tools.ts [类别...]

可选类别: ${AVAILABLE_CATEGORIES.join(', ')}

示例:
  npx ts-node src/test-tools.ts              # 运行全部测试
  npx ts-node src/test-tools.ts rss          # 仅测试 RSS
  npx ts-node src/test-tools.ts rss llm      # 测试 RSS 和 LLM
  npx ts-node src/test-tools.ts feishu       # 仅测试飞书
`);
}

// 脚本直接运行逻辑
if (require.main === module) {
  const args = process.argv.slice(2).map((a) => a.toLowerCase());

  if (args.includes('--help') || args.includes('-h')) {
    printUsage();
    process.exit(0);
  }

  const tester = new TestSuite();

  if (args.length === 0) {
    // 无参数：运行全部测试
    tester.runAll();
  } else {
    // 校验参数合法性
    const invalid = args.filter((a) => !AVAILABLE_CATEGORIES.includes(a));
    if (invalid.length > 0) {
      logger.error(`未知的测试类别: ${invalid.join(', ')}`);
      printUsage();
      process.exit(1);
    }

    // 按顺序执行指定类别
    (async () => {
      for (const category of args) {
        await TEST_CATEGORIES[category]!(tester);
        console.log('\n');
      }
      logger.info('--- 指定测试完成 ---');
    })();
  }
}

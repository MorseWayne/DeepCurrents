/**
 * 手动触发全流程并输出每日研报
 *
 * 用法:
 *   npm run report                         # 采集 → 生成 → 推送 → 终端输出
 *   npm run report -- --no-push            # 跳过推送（预览模式，不标记已报告）
 *   npm run report -- --report-only        # 仅用已有数据生成（不采集）
 *   npm run report -- --json               # JSON 格式输出
 *   npm run report -- --output report.md   # 写入文件
 *   npm run report -- --help               # 查看帮助
 */

import * as fs from 'fs';
import * as path from 'path';
import { DeepCurrentsEngine } from './monitor';
import { DailyReport } from './services/ai.service';
import { ClusteredEvent } from './services/clustering';
import { THREAT_LABELS, ThreatLevel } from './services/classifier';
import { getLogger } from './utils/logger';

const logger = getLogger('report-cli');

// ── CLI 参数解析 ──

const argv = process.argv.slice(2);

function flagValue(name: string): string | null {
  const idx = argv.indexOf(name);
  return idx >= 0 && idx + 1 < argv.length ? argv[idx + 1]! : null;
}

const opts = {
  json:       argv.includes('--json'),
  noPush:     argv.includes('--no-push'),
  reportOnly: argv.includes('--report-only'),
  output:     flagValue('--output'),
  help:       argv.includes('--help') || argv.includes('-h'),
};

// ── 帮助信息 ──

if (opts.help) {
  console.log(`
🌊 DeepCurrents — 手动触发每日研报

用法:
  npm run report [-- <options>]
  npx ts-node src/run-report.ts [<options>]

选项:
  --report-only   仅基于已采集的数据生成研报（跳过 RSS 采集）
  --no-push       不推送到飞书/Telegram，不标记新闻为已报告（预览模式）
  --json          以 JSON 格式输出研报
  --output <path> 将研报写入指定文件（不写 stdout）
  --help, -h      显示帮助信息

示例:
  npm run report                                    # 完整流程
  npm run report -- --no-push                       # 预览，不推送
  npm run report -- --report-only --json            # 用已有数据生成 JSON
  npm run report -- --output data/reports/today.md  # 写入文件
`.trimStart());
  process.exit(0);
}

// ── 研报格式化 ──

function formatMarkdown(
  report: DailyReport,
  meta: { newsCount: number; clusterCount: number; clusters?: ClusteredEvent[] },
): string {
  const L: string[] = [];

  L.push(`# 🌊 DeepCurrents 每日全球情报与宏观策略`);
  L.push('');
  L.push(`**日期**: ${report.date}  `);
  L.push(`**数据源**: ${meta.newsCount} 条新闻 → ${meta.clusterCount} 个聚类事件`);
  L.push('');
  L.push('---');
  L.push('');

  // ── 原始情报数据（聚类后） ──
  if (meta.clusters && meta.clusters.length > 0) {
    const threatIcon: Record<string, string> = {
      critical: '🔴', high: '🟠', medium: '🟡', low: '🟢', info: '🔵',
    };

    L.push(`## 📋 原始情报数据 | Raw Intelligence Data`);
    L.push('');
    L.push(`> 以下为采集到的原始信息（经聚类去重），共 ${meta.clusters.length} 个事件。多源报道已合并展示。`);
    L.push('');

    for (const [i, cluster] of meta.clusters.entries()) {
      const tIcon = threatIcon[cluster.threat.level] ?? '⚪';
      const multiSource = cluster.sourceCount > 1 ? ` — ${cluster.sourceCount} 个独立源` : '';
      L.push(`### ${i + 1}. ${tIcon} ${cluster.primaryTitle}${multiSource}`);
      L.push('');

      L.push(`| 属性 | 值 |`);
      L.push(`|------|------|`);
      L.push(`| 威胁等级 | ${cluster.threat.level.toUpperCase()} (置信度 ${(cluster.threat.confidence * 100).toFixed(0)}%) |`);
      L.push(`| 分类 | ${cluster.threat.category} |`);
      L.push(`| 首次出现 | ${cluster.firstSeen.toISOString()} |`);
      L.push(`| 最后更新 | ${cluster.lastUpdated.toISOString()} |`);
      L.push('');

      if (cluster.allItems.length > 0) {
        L.push(`**来源:**`);
        L.push('');
        for (const item of cluster.allItems) {
          const ts = item.timestamp || '未知时间';
          L.push(`- \`${ts}\` **${item.source}** (T${item.sourceTier}): ${item.title}`);
          if (item.url) L.push(`  链接: ${item.url}`);
        }
        L.push('');
      }

      const primaryItem = cluster.allItems[0];
      if (primaryItem?.content && primaryItem.content.length > 0) {
        const snippet = primaryItem.content.substring(0, 500).replace(/\s+/g, ' ').trim();
        L.push(`**正文摘要:**`);
        L.push('');
        L.push(`> ${snippet}${primaryItem.content.length > 500 ? '...' : ''}`);
        L.push('');
      }
    }

    L.push('---');
    L.push('');
  }

  // ── 核心主线 ──
  L.push(`## 核心主线 | Executive Summary`);
  L.push('');
  L.push(report.executiveSummary);
  L.push('');

  // ── 重大事件 ──
  L.push(`## 重大事件 | Key Events`);
  L.push('');
  report.globalEvents.forEach((e, i) => {
    const icon = e.threatLevel
      ? (THREAT_LABELS[e.threatLevel as ThreatLevel] ?? '') + ' '
      : '';
    L.push(`### ${i + 1}. ${icon}${e.title}`);
    L.push('');
    L.push(e.detail);
    L.push('');
  });

  // ── 关键数据点 ──
  if (report.keyDataPoints && report.keyDataPoints.length > 0) {
    L.push(`## 关键数据 | Key Data Points`);
    L.push('');
    L.push('| 指标 | 数值 | 含义 |');
    L.push('|------|------|------|');
    for (const dp of report.keyDataPoints) {
      L.push(`| ${dp.metric} | ${dp.value} | ${dp.implication} |`);
    }
    L.push('');
  }

  // ── 趋势告警 ──
  if (report.trendingAlerts && report.trendingAlerts.length > 0) {
    L.push(`## 趋势告警 | Trending Alerts`);
    L.push('');
    for (const a of report.trendingAlerts) {
      const sig = a.significance === 'high' ? '🔴' : a.significance === 'medium' ? '🟡' : '🟢';
      L.push(`- ${sig} **${a.term}**: ${a.assessment}`);
    }
    L.push('');
  }

  // ── 地缘政治简报 ──
  if (report.geopoliticalBriefing) {
    L.push(`## 地缘政治简报 | Geopolitical Briefing`);
    L.push('');
    L.push(report.geopoliticalBriefing);
    L.push('');
  }

  // ── 宏观经济分析 ──
  L.push(`## 宏观趋势深度研判 | Deep Insights`);
  L.push('');
  L.push(report.economicAnalysis);
  L.push('');

  // ── 资产配置 ──
  L.push(`## 资产配置与投资风向 | Investment Strategy`);
  L.push('');
  report.investmentTrends.forEach(t => {
    const icon = t.trend === 'Bullish' ? '🟢 看涨' : t.trend === 'Bearish' ? '🔴 看跌' : '⚪ 中性';
    const conf = t.confidence != null ? ` (${t.confidence}%)` : '';
    const tf = t.timeframe ? ` [${t.timeframe}]` : '';
    L.push(`- **${t.assetClass}** ${icon}${conf}${tf}: ${t.rationale}`);
  });
  L.push('');

  // ── 风险评估 ──
  if (report.riskAssessment) {
    L.push(`## 风险评估 | Risk Assessment`);
    L.push('');
    L.push(report.riskAssessment);
    L.push('');
  }

  // ── 监控清单 ──
  if (report.watchlist && report.watchlist.length > 0) {
    L.push(`## 监控清单 | Watchlist`);
    L.push('');
    for (const w of report.watchlist) {
      const tf = w.timeframe ? ` ⏱ ${w.timeframe}` : '';
      L.push(`- **${w.item}**${tf}: ${w.reason}`);
    }
    L.push('');
  }

  // ── 信源分析 ──
  if (report.sourceAnalysis) {
    L.push(`## 信源分析 | Source Analysis`);
    L.push('');
    L.push(report.sourceAnalysis);
    L.push('');
  }

  L.push('---');
  L.push(`*Generated by DeepCurrents Intelligence v2.2*`);
  L.push('');
  return L.join('\n');
}

// ── 输出 ──

function writeOutput(content: string, filePath: string | null): void {
  if (filePath) {
    const dir = path.dirname(path.resolve(filePath));
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.resolve(filePath), content, 'utf-8');
    logger.info(`✅ 研报已写入 ${path.resolve(filePath)}`);
  } else {
    console.log(content);
  }
}

// ── 主流程 ──

async function main() {
  const engine = new DeepCurrentsEngine();

  // 1. 采集（除非 --report-only）
  if (!opts.reportOnly) {
    logger.info('📡 正在采集全球信息源...');
    const stats = await engine.collectData();
    logger.info(
      `📡 采集完成 — 新增 ${stats.newItems} | 跳过 ${stats.skippedSources} | ` +
      `错误 ${stats.errors} | 趋势飙升 ${stats.spikeCount}`,
    );
  }

  // 2. 生成研报
  logger.info('🧠 正在生成研报...');
  const result = await engine.generateReport();
  if (!result) {
    logger.warn('⚠️  无新数据，未生成研报。');
    process.exit(1);
  }
  logger.info(
    `🧠 研报生成完成 — ${result.newsCount} 条新闻 → ${result.clusterCount} 个聚类事件`,
  );

  // 3. 推送（除非 --no-push）
  if (!opts.noPush) {
    logger.info('📤 正在推送研报...');
    await engine.deliverReport(result.report, result.newsCount, result.clusterCount);
    engine.markNewsAsReported(result.newsIds);
    logger.info('📤 推送完成，新闻已标记为已报告。');
  } else {
    logger.info('⏭️  跳过推送（--no-push），新闻未标记为已报告。');
  }

  // 4. 格式化输出
  const content = opts.json
    ? JSON.stringify(result.report, null, 2)
    : formatMarkdown(result.report, {
        newsCount: result.newsCount,
        clusterCount: result.clusterCount,
        clusters: result.clusters,
      });

  writeOutput(content, opts.output);
}

main()
  .then(() => setTimeout(() => process.exit(0), 100))
  .catch(e => {
    logger.error(`❌ 执行失败: ${e.message}`);
    setTimeout(() => process.exit(1), 100);
  });

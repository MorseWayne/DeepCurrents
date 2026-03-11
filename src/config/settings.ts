/**
 * 集中配置模块
 *
 * 所有可调参数统一从环境变量读取，附带合理默认值。
 * dotenv 在此处加载，其余模块无需重复调用。
 */

import * as dotenv from 'dotenv';
dotenv.config();

function envInt(key: string, fallback: number): number {
  const v = process.env[key];
  if (!v) return fallback;
  const n = parseInt(v, 10);
  return Number.isNaN(n) ? fallback : n;
}

function envFloat(key: string, fallback: number): number {
  const v = process.env[key];
  if (!v) return fallback;
  const n = parseFloat(v);
  return Number.isNaN(n) ? fallback : n;
}

function envStr(key: string, fallback: string): string {
  return process.env[key] || fallback;
}

export const CONFIG = {
  // ── Cron 调度 ──
  CRON_COLLECT: envStr('CRON_COLLECT', '0 * * * *'),
  CRON_REPORT: envStr('CRON_REPORT', '0 8 * * *'),
  CRON_CLEANUP: envStr('CRON_CLEANUP', '0 3 * * *'),

  // ── RSS 采集 ──
  RSS_TIMEOUT_MS: envInt('RSS_TIMEOUT_MS', 15000),
  RSS_CONCURRENCY: envInt('RSS_CONCURRENCY', 10),

  // ── 熔断器 ──
  CB_MAX_FAILURES: envInt('CB_MAX_FAILURES', 3),
  CB_COOLDOWN_MS: envInt('CB_COOLDOWN_MS', 5 * 60 * 1000),

  // ── AI ──
  AI_TIMEOUT_MS: envInt('AI_TIMEOUT_MS', 90000),
  AI_MAX_CONTEXT_TOKENS: envInt('AI_MAX_CONTEXT_TOKENS', 8000),

  // ── 标题去重 ──
  DEDUP_SIMILARITY_THRESHOLD: envFloat('DEDUP_SIMILARITY_THRESHOLD', 0.55),
  DEDUP_HOURS_BACK: envInt('DEDUP_HOURS_BACK', 24),

  // ── 研报 ──
  REPORT_MAX_NEWS: envInt('REPORT_MAX_NEWS', 500),
  DATA_RETENTION_DAYS: envInt('DATA_RETENTION_DAYS', 30),

  // ── 聚类 ──
  CLUSTER_SIMILARITY_THRESHOLD: envFloat('CLUSTER_SIMILARITY_THRESHOLD', 0.3),

  // ── 趋势检测 ──
  TRENDING_MAX_TRACKED_TERMS: envInt('TRENDING_MAX_TRACKED_TERMS', 5000),
  TRENDING_MAX_SEEN_HEADLINES: envInt('TRENDING_MAX_SEEN_HEADLINES', 50000),

  // ── 通知推送 ──
  NOTIFY_MAX_RETRIES: envInt('NOTIFY_MAX_RETRIES', 3),
  NOTIFY_BASE_DELAY_MS: envInt('NOTIFY_BASE_DELAY_MS', 1000),
} as const;

/**
 * RSS 熔断器 (Circuit Breaker)
 * 
 * 借鉴 WorldMonitor 的 per-feed 容错策略：
 * - 连续失败计数 → 自动进入冷却期
 * - 冷却期内返回缓存数据
 * - 成功后自动重置
 * - 内存缓存 + TTL 管理
 */

import { getLogger } from '../utils/logger';

const logger = getLogger('circuit-breaker');

export interface CircuitBreakerState {
  failureCount: number;
  cooldownUntil: number;
  lastSuccess: number;
}

export interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

export class RSSCircuitBreaker {
  private states = new Map<string, CircuitBreakerState>();
  private cache = new Map<string, CacheEntry<any>>();

  // 配置参数
  private maxFailures: number;
  private cooldownMs: number;
  private cacheTtlMs: number;
  private maxCacheEntries: number;

  constructor(options?: {
    maxFailures?: number;     // 最大失败次数（默认 3）
    cooldownMs?: number;      // 冷却期毫秒（默认 5分钟）
    cacheTtlMs?: number;      // 缓存 TTL（默认 30分钟）
    maxCacheEntries?: number; // 最大缓存条目（默认 100）
  }) {
    this.maxFailures = options?.maxFailures ?? 3;
    this.cooldownMs = options?.cooldownMs ?? 5 * 60 * 1000;
    this.cacheTtlMs = options?.cacheTtlMs ?? 30 * 60 * 1000;
    this.maxCacheEntries = options?.maxCacheEntries ?? 100;
  }

  /**
   * 检查源是否处于冷却期
   */
  isOnCooldown(sourceKey: string): boolean {
    const state = this.states.get(sourceKey);
    if (!state) return false;
    if (Date.now() < state.cooldownUntil) return true;
    // 冷却期结束，重置
    if (state.cooldownUntil > 0) {
      this.states.delete(sourceKey);
    }
    return false;
  }

  /**
   * 记录抓取失败
   */
  recordFailure(sourceKey: string): void {
    const state = this.states.get(sourceKey) || { failureCount: 0, cooldownUntil: 0, lastSuccess: 0 };
    state.failureCount++;
    if (state.failureCount >= this.maxFailures) {
      state.cooldownUntil = Date.now() + this.cooldownMs;
      logger.warn(`[熔断] ${sourceKey} 连续失败 ${state.failureCount} 次，进入 ${this.cooldownMs / 1000}s 冷却期`);
    }
    this.states.set(sourceKey, state);
  }

  /**
   * 记录抓取成功（重置熔断状态）
   */
  recordSuccess(sourceKey: string): void {
    this.states.delete(sourceKey);
  }

  /**
   * 设置缓存
   */
  setCache<T>(key: string, data: T): void {
    this.cache.set(key, { data, timestamp: Date.now() });
    this.pruneCache();
  }

  /**
   * 获取缓存（如未过期）
   */
  getCache<T>(key: string): T | null {
    const entry = this.cache.get(key);
    if (!entry) return null;
    if (Date.now() - entry.timestamp > this.cacheTtlMs) {
      this.cache.delete(key);
      return null;
    }
    return entry.data as T;
  }

  /**
   * 获取过期缓存（作为 fallback，不检查 TTL）
   */
  getStaleCache<T>(key: string): T | null {
    const entry = this.cache.get(key);
    return entry ? (entry.data as T) : null;
  }

  /**
   * 清理过期缓存
   */
  private pruneCache(): void {
    if (this.cache.size <= this.maxCacheEntries) return;
    const entries = Array.from(this.cache.entries())
      .sort((a, b) => a[1].timestamp - b[1].timestamp);
    const toRemove = entries.slice(0, entries.length - this.maxCacheEntries);
    for (const [key] of toRemove) {
      this.cache.delete(key);
    }
  }

  /**
   * 获取所有熔断状态（用于监控/测试）
   */
  getStates(): Map<string, CircuitBreakerState> {
    return new Map(this.states);
  }

  /**
   * 获取统计摘要
   */
  getSummary(): { totalSources: number; onCooldown: number; cached: number } {
    const now = Date.now();
    let onCooldown = 0;
    for (const state of this.states.values()) {
      if (now < state.cooldownUntil) onCooldown++;
    }
    return {
      totalSources: this.states.size,
      onCooldown,
      cached: this.cache.size,
    };
  }
}

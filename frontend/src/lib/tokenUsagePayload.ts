import { makeTokenUsageComparisonRange } from './tokenUsageRange.ts'
import type { TokenUsagePayload, TokenUsageQuery } from './types.ts'

export type TokenUsageDisplayState = 'complete' | 'syncing' | 'partial' | 'stale' | 'unconfigured'

export function resolveTokenUsageDisplayState(payload: TokenUsagePayload | null, error = ''): TokenUsageDisplayState {
  if (error === 'tokenNoDataHint' || payload?.configured === false) return 'unconfigured'
  if (payload?.freshness === 'stale' || payload?.completeness === 'stale') return 'stale'
  if (payload?.warnings?.some((warning) => warning.code === 'DETAILS_SYNCING')) return 'syncing'
  if (payload?.completeness === 'partial') return 'partial'
  return 'complete'
}

export function tokenUsageUrl(query: TokenUsageQuery) {
  const comparison = makeTokenUsageComparisonRange(query)
  const timezoneOffsetMinutes = -new Date().getTimezoneOffset()
  const params = new URLSearchParams({
    start_timestamp: String(query.startTimestamp),
    end_timestamp: String(query.endTimestamp),
    time_granularity: query.timeGranularity,
    timezone_offset_minutes: String(timezoneOffsetMinutes),
    comparison_start_timestamp: String(comparison.query.startTimestamp),
    comparison_end_timestamp: String(comparison.query.endTimestamp),
  })
  return `/api/token-usage?${params.toString()}`
}

export function normalizeTokenUsagePayload(payload: TokenUsagePayload): TokenUsagePayload {
  const numberOrUndefined = (value: number | null | undefined) => value == null ? undefined : Number(value)
  const normalize = (data: TokenUsagePayload['data']) => ({
    summary: data.summary.map((row) => ({
      ...row,
      token_id: row.api_key_id || row.token_id,
      token_name: row.api_key_name || row.token_name,
      quota: numberOrUndefined(row.actual_cost_usd ?? row.quota),
      remain_quota: numberOrUndefined(row.quota_remaining_usd ?? row.remain_quota),
      used_quota: numberOrUndefined(row.quota_used_lifetime_usd ?? row.used_quota),
      token_used: numberOrUndefined(row.total_tokens ?? row.token_used),
      avg_use_time: row.average_duration_ms == null ? row.avg_use_time : Number(row.average_duration_ms) / 1000,
    })),
    trend: data.trend.map((row) => ({
      ...row,
      token_id: row.api_key_id || row.token_id,
      token_name: row.api_key_name || row.token_name,
      quota: numberOrUndefined(row.actual_cost_usd ?? row.quota),
      count: numberOrUndefined(row.request_count ?? row.count),
      token_used: numberOrUndefined(row.total_tokens ?? row.token_used),
    })),
    models: data.models.map((row) => ({
      ...row,
      token_id: row.api_key_id || row.token_id,
      token_name: row.api_key_name || row.token_name,
      quota: numberOrUndefined(row.actual_cost_usd ?? row.quota),
      count: numberOrUndefined(row.request_count ?? row.count),
      token_used: numberOrUndefined(row.total_tokens ?? row.token_used),
    })),
  })
  return {
    ...payload,
    data: normalize(payload.data),
    comparison: payload.comparison ? { ...payload.comparison, data: normalize(payload.comparison.data) } : undefined,
  }
}

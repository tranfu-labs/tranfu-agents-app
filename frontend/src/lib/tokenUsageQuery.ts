import { createLoader, createSerializer, parseAsInteger, parseAsString, useQueryStates } from 'nuqs'
import { makeTokenUsageRange } from './tokenUsageRange.ts'
import type { TokenUsageQuery, TokenUsageRangeMeta } from './types.ts'

export type TokenUsageKindFilter = 'all' | 'personal' | 'dapp' | 'other'
export type TokenUsageRiskFilter = 'all' | 'normal' | 'low_quota' | 'exhausted' | 'high_error' | 'disabled' | 'spike' | 'high_latency' | 'restricted_model'
export type TokenUsageSortField = 'quota' | 'request_count' | 'token_name' | 'owner' | 'kind' | 'risk' | 'last_used_at' | 'remain_quota'
export type TokenUsageSortDirection = 'asc' | 'desc'

export type TokenUsageQueryState = {
  w: string
  wstart: string
  wend: string
  g: string
  kind: string
  model: string
  risk: string
  topn: number
  q: string
  hz: string
  sort: string
  dir: string
}

export type TokenUsageFilters = {
  w: string
  wstart: string
  wend: string
  granularity: TokenUsageQuery['timeGranularity']
  kind: TokenUsageKindFilter
  model: string
  risk: TokenUsageRiskFilter
  topLimit: number
  q: string
  hideZero: boolean
  sort: { field: TokenUsageSortField; dir: TokenUsageSortDirection }
}

const queryParsers = {
  w: parseAsString.withDefault('today'),
  wstart: parseAsString.withDefault(''),
  wend: parseAsString.withDefault(''),
  g: parseAsString.withDefault('hour'),
  kind: parseAsString.withDefault('all'),
  model: parseAsString.withDefault('all'),
  risk: parseAsString.withDefault('all'),
  topn: parseAsInteger.withDefault(10),
  q: parseAsString.withDefault(''),
  hz: parseAsString.withDefault('0'),
  sort: parseAsString.withDefault('quota'),
  dir: parseAsString.withDefault('desc'),
}

export const tokenUsageQueryOptions = { history: 'replace' as const }
export const loadTokenUsageQueryState = createLoader(queryParsers)
export const serializeTokenUsageQueryState = createSerializer(queryParsers)

const PRESETS = new Set(['today', 'yesterday', 'this_week', 'last_week', '7d', '14d', '30d', 'custom'])
const GRANULARITIES = new Set<TokenUsageQuery['timeGranularity']>(['hour', 'four_hour', 'day', 'week', 'month'])
const KINDS = new Set<TokenUsageKindFilter>(['all', 'personal', 'dapp', 'other'])
const RISKS = new Set<TokenUsageRiskFilter>(['all', 'normal', 'low_quota', 'exhausted', 'high_error', 'disabled', 'spike', 'high_latency', 'restricted_model'])
const TOP_LIMITS = new Set([5, 10, 20])
const SORT_FIELDS = new Set<TokenUsageSortField>(['quota', 'request_count', 'token_name', 'owner', 'kind', 'risk', 'last_used_at', 'remain_quota'])

function enumValue<T extends string>(value: unknown, allowed: Set<T>, fallback: T): T {
  const normalized = String(value || '') as T
  return allowed.has(normalized) ? normalized : fallback
}

function unixParam(value: unknown) {
  const normalized = String(value || '').trim()
  if (!/^\d+$/.test(normalized)) return ''
  const parsed = Number(normalized)
  return Number.isSafeInteger(parsed) && parsed > 0 ? String(parsed) : ''
}

export function normalizeTokenUsageFilters(params: Partial<TokenUsageQueryState>): TokenUsageFilters {
  const granularity = enumValue(params.g, GRANULARITIES, 'hour')
  const kind = enumValue(params.kind, KINDS, 'all')
  const risk = enumValue(params.risk, RISKS, 'all')
  const field = enumValue(params.sort, SORT_FIELDS, 'quota')
  const dir: TokenUsageSortDirection = params.dir === 'asc' ? 'asc' : 'desc'
  const topLimit = TOP_LIMITS.has(Number(params.topn)) ? Number(params.topn) : 10
  return {
    w: enumValue(params.w, PRESETS, 'today'),
    wstart: unixParam(params.wstart),
    wend: unixParam(params.wend),
    granularity,
    kind,
    model: String(params.model || 'all'),
    risk,
    topLimit,
    q: String(params.q || ''),
    hideZero: params.hz === '1',
    sort: { field, dir },
  }
}

export function resolveTokenUsageApiQuery(params: Partial<TokenUsageQueryState>, now = new Date()): TokenUsageQuery | null {
  const filters = normalizeTokenUsageFilters(params)
  if (filters.w !== 'custom') return makeTokenUsageRange(filters.w, filters.granularity, now)
  if (tokenUsageCustomRangeIssue(filters)) return null
  const startTimestamp = Number(filters.wstart)
  const endTimestamp = Number(filters.wend)
  return { preset: 'custom', startTimestamp, endTimestamp, timeGranularity: filters.granularity }
}

export type TokenUsageCustomRangeIssue = 'incomplete' | 'order' | null

export function tokenUsageCustomRangeIssue(params: Partial<TokenUsageQueryState> | TokenUsageFilters): TokenUsageCustomRangeIssue {
  const filters = 'granularity' in params ? params : normalizeTokenUsageFilters(params)
  if (filters.w !== 'custom') return null
  if (!filters.wstart || !filters.wend) return 'incomplete'
  return Number(filters.wend) < Number(filters.wstart) ? 'order' : null
}

export function resolveTokenUsageModel(model: string, availableModels: string[], payloadReady: boolean) {
  if (!payloadReady || model === 'all' || availableModels.includes(model)) return model
  return 'all'
}

export function tokenUsagePayloadMatchesQuery(range: TokenUsageRangeMeta | undefined, query: TokenUsageQuery) {
  return Number(range?.start_timestamp) === query.startTimestamp
    && Number(range?.end_timestamp) === query.endTimestamp
    && range?.time_granularity === query.timeGranularity
}

export function tokenUsagePresetPatch(preset: string): Partial<TokenUsageQueryState> {
  return preset === 'custom' ? { w: preset } : { w: preset, wstart: '', wend: '' }
}

export function useTokenUsageQueryState() {
  return useQueryStates(queryParsers, tokenUsageQueryOptions)
}

export type SetTokenUsageQueryState = ReturnType<typeof useTokenUsageQueryState>[1]

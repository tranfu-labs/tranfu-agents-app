import type { SkillsEvidenceItem, SkillsEvidenceKind, SkillsEvidencePayload, SkillsEvidenceRecord } from './types'

const PRESERVE = ['w', 'wstart', 'wend', 'q', 'rt', 'view', 'topn'] as const
const CLUE_PRESERVE = ['w', 'wstart', 'wend', 'q', 'rt', 'view', 'topn', 'skill', 'operator', 'limit', 'offset'] as const
const PUBLISHED_PRESERVE = ['w', 'wstart', 'wend', 'q'] as const
const COMPANY_SOURCES = new Set(['own', 'meta'])
const QUERY_KEY_EXCLUDE = new Set(['limit', 'offset', 'focus'])
export type SkillsClueKind = 'untracked' | 'idle' | 'zero-install'
export type SkillsEvidencePageMode = 'records' | 'items'
export type EvidencePageFetcher = (query: string, signal: AbortSignal) => Promise<SkillsEvidencePayload>

const CLUE_TO_EVIDENCE_KIND: Record<SkillsClueKind, SkillsEvidenceKind> = {
  untracked: 'untracked',
  idle: 'idle',
  'zero-install': 'zero_install',
}

const EVIDENCE_TO_CLUE_KIND: Partial<Record<SkillsEvidenceKind, SkillsClueKind>> = {
  untracked: 'untracked',
  idle: 'idle',
  unused_ratio: 'idle',
  zero_install: 'zero-install',
}

function normalizeWindow(params: URLSearchParams) {
  const w = params.get('w') || ''
  if (w) return w
  const win = Number(params.get('win') || 7)
  if (win === 7 || win === 30 || win === 90) return `${win}d`
  return '7d'
}

function normalizedSource(value: string | null) {
  if (!value) return ''
  return value === '非公司库' ? 'non_catalog' : value
}

export function canonicalSkillsSearch(search: string) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  params.set('w', normalizeWindow(params))
  params.delete('win')
  return params.toString() ? `?${params.toString()}` : ''
}

export function evidenceSearch(search: string, kind: SkillsEvidenceKind, extra: Record<string, string | number | undefined> = {}) {
  const current = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const next = new URLSearchParams()
  PRESERVE.forEach((key) => {
    const value = current.get(key)
    if (value) next.set(key, value)
  })
  next.set('w', normalizeWindow(current))
  next.set('kind', kind)
  const src = normalizedSource(current.get('src'))
  if (kind === 'untracked') {
    next.set('src', 'non_catalog')
  } else if (kind === 'coverage' || kind === 'idle' || kind === 'unused_ratio' || kind === 'zero_install') {
    if (COMPANY_SOURCES.has(src)) next.set('src', src)
  } else if (src) {
    next.set('src', src)
  }
  Object.entries(extra).forEach(([key, value]) => {
    if (value === undefined || value === '') return
    next.set(key, String(value))
  })
  return `?${next.toString()}`
}

export function evidencePath(search: string, kind: SkillsEvidenceKind, extra: Record<string, string | number | undefined> = {}) {
  const clueKind = EVIDENCE_TO_CLUE_KIND[kind]
  if (clueKind) return cluePath(search, clueKind, extra)
  return `/skills/evidence${evidenceSearch(search, kind, extra)}`
}

export function clueSearch(search: string, clueKind: SkillsClueKind, extra: Record<string, string | number | undefined> = {}) {
  const current = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const next = new URLSearchParams()
  CLUE_PRESERVE.forEach((key) => {
    const value = current.get(key)
    if (value) next.set(key, value)
  })
  next.set('w', normalizeWindow(current))
  if (clueKind === 'untracked') {
    next.set('src', 'non_catalog')
  } else {
    const src = normalizedSource(current.get('src'))
    if (COMPANY_SOURCES.has(src)) next.set('src', src)
  }
  Object.entries(extra).forEach(([key, value]) => {
    if (value === undefined || value === '') return
    next.set(key, String(value))
  })
  return `?${next.toString()}`
}

export function cluePath(search: string, clueKind: SkillsClueKind, extra: Record<string, string | number | undefined> = {}) {
  return `/skills/clues/${clueKind}${clueSearch(search, clueKind, extra)}`
}

export function publishedSkillsSearch(search: string, extra: Record<string, string | number | undefined> = {}) {
  const current = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const next = new URLSearchParams()
  PUBLISHED_PRESERVE.forEach((key) => {
    const value = current.get(key)
    if (value) next.set(key, value)
  })
  next.set('w', normalizeWindow(current))
  const src = normalizedSource(current.get('src'))
  if (COMPANY_SOURCES.has(src)) next.set('src', src)
  Object.entries(extra).forEach(([key, value]) => {
    if (value === undefined || value === '') return
    next.set(key, String(value))
  })
  return `?${next.toString()}`
}

export function publishedSkillsPath(search: string, extra: Record<string, string | number | undefined> = {}) {
  return `/skills/new${publishedSkillsSearch(search, extra)}`
}

export function clueApiSearch(search: string, clueKind: SkillsClueKind) {
  const params = new URLSearchParams(clueSearch(search, clueKind).slice(1))
  params.set('kind', CLUE_TO_EVIDENCE_KIND[clueKind])
  return params.toString()
}

export function legacyEvidenceCluePath(search: string) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const kind = (params.get('kind') || 'total') as SkillsEvidenceKind
  const clueKind = EVIDENCE_TO_CLUE_KIND[kind]
  if (!clueKind) return ''
  params.delete('kind')
  params.delete('focus')
  return cluePath(`?${params.toString()}`, clueKind)
}

export function skillsBackSearch(search: string) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  ;['kind', 'limit', 'offset', 'focus', 'skill', 'operator'].forEach((key) => params.delete(key))
  params.set('w', normalizeWindow(params))
  params.delete('win')
  return params.toString() ? `?${params.toString()}` : ''
}

function evidenceParams(search: string) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  params.set('w', normalizeWindow(params))
  if (!params.get('kind')) params.set('kind', 'total')
  return params
}

function finiteCount(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0
}

function recordKey(record: SkillsEvidenceRecord) {
  return [
    record.session_id || '',
    record.skill || '',
    record.first_seen || record.day || '',
    record.operator || '',
    record.runtime || '',
    record.source || '',
  ].join('\u0001')
}

function itemKey(item: SkillsEvidenceItem) {
  return [item.name || '', item.source || ''].join('\u0001')
}

function uniqueBy<T>(items: T[], keyFor: (item: T) => string) {
  const seen = new Set<string>()
  const out: T[] = []
  items.forEach((item, index) => {
    const key = keyFor(item) || `fallback:${index}:${JSON.stringify(item)}`
    if (seen.has(key)) return
    seen.add(key)
    out.push(item)
  })
  return out
}

export function evidencePageQuery(search: string, loadedCount: number, limit = 100) {
  const params = evidenceParams(search)
  params.set('offset', String(Math.max(0, Math.floor(loadedCount || 0))))
  params.set('limit', String(Math.max(1, Math.floor(limit || 100))))
  return params.toString()
}

export function evidenceQueryKey(search: string) {
  const params = evidenceParams(search)
  QUERY_KEY_EXCLUDE.forEach((key) => params.delete(key))
  return new URLSearchParams([...params.entries()].sort(([a], [b]) => a.localeCompare(b))).toString()
}

export function shouldApplyEvidencePage(requestKey: string, currentSearch: string) {
  return requestKey === evidenceQueryKey(currentSearch)
}

export function evidencePayloadForQuery<T>(payload: T | null | undefined, payloadKey: string, currentKey: string) {
  return payload && payloadKey === currentKey ? payload : null
}

export function startEvidencePageRequest(query: string, fetchPage: EvidencePageFetcher, timeoutMs = 15000) {
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, Math.max(0, timeoutMs))
  const promise = fetchPage(query, controller.signal).finally(() => clearTimeout(timer))
  return {
    controller,
    promise,
    didTimeout: () => timedOut,
  }
}

export function evidenceLoadedCount(payload: SkillsEvidencePayload | null | undefined, mode: SkillsEvidencePageMode) {
  if (!payload) return 0
  return mode === 'items'
    ? uniqueBy(payload.items || [], itemKey).length
    : uniqueBy(payload.records || [], recordKey).length
}

export function evidenceTotalCount(payload: SkillsEvidencePayload | null | undefined, mode: SkillsEvidencePageMode) {
  if (!payload) return 0
  const summary = payload.summary || {}
  const total = mode === 'items' ? finiteCount(summary.items) : finiteCount(summary.records)
  return total || evidenceLoadedCount(payload, mode)
}

export function evidenceDisplayTotalCount(payload: SkillsEvidencePayload | null | undefined, mode: SkillsEvidencePageMode) {
  return Math.max(evidenceTotalCount(payload, mode), evidenceLoadedCount(payload, mode))
}

export function evidenceHasMore(payload: SkillsEvidencePayload | null | undefined, mode: SkillsEvidencePageMode) {
  return evidenceTotalCount(payload, mode) > evidenceLoadedCount(payload, mode)
}

export function mergeEvidencePage(current: SkillsEvidencePayload, next: SkillsEvidencePayload, mode: SkillsEvidencePageMode) {
  if (current.kind !== next.kind) return next
  const merged: SkillsEvidencePayload = {
    ...current,
    today: next.today || current.today,
    window: next.window || current.window,
    summary: { ...(current.summary || {}), ...(next.summary || {}) },
    catalog: next.catalog || current.catalog,
  }
  if (mode === 'items') {
    merged.items = uniqueBy([...(current.items || []), ...(next.items || [])], itemKey)
    merged.records = current.records || []
  } else {
    merged.records = uniqueBy([...(current.records || []), ...(next.records || [])], recordKey)
    merged.items = current.items || []
  }
  return merged
}

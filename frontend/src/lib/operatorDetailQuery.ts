import { encodePathParam } from './utils.ts'

const WINDOW_KEYS = new Set(['today', 'this_week', 'last_week', '7d', '14d', '30d', '90d', 'custom'])
const RETURN_KEYS = [
  'win',
  'rt',
  'src',
  'q',
  'sort',
  'dir',
  'view',
  'lens',
  'w',
  'wstart',
  'wend',
  'cmp',
  'topn',
  'hz',
  'sel',
  'scope',
] as const

function searchParams(search: string) {
  return new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
}

function validTimestamp(value: string | null) {
  if (!value || !/^\d+$/.test(value)) return ''
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) && parsed > 0 ? String(parsed) : ''
}

function windowKey(params: URLSearchParams) {
  const raw = params.get('w') || ''
  if (WINDOW_KEYS.has(raw)) return raw
  const legacy = Number(params.get('win') || 0)
  return legacy === 7 || legacy === 30 || legacy === 90 ? `${legacy}d` : '7d'
}

function statsParams(search: string, strictCustom: boolean) {
  const source = searchParams(search)
  const out = new URLSearchParams()
  const key = windowKey(source)
  const start = validTimestamp(source.get('wstart'))
  const end = validTimestamp(source.get('wend'))
  if (key === 'custom' && (!start || !end || Number(end) < Number(start))) {
    if (strictCustom) return null
    out.set('w', '7d')
  } else {
    out.set('w', key)
    if (key === 'custom') {
      out.set('wstart', start)
      out.set('wend', end)
    }
  }
  const runtime = (source.get('rt') || '').trim()
  const sourceFilter = (source.get('src') || '').trim()
  if (runtime) out.set('rt', runtime)
  if (sourceFilter) out.set('src', sourceFilter)
  return out
}

export function operatorDetailApiQuery(search: string) {
  return statsParams(search, true)?.toString() ?? null
}

export function sanitizeSkillsReturnQuery(raw: string) {
  if (!raw || raw.includes('://') || raw.startsWith('/')) return ''
  const source = searchParams(raw)
  const out = new URLSearchParams()
  RETURN_KEYS.forEach((key) => {
    const value = source.get(key)
    if (value !== null && value.length <= 512) out.set(key, value)
  })
  out.set('view', 'operator')
  return out.toString()
}

export function operatorDetailHref(operator: string, sourceSearch: string) {
  const stats = statsParams(sourceSearch, false) || new URLSearchParams('w=7d')
  const from = sanitizeSkillsReturnQuery(sourceSearch)
  if (from) stats.set('from', from)
  return `/operator/${encodePathParam(operator)}?${stats.toString()}`
}

export function operatorDetailBackHref(detailSearch: string) {
  const detail = searchParams(detailSearch)
  const from = sanitizeSkillsReturnQuery(detail.get('from') || '')
  if (from) return `/skills?${from}`
  const stats = statsParams(detailSearch, false) || new URLSearchParams('w=7d')
  stats.set('view', 'operator')
  return `/skills?${stats.toString()}`
}

export function isOperatorDetailActivationKey(key: string) {
  return key === 'Enter' || key === ' '
}

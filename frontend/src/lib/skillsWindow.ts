import type { SkillQueryState } from './skillQuery'

export type SkillsWindowKey = 'today' | 'this_week' | 'last_week' | '7d' | '14d' | '30d' | '90d' | 'custom'

export type SkillsWindow = {
  key: SkillsWindowKey
  label: string
  days: number
  startTimestamp?: number
  endTimestamp?: number
}

const VALID_KEYS = new Set<SkillsWindowKey>(['today', 'this_week', 'last_week', '7d', '14d', '30d', '90d', 'custom'])

function startOfLocalDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function unix(date: Date) {
  return Math.floor(date.getTime() / 1000)
}

function clampDays(value: number) {
  return Math.min(90, Math.max(1, Math.round(value)))
}

function parseIntParam(value?: string | number | null) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.floor(parsed) : undefined
}

function keyFromParams(params: Partial<SkillQueryState>): SkillsWindowKey {
  const raw = String(params.w || '').trim()
  if (VALID_KEYS.has(raw as SkillsWindowKey)) return raw as SkillsWindowKey
  const win = Number(params.win || 7)
  if (win === 7 || win === 30 || win === 90) return `${win}d` as SkillsWindowKey
  return '7d'
}

export function resolveSkillsWindow(params: Partial<SkillQueryState>, now = new Date()): SkillsWindow {
  const key = keyFromParams(params)
  const today = startOfLocalDay(now)
  if (key === 'today') return { key, label: 'today', days: 1, startTimestamp: unix(today), endTimestamp: unix(now) }
  if (key === 'this_week') {
    const day = today.getDay() || 7
    const start = new Date(today)
    start.setDate(today.getDate() - day + 1)
    return { key, label: 'this_week', days: day, startTimestamp: unix(start), endTimestamp: unix(now) }
  }
  if (key === 'last_week') {
    const day = today.getDay() || 7
    const end = new Date(today)
    end.setDate(today.getDate() - day)
    const start = new Date(end)
    start.setDate(end.getDate() - 6)
    return { key, label: 'last_week', days: 7, startTimestamp: unix(start), endTimestamp: unix(end) + 86399 }
  }
  if (key === 'custom') {
    const start = parseIntParam(params.wstart)
    const end = parseIntParam(params.wend)
    if (!start || !end || end < start) return { key: '7d', label: '7d', days: 7 }
    return { key, label: 'custom', days: clampDays((end - start) / 86400 + 1), startTimestamp: start, endTimestamp: end }
  }
  const days = Number(key.slice(0, -1))
  return { key, label: key, days }
}

export function skillsWindowQuery(params: Partial<SkillQueryState>) {
  const window = resolveSkillsWindow(params)
  const out = new URLSearchParams()
  out.set('w', window.key)
  out.set('days', String(window.days))
  if (params.rt) out.set('rt', params.rt)
  if (params.src) out.set('src', params.src)
  if (window.key === 'custom' && window.startTimestamp && window.endTimestamp) {
    out.set('wstart', String(window.startTimestamp))
    out.set('wend', String(window.endTimestamp))
  }
  if (params.rt) out.set('rt', String(params.rt))
  if (params.src) out.set('src', String(params.src))
  if (params.scope === 'new') out.set('scope', 'new')
  return out.toString()
}

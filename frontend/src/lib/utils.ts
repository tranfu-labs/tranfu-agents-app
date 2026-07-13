import type { AgentSession, Lang } from './types'
import { formatLocalTimestamp } from './timeFormat.ts'

export const RT: Record<string, string> = {
  'claude-code': 'Claude Code',
  'claude-desktop': 'Claude Desktop',
  codex: 'Codex',
  'open-claw': 'Open Claw',
  hermes: 'Hermes',
  manus: 'Manus',
  mulerun: 'MuleRun',
  chatgpt: 'ChatGPT',
}

export const LIVE = ['running', 'started', 'waiting', 'blocked']
export const ACT_DAYS = 90

export function ago(ts?: string) {
  if (!ts) return '—'
  const seconds = (Date.now() - new Date(ts).getTime()) / 1000
  if (Number.isNaN(seconds)) return '—'
  return seconds < 60 ? `${Math.round(seconds)}s` : seconds < 3600 ? `${Math.round(seconds / 60)}m` : `${Math.round(seconds / 3600)}h`
}

export function dur(value?: number | null) {
  const seconds = Number(value || 0)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return `${hours}h${minutes % 60 ? ` ${minutes % 60}m` : ''}`
}

export function hashHue(value?: string) {
  let h = 0
  for (const char of value || '') h = (h * 31 + char.charCodeAt(0)) % 360
  return h
}

export function initials(value?: string) {
  const text = (value || '?').trim()
  if ([...text].every((char) => char.charCodeAt(0) < 128)) {
    return text
      .split(/[\s_\-.]+/)
      .filter(Boolean)
      .map((part) => part[0])
      .join('')
      .slice(0, 2)
      .toUpperCase()
  }
  return text.slice(0, 1)
}

export function keyOf(agent: AgentSession) {
  return `${agent.operator}::${agent.agent || agent.runtime}`
}

export function shortShim(version?: string) {
  return version ? String(version).slice(0, 8) : '—'
}

export type ShimState = 'current' | 'outdated' | 'unknown'

export function shimState(agent: AgentSession, latest?: string): ShimState {
  if (!agent.shim_version) return 'unknown'
  if (!latest) return 'current'
  return agent.shim_version === latest ? 'current' : 'outdated'
}

export function isOldShim(agent: AgentSession, latest?: string) {
  return shimState(agent, latest) === 'outdated'
}

export function genDays(agent: AgentSession, days = 30) {
  if (agent.active_days && agent.active_days.length >= days) return agent.active_days.slice(-days)
  const base = agent.active_series || [3000]
  const seed = hashHue(keyOf(agent))
  const out: number[] = []
  for (let i = 0; i < days; i += 1) {
    const jitter = ((seed * (i + 7)) % 55) / 100
    out.push((seed + i * 3) % 5 === 0 ? 0 : Math.max(0, Math.round((base[i % base.length] || 0) * (0.45 + jitter))))
  }
  return out
}

export function utcDate(day?: string) {
  const parts = String(day || '').split('-').map(Number)
  if (parts.length !== 3 || !parts[0] || !parts[1] || !parts[2]) return null
  return new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]))
}

export function isoDay(date: Date) {
  return date.toISOString().slice(0, 10)
}

export function apiToday(src?: { today?: string } | null) {
  return src?.today || isoDay(new Date())
}

export function daySeries(today: string | undefined, count: number) {
  const end = utcDate(today) || utcDate(apiToday()) || new Date()
  const days: string[] = []
  for (let i = count - 1; i >= 0; i -= 1) {
    const date = new Date(end.getTime())
    date.setUTCDate(end.getUTCDate() - i)
    days.push(isoDay(date))
  }
  return days
}

export function sourceKey(source?: string) {
  return source === '非公司库' ? 'non_catalog' : source || 'non_catalog'
}

export function sourceLabel(source: string | undefined, t: (key: string) => string) {
  return t(`source_${sourceKey(source)}`) || source || t('source_non_catalog')
}

export function skillColor(name: string) {
  return name === '__other' ? 'var(--done)' : `hsl(${hashHue(name)} 62% 56%)`
}

export function locale(lang: Lang) {
  return lang === 'zh' ? 'zh-CN' : 'en-US'
}

export function encodePathParam(value: string) {
  return encodeURIComponent(value)
}

export function fmtTs(iso?: string) {
  return formatLocalTimestamp(iso).label
}

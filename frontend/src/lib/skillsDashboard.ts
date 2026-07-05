import type { SkillTableRow } from './types'

export type RankItem = SkillTableRow & { isOther?: boolean; names?: string[]; value: number }

export function deltaRatio(current: number, previous: number): number | null {
  if (!previous && !current) return null
  if (!previous && current > 0) return Number.POSITIVE_INFINITY
  return (current - previous) / Math.max(1, previous)
}

export function formatDelta(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (!Number.isFinite(value)) return '+∞%'
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(1)}%`
}

export function buildRankItems(rows: SkillTableRow[], topN: number): RankItem[] {
  const sorted = rows
    .map((row) => ({ ...row, value: Number(row.sessions_window ?? row.sessions_30d ?? 0) }))
    .sort((a, b) => b.value - a.value || a.name.localeCompare(b.name))
  if (sorted.length <= topN) return sorted
  const top = sorted.slice(0, topN)
  const rest = sorted.slice(topN)
  const otherValue = rest.reduce((sum, row) => sum + row.value, 0)
  return [
    ...top,
    {
      name: `其他 ${rest.length} 个 skill`,
      source: 'non_catalog',
      sessions_7d: 0,
      sessions_30d: otherValue,
      sessions_window: otherValue,
      previous_sessions: rest.reduce((sum, row) => sum + Number(row.previous_sessions || 0), 0),
      sessions_total: rest.reduce((sum, row) => sum + Number(row.sessions_total || 0), 0),
      users_30d: rest.reduce((sum, row) => sum + Number(row.users_30d || 0), 0),
      runtime_counts: {},
      value: otherValue,
      isOther: true,
      names: rest.map((row) => row.name),
    },
  ]
}

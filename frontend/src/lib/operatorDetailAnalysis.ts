import type { OperatorDetail } from './types'

export function operatorCompositionLabel(windowLabel: string, t: (key: string) => string) {
  return `${t('operatorComposition')} · ${windowLabel}`
}

export type OperatorAnalysisSkill = NonNullable<NonNullable<OperatorDetail['analysis']>['skills']>[number]

export type OperatorSkillAnalysisModel = {
  mode: 'empty' | 'donut' | 'trend'
  limit: 5 | 8
  total: number
  top: OperatorAnalysisSkill[]
  other: {
    count: number
    sessions: number
    share: number
  } | null
  all: OperatorAnalysisSkill[]
}

function count(row: OperatorAnalysisSkill) {
  return Number(row.sessions_window || 0)
}

export function buildOperatorSkillAnalysis(detail: OperatorDetail | null): OperatorSkillAnalysisModel {
  const days = Math.max(1, Number(detail?.window?.days || 7))
  const limit: 5 | 8 = days === 1 ? 5 : 8
  const all = (detail?.analysis?.skills || [])
    .filter((row) => count(row) > 0)
    .slice()
    .sort((a, b) => count(b) - count(a)
      || Number(b.previous_sessions || 0) - Number(a.previous_sessions || 0)
      || a.name.localeCompare(b.name))
  const total = all.reduce((sum, row) => sum + count(row), 0)
  const normalized = all.map((row) => ({
    ...row,
    share: total ? count(row) / total : 0,
  }))
  const tail = normalized.slice(limit)
  const tailSessions = tail.reduce((sum, row) => sum + count(row), 0)
  return {
    mode: total <= 0 ? 'empty' : days === 1 ? 'donut' : 'trend',
    limit,
    total,
    top: normalized.slice(0, limit),
    other: tail.length ? {
      count: tail.length,
      sessions: tailSessions,
      share: total ? tailSessions / total : 0,
    } : null,
    all: normalized,
  }
}

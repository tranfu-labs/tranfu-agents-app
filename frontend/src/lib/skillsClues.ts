import type { SkillsEvidencePayload } from './types'
import type { SkillsClueKind } from './skillsEvidence'

type T = (key: string) => string

function windowPeriodLabel(key: string | number | undefined, t: T) {
  const value = String(key || '7d')
  const normalized = value === '30' ? '30d' : value
  const map: Record<string, string> = {
    today: 'window_period_today',
    this_week: 'window_period_this_week',
    last_week: 'window_period_last_week',
    '7d': 'window_period_7d',
    '14d': 'window_period_14d',
    '30d': 'window_period_30d',
    '90d': 'window_period_90d',
    custom: 'window_period_custom',
  }
  return map[normalized] ? t(map[normalized]) : normalized
}

export function operatorShare(records: number | undefined, total: number | undefined) {
  const count = Number(records || 0)
  const denominator = Number(total || 0)
  const pct = denominator > 0 ? Math.round((count / denominator) * 100) : 0
  return `${count}/${denominator} · ${pct}%`
}

export function showTopSkillsForClue(clueKind: SkillsClueKind, search: string, data: SkillsEvidencePayload | null) {
  if (clueKind !== 'untracked') return false
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  return !params.get('skill') && !data?.applied_filters?.skill
}

export function clueTitle(clueKind: SkillsClueKind, t: T) {
  if (clueKind === 'idle') return t('clueIdleTitle')
  if (clueKind === 'zero-install') return t('clueZeroInstallTitle')
  return t('clueUntrackedTitle')
}

function sourceChip(value: string, t: T) {
  if (value === 'non_catalog' || value === '非公司库') return `${t('sourceFilter')}：${t('sourceUntracked')}`
  if (value.includes('own') || value.includes('meta')) return `${t('sourceFilter')}：${t('sourceCompany')}`
  if (value === 'external') return `${t('sourceFilter')}：${t('source_external')}`
  return `${t('sourceFilter')}：${value}`
}

export function humanFilterChips(data: SkillsEvidencePayload | null, t: T) {
  const filters = data?.applied_filters || {}
  const chips: string[] = []
  const w = filters.w ? String(filters.w) : data?.window?.key || ''
  if (w) chips.push(windowPeriodLabel(w, t))
  const start = filters.window_start || data?.window?.start
  const end = filters.window_end || data?.window?.end
  if (start && end) chips.push(`${start} ~ ${end}`)
  const src = filters.src ? String(filters.src) : ''
  if (src) chips.push(sourceChip(src, t))
  const rt = filters.rt ? String(filters.rt) : ''
  if (rt) chips.push(`${t('runtimeFilter')}：${rt}`)
  const skill = filters.skill ? String(filters.skill) : ''
  if (skill) chips.push(`skill：${skill}`)
  const operator = filters.operator ? String(filters.operator) : ''
  if (operator) chips.push(`${t('operatorName')}：${operator}`)
  const q = filters.q ? String(filters.q) : ''
  if (q) chips.push(`${t('filterAction')}：${q}`)
  return chips
}

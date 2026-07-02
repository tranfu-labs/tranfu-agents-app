import type { SkillsEvidenceKind, SkillsEvidencePayload } from './types'

type QueryLike = {
  w?: string
  win?: number
  rt?: string
  src?: string
}

type T = (key: string) => string

const LIST_KINDS = new Set<SkillsEvidenceKind>(['idle', 'unused_ratio', 'zero_install'])

function fmt(value: unknown) {
  const num = Number(value || 0)
  return new Intl.NumberFormat('zh-CN').format(Number.isFinite(num) ? Math.round(num * 100) / 100 : 0)
}

export function truncateName(name: string, max = 18) {
  const value = String(name || '').trim()
  if (value.length <= max) return value
  return `${value.slice(0, Math.max(1, max - 1))}…`
}

export function compactNameList(names: string[], max = 1) {
  const clean = names.map((name) => truncateName(name)).filter(Boolean)
  if (!clean.length) return '—'
  const shown = clean.slice(0, max)
  const rest = clean.length - shown.length
  return rest > 0 ? `${shown.join(' / ')} +${rest}` : shown.join(' / ')
}

export function windowDisplayLabel(key: string | number | undefined, t: T) {
  const value = String(key || '7d')
  const normalized = value === '30' ? '30d' : value
  const map: Record<string, string> = {
    today: 'window_today',
    this_week: 'window_this_week',
    last_week: 'window_last_week',
    '7d': 'window_7d',
    '14d': 'window_14d',
    '30d': 'window_30d',
    '90d': 'window_90d',
    custom: 'window_custom',
  }
  return map[normalized] ? t(map[normalized]) : normalized
}

export function windowPeriodLabel(key: string | number | undefined, t: T) {
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
  return map[normalized] ? t(map[normalized]) : windowDisplayLabel(normalized, t)
}

function fillWindowPattern(pattern: string, label: string) {
  return pattern.includes('{window}') ? pattern.replace('{window}', label) : `${label} ${pattern}`
}

export function windowChangeLabel(key: string | number | undefined, t: T) {
  return `${windowPeriodLabel(key, t)}${t('changesSuffix')}`
}

export function windowUsedLabel(key: string | number | undefined, t: T) {
  return fillWindowPattern(t('usedInWindow'), windowPeriodLabel(key, t))
}

export function windowZeroUsageLabel(key: string | number | undefined, t: T) {
  return fillWindowPattern(t('zeroUsageInWindow'), windowPeriodLabel(key, t))
}

export function windowTriggersLabel(key: string | number | undefined, t: T) {
  return fillWindowPattern(t('triggersInWindow'), windowPeriodLabel(key, t))
}

function sourceText(src: string | undefined, t: T) {
  if (!src) return t('allSource')
  if (src === 'non_catalog' || src === '非公司库') return t('source_non_catalog')
  if (src === 'own') return t('source_own')
  if (src === 'meta') return t('source_meta')
  if (src === 'external') return t('source_external')
  return src
}

export function mobileFilterSummary(params: QueryLike, view: 'skill' | 'operator', t: T) {
  const windowLabel = windowDisplayLabel(params.w || (params.win ? `${params.win}d` : '7d'), t)
  const viewLabel = view === 'operator' ? t('viewOperator') : t('viewSkill')
  const runtime = params.rt || ''
  const source = params.src || ''
  const filterLabel = runtime || source ? `${runtime || t('allRuntime')} · ${sourceText(source, t)}` : t('allRuntimeSource')
  return `${windowLabel} · ${viewLabel} · ${filterLabel} · ${t('filterAction')}`
}

export function isListEvidenceKind(kind?: SkillsEvidenceKind) {
  return LIST_KINDS.has(kind || 'total')
}

export function defaultEvidenceTab(kind?: SkillsEvidenceKind) {
  return isListEvidenceKind(kind) ? '名单' : '原始记录'
}

export function evidenceSummaryLine(data: SkillsEvidencePayload | null) {
  const kind = data?.kind || 'total'
  const summary = data?.summary || {}
  const records = summary.records ?? 0
  const skills = summary.skills ?? 0
  const operators = summary.operators ?? 0
  const sessions = summary.sessions ?? 0
  const items = summary.items ?? records
  const installed = summary.installed ?? summary.installs ?? 0
  const windowKey = data?.window?.key || 'window'
  if (kind === 'total') {
    const base = `${fmt(records)} records · ${fmt(skills)} skills · ${fmt(operators)} operators · ${fmt(sessions)} sessions`
    const untracked = Number(summary.untracked_records || 0)
    return untracked > 0 ? `${base}，其中 ${fmt(untracked)} 条来自未收录 skill` : base
  }
  if (kind === 'untracked') return `${fmt(records)} 条未收录使用 · ${fmt(skills)} skills · ${fmt(operators)} operators`
  if (kind === 'idle' || kind === 'unused_ratio') return `${fmt(items)} 个装了但 ${windowKey} 没用 · ${fmt(installed)} installs`
  if (kind === 'zero_install') return `${fmt(items)} 个收录但零装机`
  return `${fmt(records)} records · ${fmt(skills)} skills · ${fmt(operators)} operators`
}

export function kpiShortConclusion(kind: SkillsEvidenceKind, value: string, names: string[], records: number | undefined, t: T) {
  if (kind === 'untracked') return `${names.length || 0} ${t('skillsUnit')} · ${fmt(records || 0)} ${t('records')}`
  if (kind === 'idle') return `${value} ${t('skillsUnit')}`
  if (kind === 'unused_ratio') return value
  if (kind === 'coverage') return `${value} ${t('usedByCompany')}`
  if (kind === 'operators') return `${value} ${t('operatorsUnit')}`
  if (kind === 'top3') return t('top3Concentrated')
  if (kind === 'avg_per_session') return value
  return value
}

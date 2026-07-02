import type { SkillsEvidenceKind, SkillsEvidencePayload } from './types'

type QueryLike = {
  w?: string
  win?: number
  rt?: string
  src?: string
}

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

function sourceText(src?: string) {
  if (!src) return '全部 source'
  if (src === 'non_catalog' || src === '非公司库') return '非公司库'
  if (src === 'own') return 'own'
  if (src === 'meta') return 'meta'
  if (src === 'external') return 'external'
  return src
}

export function mobileFilterSummary(params: QueryLike, view: 'skill' | 'operator') {
  const windowLabel = params.w || (params.win ? `${params.win}d` : '7d')
  const viewLabel = view === 'operator' ? '按人' : '按 Skill'
  const runtime = params.rt || ''
  const source = params.src || ''
  const filterLabel = runtime || source ? `${runtime || '全部 runtime'} · ${sourceText(source)}` : '全部 runtime/source'
  return `${windowLabel} · ${viewLabel} · ${filterLabel} · 筛选`
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
  const windowKey = data?.window?.key || 'W'
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

export function kpiShortConclusion(label: string, value: string, names: string[], records?: number) {
  if (label.includes('未收录')) return `${names.length || 0} 个 skill · ${fmt(records || 0)} records`
  if (label.includes('装了没用') || label.includes('闲置')) return value
  if (label.includes('覆盖')) return `${value} 公司库 skill 有使用证据`
  if (label.includes('Top3')) return '使用集中在 3 个 skill'
  if (label.includes('平均')) return value
  return value
}

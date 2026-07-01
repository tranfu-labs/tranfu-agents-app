import type { SkillsEvidenceKind } from './types'

const PRESERVE = ['w', 'wstart', 'wend', 'q', 'rt', 'view', 'topn', 'win'] as const
const COMPANY_SOURCES = new Set(['own', 'meta'])

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
  return `/skills/evidence${evidenceSearch(search, kind, extra)}`
}

export function skillsBackSearch(search: string) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  ;['kind', 'limit', 'offset', 'focus', 'skill', 'operator'].forEach((key) => params.delete(key))
  return params.toString() ? `?${params.toString()}` : ''
}

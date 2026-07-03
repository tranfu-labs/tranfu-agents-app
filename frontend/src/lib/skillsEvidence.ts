import type { SkillsEvidenceKind } from './types'

const PRESERVE = ['w', 'wstart', 'wend', 'q', 'rt', 'view', 'topn', 'win'] as const
const CLUE_PRESERVE = ['w', 'wstart', 'wend', 'q', 'rt', 'view', 'topn', 'win', 'skill', 'operator', 'limit', 'offset'] as const
const COMPANY_SOURCES = new Set(['own', 'meta'])
export type SkillsClueKind = 'untracked' | 'idle' | 'zero-install'

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
  return params.toString() ? `?${params.toString()}` : ''
}

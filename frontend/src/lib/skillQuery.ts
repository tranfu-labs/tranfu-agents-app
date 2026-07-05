import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

export type SkillQueryState = {
  win: number
  rt: string
  src: string
  q: string
  sort: string
  dir: string
  view: string
  lens: string
  w: string
  wstart: string
  wend: string
  cmp: string
  topn: number
  hz: string
  sel: string
  scope: string
}

export type SetSkillQueryState = (patch: Partial<SkillQueryState>) => void

export const SKILL_QUERY_DEFAULTS: SkillQueryState = {
  win: 7,
  rt: '',
  src: '',
  q: '',
  sort: 'sessions_window',
  dir: 'desc',
  view: 'skill',
  lens: 'all',
  w: '',
  wstart: '',
  wend: '',
  cmp: '1',
  topn: 8,
  hz: '0',
  sel: '',
  scope: 'all',
}

const STRING_KEYS = ['rt', 'src', 'q', 'sort', 'dir', 'view', 'lens', 'w', 'wstart', 'wend', 'cmp', 'hz', 'sel', 'scope'] as const
const NUMBER_KEYS = ['win', 'topn'] as const

function parseInteger(value: string | null, fallback: number) {
  if (!value) return fallback
  const next = Number(value)
  return Number.isFinite(next) && Number.isInteger(next) ? next : fallback
}

export function parseSkillQuery(searchParams: URLSearchParams): SkillQueryState {
  const parsed = { ...SKILL_QUERY_DEFAULTS }
  for (const key of STRING_KEYS) parsed[key] = searchParams.get(key) || SKILL_QUERY_DEFAULTS[key]
  for (const key of NUMBER_KEYS) parsed[key] = parseInteger(searchParams.get(key), SKILL_QUERY_DEFAULTS[key])
  return parsed
}

export function patchSkillSearchParams(searchParams: URLSearchParams, patch: Partial<SkillQueryState>) {
  const next = new URLSearchParams(searchParams)
  for (const key of STRING_KEYS) {
    if (!(key in patch)) continue
    const value = String(patch[key] || '')
    if (!value || value === SKILL_QUERY_DEFAULTS[key]) next.delete(key)
    else next.set(key, value)
  }
  for (const key of NUMBER_KEYS) {
    if (!(key in patch)) continue
    const value = Number(patch[key])
    if (!Number.isFinite(value) || value === SKILL_QUERY_DEFAULTS[key]) next.delete(key)
    else next.set(key, String(value))
  }
  return next
}

export function useSkillQueryState(): [SkillQueryState, SetSkillQueryState] {
  const [searchParams, setSearchParams] = useSearchParams()
  const params = useMemo(() => parseSkillQuery(searchParams), [searchParams])
  const setParams = useCallback<SetSkillQueryState>((patch) => {
    setSearchParams((current) => patchSkillSearchParams(current, patch), { replace: true })
  }, [setSearchParams])
  return [params, setParams]
}

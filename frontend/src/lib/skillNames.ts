import type { Lang, SkillNamesMap } from './types'

export type SkillNameLike = {
  name?: string
  skill?: string
  display_name?: string
  display_name_zh?: string
}

export function skillSlug(value: string | SkillNameLike | null | undefined) {
  if (typeof value === 'string') return value
  return String(value?.name || value?.skill || '')
}

export function skillDisplayName(
  value: string | SkillNameLike | null | undefined,
  lang: Lang,
  names?: SkillNamesMap,
) {
  const slug = skillSlug(value)
  const direct = typeof value === 'object' && value ? value : undefined
  const mapped = names?.[slug]
  const english = direct?.display_name || mapped?.display_name || ''
  const chinese = direct?.display_name_zh || mapped?.display_name_zh || ''
  return lang === 'zh'
    ? chinese || english || slug
    : english || chinese || slug
}

export function skillSearchText(value: string | SkillNameLike, names?: SkillNamesMap) {
  const slug = skillSlug(value)
  const direct = typeof value === 'object' ? value : undefined
  const mapped = names?.[slug]
  return [slug, direct?.display_name, direct?.display_name_zh, mapped?.display_name, mapped?.display_name_zh]
    .filter(Boolean)
    .join('\n')
    .toLocaleLowerCase()
}

export function skillNameMatches(value: string | SkillNameLike, query: string, names?: SkillNamesMap) {
  const needle = query.trim().toLocaleLowerCase()
  return !needle || skillSearchText(value, names).includes(needle)
}

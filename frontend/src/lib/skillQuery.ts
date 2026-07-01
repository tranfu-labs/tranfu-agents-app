import { parseAsInteger, parseAsString, useQueryStates } from 'nuqs'

const queryParsers = {
  win: parseAsInteger.withDefault(7),
  rt: parseAsString.withDefault(''),
  src: parseAsString.withDefault(''),
  q: parseAsString.withDefault(''),
  sort: parseAsString.withDefault('sessions_window'),
  dir: parseAsString.withDefault('desc'),
  view: parseAsString.withDefault('skill'),
  lens: parseAsString.withDefault('all'),
  w: parseAsString.withDefault(''),
  wstart: parseAsString.withDefault(''),
  wend: parseAsString.withDefault(''),
  cmp: parseAsString.withDefault('1'),
  topn: parseAsInteger.withDefault(8),
  hz: parseAsString.withDefault('0'),
  sel: parseAsString.withDefault(''),
}

export function useSkillQueryState() {
  return useQueryStates(queryParsers, { history: 'replace' })
}

export type SkillQueryState = ReturnType<typeof useSkillQueryState>[0]
export type SetSkillQueryState = ReturnType<typeof useSkillQueryState>[1]

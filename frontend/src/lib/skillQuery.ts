import { parseAsInteger, parseAsString, useQueryStates } from 'nuqs'

const queryParsers = {
  win: parseAsInteger.withDefault(30),
  rt: parseAsString.withDefault(''),
  src: parseAsString.withDefault(''),
  q: parseAsString.withDefault(''),
  sort: parseAsString.withDefault('sessions_30d'),
  dir: parseAsString.withDefault('desc'),
}

export function useSkillQueryState() {
  return useQueryStates(queryParsers, { history: 'replace' })
}

export type SkillQueryState = ReturnType<typeof useSkillQueryState>[0]
export type SetSkillQueryState = ReturnType<typeof useSkillQueryState>[1]

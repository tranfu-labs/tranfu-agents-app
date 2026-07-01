import type { SetSkillQueryState, SkillQueryState } from './skillQuery'

export function selectedSkillOf(params: SkillQueryState) {
  return String(params.sel || '').trim()
}

export function setSelectedSkill(params: SkillQueryState, setParams: SetSkillQueryState, name: string) {
  const current = selectedSkillOf(params)
  void setParams({ sel: current === name ? '' : name })
}

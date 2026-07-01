export const SKILLS_CHART_DAY_SLOT = 28
export const SKILLS_CHART_AXIS_PAD = 54
export const SKILLS_CHART_SHORT_DAYS = 7

export type SkillsChartLayout = {
  dayCount: number
  trackWidth: number
  daySlot: number
  rightAlign: boolean
  scrollToEnd: boolean
}

export function resolveSkillsChartLayout(dayCount: number): SkillsChartLayout {
  const safeDayCount = Math.max(1, Math.round(Number.isFinite(dayCount) ? dayCount : SKILLS_CHART_SHORT_DAYS))
  return {
    dayCount: safeDayCount,
    trackWidth: SKILLS_CHART_AXIS_PAD + safeDayCount * SKILLS_CHART_DAY_SLOT,
    daySlot: SKILLS_CHART_DAY_SLOT,
    rightAlign: true,
    scrollToEnd: safeDayCount > SKILLS_CHART_SHORT_DAYS,
  }
}

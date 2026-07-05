export const SKILLS_CHART_DAY_SLOT = 28
export const SKILLS_CHART_MIN_DAY_SLOT = 18
export const SKILLS_CHART_MAX_BAR_WIDTH = 30
export const SKILLS_CHART_AXIS_PAD = 54
export const SKILLS_CHART_SHORT_DAYS = 14

export type SkillsChartLayout = {
  dayCount: number
  trackWidth: number
  daySlot: number
  barWidth: number
  mode: 'fit' | 'scroll'
  rightAlign: boolean
  scrollToEnd: boolean
}

export function resolveSkillsChartLayout(dayCount: number, viewportWidth = 0): SkillsChartLayout {
  const safeDayCount = Math.max(1, Math.round(Number.isFinite(dayCount) ? dayCount : SKILLS_CHART_SHORT_DAYS))
  const fitMode = safeDayCount <= SKILLS_CHART_SHORT_DAYS
  const fixedTrackWidth = SKILLS_CHART_AXIS_PAD + safeDayCount * SKILLS_CHART_DAY_SLOT
  const safeViewportWidth = Math.max(0, Math.round(Number.isFinite(viewportWidth) ? viewportWidth : 0))
  const minFitWidth = SKILLS_CHART_AXIS_PAD + safeDayCount * SKILLS_CHART_MIN_DAY_SLOT
  const trackWidth = fitMode ? Math.max(minFitWidth, safeViewportWidth || fixedTrackWidth) : fixedTrackWidth
  const daySlot = (trackWidth - SKILLS_CHART_AXIS_PAD) / safeDayCount
  return {
    dayCount: safeDayCount,
    trackWidth,
    daySlot,
    barWidth: Math.min(SKILLS_CHART_MAX_BAR_WIDTH, Math.max(8, daySlot * 0.64)),
    mode: fitMode ? 'fit' : 'scroll',
    rightAlign: !fitMode,
    scrollToEnd: !fitMode,
  }
}

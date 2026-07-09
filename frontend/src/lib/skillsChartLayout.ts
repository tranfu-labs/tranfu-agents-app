export const SKILLS_CHART_DAY_SLOT = 28
export const SKILLS_CHART_MIN_DAY_SLOT = 18
export const SKILLS_CHART_MAX_BAR_WIDTH = 30
export const SKILLS_CHART_AXIS_PAD = 54
export const SKILLS_CHART_SHORT_DAYS = 14
export const SKILLS_CHART_MAX_AXIS_DAYS = 120

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

export type DetailTrendLayout = {
  dayCount: number
  trackWidth: number
  daySlot: number
  barWidth: number
  scrollToEnd: boolean
}

function validIsoDay(value?: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return ''
  return String(value)
}

function utcDay(value?: string) {
  const day = validIsoDay(value)
  if (!day) return null
  const [year, month, date] = day.split('-').map(Number)
  const parsed = new Date(Date.UTC(year, month - 1, date))
  return parsed.toISOString().slice(0, 10) === day ? parsed : null
}

function isoDay(date: Date) {
  return date.toISOString().slice(0, 10)
}

function fallbackDaySeries(endDay: string | undefined, count: number) {
  const end = utcDay(endDay) || new Date()
  const safeCount = Math.max(1, Math.round(Number.isFinite(count) ? count : SKILLS_CHART_SHORT_DAYS))
  const days: string[] = []
  for (let i = safeCount - 1; i >= 0; i -= 1) {
    const date = new Date(end.getTime())
    date.setUTCDate(end.getUTCDate() - i)
    days.push(isoDay(date))
  }
  return days
}

export function isoDayRange(start?: string, end?: string, maxDays = SKILLS_CHART_MAX_AXIS_DAYS) {
  const startDay = utcDay(start)
  const endDay = utcDay(end)
  const safeMaxDays = Math.max(1, Math.round(Number.isFinite(maxDays) ? maxDays : SKILLS_CHART_MAX_AXIS_DAYS))
  if (!startDay || !endDay || endDay < startDay) return []
  const out: string[] = []
  const cursor = new Date(startDay.getTime())
  while (cursor <= endDay) {
    out.push(cursor.toISOString().slice(0, 10))
    if (out.length > safeMaxDays) return []
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return out
}

export function resolveSkillsChartAxis(window: { start?: string; end?: string } | null | undefined, days: number, axisEnd?: string) {
  const windowAxis = isoDayRange(window?.start, window?.end)
  return windowAxis.length ? windowAxis : fallbackDaySeries(axisEnd, days)
}

export function resolveDetailTrendEndDay(today?: string, daily?: Array<{ day?: string }>, fallback?: string) {
  const payloadToday = validIsoDay(today)
  if (payloadToday) return payloadToday
  const maxDailyDay = (daily || [])
    .map((row) => validIsoDay(row.day))
    .filter(Boolean)
    .sort()
    .at(-1)
  return maxDailyDay || validIsoDay(fallback) || ''
}

export function resolveDetailTrendLayout(dayCount: number, viewportWidth = 0): DetailTrendLayout {
  const safeDayCount = Math.max(1, Math.round(Number.isFinite(dayCount) ? dayCount : SKILLS_CHART_SHORT_DAYS))
  const fitMode = safeDayCount <= SKILLS_CHART_SHORT_DAYS
  const safeViewportWidth = Math.max(0, Math.round(Number.isFinite(viewportWidth) ? viewportWidth : 0))
  const fixedTrackWidth = SKILLS_CHART_AXIS_PAD + safeDayCount * SKILLS_CHART_DAY_SLOT
  const minFitWidth = SKILLS_CHART_AXIS_PAD + safeDayCount * SKILLS_CHART_MIN_DAY_SLOT
  const trackWidth = fitMode ? Math.max(minFitWidth, safeViewportWidth || fixedTrackWidth) : fixedTrackWidth
  const daySlot = (trackWidth - SKILLS_CHART_AXIS_PAD) / safeDayCount
  return {
    dayCount: safeDayCount,
    trackWidth,
    daySlot,
    barWidth: Math.min(SKILLS_CHART_MAX_BAR_WIDTH, Math.max(8, daySlot * 0.64)),
    scrollToEnd: !fitMode,
  }
}

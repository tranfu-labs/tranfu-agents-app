import type { TokenUsageQuery } from './types'

function startOfDay(date: Date) {
  const next = new Date(date)
  next.setHours(0, 0, 0, 0)
  return next
}

function addDays(date: Date, days: number) {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

function startOfWeek(date: Date) {
  const day = date.getDay() || 7
  return startOfDay(addDays(date, 1 - day))
}

export function unix(date: Date) {
  return Math.floor(date.getTime() / 1000)
}

export function makeTokenUsageRange(preset: string, granularity: TokenUsageQuery['timeGranularity'] = 'day', reference = new Date()): TokenUsageQuery {
  const now = new Date(reference)
  now.setSeconds(0, 0)
  const today = startOfDay(now)
  const thisWeek = startOfWeek(now)
  let start = addDays(now, -7)
  let end = now
  if (preset === 'today') start = today
  if (preset === 'yesterday') {
    start = addDays(today, -1)
    end = new Date(today.getTime() - 1000)
  }
  if (preset === 'this_week') start = thisWeek
  if (preset === 'last_week') {
    start = addDays(thisWeek, -7)
    end = new Date(thisWeek.getTime() - 1000)
  }
  if (preset === '14d') start = addDays(now, -14)
  if (preset === '30d') start = addDays(now, -30)
  return { preset, startTimestamp: unix(start), endTimestamp: unix(end), timeGranularity: granularity }
}

export function makeTokenUsageComparisonRange(query: TokenUsageQuery): { label: string; query: TokenUsageQuery } {
  const start = new Date(query.startTimestamp * 1000)
  const span = Math.max(60, query.endTimestamp - query.startTimestamp)
  const today = startOfDay(new Date())
  const thisWeek = startOfWeek(new Date())

  if (query.preset === 'today') {
    const compareStart = addDays(today, -1)
    return {
      label: '较昨日',
      query: { ...query, preset: 'comparison', startTimestamp: unix(compareStart), endTimestamp: unix(new Date(compareStart.getTime() + span * 1000)) },
    }
  }
  if (query.preset === 'this_week') {
    const compareStart = addDays(thisWeek, -7)
    const elapsed = Math.min(Date.now() - thisWeek.getTime(), 7 * 86400 * 1000 - 1000)
    return {
      label: '较上周同期',
      query: { ...query, preset: 'comparison', startTimestamp: unix(compareStart), endTimestamp: unix(new Date(compareStart.getTime() + elapsed)) },
    }
  }
  if (query.preset === 'last_week') {
    const compareEnd = new Date(start.getTime() - 1000)
    return {
      label: '较前一周',
      query: { ...query, preset: 'comparison', startTimestamp: unix(new Date(compareEnd.getTime() - span * 1000)), endTimestamp: unix(compareEnd) },
    }
  }
  return {
    label: query.preset === 'yesterday' ? '较前日' : '较上一周期',
    query: { ...query, preset: 'comparison', startTimestamp: query.startTimestamp - span, endTimestamp: query.endTimestamp - span },
  }
}

export function initialTokenUsageQuery(reference = new Date()) {
  return makeTokenUsageRange('today', 'hour', reference)
}

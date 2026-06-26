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

export function makeTokenUsageRange(preset: string, granularity: TokenUsageQuery['timeGranularity'] = 'day'): TokenUsageQuery {
  const now = new Date()
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

export function initialTokenUsageQuery() {
  return makeTokenUsageRange('7d', 'day')
}

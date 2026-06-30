import type { Lang } from './types'

export type TimeDisplay = {
  label: string
  title: string
}

function pad2(value: number) {
  return String(value).padStart(2, '0')
}

function parseDate(value?: string) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function parseDateOnlyUtc(value?: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '')
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const time = Date.UTC(year, month - 1, day)
  const date = new Date(time)
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null
  return time
}

function utcDateOnly(date: Date) {
  return [
    date.getUTCFullYear(),
    pad2(date.getUTCMonth() + 1),
    pad2(date.getUTCDate()),
  ].join('-')
}

function localDateOnly(date: Date) {
  return [
    date.getFullYear(),
    pad2(date.getMonth() + 1),
    pad2(date.getDate()),
  ].join('-')
}

function sameLocalDay(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate()
}

function localDayIndex(date: Date) {
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000
}

function localTimeMinute(date: Date) {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

function localMonthDay(date: Date) {
  return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`
}

function browserTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || ''
  } catch {
    return ''
  }
}

export function localAbsoluteTime(date: Date) {
  return [
    date.getFullYear(),
    pad2(date.getMonth() + 1),
    pad2(date.getDate()),
  ].join('-') + ` ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
}

export function formatLocalTimestamp(value?: string, fallback = ''): TimeDisplay {
  const date = parseDate(value)
  if (!date) return { label: fallback, title: fallback }
  const label = localAbsoluteTime(date)
  const zone = browserTimeZone()
  return { label, title: zone ? `${label} ${zone}` : label }
}

function relativeLabel(seconds: number, lang: Lang) {
  if (seconds < 60) return lang === 'zh' ? '刚刚' : 'just now'
  if (seconds < 3600) {
    const minutes = Math.max(1, Math.floor(seconds / 60))
    return lang === 'zh' ? `${minutes}分钟前` : `${minutes}m ago`
  }
  const hours = Math.max(1, Math.floor(seconds / 3600))
  return lang === 'zh' ? `${hours}小时前` : `${hours}h ago`
}

function todayLabel(lang: Lang) {
  return lang === 'zh' ? '今天' : 'today'
}

function yesterdayLabel(lang: Lang) {
  return lang === 'zh' ? '昨天' : 'yesterday'
}

function weekdayLabel(day: number, lang: Lang) {
  const zh = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const en = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  return lang === 'zh' ? zh[day] : en[day]
}

function recentDateLabel(date: Date, daysAgo: number, lang: Lang, referenceYear: number) {
  if (daysAgo === 0) return todayLabel(lang)
  if (daysAgo === 1) return yesterdayLabel(lang)
  if (daysAgo > 1 && daysAgo < 7) return weekdayLabel(date.getDay(), lang)
  if (date.getFullYear() === referenceYear) return localMonthDay(date)
  return `${date.getFullYear()}-${localMonthDay(date)}`
}

function recentDateTimeLabel(date: Date, daysAgo: number, lang: Lang, now: Date) {
  return `${recentDateLabel(date, daysAgo, lang, now.getFullYear())} ${localTimeMinute(date)}`
}

function dateOnlyLabel(dayTime: number, referenceTime: number, daysAgo: number, lang: Lang) {
  const dayDate = new Date(dayTime)
  const referenceDate = new Date(referenceTime)
  if (daysAgo === 0) return todayLabel(lang)
  if (daysAgo === 1) return yesterdayLabel(lang)
  if (daysAgo > 1 && daysAgo < 7) return weekdayLabel(dayDate.getUTCDay(), lang)
  if (dayDate.getUTCFullYear() === referenceDate.getUTCFullYear()) {
    return `${pad2(dayDate.getUTCMonth() + 1)}-${pad2(dayDate.getUTCDate())}`
  }
  return utcDateOnly(dayDate)
}

function formatRecentRecordDay(day: string, lang: Lang, now: Date, referenceDay?: string): TimeDisplay {
  const dayTime = parseDateOnlyUtc(day)
  const referenceTime = parseDateOnlyUtc(referenceDay) ?? parseDateOnlyUtc(localDateOnly(now))
  if (dayTime === null || referenceTime === null) return { label: day, title: day }
  const daysAgo = Math.floor((referenceTime - dayTime) / 86400000)
  if (daysAgo < 0) return { label: day, title: day }
  return { label: dateOnlyLabel(dayTime, referenceTime, daysAgo, lang), title: day }
}

export function formatRecentRecordTime(firstSeen?: string, fallbackDay = '', lang: Lang = 'zh', now = new Date(), referenceDay?: string): TimeDisplay {
  const date = parseDate(firstSeen)
  if (!date) return formatRecentRecordDay(fallbackDay, lang, now, referenceDay)
  const absolute = formatLocalTimestamp(firstSeen, fallbackDay)
  if (date.getTime() > now.getTime()) return absolute
  if (!sameLocalDay(date, now)) {
    const daysAgo = Math.floor(localDayIndex(now) - localDayIndex(date))
    if (daysAgo < 1) return absolute
    return { label: recentDateTimeLabel(date, daysAgo, lang, now), title: absolute.title }
  }
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)
  return { label: relativeLabel(seconds, lang), title: absolute.title }
}

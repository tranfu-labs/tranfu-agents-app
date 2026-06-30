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

function sameLocalDay(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate()
}

function localDayIndex(date: Date) {
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000
}

function localTimeOnly(date: Date) {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
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

function relativeDateLabel(daysAgo: number, lang: Lang) {
  if (daysAgo === 0) return lang === 'zh' ? '今天' : 'today'
  if (daysAgo === 1) return lang === 'zh' ? '昨天' : 'yesterday'
  return lang === 'zh' ? `${daysAgo}天前` : `${daysAgo}d ago`
}

function formatRecentRecordDay(day: string, lang: Lang, now: Date, referenceDay?: string): TimeDisplay {
  const dayTime = parseDateOnlyUtc(day)
  const referenceTime = parseDateOnlyUtc(referenceDay) ?? parseDateOnlyUtc(utcDateOnly(now))
  if (dayTime === null || referenceTime === null) return { label: day, title: day }
  const daysAgo = Math.floor((referenceTime - dayTime) / 86400000)
  if (daysAgo < 0) return { label: day, title: day }
  return { label: relativeDateLabel(daysAgo, lang), title: day }
}

export function formatRecentRecordTime(firstSeen?: string, fallbackDay = '', lang: Lang = 'zh', now = new Date(), referenceDay?: string): TimeDisplay {
  const date = parseDate(firstSeen)
  if (!date) return formatRecentRecordDay(fallbackDay, lang, now, referenceDay)
  const absolute = formatLocalTimestamp(firstSeen, fallbackDay)
  if (date.getTime() > now.getTime()) return absolute
  if (!sameLocalDay(date, now)) {
    const daysAgo = Math.floor(localDayIndex(now) - localDayIndex(date))
    if (daysAgo < 1) return absolute
    return { label: `${relativeDateLabel(daysAgo, lang)} ${localTimeOnly(date)}`, title: absolute.title }
  }
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)
  return { label: relativeLabel(seconds, lang), title: absolute.title }
}

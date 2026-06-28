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

function sameLocalDay(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate()
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

export function formatRecentRecordTime(firstSeen?: string, fallbackDay = '', lang: Lang = 'zh', now = new Date()): TimeDisplay {
  const date = parseDate(firstSeen)
  if (!date) return { label: fallbackDay, title: fallbackDay }
  const absolute = formatLocalTimestamp(firstSeen, fallbackDay)
  if (date.getTime() > now.getTime()) return absolute
  if (!sameLocalDay(date, now)) return absolute
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)
  return { label: relativeLabel(seconds, lang), title: absolute.title }
}

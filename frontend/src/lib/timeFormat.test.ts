/// <reference types="node" />
import assert from 'node:assert/strict'
import test from 'node:test'
import { formatLocalTimestamp, formatRecentRecordTime } from './timeFormat.ts'

// These fixtures exercise browser-local formatting in a known locale. Keep the
// test process deterministic without changing the application's runtime zone.
process.env.TZ = 'Asia/Shanghai'

test('recent record uses browser-local today for relative labels', () => {
  const now = new Date('2026-06-27T17:00:00+00:00')
  const display = formatRecentRecordTime('2026-06-27T16:30:00+00:00', '2026-06-27', 'zh', now)

  assert.equal(display.label, '30分钟前')
  assert.equal(display.title, '2026-06-28 00:30:00 Asia/Shanghai')
})

test('recent record shows relative date and local time for browser-local yesterday', () => {
  const now = new Date('2026-06-27T17:00:00+00:00')
  const display = formatRecentRecordTime('2026-06-27T15:00:00+00:00', '2026-06-27', 'zh', now)

  assert.equal(display.label, '昨天 23:00')
  assert.equal(display.title, '2026-06-27 23:00:00 Asia/Shanghai')
})

test('recent record shows weekday and local time for first_seen rows within the last week', () => {
  const now = new Date('2026-06-30T04:00:00+00:00')
  const display = formatRecentRecordTime('2026-06-25T01:18:55+00:00', '2026-06-25', 'en', now)

  assert.equal(display.label, 'Thu 09:18')
  assert.equal(display.title, '2026-06-25 09:18:55 Asia/Shanghai')
})

test('recent record shows month-day and local time for older rows in the same year', () => {
  const now = new Date('2026-06-30T04:00:00+00:00')
  const display = formatRecentRecordTime('2026-06-02T01:18:55+00:00', '2026-06-02', 'zh', now)

  assert.equal(display.label, '06-02 09:18')
  assert.equal(display.title, '2026-06-02 09:18:55 Asia/Shanghai')
})

test('recent record shows full local date and time for rows from another year', () => {
  const now = new Date('2026-06-30T04:00:00+00:00')
  const display = formatRecentRecordTime('2025-12-30T01:18:55+00:00', '2025-12-30', 'zh', now)

  assert.equal(display.label, '2025-12-30 09:18')
  assert.equal(display.title, '2025-12-30 09:18:55 Asia/Shanghai')
})

test('recent record preserves future first_seen as absolute local time', () => {
  const now = new Date('2026-06-27T17:00:00+00:00')
  const display = formatRecentRecordTime('2026-06-28T01:00:00+00:00', '2026-06-28', 'zh', now)

  assert.equal(display.label, '2026-06-28 09:00:00')
  assert.equal(display.title, '2026-06-28 09:00:00 Asia/Shanghai')
})

test('recent record uses restrained just-now labels', () => {
  const now = new Date('2026-06-27T17:00:30+00:00')
  const display = formatRecentRecordTime('2026-06-27T17:00:05+00:00', '2026-06-28', 'en', now)

  assert.equal(display.label, 'just now')
  assert.equal(display.title, '2026-06-28 01:00:05 Asia/Shanghai')
})

test('recent record shows relative date for date-only today', () => {
  const display = formatRecentRecordTime(undefined, '2026-06-30', 'zh', new Date('2026-06-29T17:00:00+00:00'), '2026-06-30')

  assert.equal(display.label, '今天')
  assert.equal(display.title, '2026-06-30')
})

test('recent record shows relative date for date-only yesterday', () => {
  const display = formatRecentRecordTime(undefined, '2026-06-29', 'en', new Date('2026-06-29T17:00:00+00:00'), '2026-06-30')

  assert.equal(display.label, 'yesterday')
  assert.equal(display.title, '2026-06-29')
})

test('recent record shows weekday for date-only rows within the last week', () => {
  const display = formatRecentRecordTime(undefined, '2026-06-25', 'zh', new Date('2026-06-29T17:00:00+00:00'), '2026-06-30')

  assert.equal(display.label, '周四')
  assert.equal(display.title, '2026-06-25')
})

test('recent record shows month-day for older date-only rows in the same year', () => {
  const display = formatRecentRecordTime(undefined, '2026-06-02', 'en', new Date('2026-06-29T17:00:00+00:00'), '2026-06-30')

  assert.equal(display.label, '06-02')
  assert.equal(display.title, '2026-06-02')
})

test('recent record shows full date for date-only rows from another year', () => {
  const display = formatRecentRecordTime(undefined, '2025-12-30', 'zh', new Date('2026-06-29T17:00:00+00:00'), '2026-06-30')

  assert.equal(display.label, '2025-12-30')
  assert.equal(display.title, '2025-12-30')
})

test('recent record preserves future and invalid date-only fallbacks', () => {
  const future = formatRecentRecordTime(undefined, '2026-07-01', 'zh', new Date('2026-06-29T17:00:00+00:00'), '2026-06-30')
  const invalid = formatRecentRecordTime(undefined, '2026-02-31', 'zh', new Date('2026-06-29T17:00:00+00:00'), '2026-06-30')

  assert.equal(future.label, '2026-07-01')
  assert.equal(future.title, '2026-07-01')
  assert.equal(invalid.label, '2026-02-31')
  assert.equal(invalid.title, '2026-02-31')
})

test('local absolute timestamps are zero-padded to seconds', () => {
  const display = formatLocalTimestamp('2026-01-02T03:04:05+00:00')

  assert.equal(display.label, '2026-01-02 11:04:05')
  assert.equal(display.title, '2026-01-02 11:04:05 Asia/Shanghai')
})

/// <reference types="node" />
import assert from 'node:assert/strict'
import test from 'node:test'
import { formatLocalTimestamp, formatRecentRecordTime } from './timeFormat.ts'

test('recent record uses browser-local today for relative labels', () => {
  const now = new Date('2026-06-27T17:00:00+00:00')
  const display = formatRecentRecordTime('2026-06-27T16:30:00+00:00', '2026-06-27', 'zh', now)

  assert.equal(display.label, '30分钟前')
  assert.equal(display.title, '2026-06-28 00:30:00 Asia/Shanghai')
})

test('recent record shows absolute time for browser-local yesterday', () => {
  const now = new Date('2026-06-27T17:00:00+00:00')
  const display = formatRecentRecordTime('2026-06-27T15:00:00+00:00', '2026-06-27', 'zh', now)

  assert.equal(display.label, '2026-06-27 23:00:00')
  assert.equal(display.title, '2026-06-27 23:00:00 Asia/Shanghai')
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

test('recent record shows day-count relative date for older date-only rows', () => {
  const display = formatRecentRecordTime(undefined, '2026-06-25', 'zh', new Date('2026-06-29T17:00:00+00:00'), '2026-06-30')

  assert.equal(display.label, '5天前')
  assert.equal(display.title, '2026-06-25')
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

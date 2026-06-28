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

test('recent record falls back to day when first_seen is missing', () => {
  const display = formatRecentRecordTime(undefined, '2026-06-27', 'zh', new Date('2026-06-27T17:00:00+00:00'))

  assert.equal(display.label, '2026-06-27')
  assert.equal(display.title, '2026-06-27')
})

test('local absolute timestamps are zero-padded to seconds', () => {
  const display = formatLocalTimestamp('2026-01-02T03:04:05+00:00')

  assert.equal(display.label, '2026-01-02 11:04:05')
  assert.equal(display.title, '2026-01-02 11:04:05 Asia/Shanghai')
})

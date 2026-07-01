/// <reference types="node" />
import assert from 'node:assert/strict'
import test from 'node:test'
import { angleSpan, buildDonutSegments, buildSourceDonutSegments } from './skillsAttribution.ts'
import { buildRankItems, deltaRatio, formatDelta } from './skillsDashboard.ts'
import { classifySkillHealth } from './skillsThresholds.ts'
import { resolveSkillsWindow } from './skillsWindow.ts'
import type { SkillTableRow } from './types.ts'

test('skills window resolves presets and custom fallback', () => {
  const now = new Date('2026-07-01T12:00:00+08:00')
  assert.equal(resolveSkillsWindow({ w: 'today' }, now).days, 1)
  assert.equal(resolveSkillsWindow({ w: 'this_week' }, now).days, 3)
  assert.equal(resolveSkillsWindow({ w: 'last_week' }, now).days, 7)
  assert.equal(resolveSkillsWindow({ w: '14d' }, now).days, 14)
  assert.equal(resolveSkillsWindow({ w: 'custom' }, now).days, 30)
  assert.equal(resolveSkillsWindow({ w: 'custom', wstart: '1782864000', wend: '1783123200' }, now).days, 4)
  assert.equal(resolveSkillsWindow({ win: 7 }, now).key, '7d')
})

test('skill health thresholds keep boundary values in expected buckets', () => {
  assert.equal(classifySkillHealth('untracked', 0.099), 'good')
  assert.equal(classifySkillHealth('untracked', 0.1), 'warn')
  assert.equal(classifySkillHealth('untracked', 0.25), 'warn')
  assert.equal(classifySkillHealth('untracked', 0.251), 'bad')
  assert.equal(classifySkillHealth('coverage', 0.51), 'good')
  assert.equal(classifySkillHealth('coverage', 0.5), 'warn')
  assert.equal(classifySkillHealth('coverage', 0.29), 'bad')
  assert.equal(classifySkillHealth('top3', 0.3), 'good')
  assert.equal(classifySkillHealth('top3', 0.61), 'warn')
  assert.equal(classifySkillHealth('top3', 0.81), 'bad')
  assert.equal(classifySkillHealth('avgSkills', 1.51), 'good')
  assert.equal(classifySkillHealth('avgSkills', 0.8), 'warn')
  assert.equal(classifySkillHealth('avgSkills', 0.79), 'bad')
})

test('rank bars aggregate long tail after top N', () => {
  const rows: SkillTableRow[] = Array.from({ length: 10 }, (_, index) => ({
    name: `skill-${index}`,
    sessions_7d: 0,
    sessions_30d: 10 - index,
    sessions_window: 10 - index,
    previous_sessions: index,
    sessions_total: 10 - index,
    users_30d: 1,
  }))
  const ranked = buildRankItems(rows, 8)
  assert.equal(ranked.length, 9)
  assert.equal(ranked[8].isOther, true)
  assert.equal(ranked[8].name, '其他 2 个 skill')
  assert.deepEqual(ranked[8].names, ['skill-8', 'skill-9'])
  assert.equal(buildRankItems(rows.slice(0, 8), 8).some((item) => item.isOther), false)
})

test('delta formatting handles zero previous values', () => {
  assert.equal(formatDelta(deltaRatio(1, 0)), '+∞%')
  assert.equal(formatDelta(deltaRatio(0, 0)), '—')
  assert.equal(formatDelta(deltaRatio(15, 10)), '+50.0%')
  assert.equal(formatDelta(deltaRatio(5, 10)), '-50.0%')
})

test('source donut parent and child angles remain consistent and omit zero sectors', () => {
  const model = buildSourceDonutSegments({ own: 30, meta: 20, external: 10, non_catalog: 40 })
  const innerCataloged = model.inner.find((item) => item.key === 'cataloged')
  const innerUntracked = model.inner.find((item) => item.key === 'non_catalog')
  assert.ok(innerCataloged)
  assert.ok(innerUntracked)
  const outerCataloged = model.outer.filter((item) => item.parent === 'cataloged').reduce((sum, item) => sum + angleSpan(item), 0)
  const outerUntracked = model.outer.find((item) => item.key === 'non_catalog')
  assert.ok(outerUntracked)
  assert.ok(Math.abs(angleSpan(innerCataloged) - outerCataloged) < 0.5 * Math.PI / 180)
  assert.ok(Math.abs(angleSpan(innerUntracked) - angleSpan(outerUntracked)) < 0.5 * Math.PI / 180)
  assert.equal(buildDonutSegments([{ key: 'zero', value: 0 }, { key: 'one', value: 1 }]).length, 1)
})

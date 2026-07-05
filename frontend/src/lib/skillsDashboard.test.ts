/// <reference types="node" />
import assert from 'node:assert/strict'
import test from 'node:test'
import { angleSpan, buildDonutSegments, buildSourceDonutSegments } from './skillsAttribution.ts'
import { buildRankItems, deltaRatio, formatDelta } from './skillsDashboard.ts'
import { SKILLS_CHART_MAX_BAR_WIDTH, resolveDetailTrendEndDay, resolveDetailTrendLayout, resolveSkillsChartLayout } from './skillsChartLayout.ts'
import { classifySkillHealth } from './skillsThresholds.ts'
import { resolveSkillsWindow } from './skillsWindow.ts'
import { skillsWindowQuery } from './skillsWindow.ts'
import type { SkillTableRow } from './types.ts'

test('skills window resolves presets and custom fallback', () => {
  const now = new Date('2026-07-01T12:00:00+08:00')
  assert.equal(resolveSkillsWindow({ w: 'today' }, now).days, 1)
  assert.equal(resolveSkillsWindow({ w: 'this_week' }, now).days, 3)
  assert.equal(resolveSkillsWindow({ w: 'last_week' }, now).days, 7)
  assert.equal(resolveSkillsWindow({ w: '14d' }, now).days, 14)
  assert.equal(resolveSkillsWindow({ w: 'custom' }, now).key, '7d')
  assert.equal(resolveSkillsWindow({}, now).key, '7d')
  assert.equal(resolveSkillsWindow({ w: 'custom', wstart: '1782864000', wend: '1783123200' }, now).days, 4)
  assert.equal(resolveSkillsWindow({ win: 7 }, now).key, '7d')
  assert.equal(resolveSkillsWindow({ win: 30 }, now).key, '30d')
})

test('skills overview query sends only window and evidence-scope filters', () => {
  const query = skillsWindowQuery({
    w: '7d',
    rt: 'codex',
    src: 'own',
    q: 'openspec',
    topn: 20,
    hz: '1',
    cmp: '0',
    sel: 'alpha',
    scope: 'new',
  })
  const params = new URLSearchParams(query)
  assert.equal(params.get('w'), '7d')
  assert.equal(params.get('rt'), 'codex')
  assert.equal(params.get('src'), 'own')
  assert.equal(params.get('scope'), 'new')
  assert.equal(params.has('q'), false)
  assert.equal(params.has('topn'), false)
  assert.equal(params.has('hz'), false)
  assert.equal(params.has('cmp'), false)
  assert.equal(params.has('sel'), false)
})

test('skills chart layout fits short windows and scrolls longer windows to the end', () => {
  const oneDay = resolveSkillsChartLayout(1, 800)
  const sevenDays = resolveSkillsChartLayout(7, 800)
  const fourteenDays = resolveSkillsChartLayout(14, 800)
  const thirtyDays = resolveSkillsChartLayout(30, 800)
  const ninetyDays = resolveSkillsChartLayout(90, 800)
  assert.equal(oneDay.mode, 'fit')
  assert.equal(sevenDays.mode, 'fit')
  assert.equal(fourteenDays.mode, 'fit')
  assert.equal(sevenDays.trackWidth, 800)
  assert.equal(fourteenDays.trackWidth, 800)
  assert.equal(sevenDays.rightAlign, false)
  assert.equal(sevenDays.scrollToEnd, false)
  assert.equal(fourteenDays.scrollToEnd, false)
  assert.equal(thirtyDays.mode, 'scroll')
  assert.equal(ninetyDays.mode, 'scroll')
  assert.equal(thirtyDays.scrollToEnd, true)
  assert.equal(ninetyDays.scrollToEnd, true)
  assert.equal(thirtyDays.rightAlign, true)
  assert.equal(oneDay.barWidth, SKILLS_CHART_MAX_BAR_WIDTH)
  assert.ok(sevenDays.barWidth <= SKILLS_CHART_MAX_BAR_WIDTH)
  assert.ok(thirtyDays.trackWidth > sevenDays.trackWidth)
})

test('detail trend layout fits short windows and scrolls longer windows to the end', () => {
  const fourteenDays = resolveDetailTrendLayout(14, 360)
  const thirtyDays = resolveDetailTrendLayout(30, 360)
  const ninetyDays = resolveDetailTrendLayout(90, 360)
  const invalidDays = resolveDetailTrendLayout(Number.NaN, 360)
  assert.equal(fourteenDays.scrollToEnd, false)
  assert.equal(fourteenDays.trackWidth, 360)
  assert.equal(thirtyDays.scrollToEnd, true)
  assert.ok(thirtyDays.trackWidth > 360)
  assert.equal(ninetyDays.scrollToEnd, true)
  assert.ok(ninetyDays.trackWidth > thirtyDays.trackWidth)
  assert.ok(thirtyDays.barWidth >= 8)
  assert.ok(thirtyDays.barWidth <= SKILLS_CHART_MAX_BAR_WIDTH)
  assert.equal(invalidDays.dayCount, 14)
})

test('detail trend end day prefers payload today then max daily day before runtime fallback', () => {
  assert.equal(resolveDetailTrendEndDay('2026-07-03', [{ day: '2026-07-04' }], '2026-07-05'), '2026-07-03')
  assert.equal(
    resolveDetailTrendEndDay(undefined, [{ day: '2026-07-01' }, { day: '2026-07-04' }, { day: '2026-07-02' }], '2026-07-05'),
    '2026-07-04',
  )
  assert.equal(resolveDetailTrendEndDay('', [{ day: 'bad' }], '2026-07-05'), '2026-07-05')
  assert.equal(resolveDetailTrendEndDay('', [{ day: 'bad' }], 'bad'), '')
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

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { makeT } from './i18n.ts'
import { humanFilterChips, operatorShare, showTopSkillsForClue } from './skillsClues.ts'
import { compactNameList, defaultEvidenceTab, evidenceSummaryLine, mobileFilterSummary, untrackedUsageSummary, windowChangeLabel, windowDailyUsageTitle, windowDisplayLabel, windowTriggersLabel, windowUsedLabel, windowZeroUsageLabel } from './skillsPresentation.ts'
import type { SkillsEvidencePayload } from './types.ts'

test('mobileFilterSummary defaults to a single compressed line', () => {
  assert.equal(mobileFilterSummary({}, 'skill', makeT('zh')), '近 7 天 · 按 Skill · 全部 runtime/source · 筛选')
  assert.equal(mobileFilterSummary({}, 'skill', makeT('en')), 'Last 7 days · By skill · All runtime/source · Filters')
})

test('mobileFilterSummary reflects active runtime and source filters', () => {
  assert.equal(mobileFilterSummary({ w: '30d', rt: 'codex', src: 'non_catalog' }, 'operator', makeT('zh')), '近 30 天 · 按人 · codex · 非公司库 · 筛选')
  assert.equal(mobileFilterSummary({ w: '30d', rt: 'codex', src: 'non_catalog' }, 'operator', makeT('en')), 'Last 30 days · By operator · codex · non-catalog · Filters')
})

test('mobileFilterSummary reflects new skill scope', () => {
  assert.equal(mobileFilterSummary({ w: '7d', scope: 'new' }, 'skill', makeT('zh')), '近 7 天 · 按 Skill · 新发现名单 · 全部 runtime/source · 筛选')
  assert.equal(mobileFilterSummary({ w: '7d', scope: 'new' }, 'skill', makeT('en')), 'Last 7 days · By skill · New list · All runtime/source · Filters')
})

test('windowDisplayLabel localizes window query keys', () => {
  assert.equal(windowDisplayLabel('today', makeT('zh')), '今天')
  assert.equal(windowDisplayLabel('this_week', makeT('en')), 'This week')
  assert.equal(windowDisplayLabel('custom', makeT('zh')), '自定义')
  assert.equal(windowDisplayLabel('7d', makeT('zh')), '近 7 天')
  assert.equal(windowDisplayLabel('7d', makeT('en')), 'Last 7 days')
  assert.equal(windowDisplayLabel('14d', makeT('en')), 'Last 14 days')
})

test('window labels derive human-readable period copy without raw W', () => {
  assert.equal(windowChangeLabel('last_week', makeT('zh')), '上周变化')
  assert.equal(windowChangeLabel('7d', makeT('zh')), '近 7 天变化')
  assert.equal(windowChangeLabel('last_week', makeT('en')), 'Last week changes')
  assert.equal(windowChangeLabel('7d', makeT('en')), 'Last 7 days changes')
  assert.equal(windowUsedLabel('30d', makeT('zh')), '近 30 天使用')
  assert.equal(windowZeroUsageLabel('7d', makeT('en')), '0 in Last 7 days')
  assert.equal(windowTriggersLabel('14d', makeT('zh')), '近 14 天触发')
  assert.ok(!windowChangeLabel('7d', makeT('zh')).includes('W'))
})

test('daily usage titles derive from the selected window and view', () => {
  assert.equal(windowDailyUsageTitle('7d', 'skill', makeT('zh')), '近 7 天使用')
  assert.equal(windowDailyUsageTitle('30d', 'operator', makeT('zh')), '近 30 天使用 · 按人')
  assert.equal(windowDailyUsageTitle('7d', 'skill', makeT('en')), 'Used in Last 7 days')
  assert.equal(windowDailyUsageTitle('30d', 'operator', makeT('en')), 'Used in Last 30 days · by operator')
})

test('compactNameList truncates long skill names and avoids long slash chains', () => {
  const text = compactNameList(['openspec-driven-development', 'tranfu-website-design', 'strategy-first-development'])
  assert.equal(text, 'openspec-driven-d… +2')
  assert.ok(!text.includes(' / '))
})

test('untracked summary uses aggregate counts rather than top list length', () => {
  const data = {
    governance: {
      untracked_usage: {
        used_sessions: 12,
        skill_count: 4,
        top: [{ name: 'ghost-a', sessions: 8 }],
      },
    },
  }
  assert.equal(untrackedUsageSummary(data as any, makeT('zh')), '4 个 skill · 12 条记录')
})

test('Top3 conclusion copy uses canonical casing', () => {
  assert.equal(makeT('zh')('top3Concentrated'), '使用集中在 Top3 skill')
  assert.equal(makeT('en')('top3Concentrated'), 'Usage concentrated in Top3 skills')
})

test('evidenceSummaryLine renders total untracked as context slice', () => {
  const data: SkillsEvidencePayload = {
    kind: 'total',
    today: '2026-07-02',
    window: { key: '7d' },
    summary: { records: 284, skills: 64, operators: 8, sessions: 188, untracked_records: 92 },
  }
  assert.equal(evidenceSummaryLine(data), '284 records · 64 skills · 8 operators · 188 sessions，其中 92 条来自未收录 skill')
})

test('evidenceSummaryLine and default tab distinguish list evidence', () => {
  const data: SkillsEvidencePayload = {
    kind: 'idle',
    today: '2026-07-02',
    window: { key: '7d' },
    summary: { items: 19, installed: 33 },
  }
  assert.equal(evidenceSummaryLine(data), '19 个装了但 7d 没用 · 33 installs')
  assert.equal(defaultEvidenceTab('idle'), '名单')
  assert.equal(defaultEvidenceTab('total'), '原始记录')
})

test('humanFilterChips hides raw query field names and enum values', () => {
  const data: SkillsEvidencePayload = {
    kind: 'untracked',
    today: '2026-07-03',
    window: { key: '7d', start: '2026-06-27', end: '2026-07-03' },
    applied_filters: {
      w: '7d',
      window_start: '2026-06-27',
      window_end: '2026-07-03',
      src: 'non_catalog',
      skill: 'coolify-deploy',
    },
  }
  const text = humanFilterChips(data, makeT('zh')).join(' · ')
  assert.equal(text, '近 7 天 · 2026-06-27 ~ 2026-07-03 · 来源：未收录 · skill：coolify-deploy')
  assert.equal(text.includes('window_start'), false)
  assert.equal(text.includes('non_catalog'), false)
})

test('clue helpers render operator share and hide top skills when scoped to a skill', () => {
  const data: SkillsEvidencePayload = {
    kind: 'untracked',
    today: '2026-07-03',
    applied_filters: { skill: 'coolify-deploy' },
  }
  assert.equal(operatorShare(5, 7), '5/7 · 71%')
  assert.equal(showTopSkillsForClue('untracked', '?w=7d', null), true)
  assert.equal(showTopSkillsForClue('untracked', '?w=7d&skill=coolify-deploy', null), false)
  assert.equal(showTopSkillsForClue('untracked', '?w=7d', data), false)
  assert.equal(showTopSkillsForClue('idle', '?w=7d', null), false)
})

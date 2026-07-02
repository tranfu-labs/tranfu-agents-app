import { test } from 'node:test'
import assert from 'node:assert/strict'
import { makeT } from './i18n.ts'
import { compactNameList, defaultEvidenceTab, evidenceSummaryLine, mobileFilterSummary, windowDisplayLabel } from './skillsPresentation.ts'
import type { SkillsEvidencePayload } from './types.ts'

test('mobileFilterSummary defaults to a single compressed line', () => {
  assert.equal(mobileFilterSummary({}, 'skill', makeT('zh')), '7 天 · 按 Skill · 全部 runtime/source · 筛选')
  assert.equal(mobileFilterSummary({}, 'skill', makeT('en')), '7d · By skill · All runtime/source · Filters')
})

test('mobileFilterSummary reflects active runtime and source filters', () => {
  assert.equal(mobileFilterSummary({ w: '30d', rt: 'codex', src: 'non_catalog' }, 'operator', makeT('zh')), '30 天 · 按人 · codex · 非公司库 · 筛选')
  assert.equal(mobileFilterSummary({ w: '30d', rt: 'codex', src: 'non_catalog' }, 'operator', makeT('en')), '30d · By operator · codex · non-catalog · Filters')
})

test('windowDisplayLabel localizes window query keys', () => {
  assert.equal(windowDisplayLabel('today', makeT('zh')), '今天')
  assert.equal(windowDisplayLabel('this_week', makeT('en')), 'This week')
  assert.equal(windowDisplayLabel('custom', makeT('zh')), '自定义')
  assert.equal(windowDisplayLabel('14d', makeT('en')), '14d')
})

test('compactNameList truncates long skill names and avoids long slash chains', () => {
  const text = compactNameList(['openspec-driven-development', 'tranfu-website-design', 'strategy-first-development'])
  assert.equal(text, 'openspec-driven-d… +2')
  assert.ok(!text.includes(' / '))
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

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { compactNameList, defaultEvidenceTab, evidenceSummaryLine, mobileFilterSummary } from './skillsPresentation.ts'
import type { SkillsEvidencePayload } from './types.ts'

test('mobileFilterSummary defaults to a single compressed line', () => {
  assert.equal(mobileFilterSummary({}, 'skill'), '7d · 按 Skill · 全部 runtime/source · 筛选')
})

test('mobileFilterSummary reflects active runtime and source filters', () => {
  assert.equal(mobileFilterSummary({ w: '30d', rt: 'codex', src: 'non_catalog' }, 'operator'), '30d · 按人 · codex · 非公司库 · 筛选')
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

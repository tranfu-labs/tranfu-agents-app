import assert from 'node:assert/strict'
import test from 'node:test'
import { buildOperatorSkillAnalysis } from './operatorDetailAnalysis.ts'
import type { OperatorDetail } from './types.ts'

function detail(days: number, count: number): OperatorDetail {
  return {
    operator: 'alice',
    today: '2026-07-23',
    window: { key: days === 1 ? 'today' : `${days}d`, days, start: '2026-07-23', end: '2026-07-23' },
    analysis: {
      metrics: { sessions_window: count },
      skills: Array.from({ length: count }, (_, index) => ({
        name: `skill-${String(index).padStart(2, '0')}`,
        source: index % 2 ? 'meta' : 'own',
        sessions_window: count - index,
        previous_sessions: index,
        session_count: count - index,
      })),
    },
  }
}

test('single-day operator analysis uses top 5 plus a conserved tail', () => {
  const model = buildOperatorSkillAnalysis(detail(1, 7))
  assert.equal(model.mode, 'donut')
  assert.equal(model.limit, 5)
  assert.equal(model.top.length, 5)
  assert.equal(model.other?.count, 2)
  assert.equal(model.top.every((row) => Boolean(row.source)), true)
  const represented = model.top.reduce((sum, row) => sum + Number(row.sessions_window || 0), 0) + Number(model.other?.sessions || 0)
  assert.equal(represented, model.total)
  const share = model.top.reduce((sum, row) => sum + Number(row.share || 0), 0) + Number(model.other?.share || 0)
  assert.ok(Math.abs(share - 1) < 1e-10)
})

test('preset multi-day operator analysis uses top 8 and leaves the full list intact', () => {
  for (const days of [7, 14, 30, 90]) {
    const model = buildOperatorSkillAnalysis(detail(days, 14))
    assert.equal(model.mode, 'trend')
    assert.equal(model.limit, 8)
    assert.equal(model.top.length, 8)
    assert.equal(model.other?.count, 6)
    assert.equal(model.all.length, 14)
  }
})

test('custom and empty ranges select their data-driven modes', () => {
  const custom = detail(1, 2)
  custom.window = { key: 'custom', days: 1 }
  assert.equal(buildOperatorSkillAnalysis(custom).mode, 'donut')
  custom.window = { key: 'custom', days: 2 }
  assert.equal(buildOperatorSkillAnalysis(custom).mode, 'trend')
  const empty = detail(2, 0)
  assert.equal(buildOperatorSkillAnalysis(empty).mode, 'empty')
})

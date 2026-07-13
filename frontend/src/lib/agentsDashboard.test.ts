import assert from 'node:assert/strict'
import test from 'node:test'
import {
  agentKpiActionPatch,
  agentFiltersQuery,
  agentSectionOrder,
  agentWindowComparison,
  agentSignals,
  buildAgentKpiCards,
  buildAgentOverview,
  filterAgents,
  formatAgentDelta,
  moveAgentChartIndex,
  parseAgentFilters,
  resolveAgentChartMode,
  resolveAgentWindow,
  type AgentFilters,
} from './agentsDashboard.ts'
import type { AgentSession } from './types.ts'

function agent(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    operator: 'alice',
    runtime: 'codex',
    agent: 'code',
    status: 'done',
    ts: '2026-07-13T10:00:00Z',
    active_days: Array(90).fill(0),
    ...overrides,
  }
}

test('agent filters normalize unknown URL values and preserve meaningful params', () => {
  const filters = parseAgentFilters('?q=code&status=attention&signal=quality&rt=codex&op=alice&sort=success')
  assert.deepEqual(filters, { q: 'code', status: 'attention', signal: 'quality', rank: 'runtime', w: 'today', wstart: '', wend: '', rt: 'codex', op: 'alice', sort: 'success' })
  assert.equal(agentFiltersQuery(filters), '?q=code&status=attention&signal=quality&rt=codex&op=alice&sort=success')
  assert.equal(agentFiltersQuery({ ...filters, w: '14d' }), '?q=code&status=attention&signal=quality&w=14d&rt=codex&op=alice&sort=success')
  assert.equal(agentFiltersQuery({ ...filters, rank: 'operator' }), '?q=code&status=attention&signal=quality&rank=operator&rt=codex&op=alice&sort=success')
  assert.equal(agentFiltersQuery({ ...filters, w: 'custom', wstart: '1783900800', wend: '' }), '?q=code&status=attention&signal=quality&w=custom&wstart=1783900800&rt=codex&op=alice&sort=success')
  assert.equal(agentFiltersQuery({ ...filters, w: 'custom', wstart: '1783900800', wend: '1783987200' }), '?q=code&status=attention&signal=quality&w=custom&wstart=1783900800&wend=1783987200&rt=codex&op=alice&sort=success')
  assert.deepEqual(parseAgentFilters('?status=nope&sort=nope'), { q: '', status: 'all', signal: '', rank: 'runtime', w: 'today', wstart: '', wend: '', rt: '', op: '', sort: 'recent' })
  assert.equal(parseAgentFilters('?rank=operator').rank, 'operator')
})

test('agent issue signals respect quality and quiet boundaries', () => {
  const quiet = agent({ shim_version: 'v1', active_days: Array(90).fill(0) })
  const active = agent({ shim_version: 'v1', active_days: [...Array(89).fill(0), 1] })
  const low = agent({ shim_version: 'v1', quality: { runs: 3, success: 2 } })
  const boundary = agent({ shim_version: 'v1', quality: { runs: 5, success: 4 } })
  assert.deepEqual(agentSignals(quiet), ['quiet'])
  assert.deepEqual(agentSignals(active), [])
  assert.ok(agentSignals(low).includes('quality'))
  assert.equal(agentSignals(boundary).includes('quality'), false)
  assert.ok(agentSignals(agent({ shim_version: 'v1', status: 'blocked' })).includes('error'))
  assert.ok(agentSignals(agent(), 'new-shim').includes('shim'))
  assert.ok(agentSignals(agent({ shim_version: undefined }), 'v1').includes('shim'))
})

test('agent filtering searches task and signal-specific attention', () => {
  const a = agent({ agent: 'builder', task: 'release dashboard', quality: { runs: 4, success: 2 } })
  const b = agent({ operator: 'bob', runtime: 'claude-code', agent: 'reviewer', active_days: [...Array(89).fill(0), 4] })
  const base: AgentFilters = { q: '', status: 'all', signal: '', rank: 'runtime', w: 'today', wstart: '', wend: '', rt: '', op: '', sort: 'recent' }
  assert.deepEqual(filterAgents([a, b], { ...base, q: 'dashboard' }), [a])
  assert.deepEqual(filterAgents([a, b], { ...base, status: 'attention', signal: 'quality' }), [a])
  assert.deepEqual(filterAgents([a, b], { ...base, rt: 'claude-code' }), [b])
})

test('agent windows use the service day and compare adjacent equal ranges', () => {
  const current = Array(90).fill(0)
  current[80] = 10
  const previous = Array(90).fill(0)
  previous[70] = 5
  const first = agent({ active_days: current })
  const second = agent({ operator: 'bob', active_days: previous })
  const overview = buildAgentOverview([first, second], undefined, '2026-07-13')
  const window = resolveAgentWindow({ w: '14d', wstart: '', wend: '' }, overview.today)
  const comparison = agentWindowComparison([first, second], overview.days, window)
  assert.equal(window.days.length, 14)
  assert.equal(window.previousDays.length, 14)
  assert.deepEqual(comparison.current, { activeAgents: 1, activeSeconds: 10 })
  assert.deepEqual(comparison.previous, { activeAgents: 1, activeSeconds: 5 })
  assert.equal(comparison.currentAvailable, true)
  assert.equal(comparison.previousAvailable, true)
  assert.equal(formatAgentDelta(10, 5), '+100%')
  assert.equal(formatAgentDelta(0, 0), '—')
  assert.equal(formatAgentDelta(3, 0), '+∞%')
  assert.equal(formatAgentDelta(3, 0, false), '—')
})

test('agent custom windows keep service-day boundaries and window aggregation', () => {
  const overview = buildAgentOverview([agent({ active_days: [...Array(89).fill(0), 4] })], undefined, '2026-07-13')
  const window = resolveAgentWindow({ w: 'custom', wstart: '1783872000', wend: '1784044800' }, overview.today)
  assert.deepEqual(window.days, ['2026-07-13', '2026-07-14', '2026-07-15'])
  assert.equal(window.previousDays.length, 3)
})

test('agent overview fallback produces a 90-day series and de-duplicated group counts', () => {
  const first = agent({ active_days: [...Array(89).fill(0), 12], today_active: 12, week_active: 12, quality: { runs: 2, success: 1 } })
  const second = agent({ ts: '2026-07-13T11:00:00Z', active_days: Array(90).fill(0), today_active: 0, quality: { runs: 1, success: 1 } })
  const overview = buildAgentOverview([first, second], undefined, '2026-07-13')
  assert.equal(overview.days.length, 90)
  assert.equal(overview.daily.length, 90)
  assert.equal(overview.days.at(-1), '2026-07-13')
  assert.equal(overview.summary.agents, 2)
  assert.equal(overview.summary.runs, 3)
  assert.equal(overview.summary.success, 2)
  assert.equal(overview.runtime.length, 1)
  assert.equal(overview.operator.length, 1)
  assert.equal(overview.daily.at(-1)?.active_agents, 1)
  const shortSeries = buildAgentOverview([agent({ active_days: undefined, active_series: [0, 0, 5] })], undefined, '2026-07-13')
  assert.equal(shortSeries.daily.at(-1)?.active_agents, 1)
})

test('agent KPI model preserves eight facts and maps actions without erasing unrelated filters', () => {
  const summary = buildAgentOverview([agent({ status: 'running', today_active: 120, week_active: 600, quality: { runs: 4, success: 3, error: 1, blocked: 2 } })], undefined, '2026-07-13').summary
  const cards = buildAgentKpiCards({
    comparison: {
      current: { activeAgents: 3, activeSeconds: 540 },
      previous: { activeAgents: 2, activeSeconds: 360 },
      currentAvailable: true,
      previousAvailable: true,
    },
    summary,
    totalAgents: 5,
    attention: 1,
    t: (key) => key,
  })
  assert.deepEqual(cards.map((card) => card.key), ['active-agents', 'active-time', 'total', 'operators', 'live', 'week', 'quality', 'attention'])
  assert.equal(cards[0].value, '3')
  assert.equal(cards[0].delta, '+50%')
  assert.equal(cards[2].detail, '1/5 agentVisibleTotal')
  assert.equal(cards[4].value, '1')
  assert.equal(cards[6].value, '75%')
  assert.equal(cards[7].detail, '1 agentErrors · 2 agentBlocked')
  assert.deepEqual(agentKpiActionPatch('operator-rank'), { rank: 'operator' })
  assert.deepEqual(agentKpiActionPatch('live'), { status: 'live', signal: '' })
  assert.deepEqual(agentKpiActionPatch('week'), { sort: 'week' })
  assert.deepEqual(agentKpiActionPatch('quality'), { sort: 'success' })
  assert.deepEqual(agentKpiActionPatch('attention'), { status: 'attention', signal: '' })
  assert.equal(agentKpiActionPatch('trend'), null)
})

test('agent chart mode uses the selected metric and roving focus stays in bounds', () => {
  const today = [{ day: '2026-07-13', active_agents: 2, active_seconds: 0 }]
  const series = [...today, { day: '2026-07-14', active_agents: 1, active_seconds: 60 }]
  assert.equal(resolveAgentChartMode(today, 'agents'), 'today')
  assert.equal(resolveAgentChartMode(today, 'seconds'), 'empty')
  assert.equal(resolveAgentChartMode(series, 'agents'), 'series')
  assert.equal(moveAgentChartIndex(1, 'ArrowLeft', 3), 0)
  assert.equal(moveAgentChartIndex(1, 'ArrowRight', 3), 2)
  assert.equal(moveAgentChartIndex(0, 'ArrowLeft', 3), 0)
  assert.equal(moveAgentChartIndex(2, 'ArrowRight', 3), 2)
  assert.equal(moveAgentChartIndex(1, 'Escape', 3), 1)
})

test('agent mobile layout changes real section order instead of relying on CSS order', () => {
  assert.deepEqual(agentSectionOrder(false), ['kpis', 'signals', 'analysis', 'directory'])
  assert.deepEqual(agentSectionOrder(true), ['signals', 'directory', 'kpis', 'analysis'])
})

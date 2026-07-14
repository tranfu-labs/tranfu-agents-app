import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import {
  AGENT_UNASSIGNED,
  agentsApiQuery,
  agentKpiActionPatch,
  agentFiltersQuery,
  agentSectionOrder,
  agentWindowComparison,
  agentSignals,
  buildAgentKpiCards,
  buildAgentDailyBreakdown,
  buildAgentDisplayLabels,
  buildAgentDonutSegments,
  buildAgentDirectoryRows,
  buildAgentOverview,
  buildAgentTrendModel,
  buildAgentWindowOverview,
  filterAgents,
  formatAgentDelta,
  hasCompleteAgentWindow,
  moveAgentChartIndex,
  parseAgentFilters,
  resolveAgentChartMode,
  resolveAgentChartAnchorIndex,
  resolveAgentChartScrollLeft,
  resolveAgentWindow,
  resolveAgentsRoutePhase,
  type AgentFilters,
} from './agentsDashboard.ts'
import type { AgentSession } from './types.ts'
import { keyOf } from './utils.ts'

function readSource(relativePath: string) {
  for (const candidate of [path.join(process.cwd(), relativePath), path.join(process.cwd(), 'frontend', relativePath)]) {
    try {
      return readFileSync(candidate, 'utf8')
    } catch {
      // npm --prefix and direct node runs use different cwd shapes.
    }
  }
  throw new Error(`missing source file ${relativePath}`)
}

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
  const filters = parseAgentFilters('?q=code&status=attention&signal=quality&rank=runtime&rt=codex&op=alice&sort=success')
  assert.deepEqual(filters, { q: 'code', status: 'attention', signal: 'quality', w: 'today', wstart: '', wend: '', sort: 'success' })
  assert.equal(agentFiltersQuery(filters), '?q=code&status=attention&signal=quality&sort=success')
  assert.equal(agentFiltersQuery({ ...filters, w: '14d' }), '?q=code&status=attention&signal=quality&w=14d&sort=success')
  assert.equal(agentFiltersQuery({ ...filters, w: 'custom', wstart: '1783900800', wend: '' }), '?q=code&status=attention&signal=quality&w=custom&wstart=1783900800&sort=success')
  assert.equal(agentFiltersQuery({ ...filters, w: 'custom', wstart: '1783900800', wend: '1783987200' }), '?q=code&status=attention&signal=quality&w=custom&wstart=1783900800&wend=1783987200&sort=success')
  assert.equal(agentsApiQuery({ ...filters, q: '', status: 'all', signal: '', sort: 'window_time' }), 'w=today')
  assert.equal(agentsApiQuery({ ...filters, w: 'custom', wstart: '1783900800', wend: '' }), null)
  assert.equal(agentsApiQuery({ ...filters, w: 'custom', wstart: '1783900800', wend: '1783987200' }), 'q=code&status=attention&signal=quality&w=custom&wstart=1783900800&wend=1783987200&sort=success')
  assert.deepEqual(parseAgentFilters('?status=nope&sort=nope'), { q: '', status: 'all', signal: '', w: 'today', wstart: '', wend: '', sort: 'window_time' })
  assert.equal(agentFiltersQuery(parseAgentFilters('?rank=runtime&rt=codex&op=alice')), '')
  assert.equal(parseAgentFilters('?sort=today').sort, 'window_time')
  assert.equal(parseAgentFilters('?sort=week').sort, 'window_days')
})

test('agent route lifecycle never presents stale data as a completed failed query', () => {
  assert.equal(resolveAgentsRoutePhase(null, false, false, ''), 'pending-window')
  assert.equal(resolveAgentsRoutePhase('w=7d', false, true, ''), 'skeleton')
  assert.equal(resolveAgentsRoutePhase('w=7d', true, true, ''), 'data')
  assert.equal(resolveAgentsRoutePhase('w=7d', true, false, '500'), 'error')
  assert.equal(resolveAgentsRoutePhase('w=7d', false, false, '500'), 'error')
})

test('agent pending custom window keeps real controls alongside data skeletons', () => {
  const source = readSource('src/views/Agents.tsx')
  const pending = source.slice(source.indexOf('export function AgentsPendingWindow'), source.indexOf('export function Agents({'))
  assert.ok(pending.includes('<AgentsToolbar'))
  assert.ok(pending.includes('<AgentsSkeletonSections'))
  assert.ok(pending.includes('windowPeriodLabel(filters.w, t)'))
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
  const base: AgentFilters = { q: '', status: 'all', signal: '', w: 'today', wstart: '', wend: '', sort: 'window_time' }
  assert.deepEqual(filterAgents([a, b], { ...base, q: 'dashboard' }), [a])
  assert.deepEqual(filterAgents([a, b], { ...base, status: 'attention', signal: 'quality' }), [a])
  assert.deepEqual(filterAgents([a, b], { ...base, q: 'claude-code' }), [])
  assert.deepEqual(filterAgents([a, b], { ...base, q: 'bob' }), [])
})

test('agent labels keep same-name identities separate without exposing operator or runtime', () => {
  const first = agent({ operator: 'alice', runtime: 'codex', agent: 'builder' })
  const second = agent({ operator: 'bob', runtime: 'claude-code', agent: 'builder' })
  const labels = buildAgentDisplayLabels([second, first])
  assert.deepEqual(Object.values(labels).sort(), ['builder · 1', 'builder · 2'])
  assert.equal(Object.values(labels).some((label) => label.includes('alice') || label.includes('codex')), false)
  const activeDays = [...Array(89).fill(0), 60]
  const overview = buildAgentOverview([first, second], undefined, '2026-07-13')
  const filteredRows = buildAgentDailyBreakdown([{ ...second, active_days: activeDays }], overview.days, ['2026-07-13'], labels)
  assert.equal(filteredRows[0].segment, labels[keyOf(second)])
  assert.equal(filteredRows[0].segment, 'builder · 2')
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
  assert.deepEqual(cards.map((card) => card.key), ['active-time', 'average-time', 'active-agents', 'total', 'live', 'week', 'quality', 'attention'])
  assert.equal(cards[0].value, '9m')
  assert.equal(cards[0].delta, '+50%')
  assert.equal(cards[1].value, '3m')
  assert.equal(cards[1].delta, '+0%')
  assert.equal(cards[2].value, '3')
  assert.equal(cards[3].detail, '1/5 agentVisibleTotal')
  assert.equal(cards[4].value, '1')
  assert.equal(cards[6].value, '75%')
  assert.equal(cards[7].detail, '1 agentErrors · 2 agentBlocked')
  assert.deepEqual(agentKpiActionPatch('live'), { status: 'live', signal: '' })
  assert.deepEqual(agentKpiActionPatch('week'), { sort: 'window_time' })
  assert.deepEqual(agentKpiActionPatch('quality'), { sort: 'success' })
  assert.deepEqual(agentKpiActionPatch('attention'), { status: 'attention', signal: '' })
  assert.equal(agentKpiActionPatch('trend'), null)
})

test('agent chart mode is fixed to active time and roving focus stays in bounds', () => {
  const today = [{ day: '2026-07-13', active_agents: 2, active_seconds: 0 }]
  const series = [...today, { day: '2026-07-14', active_agents: 1, active_seconds: 60 }]
  assert.equal(resolveAgentChartMode(today), 'empty')
  assert.equal(resolveAgentChartMode([{ ...today[0], active_seconds: 20 }]), 'today')
  assert.equal(resolveAgentChartMode(series), 'series')
  assert.equal(moveAgentChartIndex(1, 'ArrowLeft', 3), 0)
  assert.equal(moveAgentChartIndex(1, 'ArrowRight', 3), 2)
  assert.equal(moveAgentChartIndex(0, 'ArrowLeft', 3), 0)
  assert.equal(moveAgentChartIndex(2, 'ArrowRight', 3), 2)
  assert.equal(moveAgentChartIndex(1, 'Escape', 3), 1)
})

test('agent chart anchor and long-window scroll follow the latest non-zero active time', () => {
  const daily = Array.from({ length: 90 }, (_, index) => ({
    day: `day-${index}`,
    active_agents: index === 40 ? 2 : 0,
    active_seconds: index === 62 ? 120 : 0,
  }))
  assert.equal(resolveAgentChartAnchorIndex(daily), 62)
  assert.equal(resolveAgentChartAnchorIndex(daily.map((row) => ({ ...row, active_agents: 0, active_seconds: 0 }))), 89)

  const dataScroll = resolveAgentChartScrollLeft(90, 40, 2574, 715, 2606)
  const latestScroll = resolveAgentChartScrollLeft(90, 89, 2574, 715, 2606)
  assert.ok(dataScroll > 0 && dataScroll < latestScroll)
  assert.equal(latestScroll, 1891)
  assert.equal(resolveAgentChartScrollLeft(7, 6, 700, 700, 700), 0)
})

test('agent windows require complete day coverage before showing comparison or analysis', () => {
  const activeDays = Array(90).fill(0)
  activeDays[89] = 60
  const item = agent({ active_days: activeDays })
  const overview = buildAgentOverview([item], undefined, '2026-07-13')
  const partialWindow = {
    key: 'custom' as const,
    days: ['2026-07-13', '2026-07-14'],
    previousDays: ['2026-07-11', '2026-07-12'],
  }
  assert.equal(hasCompleteAgentWindow(overview.days, partialWindow.days), false)
  assert.deepEqual(agentWindowComparison([item], overview.days, partialWindow), {
    current: { activeAgents: 0, activeSeconds: 0 },
    previous: { activeAgents: 0, activeSeconds: 0 },
    currentAvailable: false,
    previousAvailable: true,
  })
  const partialOverview = buildAgentWindowOverview([item], overview, partialWindow)
  assert.deepEqual(partialOverview.daily.map((row) => row.active_seconds), [0, 0])
  assert.deepEqual(partialOverview.runtime, [])
  assert.deepEqual(partialOverview.operator, [])

  const completeWindow = {
    key: 'today' as const,
    days: ['2026-07-13'],
    previousDays: ['2026-07-12'],
  }
  assert.equal(hasCompleteAgentWindow(overview.days, completeWindow.days), true)
  assert.equal(agentWindowComparison([item], overview.days, completeWindow).current.activeSeconds, 60)
})

test('agent mobile layout changes real section order instead of relying on CSS order', () => {
  assert.deepEqual(agentSectionOrder(false), ['kpis', 'signals', 'analysis', 'directory'])
  assert.deepEqual(agentSectionOrder(true), ['signals', 'directory', 'kpis', 'analysis'])
})

test('agent directory rows calculate and sort by the selected window', () => {
  const firstDays = Array(90).fill(0)
  firstDays[87] = 30
  firstDays[89] = 90
  const secondDays = Array(90).fill(0)
  secondDays[88] = 180
  const first = agent({ agent: 'first', active_days: firstDays, last_seen: '2026-07-13T09:00:00Z' })
  const second = agent({ agent: 'second', operator: 'bob', active_days: secondDays, last_seen: '2026-07-13T08:00:00Z' })
  const overview = buildAgentOverview([first, second], undefined, '2026-07-13')
  const days = ['2026-07-11', '2026-07-12', '2026-07-13']

  const byTime = buildAgentDirectoryRows([first, second], overview.days, days, 'window_time')
  assert.deepEqual(byTime.map((row) => [row.agent.agent, row.active_seconds, row.active_days]), [
    ['second', 180, 1],
    ['first', 120, 2],
  ])
  const byDays = buildAgentDirectoryRows([first, second], overview.days, days, 'window_days')
  assert.deepEqual(byDays.map((row) => row.agent.agent), ['first', 'second'])
  const today = buildAgentDirectoryRows([first, second], overview.days, ['2026-07-13'], 'window_time')
  assert.deepEqual(today.map((row) => [row.agent.agent, row.active_seconds]), [['first', 90], ['second', 0]])
})

test('agent daily breakdown uses agent identities without losing daily totals', () => {
  const codexDays = Array(90).fill(0)
  codexDays[89] = 120
  const claudeDays = Array(90).fill(0)
  claudeDays[89] = 60
  const items = [
    agent({ runtime: 'codex', operator: 'alice', active_days: codexDays }),
    agent({ runtime: 'claude-code', operator: '', agent: 'reviewer', active_days: claudeDays }),
  ]
  const overview = buildAgentOverview(items, undefined, '2026-07-13')
  const rows = buildAgentDailyBreakdown(items, overview.days, ['2026-07-13'])
  assert.deepEqual(rows, [
    { day: '2026-07-13', segment: 'code', active_agents: 1, active_seconds: 120 },
    { day: '2026-07-13', segment: 'reviewer', active_agents: 1, active_seconds: 60 },
  ])
  const window = resolveAgentWindow({ w: 'today', wstart: '', wend: '' }, overview.today)
  const windowOverview = buildAgentWindowOverview(items, overview, window)
  assert.equal(windowOverview.operator.find((row) => row.operator === AGENT_UNASSIGNED)?.today_active, 60)
  assert.equal(windowOverview.operator.some((row) => row.operator === 'claude-code'), false)
  const model = buildAgentTrendModel(rows, ['2026-07-13'])
  assert.equal(model.days[0].active_seconds, 180)
  assert.equal(model.days[0].active_agents, 2)
})

test('agent trend model keeps top eight segments and folds the rest into other', () => {
  const rows = Array.from({ length: 10 }, (_, index) => ({
    day: '2026-07-13',
    segment: `agent-${index}`,
    active_agents: 1,
    active_seconds: 100 - index,
  }))
  const model = buildAgentTrendModel(rows, ['2026-07-13'], 8)
  assert.equal(model.legend.length, 9)
  assert.equal(model.legend.at(-1), '__other')
  assert.equal(model.days[0].segments.find((item) => item.name === '__other')?.active_agents, 2)
  assert.equal(model.days[0].segments.reduce((sum, item) => sum + item.active_seconds, 0), rows.reduce((sum, item) => sum + item.active_seconds, 0))
})

test('agent donut segments preserve legend order and calculate active-time shares', () => {
  const day = {
    day: '2026-07-14',
    active_agents: 4,
    active_seconds: 180,
    segments: [
      { name: 'alice', active_agents: 3, active_seconds: 60 },
      { name: 'bob', active_agents: 1, active_seconds: 120 },
      { name: 'idle', active_agents: 0, active_seconds: 0 },
    ],
  }
  const slices = buildAgentDonutSegments(day)
  assert.deepEqual(slices.map((slice) => [slice.name, slice.value]), [['alice', 60], ['bob', 120]])
  assert.equal(slices[0].share, 1 / 3)
  assert.equal(slices[1].offset, 1 / 3)
  assert.equal(slices.reduce((sum, slice) => sum + slice.share, 0), 1)
  assert.equal(slices.reduce((sum, slice) => sum + slice.value, 0), day.active_seconds)
})

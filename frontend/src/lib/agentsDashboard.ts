import type { AgentOverview, AgentOverviewGroup, AgentSession, StatePayload } from './types.ts'
import { daySeries, isoDay, LIVE, shimState } from './utils.ts'

export const AGENT_LOW_SUCCESS_RATE = 0.8
export const AGENT_MIN_QUALITY_RUNS = 3
export const AGENT_QUIET_DAYS = 14

export type AgentSignal = 'error' | 'shim' | 'quiet' | 'quality'
export type AgentStatusFilter = 'all' | 'live' | 'attention' | 'idle' | 'done'
export type AgentSort = 'recent' | 'today' | 'week' | 'success' | 'errors' | 'name'
export type AgentWindowKey = 'today' | 'this_week' | 'last_week' | '7d' | '14d' | '30d' | '90d' | 'custom'

export type AgentFilters = {
  q: string
  status: AgentStatusFilter
  signal: AgentSignal | ''
  w: AgentWindowKey
  wstart: string
  wend: string
  rt: string
  op: string
  sort: AgentSort
}

export type AgentWindow = {
  key: AgentWindowKey
  days: string[]
  previousDays: string[]
}

export type AgentWindowStats = {
  activeAgents: number
  activeSeconds: number
}

export type AgentWindowComparison = {
  current: AgentWindowStats
  previous: AgentWindowStats
  currentAvailable: boolean
  previousAvailable: boolean
}

const STATUSES = new Set<AgentStatusFilter>(['all', 'live', 'attention', 'idle', 'done'])
const SORTS = new Set<AgentSort>(['recent', 'today', 'week', 'success', 'errors', 'name'])
const SIGNALS = new Set<AgentSignal>(['error', 'shim', 'quiet', 'quality'])
const WINDOWS = new Set<AgentWindowKey>(['today', 'this_week', 'last_week', '7d', '14d', '30d', '90d', 'custom'])

export function parseAgentFilters(search: string): AgentFilters {
  const params = new URLSearchParams(search)
  const status = params.get('status') || 'all'
  const signal = params.get('signal') || ''
  const window = params.get('w') || 'today'
  const sort = params.get('sort') || 'recent'
  return {
    q: params.get('q') || '',
    status: STATUSES.has(status as AgentStatusFilter) ? status as AgentStatusFilter : 'all',
    signal: SIGNALS.has(signal as AgentSignal) ? signal as AgentSignal : '',
    w: WINDOWS.has(window as AgentWindowKey) ? window as AgentWindowKey : 'today',
    wstart: params.get('wstart') || '',
    wend: params.get('wend') || '',
    rt: params.get('rt') || '',
    op: params.get('op') || '',
    sort: SORTS.has(sort as AgentSort) ? sort as AgentSort : 'recent',
  }
}

export function agentFiltersQuery(filters: AgentFilters) {
  const params = new URLSearchParams()
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.status !== 'all') params.set('status', filters.status)
  if (filters.signal) params.set('signal', filters.signal)
  if (filters.w !== 'today') params.set('w', filters.w)
  if (filters.w === 'custom' && filters.wstart && filters.wend) {
    params.set('wstart', filters.wstart)
    params.set('wend', filters.wend)
  }
  if (filters.rt) params.set('rt', filters.rt)
  if (filters.op) params.set('op', filters.op)
  if (filters.sort !== 'recent') params.set('sort', filters.sort)
  const query = params.toString()
  return query ? `?${query}` : ''
}

function shiftDay(day: string, offset: number) {
  const date = new Date(`${day}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return day
  date.setUTCDate(date.getUTCDate() + offset)
  return date.toISOString().slice(0, 10)
}

function daysBetween(start: string, end: string) {
  const first = new Date(`${start}T00:00:00Z`)
  const last = new Date(`${end}T00:00:00Z`)
  if (Number.isNaN(first.getTime()) || Number.isNaN(last.getTime()) || last < first) return []
  const count = Math.min(90, Math.floor((last.getTime() - first.getTime()) / 86400000) + 1)
  return Array.from({ length: count }, (_, index) => shiftDay(start, index))
}

function parseUnixDay(value: string) {
  const timestamp = Number(value)
  if (!Number.isFinite(timestamp) || timestamp <= 0) return ''
  const date = new Date(timestamp * 1000)
  return Number.isNaN(date.getTime()) ? '' : date.toISOString().slice(0, 10)
}

export function resolveAgentWindow(filters: Pick<AgentFilters, 'w' | 'wstart' | 'wend'>, today: string): AgentWindow {
  const key = WINDOWS.has(filters.w) ? filters.w : 'today'
  if (key === 'custom') {
    const start = parseUnixDay(filters.wstart)
    const end = parseUnixDay(filters.wend)
    const days = start && end ? daysBetween(start, end) : []
    if (days.length) {
      return { key, days, previousDays: daysBetween(shiftDay(days[0], -days.length), shiftDay(days[0], -1)) }
    }
    return { key: 'today', days: [today], previousDays: [shiftDay(today, -1)] }
  }
  if (key === 'today') return { key, days: [today], previousDays: [shiftDay(today, -1)] }
  if (key === 'this_week' || key === 'last_week') {
    const current = new Date(`${today}T00:00:00Z`)
    const day = current.getUTCDay() || 7
    const thisWeekStart = shiftDay(today, -day + 1)
    const end = key === 'this_week' ? today : shiftDay(thisWeekStart, -1)
    const count = key === 'this_week' ? day : 7
    const days = daysBetween(shiftDay(end, -count + 1), end)
    const previousEnd = shiftDay(end, -days.length)
    return { key, days, previousDays: daysBetween(shiftDay(previousEnd, -days.length + 1), previousEnd) }
  }
  const count = Math.min(90, Math.max(1, Number(key.slice(0, -1)) || 1))
  const days = daysBetween(shiftDay(today, -count + 1), today)
  const previousEnd = shiftDay(days[0], -1)
  return { key, days, previousDays: daysBetween(shiftDay(previousEnd, -count + 1), previousEnd) }
}

function agentSeriesByDay(agent: AgentSession, overviewDays: string[]) {
  const series = agent.active_days?.length ? agent.active_days : agent.active_series || []
  const offset = overviewDays.length - series.length
  const values = new Map<string, number>()
  series.forEach((value, index) => {
    const day = overviewDays[index + offset]
    if (day) values.set(day, Number(value || 0))
  })
  return values
}

function statsForDays(agents: AgentSession[], overviewDays: string[], days: string[]): AgentWindowStats {
  const selected = new Set(days)
  let activeSeconds = 0
  let activeAgents = 0
  agents.forEach((agent) => {
    const series = agentSeriesByDay(agent, overviewDays)
    let agentSeconds = 0
    selected.forEach((day) => { agentSeconds += Number(series.get(day) || 0) })
    activeSeconds += agentSeconds
    if (agentSeconds > 0) activeAgents += 1
  })
  return { activeAgents, activeSeconds }
}

export function agentWindowComparison(agents: AgentSession[], overviewDays: string[], window: AgentWindow): AgentWindowComparison {
  return {
    current: statsForDays(agents, overviewDays, window.days),
    previous: statsForDays(agents, overviewDays, window.previousDays),
    currentAvailable: window.days.some((day) => overviewDays.includes(day)),
    previousAvailable: window.previousDays.some((day) => overviewDays.includes(day)),
  }
}

export function formatAgentDelta(current: number, previous: number, previousAvailable = true) {
  if (!previousAvailable) return '—'
  if (!current && !previous) return '—'
  if (!previous) return current > 0 ? '+∞%' : '—'
  const delta = ((current - previous) / Math.max(1, previous)) * 100
  return `${delta >= 0 ? '+' : ''}${Math.round(delta)}%`
}

export function agentSuccessRate(agent: AgentSession) {
  const runs = Number(agent.quality?.runs || 0)
  return runs ? Number(agent.quality?.success || 0) / runs : null
}

export function agentSignals(agent: AgentSession, latestShim?: string): AgentSignal[] {
  const signals: AgentSignal[] = []
  const quality = agent.quality || {}
  if (['error', 'blocked'].includes(agent.status) || Number(quality.error || 0) > 0 || Number(quality.blocked || 0) > 0) {
    signals.push('error')
  }
  if (shimState(agent, latestShim) !== 'current') signals.push('shim')
  const activeDays = (agent.active_days || []).slice(-AGENT_QUIET_DAYS)
  if (!LIVE.includes(agent.status) && activeDays.length >= AGENT_QUIET_DAYS && activeDays.every((value) => !Number(value))) {
    signals.push('quiet')
  }
  const runs = Number(quality.runs || 0)
  const rate = agentSuccessRate(agent)
  if (runs >= AGENT_MIN_QUALITY_RUNS && rate !== null && rate < AGENT_LOW_SUCCESS_RATE) signals.push('quality')
  return signals
}

export function hasAgentSignal(agent: AgentSession, signal: AgentSignal, latestShim?: string) {
  return agentSignals(agent, latestShim).includes(signal)
}

function compareRecent(a: AgentSession, b: AgentSession) {
  return String(b.last_seen || b.ts || '').localeCompare(String(a.last_seen || a.ts || ''))
}

function compareRate(a: AgentSession, b: AgentSession) {
  const av = agentSuccessRate(a)
  const bv = agentSuccessRate(b)
  if (av === null && bv === null) return 0
  if (av === null) return 1
  if (bv === null) return -1
  return bv - av
}

export function sortAgents(agents: AgentSession[], sort: AgentSort) {
  return agents.slice().sort((a, b) => {
    let result = 0
    if (sort === 'today') result = Number(b.today_active || 0) - Number(a.today_active || 0)
    if (sort === 'week') result = Number(b.week_active || 0) - Number(a.week_active || 0)
    if (sort === 'success') result = compareRate(a, b)
    if (sort === 'errors') result = (Number(b.quality?.error || 0) + Number(b.quality?.blocked || 0)) - (Number(a.quality?.error || 0) + Number(a.quality?.blocked || 0))
    if (sort === 'name') result = `${a.agent || a.runtime} ${a.operator}`.localeCompare(`${b.agent || b.runtime} ${b.operator}`)
    if (!result) result = compareRecent(a, b)
    return result
  })
}

export function filterAgents(agents: AgentSession[], filters: AgentFilters, latestShim?: string) {
  const query = filters.q.trim().toLowerCase()
  const filtered = agents.filter((agent) => {
    const searchable = [agent.agent, agent.operator, agent.runtime, agent.task, agent.current_step, ...(agent.models || [])].filter(Boolean).join(' ').toLowerCase()
    if (query && !searchable.includes(query)) return false
    if (filters.rt && agent.runtime !== filters.rt) return false
    if (filters.op && agent.operator !== filters.op) return false
    if (filters.status === 'live' && !LIVE.includes(agent.status)) return false
    if (filters.status === 'attention' && !agentSignals(agent, latestShim).length) return false
    if (filters.signal && !agentSignals(agent, latestShim).includes(filters.signal)) return false
    if (filters.status === 'idle' && agent.status !== 'idle') return false
    if (filters.status === 'done' && agent.status !== 'done') return false
    return true
  })
  return sortAgents(filtered, filters.sort)
}

export function attentionCount(agents: AgentSession[], latestShim?: string) {
  return agents.filter((agent) => agentSignals(agent, latestShim).length > 0).length
}

function groupStats(agents: AgentSession[], field: 'runtime' | 'operator'): AgentOverviewGroup[] {
  const groups = new Map<string, AgentOverviewGroup>()
  agents.forEach((agent) => {
    const name = String(agent[field] || agent.runtime || 'unknown')
    const group = groups.get(name) || {
      [field]: name,
      agents: 0,
      live: 0,
      today_active: 0,
      week_active: 0,
      runs: 0,
      success: 0,
      errors: 0,
      blocked: 0,
      success_rate: null,
    }
    group.agents += 1
    if (LIVE.includes(agent.status)) group.live += 1
    group.today_active += Number(agent.today_active || 0)
    group.week_active += Number(agent.week_active || 0)
    group.runs += Number(agent.quality?.runs || 0)
    group.success += Number(agent.quality?.success || 0)
    group.errors += Number(agent.quality?.error || 0)
    group.blocked += Number(agent.quality?.blocked || 0)
    group.success_rate = group.runs ? group.success / group.runs : null
    groups.set(name, group)
  })
  return [...groups.values()].sort((a, b) => Number(b.agents) - Number(a.agents) || Number(b.live) - Number(a.live) || Number(b.today_active) - Number(a.today_active) || String(a[field] || '').localeCompare(String(b[field] || '')))
}

function groupWindowStats(agents: AgentSession[], field: 'runtime' | 'operator', overviewDays: string[], window: AgentWindow): AgentOverviewGroup[] {
  const groups = new Map<string, AgentOverviewGroup>()
  agents.forEach((agent) => {
    const stats = statsForDays([agent], overviewDays, window.days)
    if (!stats.activeSeconds) return
    const name = String(agent[field] || agent.runtime || 'unknown')
    const group = groups.get(name) || {
      [field]: name,
      agents: 0,
      live: 0,
      today_active: 0,
      week_active: 0,
      runs: 0,
      success: 0,
      errors: 0,
      blocked: 0,
      success_rate: null,
    }
    group.agents += 1
    if (LIVE.includes(agent.status)) group.live += 1
    group.today_active += stats.activeSeconds
    group.week_active += statsForDays([agent], overviewDays, window.previousDays).activeSeconds
    const quality = agent.quality || {}
    group.runs += Number(quality.runs || 0)
    group.success += Number(quality.success || 0)
    group.errors += Number(quality.error || 0)
    group.blocked += Number(quality.blocked || 0)
    group.success_rate = group.runs ? group.success / group.runs : null
    groups.set(name, group)
  })
  return [...groups.values()].sort((a, b) => Number(b.agents) - Number(a.agents) || Number(b.today_active) - Number(a.today_active) || String(a[field] || '').localeCompare(String(b[field] || '')))
}

function windowDaily(agents: AgentSession[], overviewDays: string[], days: string[]) {
  return days.map((day) => {
    let activeSeconds = 0
    let activeAgents = 0
    agents.forEach((agent) => {
      const value = Number(agentSeriesByDay(agent, overviewDays).get(day) || 0)
      activeSeconds += value
      if (value > 0) activeAgents += 1
    })
    return { day, active_seconds: activeSeconds, active_agents: activeAgents }
  })
}

export function buildAgentWindowOverview(agents: AgentSession[], baseOverview: AgentOverview, window: AgentWindow): AgentOverview {
  return {
    ...baseOverview,
    days: window.days,
    daily: windowDaily(agents, baseOverview.days, window.days),
    runtime: groupWindowStats(agents, 'runtime', baseOverview.days, window),
    operator: groupWindowStats(agents, 'operator', baseOverview.days, window),
  }
}

export function buildAgentOverview(agents: AgentSession[], latestShim?: string, today = isoDay(new Date())): AgentOverview {
  const days = daySeries(today, 90)
  const activeSeconds = days.map(() => 0)
  const activeAgents = days.map(() => 0)
  let runs = 0
  let success = 0
  let errors = 0
  let blocked = 0
  let todayActive = 0
  let weekActive = 0
  let outdatedShim = 0
  let unknownShim = 0
  agents.forEach((agent) => {
    const quality = agent.quality || {}
    runs += Number(quality.runs || 0)
    success += Number(quality.success || 0)
    errors += Number(quality.error || 0)
    blocked += Number(quality.blocked || 0)
    todayActive += Number(agent.today_active || 0)
    weekActive += Number(agent.week_active || 0)
    const state = shimState(agent, latestShim)
    if (state === 'outdated') outdatedShim += 1
    if (state === 'unknown') unknownShim += 1
    const series = (agent.active_days?.length ? agent.active_days : agent.active_series || []).slice(-days.length)
    const offset = days.length - series.length
    series.forEach((value, index) => {
      const target = index + offset
      if (target < 0 || target >= days.length) return
      const seconds = Number(value || 0)
      activeSeconds[target] += seconds
      if (seconds > 0) activeAgents[target] += 1
    })
  })
  return {
    today,
    days,
    summary: {
      agents: agents.length,
      live: agents.filter((agent) => LIVE.includes(agent.status)).length,
      operators: new Set(agents.map((agent) => agent.operator).filter(Boolean)).size,
      today_active: todayActive,
      week_active: weekActive,
      runs,
      success,
      errors,
      blocked,
      success_rate: runs ? success / runs : null,
      outdated_shim: outdatedShim,
      unknown_shim: unknownShim,
    },
    daily: days.map((day, index) => ({ day, active_seconds: activeSeconds[index], active_agents: activeAgents[index] })),
    runtime: groupStats(agents, 'runtime'),
    operator: groupStats(agents, 'operator'),
  }
}

export function agentOverviewOf(data: StatePayload, latestShim?: string) {
  return data.agent_overview || buildAgentOverview(data.sessions, latestShim)
}

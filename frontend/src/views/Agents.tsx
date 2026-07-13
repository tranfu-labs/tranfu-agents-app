import { useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AgentActivityChart } from '../components/agents/AgentActivityChart'
import { AgentRankPanel } from '../components/agents/AgentRankPanel'
import { Empty, QBar, ShimPill, SparkMini } from '../components/Common'
import {
  agentFiltersQuery,
  agentWindowComparison,
  agentOverviewOf,
  agentSignals,
  agentSuccessRate,
  attentionCount,
  buildAgentOverview,
  buildAgentWindowOverview,
  formatAgentDelta,
  filterAgents,
  parseAgentFilters,
  resolveAgentWindow,
  type AgentFilters,
  type AgentSignal,
} from '../lib/agentsDashboard'
import { ago, dur, encodePathParam, keyOf, LIVE, RT } from '../lib/utils'
import { statusName } from '../lib/i18n'
import { windowDisplayLabel, windowPeriodLabel } from '../lib/skillsPresentation'
import type { AgentSession, Lang, StatePayload } from '../lib/types'

const WINDOW_OPTIONS = ['today', 'this_week', 'last_week', '7d', '14d', '30d', '90d', 'custom'] as const

const SIGNALS: Array<{ key: AgentSignal; tone: string; label: string; hint: string }> = [
  { key: 'error', tone: 'bad', label: 'agentSignalError', hint: 'agentSignalErrorHint' },
  { key: 'shim', tone: 'warn', label: 'agentSignalShim', hint: 'agentSignalShimHint' },
  { key: 'quiet', tone: 'quiet', label: 'agentSignalQuiet', hint: 'agentSignalQuietHint' },
  { key: 'quality', tone: 'bad', label: 'agentSignalQuality', hint: 'agentSignalQualityHint' },
]

function statusColor(status: string) {
  return LIVE.includes(status) ? 'var(--run)' : ['error', 'blocked'].includes(status) ? 'var(--err)' : 'var(--done)'
}

function percent(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`
}

function skillsCount(agent: AgentSession) {
  return (agent.skills?.local || []).length + (agent.skills?.cross || []).length
}

function AgentCard({ agent, latestShim, lang, t }: { agent: AgentSession; latestShim?: string; lang: Lang; t: (key: string) => string }) {
  const signals = agentSignals(agent, latestShim)
  const rate = agentSuccessRate(agent)
  const quality = agent.quality || {}
  return (
    <Link className="agent-card" to={`/agent/${encodePathParam(keyOf(agent))}`}>
      <div className="agent-card-head">
        <span className="avatar agent-avatar" style={{ ['--c' as string]: `hsl(${(agent.operator || agent.agent || '').length * 47 % 360} 30% 42%)`, borderColor: statusColor(agent.status) }}>
          {(agent.operator || agent.agent || '?').slice(0, 1).toUpperCase()}
        </span>
        <span className="agent-card-identity">
          <b title={agent.agent || agent.runtime}>{agent.agent || agent.runtime}</b>
          <span>{agent.operator} · {RT[agent.runtime] || agent.runtime}</span>
        </span>
        <span className="agent-status"><i className="dot" style={{ background: statusColor(agent.status) }} />{statusName(lang, agent.status)}</span>
      </div>
      <div className="agent-card-task">
        <b>{agent.task || t('agentNoTask')}</b>
        <span>{agent.current_step ? `▸ ${agent.current_step}` : t('agentNoStep')}</span>
      </div>
      <div className="agent-card-stats">
        <span><small>{t('agentToday')}</small><b>{dur(agent.today_active)}</b></span>
        <span><small>{t('agentWeek')}</small><b>{dur(agent.week_active)}</b></span>
        <span><small>{t('agentSkillsCount')}</small><b>{skillsCount(agent)}</b></span>
        <span><small>{t('agentMcpCount')}</small><b>{agent.mcp?.length || 0}</b></span>
      </div>
      <div className="agent-card-foot">
        <SparkMini series={agent.active_series} />
        <span className="agent-quality">
          <small>{t('agentQuality')}</small>
          {rate === null ? <b>—</b> : <QBar value={Math.round(rate * 100)} />}
        </span>
        <span className="agent-shim"><ShimPill agent={agent} latest={latestShim} t={t} /></span>
      </div>
      <div className="agent-card-meta">
        <span>{t('agentLastSeen')} {ago(agent.last_seen || agent.ts)}</span>
        {signals.length ? <span className="agent-signal-count">{signals.length} {t('agentSignals')}</span> : null}
        <span>{t('agentRuns')} {quality.runs || 0}</span>
      </div>
    </Link>
  )
}

function unixToInput(value: string) {
  const ts = Number(value)
  if (!Number.isFinite(ts) || ts <= 0) return ''
  const date = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function inputToUnix(value: string) {
  const ts = new Date(value).getTime()
  return Number.isFinite(ts) ? String(Math.floor(ts / 1000)) : ''
}

function deltaTone(value: string) {
  if (value === '—') return 'snapshot'
  return value.startsWith('-') ? 'down' : 'up'
}

function Kpi({ label, value, hint, tone = '' }: { label: string; value: string | number; hint?: string; tone?: string }) {
  return (
    <div className={`agent-kpi ${tone}`}>
      <span>{label}</span>
      <b>{value}</b>
      {hint ? <small>{hint}</small> : null}
    </div>
  )
}

function AgentWindowBar({ comparison, summary, windowLabel, t }: { comparison: ReturnType<typeof agentWindowComparison>; summary: { live: number; success_rate: number | null }; windowLabel: string; t: (key: string) => string }) {
  const activeAgentsDelta = formatAgentDelta(comparison.current.activeAgents, comparison.previous.activeAgents, comparison.currentAvailable && comparison.previousAvailable)
  const activeSecondsDelta = formatAgentDelta(comparison.current.activeSeconds, comparison.previous.activeSeconds, comparison.currentAvailable && comparison.previousAvailable)
  const activeAgents = comparison.currentAvailable ? String(comparison.current.activeAgents) : '—'
  const activeSeconds = comparison.currentAvailable ? dur(comparison.current.activeSeconds) : '—'
  const values = [
    { label: t('agentWindowActiveAgents'), value: activeAgents, detail: `${t('agentWindowPrevious')} ${comparison.previousAvailable ? comparison.previous.activeAgents : '—'}`, delta: activeAgentsDelta, snapshot: false },
    { label: t('agentWindowActiveTime'), value: activeSeconds, detail: `${t('agentWindowPrevious')} ${comparison.previousAvailable ? dur(comparison.previous.activeSeconds) : '—'}`, delta: activeSecondsDelta, snapshot: false },
    { label: t('agentWindowLiveSnapshot'), value: String(summary.live), detail: t('agentWindowSnapshot'), delta: t('snapshot'), snapshot: true },
    { label: t('agentWindowQualitySnapshot'), value: percent(summary.success_rate), detail: t('agentWindowSnapshot'), delta: t('snapshot'), snapshot: true },
  ]
  return (
    <section className="frame skills-kpi-frame agents-window-frame">
      <h2><span><span className="sl">//</span>{t('agentWindowChange')}</span><span className="cnt">{windowLabel}</span></h2>
      <div className="skills-kpi agents-window-kpi">
        {values.map((item) => (
          <div className="stat skills-kpi-card" key={item.label}>
            <div className="skills-kpi-top"><div className="v">{item.value}</div></div>
            <div className="l">{item.label}</div>
            <span className="evidence-names">{item.detail}</span>
            <span className={`delta ${item.snapshot ? 'snapshot' : deltaTone(item.delta)}`}>{item.delta}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

export function Agents({ data, lang, t }: { data: StatePayload; lang: Lang; t: (key: string) => string }) {
  const location = useLocation()
  const navigate = useNavigate()
  const filters = useMemo(() => parseAgentFilters(location.search), [location.search])
  const [filtersOpen, setFiltersOpen] = useState(false)
  const latestShim = data.shim?.version
  const allOverview = agentOverviewOf(data, latestShim)
  const visibleAgents = useMemo(() => filterAgents(data.sessions, filters, latestShim), [data.sessions, filters, latestShim])
  const hasFilters = Boolean(filters.q || filters.status !== 'all' || filters.signal || filters.w !== 'today' || filters.wstart || filters.wend || filters.rt || filters.op || filters.sort !== 'recent')
  const overview = hasFilters ? buildAgentOverview(visibleAgents, latestShim, allOverview.today) : allOverview
  const window = useMemo(() => resolveAgentWindow(filters, allOverview.today), [filters, allOverview.today])
  const windowOverview = useMemo(() => buildAgentWindowOverview(visibleAgents, overview, window), [visibleAgents, overview, window])
  const comparison = useMemo(() => agentWindowComparison(visibleAgents, overview.days, window), [visibleAgents, overview.days, window])
  const windowLabel = windowPeriodLabel(window.key, t)
  const rankView = filters.rank
  const summary = overview.summary
  const qualityHint = summary.runs ? `${summary.success}/${summary.runs}` : t('agentNoRuns')
  const updateFilters = (patch: Partial<AgentFilters>) => {
    const next = { ...filters, ...patch }
    navigate(`/agents${agentFiltersQuery(next)}`, { replace: true })
  }
  const clearFilters = () => navigate('/agents', { replace: true })
  const signalCount = (signal: AgentSignal) => visibleAgents.filter((agent) => agentSignals(agent, latestShim).includes(signal)).length

  return (
    <div className="agents-page">
      <section className="frame agents-toolbar-frame">
        <h2>
          <span><span className="sl">//</span>{t('agentsDashboardTitle')}</span>
          <span className="cnt">{visibleAgents.length} / {data.sessions.length} · {summary.live} {t('agentLiveShort')}</span>
        </h2>
        <button type="button" className="agents-mobile-filter-summary" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((value) => !value)}>
          <span>{filters.q || `${windowLabel} · ${visibleAgents.length} · ${summary.live} ${t('agentLiveShort')} · ${filters.rt ? (RT[filters.rt] || filters.rt) : t('all')}`}</span><b>{filtersOpen ? '⌃' : '⌄'}</b>
        </button>
        <div className={`toolbar agents-toolbar ${filtersOpen ? 'mobile-open' : ''}`}>
          <div className="seg agents-view-seg" role="group" aria-label={t('agentRank')}>
            <button type="button" className={rankView === 'runtime' ? 'on' : ''} aria-pressed={rankView === 'runtime'} onClick={() => updateFilters({ rank: 'runtime' })}>{t('agentRankRuntime')}</button>
            <button type="button" className={rankView === 'operator' ? 'on' : ''} aria-pressed={rankView === 'operator'} onClick={() => updateFilters({ rank: 'operator' })}>{t('agentRankOperator')}</button>
          </div>
          <label className="field agents-search-field"><span>{t('agentSearch')}</span><input value={filters.q} onChange={(event) => updateFilters({ q: event.target.value })} placeholder={t('agentSearchHint')} /></label>
          <label className="field"><span>{t('agentStatusFilter')}</span><select value={filters.status} onChange={(event) => updateFilters({ status: event.target.value as AgentFilters['status'], signal: '' })}>
            <option value="all">{t('all')}</option><option value="live">{t('agentStatusLive')}</option><option value="attention">{t('agentStatusAttention')}</option><option value="idle">{t('agentStatusIdle')}</option><option value="done">{t('agentStatusDone')}</option>
          </select></label>
          <label className="field"><span>{t('windowFilter')}</span><select value={filters.w} onChange={(event) => updateFilters({ w: event.target.value as AgentFilters['w'], wstart: '', wend: '' })}>
            {WINDOW_OPTIONS.map((key) => <option value={key} key={key}>{windowDisplayLabel(key, t)}</option>)}
          </select></label>
          {filters.w === 'custom' ? (
            <>
              <label className="field"><span>{t('customStart')}</span><input type="datetime-local" value={unixToInput(filters.wstart)} onChange={(event) => updateFilters({ w: 'custom', wstart: inputToUnix(event.target.value) })} /></label>
              <label className="field"><span>{t('customEnd')}</span><input type="datetime-local" value={unixToInput(filters.wend)} onChange={(event) => updateFilters({ w: 'custom', wend: inputToUnix(event.target.value) })} /></label>
            </>
          ) : null}
          <label className="field"><span>{t('agentRuntimeFilter')}</span><select value={filters.rt} onChange={(event) => updateFilters({ rt: event.target.value })}>
            <option value="">{t('all')}</option>
            {[...new Set(data.sessions.map((agent) => agent.runtime).filter(Boolean))].sort().map((runtime) => <option value={runtime} key={runtime}>{RT[runtime] || runtime}</option>)}
          </select></label>
          <label className="field"><span>{t('agentOperatorFilter')}</span><select value={filters.op} onChange={(event) => updateFilters({ op: event.target.value })}>
            <option value="">{t('all')}</option>
            {[...new Set(data.sessions.map((agent) => agent.operator).filter(Boolean))].sort().map((operator) => <option value={operator} key={operator}>{operator}</option>)}
          </select></label>
          <label className="field"><span>{t('agentSort')}</span><select value={filters.sort} onChange={(event) => updateFilters({ sort: event.target.value as AgentFilters['sort'] })}>
            <option value="recent">{t('agentSortRecent')}</option><option value="today">{t('agentSortToday')}</option><option value="week">{t('agentSortWeek')}</option><option value="success">{t('agentSortSuccess')}</option><option value="errors">{t('agentSortErrors')}</option><option value="name">{t('agentSortName')}</option>
          </select></label>
          {hasFilters ? <button className="agent-clear-filters" type="button" onClick={clearFilters}>{t('agentFiltersClear')}</button> : null}
        </div>
      </section>

      <AgentWindowBar comparison={comparison} summary={summary} windowLabel={windowLabel} t={t} />

      <section className="frame agents-kpi-frame">
        <div className="agent-kpis">
          <Kpi label={t('agentTotal')} value={summary.agents} hint={`${summary.operators} ${t('agentOperators')}`} />
          <Kpi label={t('agentLive')} value={summary.live} hint={t('agentLiveHint')} tone="live" />
          <Kpi label={t('agentTodayActive')} value={dur(summary.today_active)} hint={`${t('agentWeekActive')} ${dur(summary.week_active)}`} />
          <Kpi label={t('agentQuality')} value={percent(summary.success_rate)} hint={`${t('agentRuns')} ${qualityHint}`} tone={summary.errors || summary.blocked ? 'bad' : ''} />
          <Kpi label={t('agentAttention')} value={attentionCount(visibleAgents, latestShim)} hint={`${summary.errors} ${t('agentErrors')} · ${summary.blocked} ${t('agentBlocked')}`} tone={attentionCount(visibleAgents, latestShim) ? 'warn' : ''} />
        </div>
      </section>

      <section className="frame agents-signals-frame">
        <div className="skills-health agents-health">
          <b>{t('agentSignalsTitle')}</b>
          {SIGNALS.map((signal) => {
            const count = signalCount(signal.key)
            const selected = filters.signal === signal.key
            return (
              <button type="button" className={`signal ${signal.tone} ${selected ? 'selected' : ''}`} key={signal.key} onClick={() => updateFilters({ status: count && !selected ? 'attention' : 'all', signal: selected ? '' : signal.key })}>
                <i />
                <span>{t(signal.label)}</span>
                <strong>{count}</strong>
              </button>
            )
          })}
        </div>
      </section>

      <div className="agents-analysis">
        <AgentRankPanel overview={windowOverview} view={rankView} onFilter={(key, value) => updateFilters({ [key]: value, signal: '' })} windowLabel={windowLabel} t={t} />
        <AgentActivityChart overview={windowOverview} currentDay={window.days.at(-1) === allOverview.today ? allOverview.today : undefined} windowLabel={windowLabel} t={t} />
      </div>

      <section className="frame agents-list-frame">
        <h2><span><span className="sl">//</span>{t('agentDirectory')}</span><span className="cnt">{visibleAgents.length} {t('agentCards')}</span></h2>
        {visibleAgents.length ? <div className="agent-card-grid">{visibleAgents.map((agent) => <AgentCard key={keyOf(agent)} agent={agent} latestShim={latestShim} lang={lang} t={t} />)}</div> : <Empty title={t('agentNoAgents')} hint={t('agentNoAgentsHint')} />}
      </section>
    </div>
  )
}

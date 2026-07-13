import { useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AgentActivityChart } from '../components/agents/AgentActivityChart'
import { AgentRankPanel } from '../components/agents/AgentRankPanel'
import { Empty, QBar, ShimPill, SparkMini } from '../components/Common'
import {
  agentFiltersQuery,
  agentOverviewOf,
  agentSignals,
  agentSuccessRate,
  attentionCount,
  buildAgentOverview,
  filterAgents,
  parseAgentFilters,
  type AgentFilters,
  type AgentSignal,
} from '../lib/agentsDashboard'
import { ago, dur, encodePathParam, keyOf, LIVE, RT } from '../lib/utils'
import { statusName } from '../lib/i18n'
import type { AgentSession, Lang, StatePayload } from '../lib/types'

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

function Kpi({ label, value, hint, tone = '' }: { label: string; value: string | number; hint?: string; tone?: string }) {
  return (
    <div className={`agent-kpi ${tone}`}>
      <span>{label}</span>
      <b>{value}</b>
      {hint ? <small>{hint}</small> : null}
    </div>
  )
}

export function Agents({ data, lang, t }: { data: StatePayload; lang: Lang; t: (key: string) => string }) {
  const location = useLocation()
  const navigate = useNavigate()
  const filters = useMemo(() => parseAgentFilters(location.search), [location.search])
  const [rankView, setRankView] = useState<'runtime' | 'operator'>('runtime')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const latestShim = data.shim?.version
  const allOverview = agentOverviewOf(data, latestShim)
  const visibleAgents = useMemo(() => filterAgents(data.sessions, filters, latestShim), [data.sessions, filters, latestShim])
  const hasFilters = Boolean(filters.q || filters.status !== 'all' || filters.signal || filters.rt || filters.op || filters.sort !== 'recent')
  const overview = hasFilters ? buildAgentOverview(visibleAgents, latestShim, allOverview.today) : allOverview
  const updateFilters = (patch: Partial<AgentFilters>) => {
    const next = { ...filters, ...patch }
    navigate(`/agents${agentFiltersQuery(next)}`, { replace: true })
  }
  const clearFilters = () => navigate('/agents', { replace: true })
  const signalCount = (signal: AgentSignal) => visibleAgents.filter((agent) => agentSignals(agent, latestShim).includes(signal)).length
  const summary = overview.summary
  const qualityHint = summary.runs ? `${summary.success}/${summary.runs}` : t('agentNoRuns')

  return (
    <div className="agents-page">
      <section className="frame agents-toolbar-frame">
        <h2>
          <span><span className="sl">//</span>{t('agentsDashboardTitle')}</span>
          <span className="cnt">{visibleAgents.length} / {data.sessions.length} · {summary.live} {t('agentLiveShort')}</span>
        </h2>
        <button type="button" className="agents-mobile-filter-summary" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((value) => !value)}>
          <span>{filters.q || `${visibleAgents.length} · ${summary.live} ${t('agentLiveShort')} · ${filters.rt ? (RT[filters.rt] || filters.rt) : t('all')}`}</span><b>{filtersOpen ? '⌃' : '⌄'}</b>
        </button>
        <div className={`toolbar agents-toolbar ${filtersOpen ? 'mobile-open' : ''}`}>
          <label className="field agents-search-field"><span>{t('agentSearch')}</span><input value={filters.q} onChange={(event) => updateFilters({ q: event.target.value })} placeholder={t('agentSearchHint')} /></label>
          <label className="field"><span>{t('agentStatusFilter')}</span><select value={filters.status} onChange={(event) => updateFilters({ status: event.target.value as AgentFilters['status'], signal: '' })}>
            <option value="all">{t('all')}</option><option value="live">{t('agentStatusLive')}</option><option value="attention">{t('agentStatusAttention')}</option><option value="idle">{t('agentStatusIdle')}</option><option value="done">{t('agentStatusDone')}</option>
          </select></label>
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

      <section className="frame agents-kpi-frame">
        <div className="agent-kpis">
          <Kpi label={t('agentTotal')} value={summary.agents} hint={`${summary.operators} ${t('agentOperators')}`} />
          <Kpi label={t('agentLive')} value={summary.live} hint={t('agentLiveHint')} tone="live" />
          <Kpi label={t('agentTodayActive')} value={dur(summary.today_active)} hint={`${t('agentWeekActive')} ${dur(summary.week_active)}`} />
          <Kpi label={t('agentQuality')} value={percent(summary.success_rate)} hint={`${t('agentRuns')} ${qualityHint}`} tone={summary.errors || summary.blocked ? 'bad' : ''} />
          <Kpi label={t('agentAttention')} value={attentionCount(visibleAgents, latestShim)} hint={`${summary.errors} ${t('agentErrors')} · ${summary.blocked} ${t('agentBlocked')}`} tone={attentionCount(visibleAgents, latestShim) ? 'warn' : ''} />
        </div>
      </section>

      <div className="agents-analysis">
        <AgentActivityChart overview={overview} t={t} />
        <AgentRankPanel overview={overview} view={rankView} setView={setRankView} onFilter={(key, value) => updateFilters({ [key]: value, signal: '' })} t={t} />
      </div>

      <section className="frame agents-signals-frame">
        <div className="agents-panel-title"><b>{t('agentSignalsTitle')}</b><span className="cnt">{attentionCount(visibleAgents, latestShim)} {t('agentAttention')}</span></div>
        <div className="agent-signals">
          {SIGNALS.map((signal) => {
            const count = signalCount(signal.key)
            const selected = filters.signal === signal.key
            return (
              <button type="button" className={`agent-signal ${signal.tone} ${selected ? 'selected' : ''}`} key={signal.key} onClick={() => updateFilters({ status: count && !selected ? 'attention' : 'all', signal: selected ? '' : signal.key })}>
                <span className="agent-signal-dot" />
                <span><b>{t(signal.label)}</b><small>{t(signal.hint)}</small></span>
                <strong>{count}</strong>
              </button>
            )
          })}
        </div>
      </section>

      <section className="frame agents-list-frame">
        <h2><span><span className="sl">//</span>{t('agentDirectory')}</span><span className="cnt">{visibleAgents.length} {t('agentCards')}</span></h2>
        {visibleAgents.length ? <div className="agent-card-grid">{visibleAgents.map((agent) => <AgentCard key={keyOf(agent)} agent={agent} latestShim={latestShim} lang={lang} t={t} />)}</div> : <Empty title={t('agentNoAgents')} hint={t('agentNoAgentsHint')} />}
      </section>
    </div>
  )
}

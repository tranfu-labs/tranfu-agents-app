import { Fragment, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AgentActivityChart } from '../components/agents/AgentActivityChart'
import { AgentDirectoryTable } from '../components/agents/AgentDirectoryTable'
import { AgentKpiGrid } from '../components/agents/AgentKpiGrid'
import { AgentRankPanel } from '../components/agents/AgentRankPanel'
import { Empty } from '../components/Common'
import {
  agentKpiActionPatch,
  agentFiltersQuery,
  agentSectionOrder,
  parseAgentFilters,
  type AgentFilters,
  type AgentKpiAction,
  type AgentSectionKey,
  type AgentSignal,
  type AgentWindowComparison,
} from '../lib/agentsDashboard'
import { dur } from '../lib/utils'
import { windowDisplayLabel, windowPeriodLabel } from '../lib/skillsPresentation'
import type { AgentOverview, AgentsPayload, Lang } from '../lib/types'

const WINDOW_OPTIONS = ['today', 'this_week', 'last_week', '7d', '14d', '30d', '90d', 'custom'] as const

const SIGNALS: Array<{ key: AgentSignal; tone: string; label: string; hint: string }> = [
  { key: 'error', tone: 'bad', label: 'agentSignalError', hint: 'agentSignalErrorHint' },
  { key: 'shim', tone: 'warn', label: 'agentSignalShim', hint: 'agentSignalShimHint' },
  { key: 'quiet', tone: 'quiet', label: 'agentSignalQuiet', hint: 'agentSignalQuietHint' },
  { key: 'quality', tone: 'bad', label: 'agentSignalQuality', hint: 'agentSignalQualityHint' },
]

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

function useMobileAgentsLayout() {
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 600px)').matches)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined
    const query = window.matchMedia('(max-width: 600px)')
    const update = () => setMobile(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  return mobile
}

function focusAgentSection(id: string) {
  window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
    const target = document.getElementById(id)
    target?.focus({ preventScroll: true })
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }))
}

export function AgentsSkeleton({ t }: { t: (key: string) => string }) {
  const mobileLayout = useMobileAgentsLayout()
  return (
    <div className="agents-page agents-skeleton" aria-busy="true" aria-label={t('loading')}>
      <section className="frame agents-skeleton-toolbar"><span /></section>
      <AgentsSkeletonSections mobileLayout={mobileLayout} />
    </div>
  )
}

function AgentsSkeletonSections({ mobileLayout }: { mobileLayout: boolean }) {
  const sections: Record<AgentSectionKey, ReactNode> = {
    kpis: <section className="frame agents-skeleton-kpis">{Array.from({ length: 8 }, (_, index) => <span key={index} />)}</section>,
    signals: <section className="frame agents-skeleton-signals"><span /><span /><span /><span /></section>,
    analysis: (
      <div className="agents-analysis">
        <section className="frame agents-skeleton-rank"><span /><span /><span /><span /></section>
        <section className="frame agents-skeleton-trend"><span /></section>
      </div>
    ),
    directory: <section className="frame agents-skeleton-directory"><span /><span /><span /></section>,
  }
  return (
    <div className="agents-skeleton agents-skeleton-sections">
      {agentSectionOrder(mobileLayout).map((key) => <Fragment key={key}>{sections[key]}</Fragment>)}
    </div>
  )
}

export function AgentsLoadError({ retry, t }: { retry: () => void; t: (key: string) => string }) {
  return (
    <section className="frame agents-load-error">
      <Empty title={t('loadError')} />
      <button type="button" onClick={retry}>{t('refresh')}</button>
    </section>
  )
}

function AgentsToolbar({ filters, filtersOpen, visibleCount, activeSeconds, windowLabel, onToggleFilters, updateFilters, clearFilters, t }: {
  filters: AgentFilters
  filtersOpen: boolean
  visibleCount: number
  activeSeconds: number
  windowLabel: string
  onToggleFilters: () => void
  updateFilters: (patch: Partial<AgentFilters>) => void
  clearFilters: () => void
  t: (key: string) => string
}) {
  const hasFilters = Boolean(filters.q || filters.status !== 'all' || filters.signal)
  return (
    <section className="frame agents-toolbar-frame">
      <h2>
        <span><span className="sl">//</span>{t('skillsControls')}</span>
        <span className="cnt">{t('agentScopeDuration')}</span>
      </h2>
      <button type="button" className="agents-mobile-filter-summary" aria-expanded={filtersOpen} onClick={onToggleFilters}>
        <span>{filters.q || `${windowLabel} · ${visibleCount} Agent · ${dur(activeSeconds)}`}</span><b>{filtersOpen ? '⌃' : '⌄'}</b>
      </button>
      <div className={`toolbar agents-toolbar ${filtersOpen ? 'mobile-open' : ''}`}>
        <span className="agent-scope-chip">{t('agentScopeAgent')}</span>
        <label className="field agents-search-field"><span>{t('agentSearch')}</span><input value={filters.q} onChange={(event) => updateFilters({ q: event.target.value })} placeholder={t('agentSearchAgentsHint')} /></label>
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
        <label className="field"><span>{t('agentSort')}</span><select value={filters.sort} onChange={(event) => updateFilters({ sort: event.target.value as AgentFilters['sort'] })}>
          <option value="window_time">{t('agentSortWindowTime')}</option><option value="window_days">{t('agentSortWindowDays')}</option><option value="recent">{t('agentSortRecent')}</option><option value="success">{t('agentSortSuccess')}</option><option value="errors">{t('agentSortErrors')}</option><option value="name">{t('agentSortName')}</option>
        </select></label>
        {hasFilters ? <button className="agent-clear-filters" type="button" onClick={clearFilters}>{t('agentFiltersClear')}</button> : null}
      </div>
    </section>
  )
}

export function AgentsPendingWindow({ t }: { t: (key: string) => string }) {
  const location = useLocation()
  const navigate = useNavigate()
  const filters = useMemo(() => parseAgentFilters(location.search), [location.search])
  const [filtersOpen, setFiltersOpen] = useState(false)
  const mobileLayout = useMobileAgentsLayout()
  useEffect(() => {
    const canonicalSearch = agentFiltersQuery(filters)
    if (location.search !== canonicalSearch) navigate(`/agents${canonicalSearch}`, { replace: true })
  }, [filters, location.search, navigate])
  const updateFilters = (patch: Partial<AgentFilters>) => navigate(`/agents${agentFiltersQuery({ ...filters, ...patch })}`, { replace: true })
  return (
    <div className="agents-page agents-pending-window" aria-busy="true" aria-label={t('loading')}>
      <AgentsToolbar
        filters={filters}
        filtersOpen={filtersOpen}
        visibleCount={0}
        activeSeconds={0}
        windowLabel={windowPeriodLabel(filters.w, t)}
        onToggleFilters={() => setFiltersOpen((value) => !value)}
        updateFilters={updateFilters}
        clearFilters={() => navigate('/agents', { replace: true })}
        t={t}
      />
      <AgentsSkeletonSections mobileLayout={mobileLayout} />
    </div>
  )
}

export function Agents({ data, loading, lang, t }: { data: AgentsPayload; loading?: boolean; lang: Lang; t: (key: string) => string }) {
  const location = useLocation()
  const navigate = useNavigate()
  const filters = useMemo(() => parseAgentFilters(location.search), [location.search])
  const [filtersOpen, setFiltersOpen] = useState(false)
  const mobileLayout = useMobileAgentsLayout()
  const latestShim = data.shim?.version
  useEffect(() => {
    const canonicalSearch = agentFiltersQuery(filters)
    if (location.search !== canonicalSearch) navigate(`/agents${canonicalSearch}`, { replace: true })
  }, [filters, location.search, navigate])
  const visibleAgents = data.agents
  const agentLabels = data.agent_labels
  const directoryRows = useMemo(() => data.agents.map((agent) => ({
    agent,
    active_seconds: agent.active_seconds,
    active_days: agent.window_active_days,
  })), [data.agents])
  const agentsByKey = useMemo(() => new Map(directoryRows.map((row) => [row.agent.key, row])), [directoryRows])
  const rankingRows = useMemo(() => data.ranking.map((rank) => agentsByKey.get(rank.key)).filter((row): row is NonNullable<typeof row> => Boolean(row)), [agentsByKey, data.ranking])
  const trendBreakdown = useMemo(() => data.daily.flatMap((row) => row.segments.map((segment) => ({
    day: row.day,
    segment: agentLabels[segment.key] || segment.agent || 'Agent',
    active_agents: segment.active_agents,
    active_seconds: segment.active_seconds,
  }))), [agentLabels, data.daily])
  const overview = useMemo<AgentOverview>(() => ({
    today: data.today,
    days: data.window.days,
    summary: data.summary,
    daily: data.daily.map(({ day, active_agents, active_seconds }) => ({ day, active_agents, active_seconds })),
    runtime: [],
    operator: [],
  }), [data])
  const comparison = useMemo<AgentWindowComparison>(() => ({
    current: { activeAgents: data.comparison.current.active_agents, activeSeconds: data.comparison.current.active_seconds },
    previous: { activeAgents: data.comparison.previous.active_agents, activeSeconds: data.comparison.previous.active_seconds },
    currentAvailable: data.comparison.current.available,
    previousAvailable: data.comparison.previous.available,
  }), [data.comparison])
  const windowLabel = windowPeriodLabel(data.window.key, t)
  const summary = data.summary
  const attention = data.summary.attention
  const updateFilters = (patch: Partial<AgentFilters>) => {
    const next = { ...filters, ...patch }
    navigate(`/agents${agentFiltersQuery(next)}`, { replace: true })
  }
  const clearFilters = () => navigate('/agents', { replace: true })
  const signalCount = (signal: AgentSignal) => Number(data.signals[signal] || 0)
  const handleKpiAction = (action: AgentKpiAction) => {
    const patch = agentKpiActionPatch(action)
    if (patch) updateFilters(patch)
    const target = action === 'trend' ? 'agents-trend' : 'agents-directory'
    focusAgentSection(target)
  }

  const sections: Record<AgentSectionKey, ReactNode> = {
    kpis: (
      <AgentKpiGrid
        comparison={comparison}
        summary={summary}
        totalAgents={data.summary.total_agents}
        attention={attention}
        windowKey={data.window.key}
        windowLabel={windowLabel}
        onAction={handleKpiAction}
        t={t}
      />
    ),
    signals: (
      <section className="frame agents-signals-frame">
        <div className="agents-health">
          <b>{t('agentSignalsTitle')}</b>
          {SIGNALS.map((signal) => {
            const count = signalCount(signal.key)
            const selected = filters.signal === signal.key
            return (
              <button type="button" className={`agent-health-signal ${signal.tone} ${selected ? 'selected' : ''}`} key={signal.key} onClick={() => updateFilters({ status: count && !selected ? 'attention' : 'all', signal: selected ? '' : signal.key })}>
                <i />
                <span>{t(signal.label)}</span>
                <strong>{count}</strong>
              </button>
            )
          })}
        </div>
      </section>
    ),
    analysis: (
      <div className="agents-analysis">
        <AgentRankPanel rows={rankingRows} labels={agentLabels} lang={lang} windowLabel={windowLabel} t={t} />
        <AgentActivityChart key={`${data.window.key}:${data.window.start}:${data.window.end}:${data.window.days.length}`} overview={overview} breakdown={trendBreakdown} currentDay={data.window.end === data.today ? data.today : undefined} windowLabel={windowLabel} t={t} />
      </div>
    ),
    directory: (
      <section id="agents-directory" tabIndex={-1} className="frame agents-list-frame">
        <h2><span><span className="sl">//</span>{t('agentDirectory')}</span><span className="cnt">{directoryRows.length} {t('agentRows')}</span></h2>
        {directoryRows.length ? <AgentDirectoryTable rows={directoryRows} labels={agentLabels} latestShim={latestShim} lang={lang} windowLabel={windowLabel} t={t} /> : <Empty title={t('agentNoAgents')} hint={t('agentNoAgentsHint')} />}
      </section>
    ),
  }

  return (
    <div className={`agents-page ${loading ? 'is-loading' : ''}`} aria-busy={loading || undefined}>
      <AgentsToolbar
        filters={filters}
        filtersOpen={filtersOpen}
        visibleCount={visibleAgents.length}
        activeSeconds={data.summary.active_seconds}
        windowLabel={windowLabel}
        onToggleFilters={() => setFiltersOpen((value) => !value)}
        updateFilters={updateFilters}
        clearFilters={clearFilters}
        t={t}
      />
      {loading
        ? <AgentsSkeletonSections mobileLayout={mobileLayout} />
        : agentSectionOrder(mobileLayout).map((key) => <Fragment key={key}>{sections[key]}</Fragment>)}
    </div>
  )
}

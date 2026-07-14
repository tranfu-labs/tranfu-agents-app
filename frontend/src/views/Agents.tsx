import { Fragment, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AgentActivityChart } from '../components/agents/AgentActivityChart'
import { AgentDirectoryTable } from '../components/agents/AgentDirectoryTable'
import { AgentKpiGrid } from '../components/agents/AgentKpiGrid'
import { AgentRankPanel } from '../components/agents/AgentRankPanel'
import { Empty } from '../components/Common'
import {
  buildAgentDailyBreakdown,
  buildAgentDirectoryRows,
  agentKpiActionPatch,
  agentFiltersQuery,
  agentSectionOrder,
  agentWindowComparison,
  agentOverviewOf,
  agentSignals,
  attentionCount,
  buildAgentOverview,
  buildAgentWindowOverview,
  filterAgents,
  parseAgentFilters,
  resolveAgentWindow,
  type AgentFilters,
  type AgentKpiAction,
  type AgentSectionKey,
  type AgentSignal,
} from '../lib/agentsDashboard'
import { RT } from '../lib/utils'
import { windowDisplayLabel, windowPeriodLabel } from '../lib/skillsPresentation'
import type { Lang, StatePayload } from '../lib/types'

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

export function Agents({ data, lang, t }: { data: StatePayload; lang: Lang; t: (key: string) => string }) {
  const location = useLocation()
  const navigate = useNavigate()
  const filters = useMemo(() => parseAgentFilters(location.search), [location.search])
  const [filtersOpen, setFiltersOpen] = useState(false)
  const mobileLayout = useMobileAgentsLayout()
  const latestShim = data.shim?.version
  const allOverview = agentOverviewOf(data, latestShim)
  const visibleAgents = useMemo(() => filterAgents(data.sessions, filters, latestShim), [data.sessions, filters, latestShim])
  const hasFilters = Boolean(filters.q || filters.status !== 'all' || filters.signal || filters.w !== 'today' || filters.wstart || filters.wend || filters.rt || filters.op || filters.sort !== 'recent')
  const overview = hasFilters ? buildAgentOverview(visibleAgents, latestShim, allOverview.today) : allOverview
  const window = useMemo(() => resolveAgentWindow(filters, allOverview.today), [filters, allOverview.today])
  const windowOverview = useMemo(() => buildAgentWindowOverview(visibleAgents, overview, window), [visibleAgents, overview, window])
  const trendBreakdown = useMemo(() => buildAgentDailyBreakdown(visibleAgents, overview.days, window.days, filters.rank), [visibleAgents, overview.days, window.days, filters.rank])
  const directoryRows = useMemo(() => buildAgentDirectoryRows(visibleAgents, overview.days, window.days, filters.sort), [visibleAgents, overview.days, window.days, filters.sort])
  const comparison = useMemo(() => agentWindowComparison(visibleAgents, overview.days, window), [visibleAgents, overview.days, window])
  const windowLabel = windowPeriodLabel(window.key, t)
  const rankView = filters.rank
  const summary = overview.summary
  const attention = attentionCount(visibleAgents, latestShim)
  const updateFilters = (patch: Partial<AgentFilters>) => {
    const next = { ...filters, ...patch }
    navigate(`/agents${agentFiltersQuery(next)}`, { replace: true })
  }
  const clearFilters = () => navigate('/agents', { replace: true })
  const signalCount = (signal: AgentSignal) => visibleAgents.filter((agent) => agentSignals(agent, latestShim).includes(signal)).length
  const handleKpiAction = (action: AgentKpiAction) => {
    const patch = agentKpiActionPatch(action)
    if (patch) updateFilters(patch)
    const target = action === 'trend' ? 'agents-trend'
      : action === 'operator-rank' ? 'agents-rank'
        : 'agents-directory'
    focusAgentSection(target)
  }

  const sections: Record<AgentSectionKey, ReactNode> = {
    kpis: (
      <AgentKpiGrid
        comparison={comparison}
        summary={summary}
        totalAgents={data.sessions.length}
        attention={attention}
        windowKey={window.key}
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
        <AgentRankPanel overview={windowOverview} view={rankView} onFilter={(key, value) => updateFilters({ [key]: value, signal: '' })} windowLabel={windowLabel} t={t} />
        <AgentActivityChart key={`${filters.rank}:${window.key}:${window.days[0] || ''}:${window.days.at(-1) || ''}:${window.days.length}`} overview={windowOverview} breakdown={trendBreakdown} view={filters.rank} currentDay={window.days.at(-1) === allOverview.today ? allOverview.today : undefined} windowLabel={windowLabel} t={t} />
      </div>
    ),
    directory: (
      <section id="agents-directory" tabIndex={-1} className="frame agents-list-frame">
        <h2><span><span className="sl">//</span>{t('agentDirectory')}</span><span className="cnt">{directoryRows.length} {t('agentRows')}</span></h2>
        {directoryRows.length ? <AgentDirectoryTable rows={directoryRows} latestShim={latestShim} lang={lang} windowLabel={windowLabel} t={t} /> : <Empty title={t('agentNoAgents')} hint={t('agentNoAgentsHint')} />}
      </section>
    ),
  }

  return (
    <div className="agents-page">
      <section className="frame agents-toolbar-frame">
        <h2>
          <span><span className="sl">//</span>{t('skillsControls')}</span>
          <span className="cnt">{t(rankView === 'runtime' ? 'agentRankRuntimeHint' : 'agentRankOperatorHint')}</span>
        </h2>
        <button type="button" className="agents-mobile-filter-summary" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((value) => !value)}>
          <span>{filters.q || `${windowLabel} · ${visibleAgents.length} · ${summary.live} ${t('agentLiveShort')} · ${filters.rt ? (RT[filters.rt] || filters.rt) : t('all')}`}</span><b>{filtersOpen ? '⌃' : '⌄'}</b>
        </button>
        <div className={`toolbar agents-toolbar ${filtersOpen ? 'mobile-open' : ''}`}>
          <div className="seg agents-view-seg" role="group" aria-label={t('agentRank')}>
            <button type="button" className={rankView === 'operator' ? 'on' : ''} aria-pressed={rankView === 'operator'} onClick={() => updateFilters({ rank: 'operator' })}>{t('agentRankOperator')}</button>
            <button type="button" className={rankView === 'runtime' ? 'on' : ''} aria-pressed={rankView === 'runtime'} onClick={() => updateFilters({ rank: 'runtime' })}>{t('agentRankRuntime')}</button>
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
            <option value="recent">{t('agentSortRecent')}</option><option value="window_time">{t('agentSortWindowTime')}</option><option value="window_days">{t('agentSortWindowDays')}</option><option value="success">{t('agentSortSuccess')}</option><option value="errors">{t('agentSortErrors')}</option><option value="name">{t('agentSortName')}</option>
          </select></label>
          {hasFilters ? <button className="agent-clear-filters" type="button" onClick={clearFilters}>{t('agentFiltersClear')}</button> : null}
        </div>
      </section>
      {agentSectionOrder(mobileLayout).map((key) => <Fragment key={key}>{sections[key]}</Fragment>)}
    </div>
  )
}

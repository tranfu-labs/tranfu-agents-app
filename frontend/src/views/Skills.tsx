import type { KeyboardEvent, MouseEvent } from 'react'
import { useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { RuntimeBars, MiniTrend, StackedSkillChart } from '../components/Charts'
import { Empty, SectionTitle } from '../components/Common'
import { AttributionDonuts } from '../components/skills/AttributionDonuts'
import { FunnelSection } from '../components/skills/FunnelSection'
import { GovernanceTodo } from '../components/skills/GovernanceTodo'
import { HealthBar } from '../components/skills/HealthBar'
import { KpiStrip } from '../components/skills/KpiStrip'
import { RankBars } from '../components/skills/RankBars'
import { SkillDrawer } from '../components/skills/SkillDrawer'
import { SkillsDetailTable } from '../components/skills/SkillsDetailTable'
import type { SetSkillQueryState, SkillQueryState } from '../lib/skillQuery'
import { useSkillQueryState } from '../lib/skillQuery'
import { setSelectedSkill, selectedSkillOf } from '../lib/skillsSelection'
import { resolveSkillsWindow } from '../lib/skillsWindow'
import { mobileFilterSummary, windowDisplayLabel, windowPeriodLabel } from '../lib/skillsPresentation'
import type { OperatorTableRow, SkillsOverview, SkillTableRow } from '../lib/types'
import { encodePathParam, RT, sourceKey, sourceLabel } from '../lib/utils'

type FilterableSkill = { name?: string; skill?: string; runtime?: string; source?: string; runtime_counts?: Record<string, number> }
type FilterableOperator = { operator?: string; runtime?: string; source?: string; runtime_counts?: Record<string, number>; source_counts?: Record<string, number> }

const WINDOW_OPTIONS = ['today', 'this_week', 'last_week', '7d', '14d', '30d', '90d', 'custom'] as const
const TOP_OPTIONS = [5, 8, 10, 20]

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

function skillPass(row: FilterableSkill, q: string, runtime: string, source: string) {
  const needle = q.trim().toLowerCase()
  const name = String(row.name || row.skill || '')
  if (needle && !name.toLowerCase().includes(needle)) return false
  if (source && sourceKey(row.source) !== source) return false
  if (runtime) {
    if (row.runtime) return row.runtime === runtime
    return Boolean(row.runtime_counts?.[runtime])
  }
  return true
}

function operatorNamePass(row: FilterableOperator, q: string) {
  const needle = q.trim().toLowerCase()
  const operator = String(row.operator || '')
  return !needle || operator.toLowerCase().includes(needle)
}

function sortedRows<T extends object>(rows: T[], sort: string, dir: string) {
  const direction = dir === 'asc' ? 1 : -1
  return rows.slice().sort((a, b) => {
    const av = (a as Record<string, unknown>)[sort] ?? ''
    const bv = (b as Record<string, unknown>)[sort] ?? ''
    if (typeof av === 'number' || typeof bv === 'number') return (Number(av || 0) - Number(bv || 0)) * direction
    return String(av).localeCompare(String(bv)) * direction
  })
}

function rowKey(event: KeyboardEvent<HTMLTableRowElement>, go: () => void) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  go()
}

function SkillsToolbar({ data, params, setParams, view, t }: { data: SkillsOverview | null; params: SkillQueryState; setParams: SetSkillQueryState; view: 'skill' | 'operator'; t: (key: string) => string }) {
  const [filtersOpen, setFiltersOpen] = useState(false)
  const location = useLocation()
  const runtimes = new Set<string>()
  data?.daily?.forEach((row) => row.runtime && runtimes.add(row.runtime))
  data?.operator_daily?.forEach((row) => row.runtime && runtimes.add(row.runtime))
  data?.table?.forEach((row) => Object.keys(row.runtime_counts || {}).forEach((runtime) => runtimes.add(runtime)))
  data?.operator_table?.forEach((row) => Object.keys(row.runtime_counts || {}).forEach((runtime) => runtimes.add(runtime)))
  const update = (patch: Partial<typeof params>) => void setParams(patch)
  const currentWindow = params.w || `${params.win || 30}d`
  const newScopeSearch = useMemo(() => {
    const search = new URLSearchParams(location.search)
    search.set('w', params.w || `${params.win || 7}d`)
    search.set('scope', 'new')
    return `/skills?${search.toString()}`
  }, [location.search, params.w, params.win])
  const setView = (next: 'skill' | 'operator') => {
    if (next === view) return
    update({ view: next, q: '', sel: '', sort: 'sessions_window', dir: 'desc' })
  }
  const filterSummary = mobileFilterSummary(params, view, t)
  return (
    <section className="frame skills-toolbar-frame">
      <h2><span><span className="sl">//</span>{t('skillsControls')}</span><span className="cnt">{view === 'operator' ? t('viewOperatorHint') : t('viewSkillHint')}</span></h2>
      <button
        type="button"
        className="skills-mobile-filter-summary"
        aria-expanded={filtersOpen}
        onClick={() => setFiltersOpen((value) => !value)}
      >
        <span>{filterSummary}</span>
        <b aria-hidden="true">{filtersOpen ? '⌃' : '⌄'}</b>
      </button>
      <Link className="skills-mobile-new-link" to={newScopeSearch} aria-label={t('newSkillsLinkLabel')} title={t('newSkillsLinkLabel')}>
        {t('newSkillsSummary')} {data?.new_skill_count ?? 0}
      </Link>
      <div className={`toolbar skills-dashboard-toolbar ${filtersOpen ? 'mobile-open' : ''}`}>
        <div className="seg skills-view-seg">
          <button type="button" aria-pressed={view === 'skill'} className={view === 'skill' ? 'on' : ''} onClick={() => setView('skill')}>{t('viewSkill')}</button>
          <button type="button" aria-pressed={view === 'operator'} className={view === 'operator' ? 'on' : ''} onClick={() => setView('operator')}>{t('viewOperator')}</button>
        </div>
        <label className="field">
          <span>{t('windowFilter')}</span>
          <select value={currentWindow} onChange={(event) => update({ w: event.target.value, win: event.target.value.endsWith('d') ? Number(event.target.value.slice(0, -1)) : params.win })}>
            {WINDOW_OPTIONS.map((key) => <option value={key} key={key}>{windowDisplayLabel(key, t)}</option>)}
          </select>
        </label>
        {currentWindow === 'custom' ? (
          <>
            <label className="field">
              <span>{t('customStart')}</span>
              <input type="datetime-local" value={unixToInput(params.wstart)} onChange={(event) => update({ w: 'custom', wstart: inputToUnix(event.target.value) })} />
            </label>
            <label className="field">
              <span>{t('customEnd')}</span>
              <input type="datetime-local" value={unixToInput(params.wend)} onChange={(event) => update({ w: 'custom', wend: inputToUnix(event.target.value) })} />
            </label>
          </>
        ) : null}
        {params.scope === 'new' ? (
          <button type="button" className="scope-chip" onClick={() => update({ scope: 'all' })} aria-label={t('clearScope')} title={t('clearScope')}>
            {t('newSkillsScope')} ×
          </button>
        ) : null}
        <label className="field search-field">
          <span>{view === 'operator' ? t('operatorSearch') : t('skillSearch')}</span>
          <input value={params.q} onChange={(event) => update({ q: event.target.value })} />
        </label>
        <label className="field">
          <span>{t('runtimeFilter')}</span>
          <select value={params.rt} onChange={(event) => update({ rt: event.target.value })}>
            <option value="">{t('all')}</option>
            {[...runtimes].sort().map((runtime) => <option value={runtime} key={runtime}>{RT[runtime] || runtime}</option>)}
          </select>
        </label>
        <label className="field">
          <span>{t('sourceFilter')}</span>
          <select value={params.src} onChange={(event) => update({ src: event.target.value })}>
            <option value="">{t('all')}</option>
            {['own', 'meta', 'external', 'non_catalog'].map((source) => <option value={source} key={source}>{sourceLabel(source, t)}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Top</span>
          <select value={params.topn} onChange={(event) => update({ topn: Number(event.target.value) })}>
            {TOP_OPTIONS.map((value) => <option value={value} key={value}>{value}</option>)}
          </select>
        </label>
        <label className="field inline-check">
          <input type="checkbox" checked={params.hz === '1'} onChange={(event) => update({ hz: event.target.checked ? '1' : '0' })} />
          <span>{t('hideZeroUsage')}</span>
        </label>
      </div>
    </section>
  )
}

function OperatorTable({ rows, params, setParams, windowKey, t }: { rows: OperatorTableRow[]; params: SkillQueryState; setParams: SetSkillQueryState; windowKey: string; t: (key: string) => string }) {
  const location = useLocation()
  const navigate = useNavigate()
  const windowLabel = windowPeriodLabel(windowKey, t)
  const updateSort = (key: string) => {
    const dir = params.sort === key && params.dir !== 'asc' ? 'asc' : 'desc'
    void setParams({ sort: key, dir })
  }
  const openOperator = (operator: string) => navigate(`/operator/${encodePathParam(operator)}${location.search}`)
  const head = (key: string, label: string, cls = '') => (
    <th className={`sort ${cls}`} onClick={(event: MouseEvent<HTMLTableCellElement>) => {
      event.stopPropagation()
      updateSort(key)
    }}>
      {label}
      {params.sort === key ? (params.dir === 'asc' ? ' ↑' : ' ↓') : ''}
    </th>
  )
  if (!rows.length) return <Empty title={t('noOperators')} hint={t('noOperatorsH')} />
  return (
    <div className="skills-wrap">
      <table className="skill-table mobile-card-table">
        <thead>
          <tr>
            {head('operator', t('operatorName'))}
            {head('sessions_window', windowLabel, 'num')}
            {head('previous_sessions', t('previousWindow'), 'num')}
            {head('sessions_7d', t('skill7'), 'num')}
            {head('sessions_30d', t('skill30'), 'num')}
            {head('sessions_total', t('skillTotal'), 'num')}
            {head('skill_count', t('skillsUsed'), 'num')}
            {head('session_count', t('sessionCount'), 'num')}
            <th>{t('runtimeFilter')}</th>
            <th>{t('trend')}</th>
            {head('last_day', t('skillLast'))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.operator} role="link" tabIndex={0} onClick={() => openOperator(row.operator)} onKeyDown={(event) => rowKey(event, () => openOperator(row.operator))}>
              <td className="mobile-main" data-label={t('operatorName')}><b>{row.operator}</b></td>
              <td className="num" data-label={windowLabel}>{row.sessions_window ?? row.sessions_30d}</td>
              <td className="num" data-label={t('previousWindow')}>{row.previous_sessions || '—'}</td>
              <td className="num" data-label={t('skill7')}>{row.sessions_7d}</td>
              <td className="num" data-label={t('skill30')}>{row.sessions_30d}</td>
              <td className="num" data-label={t('skillTotal')}>{row.sessions_total}</td>
              <td className="num" data-label={t('skillsUsed')}>{row.skill_count}</td>
              <td className="num" data-label={t('sessionCount')}>{row.session_count}</td>
              <td data-label={t('runtimeFilter')}><RuntimeBars counts={row.runtime_counts} /></td>
              <td data-label={t('trend')}><MiniTrend values={row.trend_14d} /></td>
              <td className="q" data-label={t('skillLast')}>{row.last_day || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SkillsView({ data, loading, error, t }: { data: SkillsOverview | null; loading: boolean; error: string; t: (key: string) => string }) {
  const [params, setParams] = useSkillQueryState()
  const location = useLocation()
  const [drawerSkill, setDrawerSkill] = useState('')
  const skillsWindow = resolveSkillsWindow(params)
  const view = params.view === 'operator' ? 'operator' : 'skill'
  const selected = selectedSkillOf(params)
  const topN = TOP_OPTIONS.includes(params.topn) ? params.topn : 8
  const filteredSkillDaily = (data?.daily || []).filter((row) => skillPass({ skill: row.skill, runtime: row.runtime, source: row.source }, params.q, params.rt, params.src))
  const filteredOperatorDaily = (data?.operator_daily || []).filter((row) => operatorNamePass({ operator: row.operator }, params.q))
  const skillRowsBase = (data?.table || [])
    .filter((row) => skillPass(row, params.q, params.rt, params.src))
    .filter((row) => params.hz !== '1' || Number(row.sessions_window ?? row.sessions_30d ?? 0) > 0)
  const skillRows = sortedRows(skillRowsBase, params.sort, params.dir) as SkillTableRow[]
  const rankRows = useMemo(() => skillRowsBase.slice().sort((a, b) => Number(b.sessions_window ?? b.sessions_30d ?? 0) - Number(a.sessions_window ?? a.sessions_30d ?? 0)), [skillRowsBase])
  const operatorRows = sortedRows((data?.operator_table || []).filter((row) => operatorNamePass(row, params.q)), params.sort, params.dir) as OperatorTableRow[]
  const chartRows = view === 'operator' ? filteredOperatorDaily : filteredSkillDaily
  const chartDays = data?.days || skillsWindow.days
  const isShortWindow = chartDays <= 14

  const openSkill = (name: string) => {
    setDrawerSkill(name)
    if (selected !== name) void setParams({ sel: name })
  }
  const selectSkill = (name: string) => setSelectedSkill(params, setParams, name)
  const setSource = (source: string) => void setParams({ src: params.src === source ? '' : source })

  if (loading && !data) {
    return (
      <div className="skills-page skills-dashboard">
        <SkillsToolbar data={data} params={params} setParams={setParams} view={view} t={t} />
        <section className="frame"><Empty title={t('loading')} /></section>
      </div>
    )
  }

  return (
    <div className={`skills-page skills-dashboard ${loading ? 'is-refreshing' : ''}`}>
      <SkillsToolbar data={data} params={params} setParams={setParams} view={view} t={t} />
      {error ? <div className="note-warn">{t(error)}</div> : null}
      <KpiStrip data={data} view={view} t={t} />
      <HealthBar data={data} view={view} t={t} />
      <div className={`skills-analysis ${isShortWindow ? 'skills-analysis--short' : 'skills-analysis--long'}`}>
        <section className="frame skills-rank-panel">
          <SectionTitle title={view === 'operator' ? t('operatorRank') : t('mainRank')} count={view === 'operator' ? operatorRows.length : rankRows.length} />
          {view === 'operator' ? (
            <>
              <div className="usage-note">{t('operatorMetricNote')}</div>
              <OperatorTable rows={operatorRows} params={params} setParams={setParams} windowKey={skillsWindow.key} t={t} />
            </>
          ) : (
            <RankBars rows={rankRows} topN={topN} selected={selected} onSelect={selectSkill} t={t} />
          )}
        </section>
        <section className="frame skills-trend-panel">
          <SectionTitle title={view === 'operator' ? t('dailyByOperator') : t('dailyUsed')} count={skillsWindow.label} />
          <StackedSkillChart rows={chartRows} overview={data} days={chartDays} t={t} segmentKey={view === 'operator' ? 'operator' : 'skill'} selectedSegment={view === 'skill' ? selected : ''} topN={topN} emptyTitle={view === 'operator' ? t('noOperators') : undefined} emptyHint={view === 'operator' ? t('noOperatorsH') : undefined} />
        </section>
      </div>
      <section className="frame skills-governance-row-frame">
        <GovernanceTodo data={data} view={view} t={t} />
      </section>
      {view === 'skill' ? <AttributionDonuts data={data} selected={selected} rows={skillRowsBase} setSource={setSource} t={t} /> : null}
      {view === 'skill' ? <SkillsDetailTable rows={skillRows} allRows={data?.table || []} params={params} setParams={setParams} selected={selected} onOpen={openSkill} t={t} /> : null}
      <FunnelSection data={data} t={t} />
      {drawerSkill ? <SkillDrawer name={drawerSkill} row={(data?.table || []).find((row) => row.name === drawerSkill)} search={location.search} onClose={() => setDrawerSkill('')} t={t} /> : null}
    </div>
  )
}

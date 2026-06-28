import type { KeyboardEvent, MouseEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { RuntimeBars, MiniTrend, StackedSkillChart } from '../components/Charts'
import { Empty, SectionTitle } from '../components/Common'
import type { SetSkillQueryState, SkillQueryState } from '../lib/skillQuery'
import { useSkillQueryState } from '../lib/skillQuery'
import type { GovernanceUntrackedSkill, OperatorTableRow, SkillsOverview, SkillTableRow } from '../lib/types'
import { encodePathParam, RT, sourceKey, sourceLabel } from '../lib/utils'

type FilterableSkill = { name?: string; skill?: string; runtime?: string; source?: string; runtime_counts?: Record<string, number> }
type FilterableOperator = { operator?: string; runtime?: string; source?: string; runtime_counts?: Record<string, number>; source_counts?: Record<string, number> }

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

function operatorPass(row: FilterableOperator, q: string, runtime: string, source: string) {
  const needle = q.trim().toLowerCase()
  const operator = String(row.operator || '')
  if (needle && !operator.toLowerCase().includes(needle)) return false
  if (source) {
    const sourceOk = row.source ? sourceKey(row.source) === source : Object.keys(row.source_counts || {}).some((item) => sourceKey(item) === source)
    if (!sourceOk) return false
  }
  if (runtime) {
    if (row.runtime) return row.runtime === runtime
    return Boolean(row.runtime_counts?.[runtime])
  }
  return true
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

function pct(value?: number) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

function FilterBar({ data, t, params, setParams, view }: { data: SkillsOverview | null; t: (key: string) => string; params: SkillQueryState; setParams: SetSkillQueryState; view: 'skill' | 'operator' }) {
  const runtimes = new Set<string>()
  data?.daily?.forEach((row) => row.runtime && runtimes.add(row.runtime))
  data?.operator_daily?.forEach((row) => row.runtime && runtimes.add(row.runtime))
  data?.table?.forEach((row) => Object.keys(row.runtime_counts || {}).forEach((runtime) => runtimes.add(runtime)))
  data?.operator_table?.forEach((row) => Object.keys(row.runtime_counts || {}).forEach((runtime) => runtimes.add(runtime)))
  const update = (patch: Partial<typeof params>) => void setParams(patch)
  return (
    <div className="toolbar">
      <label className="field">
        <span>{view === 'operator' ? t('operatorSearch') : t('skillSearch')}</span>
        <input value={params.q} onChange={(event) => update({ q: event.target.value })} />
      </label>
      <label className="field">
        <span>{t('runtimeFilter')}</span>
        <select value={params.rt} onChange={(event) => update({ rt: event.target.value })}>
          <option value="">{t('all')}</option>
          {[...runtimes].sort().map((runtime) => (
            <option value={runtime} key={runtime}>
              {RT[runtime] || runtime}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{t('sourceFilter')}</span>
        <select value={params.src} onChange={(event) => update({ src: event.target.value })}>
          <option value="">{t('all')}</option>
          {['own', 'meta', 'external', 'non_catalog'].map((source) => (
            <option value={source} key={source}>
              {sourceLabel(source === 'non_catalog' ? '非公司库' : source, t)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{t('windowFilter')}</span>
        <select value={params.win} onChange={(event) => update({ win: Number(event.target.value) })}>
          {[7, 30, 90].map((days) => (
            <option value={days} key={days}>
              {days}d
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}

function ViewSwitch({ view, setParams, t }: { view: 'skill' | 'operator'; setParams: SetSkillQueryState; t: (key: string) => string }) {
  const setView = (next: 'skill' | 'operator') => {
    if (next === view) return
    void setParams({ view: next, sort: 'sessions_30d', dir: 'desc' })
  }
  return (
    <section className="frame viewcard">
      <h2>
        <span>
          <span className="sl">//</span>
          {t('viewBy')}
        </span>
        <span className="cnt">{view === 'operator' ? t('viewOperatorHint') : t('viewSkillHint')}</span>
      </h2>
      <div className="viewbody">
        <div className="seg">
          <button type="button" aria-pressed={view === 'skill'} className={view === 'skill' ? 'on' : ''} onClick={() => setView('skill')}>
            {t('viewSkill')}
          </button>
          <button type="button" aria-pressed={view === 'operator'} className={view === 'operator' ? 'on' : ''} onClick={() => setView('operator')}>
            {t('viewOperator')}
          </button>
        </div>
      </div>
    </section>
  )
}

function SkillsTable({ rows, params, setParams, t }: { rows: SkillTableRow[]; params: SkillQueryState; setParams: SetSkillQueryState; t: (key: string) => string }) {
  const location = useLocation()
  const navigate = useNavigate()
  const updateSort = (key: string) => {
    const dir = params.sort === key && params.dir !== 'asc' ? 'asc' : 'desc'
    void setParams({ sort: key, dir })
  }
  const openSkill = (name: string) => navigate(`/skill/${encodePathParam(name)}${location.search}`)
  const head = (key: string, label: string, cls = '') => (
    <th className={`sort ${cls}`} onClick={(event: MouseEvent<HTMLTableCellElement>) => {
      event.stopPropagation()
      updateSort(key)
    }}>
      {label}
      {params.sort === key ? (params.dir === 'asc' ? ' ↑' : ' ↓') : ''}
    </th>
  )
  if (!rows.length) return <Empty title={t('noSkills')} hint={t('noSkillsH')} />
  return (
    <div className="skills-wrap">
      <table className="skill-table mobile-card-table">
        <thead>
          <tr>
            {head('name', t('skillName'))}
            {head('source', t('sourceFilter'))}
            {head('sessions_7d', t('skill7'), 'num')}
            {head('sessions_30d', t('skill30'), 'num')}
            {head('sessions_total', t('skillTotal'), 'num')}
            {head('users_30d', t('skillUsers30'), 'num')}
            <th>{t('runtimeFilter')}</th>
            <th>{t('trend')}</th>
            {head('last_day', t('skillLast'))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} role="link" tabIndex={0} onClick={() => openSkill(row.name)} onKeyDown={(event) => rowKey(event, () => openSkill(row.name))}>
              <td className="mobile-main" data-label={t('skillName')}>
                <b>{row.name}</b>
              </td>
              <td data-label={t('sourceFilter')}>
                <span className="source-pill">{sourceLabel(row.source, t)}</span>
              </td>
              <td className="num" data-label={t('skill7')}>{row.sessions_7d}</td>
              <td className="num" data-label={t('skill30')}>{row.sessions_30d}</td>
              <td className="num" data-label={t('skillTotal')}>{row.sessions_total}</td>
              <td className="num" data-label={t('skillUsers30')}>{row.users_30d}</td>
              <td data-label={t('runtimeFilter')}>
                <RuntimeBars counts={row.runtime_counts} />
              </td>
              <td data-label={t('trend')}>
                <MiniTrend values={row.trend_14d} />
              </td>
              <td className="q" data-label={t('skillLast')}>{row.last_day || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function GovernanceLens({ data, lens, setParams, t }: { data: SkillsOverview | null; lens: 'all' | 'untracked'; setParams: SetSkillQueryState; t: (key: string) => string }) {
  const stats = data?.governance?.untracked_usage
  const setLens = (next: 'all' | 'untracked') => {
    if (next === lens) return
    void setParams({ lens: next })
  }
  return (
    <div className="governance-lens">
      <div className="lens-title">{t('governanceLens')}</div>
      <div className="seg lens-seg">
        <button type="button" aria-pressed={lens === 'all'} className={lens === 'all' ? 'on' : ''} onClick={() => setLens('all')}>
          {t('lensAllSkills')}
        </button>
        <button type="button" aria-pressed={lens === 'untracked'} className={lens === 'untracked' ? 'on' : ''} onClick={() => setLens('untracked')}>
          {t('lensUntrackedUsage')} {pct(stats?.ratio)} · {stats?.used_sessions || 0}/{stats?.total_sessions || 0}
        </button>
      </div>
      <div className="lens-note">{t('untrackedUsageNote')}</div>
    </div>
  )
}

function GovernanceSkillTable({ rows, t }: { rows: GovernanceUntrackedSkill[]; t: (key: string) => string }) {
  const location = useLocation()
  const navigate = useNavigate()
  const openSkill = (name: string) => navigate(`/skill/${encodePathParam(name)}${location.search}`)
  if (!rows.length) return <Empty title={t('noUntrackedSkills')} hint={t('noUntrackedSkillsH')} />
  return (
    <div className="skills-wrap">
      <table className="skill-table mobile-card-table">
        <thead>
          <tr>
            <th>{t('skillName')}</th>
            <th className="num">{t('usageShare')}</th>
            <th className="num">{t('usedSessions')}</th>
            <th className="num">{t('skillUsers30')}</th>
            <th>{t('runtimeFilter')}</th>
            <th>{t('trend')}</th>
            <th>{t('skillLast')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} role="link" tabIndex={0} onClick={() => openSkill(row.name)} onKeyDown={(event) => rowKey(event, () => openSkill(row.name))}>
              <td className="mobile-main" data-label={t('skillName')}>
                <b>{row.name}</b>
              </td>
              <td className="num" data-label={t('usageShare')}>{pct(row.share)}</td>
              <td className="num" data-label={t('usedSessions')}>{row.sessions}</td>
              <td className="num" data-label={t('skillUsers30')}>{row.users_30d}</td>
              <td data-label={t('runtimeFilter')}>
                <RuntimeBars counts={row.runtime_counts} />
              </td>
              <td data-label={t('trend')}>
                <MiniTrend values={row.trend_14d} />
              </td>
              <td className="q" data-label={t('skillLast')}>{row.last_day || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function OperatorTable({ rows, params, setParams, t }: { rows: OperatorTableRow[]; params: SkillQueryState; setParams: SetSkillQueryState; t: (key: string) => string }) {
  const location = useLocation()
  const navigate = useNavigate()
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
              <td className="mobile-main" data-label={t('operatorName')}>
                <b>{row.operator}</b>
              </td>
              <td className="num" data-label={t('skill7')}>{row.sessions_7d}</td>
              <td className="num" data-label={t('skill30')}>{row.sessions_30d}</td>
              <td className="num" data-label={t('skillTotal')}>{row.sessions_total}</td>
              <td className="num" data-label={t('skillsUsed')}>{row.skill_count}</td>
              <td className="num" data-label={t('sessionCount')}>{row.session_count}</td>
              <td data-label={t('runtimeFilter')}>
                <RuntimeBars counts={row.runtime_counts} />
              </td>
              <td data-label={t('trend')}>
                <MiniTrend values={row.trend_14d} />
              </td>
              <td className="q" data-label={t('skillLast')}>{row.last_day || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Funnel({ data, t }: { data: SkillsOverview | null; t: (key: string) => string }) {
  const funnel = data?.funnel
  if (!funnel?.available) {
    return <Empty title={t('catalogUnavailable')} hint={data?.catalog?.error || ''} />
  }
  const max = Math.max((funnel.catalog || []).length, 1)
  const rows = [
    ['catalog', t('catalogCollected'), funnel.catalog || []],
    ['installed', t('installed'), funnel.installed || []],
    ['used_30d', t('used30'), funnel.used_30d || []],
    ['idle', t('idleSkills'), funnel.idle || []],
  ] as const
  return (
    <div className="funnel">
      {data?.catalog?.stale ? <div className="note-warn">{t('catalogStale')}</div> : null}
      <div className="hint" style={{ margin: '0 0 2px' }}>
        {t('installedSnapshot')}
      </div>
      {rows.map(([key, label, list]) => {
        const pct = max ? Math.max(2, Math.round((list.length / max) * 100)) : 0
        return (
          <details key={key}>
            <summary className="funnel-row">
              <div className="funnel-name">{label}</div>
              <div className="funnel-track">
                <div className="funnel-fill" style={{ width: `${pct}%` }} />
              </div>
              <div className="funnel-num">{list.length}</div>
            </summary>
            <div className="funnel-list">
              {list.length ? list.map((item) => <span className="tag" key={item.name}>{item.name}</span>) : <span className="hint">{t('none')}</span>}
            </div>
          </details>
        )
      })}
    </div>
  )
}

export function SkillsView({ data, loading, error, t }: { data: SkillsOverview | null; loading: boolean; error: string; t: (key: string) => string }) {
  const [params, setParams] = useSkillQueryState()
  const days = [7, 30, 90].includes(params.win) ? params.win : 30
  const view = params.view === 'operator' ? 'operator' : 'skill'
  const lens = params.lens === 'untracked' ? 'untracked' : 'all'
  const filteredSkillDaily = (data?.daily || []).filter((row) => skillPass({ skill: row.skill, runtime: row.runtime, source: row.source }, params.q, params.rt, params.src))
  const filteredOperatorDaily = (data?.operator_daily || []).filter((row) => operatorPass({ operator: row.operator, runtime: row.runtime, source: row.source }, params.q, params.rt, params.src))
  const skillRows = sortedRows((data?.table || []).filter((row) => skillPass(row, params.q, params.rt, params.src)), params.sort, params.dir) as SkillTableRow[]
  const governanceRows = (data?.governance?.untracked_usage?.top || []).filter((row) => skillPass(row, params.q, params.rt, params.src))
  const operatorRows = sortedRows((data?.operator_table || []).filter((row) => operatorPass(row, params.q, params.rt, params.src)), params.sort, params.dir) as OperatorTableRow[]
  const chartRows = view === 'operator' ? filteredOperatorDaily : filteredSkillDaily
  const rankCount = view === 'operator' ? operatorRows.length : lens === 'untracked' ? governanceRows.length : skillRows.length

  if (loading && !data) {
    return (
      <div className="skills-page">
        <ViewSwitch view={view} setParams={setParams} t={t} />
        <section className="frame">
          <Empty title={t('loading')} />
        </section>
      </div>
    )
  }

  return (
    <div className="skills-page">
      <ViewSwitch view={view} setParams={setParams} t={t} />
      <section className="frame">
        <h2>
          <span>
            <span className="sl">//</span>
            {t('skillsStats')}
          </span>
          <span className="cnt">{loading ? t('loading') : error ? t(error) : ''}</span>
        </h2>
        <FilterBar data={data} t={t} params={params} setParams={setParams} view={view} />
      </section>
      <section className="frame" style={{ marginTop: 16 }}>
        <h2>
          <span>
            <span className="sl">//</span>
            {view === 'operator' ? t('dailyByOperator') : t('dailyUsed')}
          </span>
          <span className="cnt">{days}d</span>
        </h2>
        <StackedSkillChart rows={chartRows} overview={data} days={days} t={t} segmentKey={view === 'operator' ? 'operator' : 'skill'} emptyTitle={view === 'operator' ? t('noOperators') : undefined} emptyHint={view === 'operator' ? t('noOperatorsH') : undefined} />
      </section>
      <div className="split" style={{ marginTop: 16 }}>
        <section className="frame">
          <SectionTitle title={view === 'operator' ? t('operatorRank') : t('mainRank')} count={rankCount} />
          {view === 'operator' ? (
            <>
              <div className="usage-note">{t('operatorMetricNote')}</div>
              <OperatorTable rows={operatorRows} params={params} setParams={setParams} t={t} />
            </>
          ) : (
            <>
              <GovernanceLens data={data} lens={lens} setParams={setParams} t={t} />
              {lens === 'untracked' ? <GovernanceSkillTable rows={governanceRows} t={t} /> : <SkillsTable rows={skillRows} params={params} setParams={setParams} t={t} />}
            </>
          )}
        </section>
        <section className="frame">
          <SectionTitle title={t('companyFunnel')} />
          <Funnel data={data} t={t} />
        </section>
      </div>
    </div>
  )
}

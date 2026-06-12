import { Link, useLocation } from 'react-router-dom'
import { RuntimeBars, MiniTrend, StackedSkillChart } from '../components/Charts'
import { Empty, SectionTitle } from '../components/Common'
import type { SetSkillQueryState, SkillQueryState } from '../lib/skillQuery'
import { useSkillQueryState } from '../lib/skillQuery'
import type { SkillsOverview, SkillTableRow } from '../lib/types'
import { encodePathParam, RT, sourceKey, sourceLabel } from '../lib/utils'

type SortKey = keyof SkillTableRow | 'source'

type FilterableSkill = { name?: string; skill?: string; runtime?: string; source?: string; runtime_counts?: Record<string, number> }

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

function sortedRows(rows: SkillTableRow[], sort: string, dir: string) {
  const direction = dir === 'asc' ? 1 : -1
  const key = sort as SortKey
  return rows.slice().sort((a, b) => {
    const av = a[key as keyof SkillTableRow] ?? ''
    const bv = b[key as keyof SkillTableRow] ?? ''
    if (typeof av === 'number' || typeof bv === 'number') return (Number(av || 0) - Number(bv || 0)) * direction
    return String(av).localeCompare(String(bv)) * direction
  })
}

function FilterBar({ data, t, params, setParams }: { data: SkillsOverview | null; t: (key: string) => string; params: SkillQueryState; setParams: SetSkillQueryState }) {
  const runtimes = new Set<string>()
  data?.daily?.forEach((row) => row.runtime && runtimes.add(row.runtime))
  data?.table?.forEach((row) => Object.keys(row.runtime_counts || {}).forEach((runtime) => runtimes.add(runtime)))
  const update = (patch: Partial<typeof params>) => void setParams(patch)
  return (
    <div className="toolbar">
      <label className="field">
        <span>{t('skillSearch')}</span>
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

function SkillsTable({ rows, params, setParams, t }: { rows: SkillTableRow[]; params: SkillQueryState; setParams: SetSkillQueryState; t: (key: string) => string }) {
  const location = useLocation()
  const updateSort = (key: string) => {
    const dir = params.sort === key && params.dir !== 'asc' ? 'asc' : 'desc'
    void setParams({ sort: key, dir })
  }
  const head = (key: string, label: string, cls = '') => (
    <th className={`sort ${cls}`} onClick={() => updateSort(key)}>
      {label}
      {params.sort === key ? (params.dir === 'asc' ? ' ↑' : ' ↓') : ''}
    </th>
  )
  if (!rows.length) return <Empty title={t('noSkills')} hint={t('noSkillsH')} />
  return (
    <div className="skills-wrap">
      <table className="skill-table">
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
            <tr key={row.name}>
              <td>
                <Link to={`/skill/${encodePathParam(row.name)}${location.search}`}>
                  <b>{row.name}</b>
                </Link>
              </td>
              <td>
                <span className="source-pill">{sourceLabel(row.source, t)}</span>
              </td>
              <td className="num">{row.sessions_7d}</td>
              <td className="num">{row.sessions_30d}</td>
              <td className="num">{row.sessions_total}</td>
              <td className="num">{row.users_30d}</td>
              <td>
                <RuntimeBars counts={row.runtime_counts} />
              </td>
              <td>
                <MiniTrend values={row.trend_14d} />
              </td>
              <td className="q">{row.last_day || '—'}</td>
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
  const filteredDaily = (data?.daily || []).filter((row) => skillPass({ skill: row.skill, runtime: row.runtime, source: row.source }, params.q, params.rt, params.src))
  const rows = sortedRows((data?.table || []).filter((row) => skillPass(row, params.q, params.rt, params.src)), params.sort, params.dir)

  if (loading && !data) {
    return (
      <section className="frame">
        <Empty title={t('loading')} />
      </section>
    )
  }

  return (
    <>
      <section className="frame">
        <h2>
          <span>
            <span className="sl">//</span>
            {t('skillsStats')}
          </span>
          <span className="cnt">{loading ? t('loading') : error ? t(error) : ''}</span>
        </h2>
        <FilterBar data={data} t={t} params={params} setParams={setParams} />
      </section>
      <section className="frame" style={{ marginTop: 16 }}>
        <h2>
          <span>
            <span className="sl">//</span>
            {t('dailyUsed')}
          </span>
          <span className="cnt">{days}d</span>
        </h2>
        <StackedSkillChart rows={filteredDaily} overview={data} days={days} t={t} />
      </section>
      <div className="split" style={{ marginTop: 16 }}>
        <section className="frame">
          <SectionTitle title={t('mainRank')} count={rows.length} />
          <SkillsTable rows={rows} params={params} setParams={setParams} t={t} />
        </section>
        <section className="frame">
          <SectionTitle title={t('companyFunnel')} />
          <Funnel data={data} t={t} />
        </section>
      </div>
    </>
  )
}

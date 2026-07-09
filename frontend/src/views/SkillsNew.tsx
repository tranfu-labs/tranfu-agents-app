import type { KeyboardEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Empty, SectionTitle } from '../components/Common'
import { useSkillQueryState } from '../lib/skillQuery'
import { canonicalSkillsSearch } from '../lib/skillsEvidence'
import { formatRecentRecordTime } from '../lib/timeFormat'
import type { Lang, PublishedSkill, SkillsOverview } from '../lib/types'
import { encodePathParam, sourceLabel } from '../lib/utils'
import { windowDisplayLabel, windowPeriodLabel } from '../lib/skillsPresentation'

const WINDOW_OPTIONS = ['today', 'this_week', 'last_week', '7d', '14d', '30d', '90d', 'custom'] as const

function n(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(Math.round(Number(value || 0)))
}

function unixToInput(value: string) {
  const ts = Number(value)
  if (!Number.isFinite(ts) || ts <= 0) return ''
  const date = new Date(ts * 1000)
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function inputToUnix(value: string) {
  const ts = new Date(value).getTime()
  return Number.isFinite(ts) ? String(Math.floor(ts / 1000)) : ''
}

function rowKey(event: KeyboardEvent<HTMLTableRowElement>, action: () => void) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  action()
}

function filterRows(rows: PublishedSkill[], q: string, source: string) {
  const needle = q.trim().toLowerCase()
  return rows.filter((row) => {
    if (needle && !row.name.toLowerCase().includes(needle)) return false
    if (source && row.source !== source) return false
    return true
  })
}

export function SkillsNewView({ data, loading, error, lang, t }: { data: SkillsOverview | null; loading: boolean; error: string; lang: Lang; t: (key: string) => string }) {
  const [params, setParams] = useSkillQueryState()
  const location = useLocation()
  const navigate = useNavigate()
  const currentWindow = params.w || `${params.win || 7}d`
  const source = params.src === 'own' || params.src === 'meta' ? params.src : ''
  const rows = filterRows(data?.published_skills || [], params.q, source)
  const backSearch = new URLSearchParams(canonicalSkillsSearch(location.search).slice(1))
  backSearch.delete('src')
  const back = `/skills${backSearch.toString() ? `?${backSearch.toString()}` : ''}`
  const update = (patch: Partial<typeof params>) => void setParams(patch)
  const openSkill = (row: PublishedSkill) => {
    if (!row.last_day) return
    navigate(`/skill/${encodePathParam(row.name)}${canonicalSkillsSearch(location.search)}`)
  }
  return (
    <div className={`skills-page skills-dashboard skills-new-page ${loading ? 'is-refreshing' : ''}`}>
      <section className="frame evidence-hero skills-new-hero">
        <div className="pad">
          <Link className="token-link-btn" to={back}>← {t('skillsNav')}</Link>
          <div>
            <h1>{t('publishedSkillsTitle')}</h1>
            <p>{windowPeriodLabel(data?.window?.key || currentWindow, t)} · {data?.window?.start || '—'} .. {data?.window?.end || '—'} · {t('publishedSkillsSubtitle')}</p>
          </div>
          <div className="evidence-summary-line">
            <span>{n(rows.length)} {t('publishedCount')}</span>
            {data?.catalog?.stale ? <span className="note-warn">{t('catalogStale')}</span> : null}
            {data?.catalog?.available === false ? <span className="note-warn">{t('catalogUnavailable')}</span> : null}
          </div>
        </div>
      </section>

      <section className="frame skills-toolbar-frame skills-new-toolbar">
        <h2><span><span className="sl">//</span>{t('skillsControls')}</span><span className="cnt">{loading ? t('loading') : error ? t(error) : `${rows.length}`}</span></h2>
        <div className="toolbar skills-dashboard-toolbar mobile-open">
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
          <label className="field search-field">
            <span>{t('skillSearch')}</span>
            <input value={params.q} onChange={(event) => update({ q: event.target.value })} />
          </label>
          <label className="field">
            <span>{t('sourceFilter')}</span>
            <select value={source} onChange={(event) => update({ src: event.target.value })}>
              <option value="">{t('all')}</option>
              <option value="own">{sourceLabel('own', t)}</option>
              <option value="meta">{sourceLabel('meta', t)}</option>
            </select>
          </label>
        </div>
      </section>

      {error ? <div className="note-warn">{t(error)}</div> : null}
      {loading && !data ? <section className="frame"><Empty title={t('loading')} /></section> : null}

      <section className="frame evidence-primary">
        <SectionTitle title={t('publishedSkillsTitle')} count={rows.length} />
        {rows.length ? (
          <div className="skills-wrap">
            <table className="skill-table mobile-card-table published-skills-table">
              <thead>
                <tr>
                  <th>{t('skillName')}</th>
                  <th>{t('sourceFilter')}</th>
                  <th>{t('cfg_ver')}</th>
                  <th>{t('publishedAt')}</th>
                  <th>{t('updatedAt')}</th>
                  <th>{t('author')}</th>
                  <th className="num">{t('installs')}</th>
                  <th className="num">{t('windowUsage')}</th>
                  <th>{t('lastUsed')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const published = formatRecentRecordTime(row.published_at, row.published_day || '', lang, undefined, data?.today)
                  const canOpen = Boolean(row.last_day)
                  return (
                    <tr
                      className={canOpen ? 'clickable' : 'not-clickable'}
                      key={row.name}
                      role={canOpen ? 'link' : undefined}
                      tabIndex={canOpen ? 0 : undefined}
                      onClick={canOpen ? () => openSkill(row) : undefined}
                      onKeyDown={canOpen ? (event) => rowKey(event, () => openSkill(row)) : undefined}
                    >
                      <td className="mobile-main" data-label={t('skillName')}><b>{row.name}</b></td>
                      <td data-label={t('sourceFilter')}><span className="source-pill">{sourceLabel(row.source, t)}</span></td>
                      <td data-label={t('cfg_ver')}>{row.version || '—'}</td>
                      <td data-label={t('publishedAt')} title={published.title}>{published.label}</td>
                      <td data-label={t('updatedAt')}>{row.updated_at || '—'}</td>
                      <td data-label={t('author')}>{row.author || '—'}</td>
                      <td className="num" data-label={t('installs')}>{row.installers || 0}</td>
                      <td className="num" data-label={t('windowUsage')}>{row.window_sessions || 0}</td>
                      <td data-label={t('lastUsed')}>{row.last_day || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : <Empty title={t('publishedSkillsEmpty')} hint={t('publishedSkillsEmptyHint')} />}
      </section>
    </div>
  )
}

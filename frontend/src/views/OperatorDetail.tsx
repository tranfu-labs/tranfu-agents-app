import type { KeyboardEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Distribution, RuntimeBars, StackedSkillChart } from '../components/Charts'
import { Empty } from '../components/Common'
import { formatRecentRecordTime } from '../lib/timeFormat'
import type { Lang, OperatorDetail } from '../lib/types'
import { encodePathParam, RT, sourceLabel } from '../lib/utils'

function operatorBack(search: string) {
  const params = new URLSearchParams(search)
  params.set('view', 'operator')
  const next = params.toString()
  return `/skills${next ? `?${next}` : ''}`
}

function rowKey(event: KeyboardEvent<HTMLTableRowElement>, go: () => void) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  go()
}

export function OperatorDetailView({ data, loading, error, lang, t }: { data: OperatorDetail | null; loading: boolean; error: string; lang: Lang; t: (key: string) => string }) {
  const params = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const back = operatorBack(location.search)
  const backQuery = back.includes('?') ? back.slice(back.indexOf('?')) : ''
  if (loading && !data) {
    return (
      <>
        <Link className="back" to={back}>
          ← {t('skillsNav')}
        </Link>
        <section className="frame">
          <Empty title={t('loading')} />
        </section>
      </>
    )
  }
  if (!data) {
    return (
      <>
        <Link className="back" to={back}>
          ← {t('skillsNav')}
        </Link>
        <section className="frame">
          <Empty title={error ? t(error) : t('operatorNotFound')} hint={params.name ? decodeURIComponent(params.name) : ''} />
        </section>
      </>
    )
  }

  const metrics = data.metrics || {}
  const stats: Array<[string, string | number | undefined]> = [
    ['skill7', metrics.sessions_7d],
    ['skill30', metrics.sessions_30d],
    ['skillTotal', metrics.sessions_total],
    ['skillsUsed', metrics.skill_count],
    ['sessionCount', metrics.session_count],
    ['first', metrics.first_day || '—'],
    ['skillLast', metrics.last_day || '—'],
  ]
  const skillRows = (data.skills || []).slice().sort((a, b) => {
    const recent = Number(b.sessions_7d || 0) - Number(a.sessions_7d || 0)
    if (recent) return recent
    const total = Number(b.sessions_total || 0) - Number(a.sessions_total || 0)
    if (total) return total
    return String(a.name || '').localeCompare(String(b.name || ''))
  })
  const openSkill = (name: string) => navigate(`/skill/${encodePathParam(name)}${backQuery}`)

  return (
    <>
      <Link className="back" to={back}>
        ← {t('skillsNav')}
      </Link>
      <div className="dhead">
        <span className="alabel">
          {t('operatorName')}: {data.operator}
        </span>
      </div>
      <div className="statgrid operator-stats">
        {stats.map(([key, value]) => (
          <div className="stat" key={key}>
            <div className="v">{String(value ?? '—')}</div>
            <div className="l">{t(key)}</div>
          </div>
        ))}
      </div>
      <div className="note-warn">{t('operatorMetricNote')}</div>
      <section className="frame">
        <h2>
          <span>
            <span className="sl">//</span>
            {t('dailyBySkill')}
          </span>
        </h2>
        <StackedSkillChart rows={data.daily || []} days={30} t={t} today={data.today} segmentKey="skill" emptyTitle={t('noSkills')} emptyHint={t('noSkillsH')} />
      </section>
      <div className="dist-mirror" style={{ marginTop: 16 }}>
        <section className="frame">
          <h2>
            <span>
              <span className="sl">//</span>
              {t('runtimeDist')}
            </span>
          </h2>
          <div className="pad">
            <Distribution items={data.runtime} labelKey="runtime" />
          </div>
        </section>
        <section className="frame">
          <h2>
            <span>
              <span className="sl">//</span>
              {t('skillRank')}
            </span>
          </h2>
          <div className="skills-wrap">
            <table className="skill-table">
              <thead>
                <tr>
                  <th>{t('skillName')}</th>
                  <th>{t('sourceFilter')}</th>
                  <th className="num">{t('skill7')}</th>
                  <th className="num">{t('skill30')}</th>
                  <th className="num">{t('skillTotal')}</th>
                  <th>{t('runtimeFilter')}</th>
                  <th>{t('skillLast')}</th>
                </tr>
              </thead>
              <tbody>
                {skillRows.map((row) => (
                  <tr key={row.name} role="link" tabIndex={0} onClick={() => openSkill(row.name)} onKeyDown={(event) => rowKey(event, () => openSkill(row.name))}>
                    <td>
                      <b>{row.name}</b>
                    </td>
                    <td>
                      <span className="source-pill">{sourceLabel(row.source, t)}</span>
                    </td>
                    <td className="num">{row.sessions_7d || 0}</td>
                    <td className="num">{row.sessions_30d || 0}</td>
                    <td className="num">{row.sessions_total || 0}</td>
                    <td>
                      <RuntimeBars counts={row.runtime_counts} />
                    </td>
                    <td className="q">{row.last_day || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      <section className="frame" style={{ marginTop: 16 }}>
        <h2>
          <span>
            <span className="sl">//</span>
            {t('recentRecords')}
          </span>
        </h2>
        <table className="records-table">
          <thead>
            <tr>
              <th>{t('skillLast')}</th>
              <th>{t('skillName')}</th>
              <th>{t('th_rt')}</th>
              <th>{t('session')}</th>
            </tr>
          </thead>
          <tbody>
            {(data.records || []).map((record) => {
              const time = formatRecentRecordTime(record.first_seen, record.day || '', lang)
              return (
                <tr key={`${record.session_id}-${record.skill}-${record.day}`}>
                  <td className="q" title={time.title}>{time.label}</td>
                  <td>{record.skill || ''}</td>
                  <td>{RT[record.runtime || ''] || record.runtime || ''}</td>
                  <td className="q">{(record.session_id || '').slice(0, 12)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </>
  )
}

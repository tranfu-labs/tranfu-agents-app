import { Link, useLocation, useParams } from 'react-router-dom'
import { DetailTrend, Distribution } from '../components/Charts'
import { Empty } from '../components/Common'
import { formatRecentRecordTime } from '../lib/timeFormat'
import type { Lang, SkillDetail as SkillDetailPayload } from '../lib/types'
import { RT, sourceLabel } from '../lib/utils'
import { skillDisplayName } from '../lib/skillNames'

export function SkillDetailView({ data, loading, error, lang, t }: { data: SkillDetailPayload | null; loading: boolean; error: string; lang: Lang; t: (key: string) => string }) {
  const params = useParams()
  const location = useLocation()
  const back = `/skills${location.search}`
  if (loading && !data) {
    return (
      <div className="skill-detail-page">
        <Link className="back" to={back}>
          ← {t('skillsNav')}
        </Link>
        <section className="frame">
          <Empty title={t('loading')} />
        </section>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="skill-detail-page">
        <Link className="back" to={back}>
          ← {t('skillsNav')}
        </Link>
        <section className="frame">
          <Empty title={error ? t(error) : t('skillNotFound')} hint={params.name ? decodeURIComponent(params.name) : ''} />
        </section>
      </div>
    )
  }

  const metrics = data.metrics || {}
  const stats: Array<[string, string | number | undefined]> = [
    ['skill7', metrics.sessions_7d],
    ['skill30', metrics.sessions_30d],
    ['skillTotal', metrics.sessions_total],
    ['skillUsers30', metrics.users_30d],
    ['first', metrics.first_day || '—'],
    ['skillLast', metrics.last_day || '—'],
  ]
  return (
    <div className="skill-detail-page">
      <Link className="back" to={back}>
        ← {t('skillsNav')}
      </Link>
      <div className="dhead">
        <span className="alabel">{skillDisplayName(data, lang, data.skill_names)}</span>
        <span className="source-pill">{sourceLabel(data.source, t)}</span>
      </div>
      <div className="statgrid">
        {stats.map(([key, value]) => (
          <div className="stat" key={key}>
            <div className="v">{String(value ?? '—')}</div>
            <div className="l">{t(key)}</div>
          </div>
        ))}
      </div>
      {metrics.equipped_total ? (
        <div className="note-warn">
          {t('equippedSessions')}: <b className="mono">{metrics.equipped_total}</b> · {t('equippedNote')}
        </div>
      ) : null}
      <section className="frame">
        <h2>
          <span>
            <span className="sl">//</span>
            {t('trend')}
          </span>
        </h2>
        <DetailTrend detail={data} t={t} />
      </section>
      <div className="dist" style={{ marginTop: 16 }}>
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
              {t('operatorDist')}
            </span>
          </h2>
          <div className="pad">
            <Distribution items={data.operators} labelKey="operator" />
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
        <table className="records-table mobile-card-table">
          <thead>
            <tr>
              <th>{t('skillLast')}</th>
              <th>{t('th_disp')}</th>
              <th>{t('th_rt')}</th>
              <th>{t('mode')}</th>
              <th>{t('session')}</th>
            </tr>
          </thead>
          <tbody>
            {(data.records || []).map((record) => {
              const time = formatRecentRecordTime(record.first_seen, record.day || '', lang, undefined, data.today)
              return (
                <tr key={`${record.session_id}-${record.mode}-${record.day}`}>
                  <td className="q mobile-main" data-label={t('skillLast')} title={time.title}>{time.label}</td>
                  <td data-label={t('th_disp')}>{record.operator || ''}</td>
                  <td data-label={t('th_rt')}>{RT[record.runtime || ''] || record.runtime || ''}</td>
                  <td data-label={t('mode')}>
                    <span className="source-pill">{record.mode || 'used'}</span>
                  </td>
                  <td className="q" data-label={t('session')}>{(record.session_id || '').slice(0, 12)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </div>
  )
}

import { Link, useLocation, useParams } from 'react-router-dom'
import { DetailTrend, Distribution } from '../components/Charts'
import { Empty } from '../components/Common'
import type { SkillDetail as SkillDetailPayload } from '../lib/types'
import { fmtTs, RT, sourceLabel } from '../lib/utils'

export function SkillDetailView({ data, loading, error, t }: { data: SkillDetailPayload | null; loading: boolean; error: string; t: (key: string) => string }) {
  const params = useParams()
  const location = useLocation()
  const back = `/skills${location.search}`
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
          <Empty title={error ? t(error) : t('skillNotFound')} hint={params.name ? decodeURIComponent(params.name) : ''} />
        </section>
      </>
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
    <>
      <Link className="back" to={back}>
        ← {t('skillsNav')}
      </Link>
      <div className="dhead">
        <span className="alabel">{data.name}</span>
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
        <table className="records-table">
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
            {(data.records || []).map((record) => (
              <tr key={`${record.session_id}-${record.mode}-${record.day}`}>
                <td className="q">{fmtTs(record.first_seen) || record.day || ''}</td>
                <td>{record.operator || ''}</td>
                <td>{RT[record.runtime || ''] || record.runtime || ''}</td>
                <td>
                  <span className="source-pill">{record.mode || 'used'}</span>
                </td>
                <td className="q">{(record.session_id || '').slice(0, 12)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  )
}

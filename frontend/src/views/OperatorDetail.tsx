import type { KeyboardEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Distribution, RuntimeBars, StackedSkillChart } from '../components/Charts'
import { Empty, SectionTitle } from '../components/Common'
import { OperatorCompactRank, OperatorSkillDonut } from '../components/skills/OperatorSkillAnalysis'
import { buildOperatorSkillAnalysis, operatorCompositionLabel } from '../lib/operatorDetailAnalysis'
import { isOperatorDetailActivationKey, operatorDetailBackHref } from '../lib/operatorDetailQuery'
import { skillDisplayName } from '../lib/skillNames'
import { windowPeriodLabel } from '../lib/skillsPresentation'
import { formatRecentRecordTime } from '../lib/timeFormat'
import type { Lang, OperatorDetail } from '../lib/types'
import { encodePathParam, RT, sourceLabel } from '../lib/utils'

function rowKey(event: KeyboardEvent<HTMLTableRowElement>, go: () => void) {
  if (!isOperatorDetailActivationKey(event.key)) return
  event.preventDefault()
  go()
}

function percent(value: number | undefined) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

export function OperatorDetailView({
  data,
  loading,
  error,
  lang,
  t,
}: {
  data: OperatorDetail | null
  loading: boolean
  error: string
  lang: Lang
  t: (key: string) => string
}) {
  const params = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const back = operatorDetailBackHref(location.search)
  if (loading && !data) {
    return (
      <div className="operator-detail-page">
        <Link className="back" to={back}>← {t('viewOperator')}</Link>
        <section className="frame operator-loading">
          <Empty title={t('loading')} hint={t('operatorLoadingHint')} />
        </section>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="operator-detail-page">
        <Link className="back" to={back}>← {t('viewOperator')}</Link>
        <section className="frame">
          <Empty title={error ? t(error) : t('operatorNotFound')} hint={params.name ? decodeURIComponent(params.name) : ''} />
        </section>
      </div>
    )
  }

  const analysis = data.analysis || {}
  const metrics = analysis.metrics || {}
  const model = buildOperatorSkillAnalysis(data)
  const windowKey = data.window?.key || '7d'
  const windowDays = Math.max(1, Number(data.window?.days || 7))
  const windowLabel = windowPeriodLabel(windowKey, t)
  const compositionLabel = operatorCompositionLabel(windowLabel, t)
  const runtimeFilter = data.applied_filters?.rt || ''
  const sourceFilter = data.applied_filters?.src || ''
  const filterSummary = [
    windowLabel,
    runtimeFilter ? (RT[runtimeFilter] || runtimeFilter) : '',
    sourceFilter ? sourceLabel(sourceFilter, t) : '',
  ].filter(Boolean).join(' · ')
  const backQuery = back.includes('?') ? back.slice(back.indexOf('?')) : ''
  const openSkill = (name: string) => navigate(`/skill/${encodePathParam(name)}${backQuery}`)
  const stats: Array<[string, string | number | undefined]> = [
    ['operatorWindowRecords', metrics.sessions_window || 0],
    ['skillsUsed', metrics.skill_count || 0],
    ['sessionCount', metrics.session_count || 0],
    ['operatorRuntimeCount', metrics.runtime_count || 0],
  ]

  return (
    <div className={`operator-detail-page ${loading ? 'is-refreshing' : ''}`}>
      <Link className="back" to={back}>← {t('viewOperator')}</Link>
      <section className="frame operator-hero">
        <div className="operator-hero-main">
          <span className="operator-eyebrow">{t('operatorDetailTitle')}</span>
          <h1>{data.operator} · {windowLabel}</h1>
          {runtimeFilter || sourceFilter ? (
            <div className="operator-filter-chips">
              {runtimeFilter ? <span>{RT[runtimeFilter] || runtimeFilter}</span> : null}
              {sourceFilter ? <span>{sourceLabel(sourceFilter, t)}</span> : null}
            </div>
          ) : null}
        </div>
      </section>

      <section className="frame operator-summary">
        <SectionTitle title={t('currentWindowSummary')} count={windowLabel} />
        <div className="statgrid operator-stats">
          {stats.map(([key, value]) => (
            <div className="stat" key={key}>
              <div className="v">{String(value ?? 0)}</div>
              <div className="l">{t(key)}</div>
            </div>
          ))}
        </div>
        <div className="operator-comparison">
          {t('previousWindow')}: <b>{Number(metrics.previous_sessions || 0)}</b>
        </div>
      </section>

      <div className="note-warn">{t('operatorMetricNote')}</div>

      {model.mode === 'empty' ? (
        <section className="frame operator-range-empty">
          <Empty title={t('operatorRangeEmpty')} hint={filterSummary} />
        </section>
      ) : (
        <div className={`operator-analysis operator-analysis--${model.mode}`}>
          <section className="frame operator-chart-panel">
            <SectionTitle
              title={model.mode === 'donut' ? compositionLabel : `${t('dailyBySkill')} · ${windowLabel}`}
              count={`Top ${model.limit} + ${t('other')}`}
            />
            {model.mode === 'donut' ? (
              <OperatorSkillDonut model={model} lang={lang} names={data.skill_names} windowLabel={windowLabel} t={t} />
            ) : (
              <StackedSkillChart
                rows={analysis.daily || []}
                days={windowDays}
                t={t}
                lang={lang}
                skillNames={data.skill_names}
                today={data.window?.end || data.today}
                currentDay={data.window?.end === data.today ? data.today : '__not-current__'}
                segmentKey="skill"
                topN={8}
                ariaLabel={`${t('dailyBySkill')} · ${windowLabel}`}
                emptyTitle={t('operatorRangeEmpty')}
                emptyHint={filterSummary}
              />
            )}
          </section>
          <section className="frame operator-rank-panel">
            <SectionTitle title={`${t('skillRank')} · Top ${model.limit}`} count={model.all.length} />
            <OperatorCompactRank model={model} lang={lang} names={data.skill_names} openSkill={openSkill} t={t} />
          </section>
        </div>
      )}

      <section className="frame operator-runtime">
        <SectionTitle title={t('runtimeDist')} count={analysis.runtime?.length || 0} />
        <div className="pad">
          {analysis.runtime?.length ? <Distribution items={analysis.runtime} labelKey="runtime" /> : <Empty title={t('operatorRangeEmpty')} hint={filterSummary} />}
        </div>
      </section>

      <section className="frame operator-full-list">
        <SectionTitle title={t('completeSkillList')} count={model.all.length} />
        {model.all.length ? (
          <div className="skills-wrap">
            <table className="skill-table mobile-card-table">
              <thead>
                <tr>
                  <th>{t('skillName')}</th>
                  <th>{t('sourceFilter')}</th>
                  <th className="num">{windowLabel}</th>
                  <th className="num">{t('previousWindow')}</th>
                  <th className="num">{t('usageShare')}</th>
                  <th className="num">{t('sessionCount')}</th>
                  <th>{t('runtimeFilter')}</th>
                  <th>{t('skillLast')}</th>
                </tr>
              </thead>
              <tbody>
                {model.all.map((row) => (
                  <tr key={row.name} role="link" tabIndex={0} onClick={() => openSkill(row.name)} onKeyDown={(event) => rowKey(event, () => openSkill(row.name))}>
                    <td className="mobile-main" data-label={t('skillName')}><b>{skillDisplayName(row, lang, data.skill_names)}</b></td>
                    <td data-label={t('sourceFilter')}><span className="source-pill">{sourceLabel(row.source, t)}</span></td>
                    <td className="num" data-label={windowLabel}>{Number(row.sessions_window || 0)}</td>
                    <td className="num" data-label={t('previousWindow')}>{Number(row.previous_sessions || 0)}</td>
                    <td className="num" data-label={t('usageShare')}>{percent(row.share)}</td>
                    <td className="num" data-label={t('sessionCount')}>{Number(row.session_count || 0)}</td>
                    <td data-label={t('runtimeFilter')}><RuntimeBars counts={row.runtime_counts} /></td>
                    <td className="q" data-label={t('skillLast')}>{row.last_day || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty title={t('operatorRangeEmpty')} hint={filterSummary} />}
      </section>

      <section className="frame operator-records">
        <SectionTitle title={t('recentRecords')} count={analysis.records?.length || 0} />
        {analysis.records?.length ? (
          <table className="records-table mobile-card-table">
            <thead>
              <tr>
                <th>{t('skillLast')}</th>
                <th>{t('skillName')}</th>
                <th>{t('th_rt')}</th>
                <th>{t('session')}</th>
              </tr>
            </thead>
            <tbody>
              {analysis.records.map((record) => {
                const time = formatRecentRecordTime(record.first_seen, record.day || '', lang, undefined, data.today)
                return (
                  <tr key={`${record.session_id}-${record.skill}-${record.day}`}>
                    <td className="q mobile-main" data-label={t('skillLast')} title={time.title}>{time.label}</td>
                    <td data-label={t('skillName')}>{skillDisplayName(record, lang, data.skill_names)}</td>
                    <td data-label={t('th_rt')}>{RT[record.runtime || ''] || record.runtime || ''}</td>
                    <td className="q" data-label={t('session')}>{(record.session_id || '').slice(0, 12)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : <Empty title={t('noRecords')} hint={filterSummary} />}
      </section>
    </div>
  )
}

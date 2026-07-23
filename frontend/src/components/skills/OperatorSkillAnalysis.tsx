import { buildDonutSegments, donutArcPath } from '../../lib/skillsAttribution.ts'
import { operatorCompositionLabel, type OperatorSkillAnalysisModel } from '../../lib/operatorDetailAnalysis.ts'
import type { Lang, SkillNamesMap } from '../../lib/types'
import { skillDisplayName } from '../../lib/skillNames.ts'
import { skillColor, sourceLabel } from '../../lib/utils.ts'

function percent(value: number | undefined) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

export function OperatorSkillDonut({
  model,
  lang,
  names,
  windowLabel,
  t,
}: {
  model: OperatorSkillAnalysisModel
  lang: Lang
  names?: SkillNamesMap
  windowLabel: string
  t: (key: string) => string
}) {
  const items = [
    ...model.top.map((row) => ({ key: row.name, value: Number(row.sessions_window || 0) })),
    ...(model.other ? [{ key: '__other', value: model.other.sessions }] : []),
  ]
  const segments = buildDonutSegments(items)
  const labels = new Map(model.top.map((row) => [row.name, skillDisplayName(row, lang, names)]))
  const ariaLabel = operatorCompositionLabel(windowLabel, t)
  return (
    <div className="operator-donut">
      <svg viewBox="0 0 100 100" role="img" aria-label={ariaLabel}>
        <circle cx="50" cy="50" r="42" fill="none" stroke="var(--line)" strokeWidth="16" />
        {segments.map((segment) => (
          <path
            key={segment.key}
            d={donutArcPath(segment, 30, 46)}
            fill={skillColor(segment.key)}
          >
            <title>{`${segment.key === '__other' ? t('other') : labels.get(segment.key)}: ${segment.value}`}</title>
          </path>
        ))}
        <text x="50" y="49" textAnchor="middle" className="operator-donut-total">{model.total}</text>
        <text x="50" y="60" textAnchor="middle" className="operator-donut-label">{t('records')}</text>
      </svg>
      <div className="operator-donut-legend">
        {model.top.map((row) => (
          <span key={row.name}>
            <i style={{ background: skillColor(row.name) }} />
            <b>{skillDisplayName(row, lang, names)}</b>
            <em>{percent(row.share)}</em>
          </span>
        ))}
        {model.other ? (
          <span>
            <i style={{ background: skillColor('__other') }} />
            <b>{t('other')}</b>
            <em>{percent(model.other.share)}</em>
          </span>
        ) : null}
      </div>
    </div>
  )
}

export function OperatorCompactRank({
  model,
  lang,
  names,
  openSkill,
  t,
}: {
  model: OperatorSkillAnalysisModel
  lang: Lang
  names?: SkillNamesMap
  openSkill: (name: string) => void
  t: (key: string) => string
}) {
  return (
    <div className="operator-compact-rank">
      {model.top.map((row, index) => (
        <button type="button" key={row.name} onClick={() => openSkill(row.name)}>
          <span className="operator-rank-index">{index + 1}</span>
          <span className="operator-rank-main">
            <b>{skillDisplayName(row, lang, names)}</b>
            <small>
              <span className="source-pill">{sourceLabel(row.source, t)}</span>
              {Number(row.sessions_window || 0)} {t('records')} · {Number(row.session_count || 0)} {t('sessionsUnit')} · {percent(row.share)}
            </small>
          </span>
          <span aria-hidden="true">→</span>
        </button>
      ))}
      {model.other ? (
        <div className="operator-rank-other">
          <span>{t('other')} {model.other.count} {t('skillsUnit')}</span>
          <b>{model.other.sessions} {t('records')}</b>
        </div>
      ) : null}
    </div>
  )
}

import { Link, useLocation } from 'react-router-dom'
import type { SkillsEvidenceKind, SkillsOverview } from '../../lib/types'
import { classifySkillHealth, type HealthMetric } from '../../lib/skillsThresholds'
import { evidencePath } from '../../lib/skillsEvidence'
import { compactNameList } from '../../lib/skillsPresentation'

function pct(value?: number) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

function stateBy(value: number, good: number, warn: number) {
  if (value >= good) return 'good'
  if (value >= warn) return 'warn'
  return 'bad'
}

function OperatorHealth({ data, t }: { data: SkillsOverview | null; t: (key: string) => string }) {
  const location = useLocation()
  const rows = data?.operator_table || []
  const total30 = rows.reduce((sum, row) => sum + Number(row.sessions_30d || 0), 0)
  const active7 = rows.filter((row) => Number(row.sessions_7d || 0) > 0).length
  const active30 = rows.filter((row) => Number(row.sessions_30d || 0) > 0).length
  const avgSkills = active30 ? rows.reduce((sum, row) => sum + Number(row.skill_count || 0), 0) / active30 : 0
  const top3 = rows.slice().sort((a, b) => Number(b.sessions_30d || 0) - Number(a.sessions_30d || 0)).slice(0, 3).reduce((sum, row) => sum + Number(row.sessions_30d || 0), 0)
  const runtimes = new Set<string>()
  rows.forEach((row) => Object.keys(row.runtime_counts || {}).forEach((key) => runtimes.add(key)))
  const values: Array<[string, string, 'good' | 'warn' | 'bad', SkillsEvidenceKind]> = [
    [t('activeRate7d'), pct(rows.length ? active7 / rows.length : 0), stateBy(rows.length ? active7 / rows.length : 0, 0.6, 0.3), 'operators'],
    [t('avgSkillsPerOperator'), avgSkills.toFixed(2), stateBy(avgSkills, 3, 1), 'avg_per_session'],
    [t('kpiTop3Share'), pct(total30 ? top3 / total30 : 0), total30 && top3 / total30 > 0.8 ? 'bad' : total30 && top3 / total30 > 0.6 ? 'warn' : 'good', 'top3'],
    [t('runtimeCoverage'), `${runtimes.size} ${t('categoryUnit')}`, stateBy(runtimes.size, 2, 1), 'runtime'],
    [t('kpiActiveOperators'), `${active30} ${t('operatorsUnit')}`, active30 ? 'good' : 'bad', 'operators'],
  ]
  return (
    <section className="frame skills-health-frame">
      <div className="skills-health">
        <b>{t('usageSignals')}</b>
        {values.map(([title, value, state, kind]) => (
          <span className={state} key={title}>
            <i />
            {title} <strong>{value}</strong>
            <Link className="evidence-icon-link" to={evidencePath(location.search, kind)} aria-label={`${t('viewEvidence')}: ${title}`} title={`${t('viewEvidence')}: ${title}`}>↗</Link>
          </span>
        ))}
      </div>
    </section>
  )
}

export function HealthBar({ data, view = 'skill', t }: { data: SkillsOverview | null; view?: 'skill' | 'operator'; t: (key: string) => string }) {
  const location = useLocation()
  if (view === 'operator') return <OperatorHealth data={data} t={t} />
  const installed = data?.funnel?.installed?.length || 0
  const idle = data?.governance?.idle_installed?.count ?? data?.funnel?.idle?.length ?? 0
  const catalogCount = data?.funnel?.catalog?.length || 0
  const usedCompany = data?.funnel?.used_30d?.length || 0
  const untrackedNames = compactNameList((data?.governance?.untracked_usage?.top || []).slice(0, 2).map((row) => row.name), 2)
  const idleNames = compactNameList((data?.governance?.idle_installed?.top || []).slice(0, 2).map((row) => row.name), 1)
  const topNames = compactNameList((data?.table || []).slice(0, 3).map((row) => row.name), 1)
  const values: Array<[HealthMetric, string, string, number, SkillsEvidenceKind, string]> = [
    ['untracked', t('kpiUntrackedShare'), pct(data?.period_comparison?.current_untracked_share ?? data?.governance?.untracked_usage?.ratio), data?.period_comparison?.current_untracked_share ?? data?.governance?.untracked_usage?.ratio ?? 0, 'untracked', `${untrackedNames} ${t('autoUsed')}`],
    ['idleRatio', t('kpiUnusedRatio'), pct(installed ? idle / installed : 0), installed ? idle / installed : 0, 'unused_ratio', `${idleNames} ${t('installedUnusedText')}`],
    ['coverage', t('kpiCoverage'), pct(catalogCount ? usedCompany / catalogCount : 0), catalogCount ? usedCompany / catalogCount : 0, 'coverage', `${usedCompany}/${catalogCount} ${t('usedByCompany')}`],
    ['top3', t('kpiTop3Share'), pct(data?.period_comparison?.current_top3_share), data?.period_comparison?.current_top3_share ?? 0, 'top3', `${t('top3Concentrated')}: ${topNames}`],
    ['avgSkills', t('kpiAvgSkillPerSession'), (data?.period_comparison?.current_avg_skills_per_session ?? 0).toFixed(2), data?.period_comparison?.current_avg_skills_per_session ?? 0, 'avg_per_session', `${t('avgPrefix')} ${((data?.period_comparison?.current_avg_skills_per_session ?? 0)).toFixed(2)} ${t('perSession')}`],
  ]
  return (
    <section className="frame skills-health-frame">
      <div className="skills-health">
        <b>{t('healthIssues')}</b>
        {values.map(([metric, title, value, raw, kind, names]) => {
          const state = classifySkillHealth(metric, raw)
          return (
            <span className={state} key={metric}>
              <i />
              {title} <strong>{value}</strong>{names ? <em>{names}</em> : null}
              <Link className="evidence-icon-link" to={evidencePath(location.search, kind)} aria-label={`${t('viewEvidence')}: ${title}`} title={`${t('viewEvidence')}: ${title}`}>↗</Link>
            </span>
          )
        })}
      </div>
    </section>
  )
}

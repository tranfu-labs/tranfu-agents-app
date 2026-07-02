import { Link, useLocation } from 'react-router-dom'
import type { SkillsEvidenceKind, SkillsOverview } from '../../lib/types'
import { evidencePath } from '../../lib/skillsEvidence'

function pct(value?: number) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

function OperatorHealth({ data, t }: { data: SkillsOverview | null; t: (key: string) => string }) {
  const location = useLocation()
  const rows = data?.operator_table || []
  const totalWindow = rows.reduce((sum, row) => sum + Number(row.sessions_window ?? row.sessions_30d ?? 0), 0)
  const active7 = rows.filter((row) => Number(row.sessions_7d || 0) > 0).length
  const activeWindow = rows.filter((row) => Number(row.sessions_window ?? row.sessions_30d ?? 0) > 0).length
  const avgSkills = activeWindow ? rows.reduce((sum, row) => sum + Number(row.window_skill_count ?? row.skill_count ?? 0), 0) / activeWindow : 0
  const top3 = rows.slice().sort((a, b) => Number(b.sessions_window ?? b.sessions_30d ?? 0) - Number(a.sessions_window ?? a.sessions_30d ?? 0)).slice(0, 3).reduce((sum, row) => sum + Number(row.sessions_window ?? row.sessions_30d ?? 0), 0)
  const runtimes = new Set<string>()
  rows.forEach((row) => Object.keys(row.window_runtime_counts || row.runtime_counts || {}).forEach((key) => runtimes.add(key)))
  const values: Array<[string, string, SkillsEvidenceKind]> = [
    [t('activeRate7d'), pct(rows.length ? active7 / rows.length : 0), 'operators'],
    [t('avgSkillsPerOperator'), avgSkills.toFixed(2), 'avg_per_session'],
    [t('kpiTop3Share'), pct(totalWindow ? top3 / totalWindow : 0), 'top3'],
    [t('runtimeCoverage'), `${runtimes.size} ${t('categoryUnit')}`, 'runtime'],
    [t('kpiActiveOperators'), `${activeWindow} ${t('operatorsUnit')}`, 'operators'],
  ]
  return (
    <section className="frame skills-health-frame">
      <div className="skills-health">
        <b>{t('usageSignals')}</b>
        {values.map(([title, value, kind]) => (
          <span className="signal" key={title}>
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
  const values: Array<[string, string, SkillsEvidenceKind]> = [
    [t('kpiUntrackedShare'), pct(data?.period_comparison?.current_untracked_share ?? data?.governance?.untracked_usage?.ratio), 'untracked'],
    [t('kpiUnusedRatio'), pct(installed ? idle / installed : 0), 'unused_ratio'],
    [t('kpiCoverage'), pct(catalogCount ? usedCompany / catalogCount : 0), 'coverage'],
    [t('kpiTop3Share'), pct(data?.period_comparison?.current_top3_share), 'top3'],
    [t('kpiAvgSkillPerSession'), (data?.period_comparison?.current_avg_skills_per_session ?? 0).toFixed(2), 'avg_per_session'],
  ]
  return (
    <section className="frame skills-health-frame">
      <div className="skills-health">
        <b>{t('healthIssues')}</b>
        {values.map(([title, value, kind]) => {
          return (
            <span className="signal" key={kind}>
              <i />
              {title} <strong>{value}</strong>
              <Link className="evidence-icon-link" to={evidencePath(location.search, kind)} aria-label={`${t('viewEvidence')}: ${title}`} title={`${t('viewEvidence')}: ${title}`}>↗</Link>
            </span>
          )
        })}
      </div>
    </section>
  )
}

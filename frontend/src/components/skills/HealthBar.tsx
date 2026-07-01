import { Link, useLocation } from 'react-router-dom'
import type { SkillsEvidenceKind, SkillsOverview } from '../../lib/types'
import { classifySkillHealth, type HealthMetric } from '../../lib/skillsThresholds'
import { evidencePath } from '../../lib/skillsEvidence'

function pct(value?: number) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

function stateBy(value: number, good: number, warn: number) {
  if (value >= good) return 'good'
  if (value >= warn) return 'warn'
  return 'bad'
}

function OperatorHealth({ data }: { data: SkillsOverview | null }) {
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
    ['活跃率', pct(rows.length ? active7 / rows.length : 0), stateBy(rows.length ? active7 / rows.length : 0, 0.6, 0.3), 'operators'],
    ['人均 skill', avgSkills.toFixed(2), stateBy(avgSkills, 3, 1), 'avg_per_session'],
    ['Top3 集中度', pct(total30 ? top3 / total30 : 0), total30 && top3 / total30 > 0.8 ? 'bad' : total30 && top3 / total30 > 0.6 ? 'warn' : 'good', 'top3'],
    ['runtime 覆盖', `${runtimes.size} 类`, stateBy(runtimes.size, 2, 1), 'runtime'],
    ['活跃操作员', `${active30} 人`, active30 ? 'good' : 'bad', 'operators'],
  ]
  return (
    <section className="frame">
      <div className="skills-health">
        <b>使用线索</b>
        {values.map(([title, value, state, kind]) => (
          <span className={state} key={title}><i />{title} <strong>{value}</strong><Link to={evidencePath(location.search, kind)}>证据</Link></span>
        ))}
      </div>
    </section>
  )
}

export function HealthBar({ data, view = 'skill' }: { data: SkillsOverview | null; view?: 'skill' | 'operator' }) {
  const location = useLocation()
  if (view === 'operator') return <OperatorHealth data={data} />
  const installed = data?.funnel?.installed?.length || 0
  const idle = data?.governance?.idle_installed?.count ?? data?.funnel?.idle?.length ?? 0
  const catalogCount = data?.funnel?.catalog?.length || 0
  const usedCompany = data?.funnel?.used_30d?.length || 0
  const untrackedNames = (data?.governance?.untracked_usage?.top || []).slice(0, 2).map((row) => row.name).join(' / ')
  const idleNames = (data?.governance?.idle_installed?.top || []).slice(0, 2).map((row) => row.name).join(' / ')
  const topNames = (data?.table || []).slice(0, 3).map((row) => row.name).join(' / ')
  const values: Array<[HealthMetric, string, string, number, SkillsEvidenceKind, string]> = [
    ['untracked', '未收录', pct(data?.period_comparison?.current_untracked_share ?? data?.governance?.untracked_usage?.ratio), data?.period_comparison?.current_untracked_share ?? data?.governance?.untracked_usage?.ratio ?? 0, 'untracked', untrackedNames],
    ['idleRatio', '装了没用', pct(installed ? idle / installed : 0), installed ? idle / installed : 0, 'unused_ratio', idleNames],
    ['coverage', '覆盖率', pct(catalogCount ? usedCompany / catalogCount : 0), catalogCount ? usedCompany / catalogCount : 0, 'coverage', (data?.funnel?.used_30d || []).slice(0, 2).map((row) => row.name).join(' / ')],
    ['top3', 'Top3 集中度', pct(data?.period_comparison?.current_top3_share), data?.period_comparison?.current_top3_share ?? 0, 'top3', topNames],
    ['avgSkills', '平均 skill/会', (data?.period_comparison?.current_avg_skills_per_session ?? 0).toFixed(2), data?.period_comparison?.current_avg_skills_per_session ?? 0, 'avg_per_session', topNames],
  ]
  return (
    <section className="frame">
      <div className="skills-health">
        <b>问题线索</b>
        {values.map(([metric, title, value, raw, kind, names]) => {
          const state = classifySkillHealth(metric, raw)
          return <span className={state} key={metric}><i />{title} <strong>{value}</strong>{names ? <em>{names}</em> : null}<Link to={evidencePath(location.search, kind)}>证据</Link></span>
        })}
      </div>
    </section>
  )
}

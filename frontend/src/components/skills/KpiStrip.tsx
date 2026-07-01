import type { SkillsOverview } from '../../lib/types'
import { deltaRatio, formatDelta } from '../../lib/skillsDashboard'

function n(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(Math.round(Number(value || 0)))
}

function pct(value?: number) {
  return `${((Number(value || 0)) * 100).toFixed(1)}%`
}

function Delta({ current, previous, snapshot, show = true }: { current?: number; previous?: number; snapshot?: boolean; show?: boolean }) {
  if (snapshot) return <span className="delta snapshot">快照</span>
  if (!show) return <span className="delta snapshot">环比关</span>
  const ratio = deltaRatio(Number(current || 0), Number(previous || 0))
  const cls = ratio === null ? '' : ratio >= 0 ? 'up' : 'down'
  return <span className={`delta ${cls}`}>{formatDelta(ratio)}</span>
}

function operatorCards(data: SkillsOverview | null) {
  const rows = data?.operator_table || []
  const active30 = rows.filter((row) => Number(row.sessions_30d || 0) > 0).length
  const active7 = rows.filter((row) => Number(row.sessions_7d || 0) > 0).length
  const sessions30 = rows.reduce((sum, row) => sum + Number(row.sessions_30d || 0), 0)
  const sessionCount = rows.reduce((sum, row) => sum + Number(row.session_count || 0), 0)
  const skillCount = rows.reduce((sum, row) => sum + Number(row.skill_count || 0), 0)
  const top3 = rows.slice().sort((a, b) => Number(b.sessions_30d || 0) - Number(a.sessions_30d || 0)).slice(0, 3).reduce((sum, row) => sum + Number(row.sessions_30d || 0), 0)
  const runtimes = new Set<string>()
  const sources = new Set<string>()
  rows.forEach((row) => {
    Object.keys(row.runtime_counts || {}).forEach((key) => runtimes.add(key))
    Object.keys(row.source_counts || {}).forEach((key) => sources.add(key))
  })
  return [
    ['30d 使用记录', n(sessions30), 0, 0, 'snapshot'],
    ['活跃操作员', `${n(active30)} 人`, 0, 0, 'snapshot'],
    ['7d 活跃率', pct(rows.length ? active7 / rows.length : 0), 0, 0, 'snapshot'],
    ['人均 skill', active30 ? (skillCount / active30).toFixed(2) : '0.00', 0, 0, 'snapshot'],
    ['人均会话', active30 ? (sessionCount / active30).toFixed(2) : '0.00', 0, 0, 'snapshot'],
    ['Top3 集中度', pct(sessions30 ? top3 / sessions30 : 0), 0, 0, 'snapshot'],
    ['runtime 覆盖', `${n(runtimes.size)} 类`, 0, 0, 'snapshot'],
    ['来源覆盖', `${n(sources.size)} 类`, 0, 0, 'snapshot'],
  ] as const
}

export function KpiStrip({ data, view = 'skill', showComparison = true }: { data: SkillsOverview | null; view?: 'skill' | 'operator'; showComparison?: boolean }) {
  if (view === 'operator') {
    const cards = operatorCards(data)
    return (
      <section className="frame skills-kpi-frame">
        <h2><span><span className="sl">//</span>KPI 环带</span><span className="cnt">operator</span></h2>
        <div className="skills-kpi">
          {cards.map(([label, value]) => (
            <div className="stat skills-kpi-card" key={label}>
              <div className="v">{value}</div>
              <span className="delta snapshot">快照</span>
              <div className="l">{label}</div>
            </div>
          ))}
        </div>
      </section>
    )
  }
  const period = data?.period_comparison
  const catalogCount = data?.funnel?.catalog?.length || 0
  const usedCompany = data?.funnel?.used_30d?.length || period?.current_company_skill_count || 0
  const previousCompany = period?.previous_company_skill_count || 0
  const installed = data?.funnel?.installed?.length || 0
  const idle = data?.governance?.idle_installed?.count ?? data?.funnel?.idle?.length ?? 0
  const currentSessions = period?.current_sessions ?? data?.table?.reduce((sum, row) => sum + Number(row.sessions_window ?? row.sessions_30d ?? 0), 0) ?? 0
  const previousSessions = period?.previous_sessions ?? 0
  const top3Share = period?.current_top3_share ?? 0
  const idleRatio = installed ? idle / installed : 0
  const coverage = catalogCount ? usedCompany / catalogCount : 0
  const previousCoverage = catalogCount ? previousCompany / catalogCount : 0
  const cards = [
    ['总触发次数', n(currentSessions), currentSessions, previousSessions],
    ['公司库覆盖率', `${usedCompany}/${catalogCount}`, coverage, previousCoverage, 'pct'],
    ['活跃操作员数', `${n(period?.current_operators)} 人`, period?.current_operators, period?.previous_operators],
    ['平均 skill/会', (period?.current_avg_skills_per_session ?? 0).toFixed(2), period?.current_avg_skills_per_session, period?.previous_avg_skills_per_session],
    ['未收录占比', pct(period?.current_untracked_share ?? data?.governance?.untracked_usage?.ratio), period?.current_untracked_share, period?.previous_untracked_share, 'pct'],
    ['闲置 Skill 数', `${n(idle)} 个`, 0, 0, 'snapshot'],
    ['装了没用比例', pct(idleRatio), 0, 0, 'snapshot'],
    ['Top3 集中度', pct(top3Share), top3Share, period?.previous_top3_share, 'pct'],
  ] as const

  return (
    <section className="frame skills-kpi-frame">
      <h2><span><span className="sl">//</span>KPI 环带</span><span className="cnt">{period?.window || `${data?.days || 30}d`}</span></h2>
      <div className="skills-kpi">
        {cards.map(([label, value, current, previous, kind]) => (
          <div className="stat skills-kpi-card" key={label}>
            <div className="v">{value}</div>
            <Delta current={kind === 'pct' ? Number(current) : Number(current || 0)} previous={kind === 'pct' ? Number(previous) : Number(previous || 0)} snapshot={kind === 'snapshot'} show={showComparison} />
            <div className="l">{label}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

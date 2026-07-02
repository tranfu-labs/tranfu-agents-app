import { Link, useLocation } from 'react-router-dom'
import type { SkillsEvidenceKind, SkillsOverview } from '../../lib/types'
import { deltaRatio, formatDelta } from '../../lib/skillsDashboard'
import { evidencePath } from '../../lib/skillsEvidence'
import { compactNameList, kpiShortConclusion } from '../../lib/skillsPresentation'

type EvidenceCard = {
  label: string
  value: string
  current?: number
  previous?: number
  kind: SkillsEvidenceKind
  names: string[]
  detail?: string
  records?: number
  pct?: boolean
  snapshot?: boolean
}

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
  return <span className="delta">{formatDelta(ratio)}</span>
}

function operatorCards(data: SkillsOverview | null): EvidenceCard[] {
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
  const topOps = rows.slice().sort((a, b) => Number(b.sessions_30d || 0) - Number(a.sessions_30d || 0)).slice(0, 2).map((row) => row.operator)
  return [
    { label: '30d 使用记录', value: n(sessions30), current: 0, previous: 0, kind: 'total', names: topOps, detail: `${n(sessions30)} records`, snapshot: true },
    { label: '活跃操作员', value: `${n(active30)} 人`, current: 0, previous: 0, kind: 'operators', names: topOps, detail: `${n(active30)} operators`, snapshot: true },
    { label: '7d 活跃率', value: pct(rows.length ? active7 / rows.length : 0), current: 0, previous: 0, kind: 'operators', names: topOps, detail: `${n(active7)}/${n(rows.length)} active`, snapshot: true },
    { label: '人均 skill', value: active30 ? (skillCount / active30).toFixed(2) : '0.00', current: 0, previous: 0, kind: 'avg_per_session', names: topOps, detail: '按人均值', snapshot: true },
    { label: '人均会话', value: active30 ? (sessionCount / active30).toFixed(2) : '0.00', current: 0, previous: 0, kind: 'avg_per_session', names: topOps, detail: '按人均值', snapshot: true },
    { label: 'Top3 集中度', value: pct(sessions30 ? top3 / sessions30 : 0), current: 0, previous: 0, kind: 'top3', names: topOps, detail: '使用集中在 3 人', snapshot: true },
    { label: 'runtime 覆盖', value: `${n(runtimes.size)} 类`, current: 0, previous: 0, kind: 'runtime', names: [...runtimes].slice(0, 2), detail: compactNameList([...runtimes], 1), snapshot: true },
    { label: '来源覆盖', value: `${n(sources.size)} 类`, current: 0, previous: 0, kind: 'source', names: [...sources].slice(0, 2), detail: compactNameList([...sources], 1), snapshot: true },
  ]
}

export function KpiStrip({ data, view = 'skill', showComparison = true }: { data: SkillsOverview | null; view?: 'skill' | 'operator'; showComparison?: boolean }) {
  const location = useLocation()
  if (view === 'operator') {
    const cards = operatorCards(data)
    return (
      <section className="frame skills-kpi-frame">
        <h2><span><span className="sl">//</span>过去 W 变化</span><span className="cnt">operator</span></h2>
        <div className="skills-kpi">
          {cards.map((card) => (
            <div className="stat skills-kpi-card" key={card.label}>
              <div className="v">{card.value}</div>
              <span className="evidence-names">{card.detail || compactNameList(card.names, 1)}</span>
              <Link className="evidence-icon-link" to={evidencePath(location.search, card.kind)} aria-label={`查看${card.label}证据`} title={`查看${card.label}证据`}>↗</Link>
              <div className="l">{card.label}</div>
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
  const topRows = (data?.table || []).slice().sort((a, b) => Number(b.sessions_window ?? b.sessions_30d ?? 0) - Number(a.sessions_window ?? a.sessions_30d ?? 0))
  const topNames = topRows.slice(0, 3).map((row) => row.name)
  const untrackedNames = (data?.governance?.untracked_usage?.top || []).slice(0, 2).map((row) => row.name)
  const idleNames = (data?.governance?.idle_installed?.top || []).slice(0, 2).map((row) => row.name)
  const operatorNames = (data?.operator_table || []).slice(0, 2).map((row) => row.operator)
  const companyNames = (data?.funnel?.used_30d || []).slice(0, 2).map((row) => row.name)
  const untrackedRecords = data?.governance?.untracked_usage?.used_sessions || 0
  const baseCards: EvidenceCard[] = [
    { label: '总触发次数', value: n(currentSessions), current: currentSessions, previous: previousSessions, kind: 'total', names: topNames },
    { label: '公司库覆盖率', value: `${usedCompany}/${catalogCount}`, current: coverage, previous: previousCoverage, kind: 'coverage', names: companyNames, pct: true },
    { label: '活跃操作员数', value: `${n(period?.current_operators)} 人`, current: period?.current_operators, previous: period?.previous_operators, kind: 'operators', names: operatorNames },
    { label: '平均 skill/会', value: (period?.current_avg_skills_per_session ?? 0).toFixed(2), current: period?.current_avg_skills_per_session, previous: period?.previous_avg_skills_per_session, kind: 'avg_per_session', names: topNames },
    { label: '未收录占比', value: pct(period?.current_untracked_share ?? data?.governance?.untracked_usage?.ratio), current: period?.current_untracked_share, previous: period?.previous_untracked_share, kind: 'untracked', names: untrackedNames, pct: true },
    { label: '闲置 Skill 数', value: `${n(idle)} 个`, current: 0, previous: 0, kind: 'idle', names: idleNames, snapshot: true },
    { label: '装了没用比例', value: pct(idleRatio), current: 0, previous: 0, kind: 'unused_ratio', names: idleNames, snapshot: true },
    { label: 'Top3 集中度', value: pct(top3Share), current: top3Share, previous: period?.previous_top3_share, kind: 'top3', names: topNames, pct: true },
  ]
  const cards = baseCards.map((card) => ({ ...card, records: card.kind === 'untracked' ? untrackedRecords : undefined, detail: kpiShortConclusion(card.label, card.value, card.names, card.kind === 'untracked' ? untrackedRecords : undefined) }))

  return (
    <section className="frame skills-kpi-frame">
      <h2><span><span className="sl">//</span>过去 W 变化</span><span className="cnt">{period?.window || `${data?.days || 30}d`}</span></h2>
      <div className="skills-kpi">
        {cards.map((card) => (
            <div className="stat skills-kpi-card" key={card.label}>
              <div className="v">{card.value}</div>
              <Delta current={card.pct ? Number(card.current) : Number(card.current || 0)} previous={card.pct ? Number(card.previous) : Number(card.previous || 0)} snapshot={card.snapshot} show={showComparison} />
              <span className="evidence-names">{card.detail || compactNameList(card.names, 1)}</span>
              <Link className="evidence-icon-link" to={evidencePath(location.search, card.kind)} aria-label={`查看${card.label}证据`} title={`查看${card.label}证据`}>↗</Link>
              <div className="l">{card.label}</div>
            </div>
        ))}
      </div>
    </section>
  )
}

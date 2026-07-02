import { Link, useLocation } from 'react-router-dom'
import type { SkillsEvidenceKind, SkillsOverview } from '../../lib/types'
import { deltaRatio, formatDelta } from '../../lib/skillsDashboard'
import { evidencePath } from '../../lib/skillsEvidence'
import { compactNameList, kpiShortConclusion, windowDisplayLabel } from '../../lib/skillsPresentation'

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

function Delta({ current, previous, snapshot, show = true, t }: { current?: number; previous?: number; snapshot?: boolean; show?: boolean; t: (key: string) => string }) {
  if (snapshot) return <span className="delta snapshot">{t('snapshot')}</span>
  if (!show) return <span className="delta snapshot">{t('comparisonOff')}</span>
  const ratio = deltaRatio(Number(current || 0), Number(previous || 0))
  return <span className="delta">{formatDelta(ratio)}</span>
}

function operatorCards(data: SkillsOverview | null, t: (key: string) => string): EvidenceCard[] {
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
    { label: t('usageRecords30d'), value: n(sessions30), current: 0, previous: 0, kind: 'total', names: topOps, detail: `${n(sessions30)} ${t('records')}`, snapshot: true },
    { label: t('kpiActiveOperators'), value: n(active30), current: 0, previous: 0, kind: 'operators', names: topOps, detail: `${n(active30)} ${t('operatorsUnit')}`, snapshot: true },
    { label: t('activeRate7d'), value: pct(rows.length ? active7 / rows.length : 0), current: 0, previous: 0, kind: 'operators', names: topOps, detail: `${n(active7)}/${n(rows.length)} ${t('inUse')}`, snapshot: true },
    { label: t('avgSkillsPerOperator'), value: active30 ? (skillCount / active30).toFixed(2) : '0.00', current: 0, previous: 0, kind: 'avg_per_session', names: topOps, detail: t('avgPrefix'), snapshot: true },
    { label: t('avgSessionsPerOperator'), value: active30 ? (sessionCount / active30).toFixed(2) : '0.00', current: 0, previous: 0, kind: 'avg_per_session', names: topOps, detail: t('avgPrefix'), snapshot: true },
    { label: t('kpiTop3Share'), value: pct(sessions30 ? top3 / sessions30 : 0), current: 0, previous: 0, kind: 'top3', names: topOps, detail: t('top3Concentrated'), snapshot: true },
    { label: t('runtimeCoverage'), value: `${n(runtimes.size)} ${t('categoryUnit')}`, current: 0, previous: 0, kind: 'runtime', names: [...runtimes].slice(0, 2), detail: compactNameList([...runtimes], 1), snapshot: true },
    { label: t('sourceCoverage'), value: `${n(sources.size)} ${t('categoryUnit')}`, current: 0, previous: 0, kind: 'source', names: [...sources].slice(0, 2), detail: compactNameList([...sources], 1), snapshot: true },
  ]
}

export function KpiStrip({ data, view = 'skill', showComparison = true, t }: { data: SkillsOverview | null; view?: 'skill' | 'operator'; showComparison?: boolean; t: (key: string) => string }) {
  const location = useLocation()
  if (view === 'operator') {
    const cards = operatorCards(data, t)
    return (
      <section className="frame skills-kpi-frame">
        <h2><span><span className="sl">//</span>{t('kpiPeriodChange')}</span><span className="cnt">operator</span></h2>
        <div className="skills-kpi">
          {cards.map((card) => (
            <div className="stat skills-kpi-card" key={card.label}>
              <div className="skills-kpi-top">
                <div className="v">{card.value}</div>
                <Link className="evidence-icon-link" to={evidencePath(location.search, card.kind)} aria-label={`${t('viewEvidence')}: ${card.label}`} title={`${t('viewEvidence')}: ${card.label}`}>↗</Link>
              </div>
              <div className="l">{card.label}</div>
              <span className="evidence-names">{card.detail || compactNameList(card.names, 1)}</span>
              <Delta snapshot={card.snapshot} t={t} />
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
    { label: t('kpiTotalTriggers'), value: n(currentSessions), current: currentSessions, previous: previousSessions, kind: 'total', names: topNames },
    { label: t('kpiCoverage'), value: `${usedCompany}/${catalogCount}`, current: coverage, previous: previousCoverage, kind: 'coverage', names: companyNames, pct: true },
    { label: t('kpiActiveOperators'), value: n(period?.current_operators), current: period?.current_operators, previous: period?.previous_operators, kind: 'operators', names: operatorNames },
    { label: t('kpiAvgSkillPerSession'), value: (period?.current_avg_skills_per_session ?? 0).toFixed(2), current: period?.current_avg_skills_per_session, previous: period?.previous_avg_skills_per_session, kind: 'avg_per_session', names: topNames },
    { label: t('kpiUntrackedShare'), value: pct(period?.current_untracked_share ?? data?.governance?.untracked_usage?.ratio), current: period?.current_untracked_share, previous: period?.previous_untracked_share, kind: 'untracked', names: untrackedNames, pct: true },
    { label: t('kpiIdleSkills'), value: n(idle), current: 0, previous: 0, kind: 'idle', names: idleNames, snapshot: true },
    { label: t('kpiUnusedRatio'), value: pct(idleRatio), current: 0, previous: 0, kind: 'unused_ratio', names: idleNames, snapshot: true },
    { label: t('kpiTop3Share'), value: pct(top3Share), current: top3Share, previous: period?.previous_top3_share, kind: 'top3', names: topNames, pct: true },
  ]
  const cards = baseCards.map((card) => ({ ...card, records: card.kind === 'untracked' ? untrackedRecords : undefined, detail: kpiShortConclusion(card.kind, card.value, card.names, card.kind === 'untracked' ? untrackedRecords : undefined, t) }))

  return (
    <section className="frame skills-kpi-frame">
      <h2><span><span className="sl">//</span>{t('kpiPeriodChange')}</span><span className="cnt">{windowDisplayLabel(period?.window || `${data?.days || 30}d`, t)}</span></h2>
      <div className="skills-kpi">
        {cards.map((card) => (
            <div className="stat skills-kpi-card" key={card.label}>
              <div className="skills-kpi-top">
                <div className="v">{card.value}</div>
                <Link className="evidence-icon-link" to={evidencePath(location.search, card.kind)} aria-label={`${t('viewEvidence')}: ${card.label}`} title={`${t('viewEvidence')}: ${card.label}`}>↗</Link>
              </div>
              <div className="l">{card.label}</div>
              <span className="evidence-names">{card.detail || compactNameList(card.names, 1)}</span>
              <Delta current={card.pct ? Number(card.current) : Number(card.current || 0)} previous={card.pct ? Number(card.previous) : Number(card.previous || 0)} snapshot={card.snapshot} show={showComparison} t={t} />
            </div>
        ))}
      </div>
    </section>
  )
}

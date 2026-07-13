import type { AgentOverview, AgentOverviewGroup } from '../../lib/types'
import { dur, RT } from '../../lib/utils'

type RankView = 'runtime' | 'operator'

export function AgentRankPanel({ overview, view, onFilter, windowLabel, t }: {
  overview: AgentOverview
  view: RankView
  onFilter: (key: 'rt' | 'op', value: string) => void
  windowLabel: string
  t: (key: string) => string
}) {
  const rows = view === 'runtime' ? overview.runtime : overview.operator
  const maxAgents = Math.max(...rows.map((row) => row.agents), 1)
  const nameOf = (row: AgentOverviewGroup) => String(row.runtime || row.operator || '—')
  return (
    <section className="frame agents-rank-panel">
      <div className="agents-panel-title">
        <b>{t('agentRank')}</b>
      </div>
      <div className="agent-rank-list">
        {rows.length ? rows.map((row) => {
          const name = nameOf(row)
          const rate = row.success_rate === null ? '—' : `${Math.round(row.success_rate * 100)}%`
          return (
            <button type="button" className="agent-rank-row" key={name} onClick={() => onFilter(view === 'runtime' ? 'rt' : 'op', name)}>
              <span className="agent-rank-name" title={name}>{view === 'runtime' ? (RT[name] || name) : name}</span>
              <span className="agent-rank-track"><i style={{ width: `${Math.max(3, Math.round((row.agents / maxAgents) * 100))}%` }} /></span>
              <span className="agent-rank-count">{row.agents} · {row.live} {t('agentLiveShort')}</span>
              <span className="agent-rank-meta">{dur(row.today_active)} · {windowLabel} · {rate}</span>
            </button>
          )
        }) : <div className="hint">{t('agentNoRank')}</div>}
      </div>
    </section>
  )
}

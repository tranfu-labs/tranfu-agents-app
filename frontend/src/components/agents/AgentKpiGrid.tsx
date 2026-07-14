import {
  buildAgentKpiCards,
  type AgentKpiAction,
  type AgentWindowComparison,
} from '../../lib/agentsDashboard'
import { windowChangeLabel } from '../../lib/skillsPresentation'
import type { AgentOverview } from '../../lib/types'

function deltaTone(value: string) {
  if (value === '—') return 'snapshot'
  return value.startsWith('-') ? 'down' : 'up'
}

const ACTION_LABELS: Record<AgentKpiAction, string> = {
  trend: 'agentKpiViewTrend',
  directory: 'agentKpiViewDirectory',
  live: 'agentKpiFilterLive',
  week: 'agentKpiSortWeek',
  quality: 'agentKpiSortQuality',
  attention: 'agentKpiFilterAttention',
}

export function AgentKpiGrid({ comparison, summary, totalAgents, attention, windowKey, windowLabel, onAction, t }: {
  comparison: AgentWindowComparison
  summary: AgentOverview['summary']
  totalAgents: number
  attention: number
  windowKey: string
  windowLabel: string
  onAction: (action: AgentKpiAction) => void
  t: (key: string) => string
}) {
  const cards = buildAgentKpiCards({ comparison, summary, totalAgents, attention, t })
  return (
    <section className="frame agents-window-frame">
      <h2><span><span className="sl">//</span>{windowChangeLabel(windowKey, t)}</span><span className="cnt">{windowLabel}</span></h2>
      <div className="agents-window-kpi">
        {cards.map((item) => (
          <div className={`stat agent-kpi-card agent-kpi-${item.key}`} key={item.key}>
            <div className="agent-kpi-top">
              <div className="v">{item.value}</div>
              <button
                type="button"
                className="agent-kpi-action"
                aria-label={t(ACTION_LABELS[item.action])}
                title={t(ACTION_LABELS[item.action])}
                onClick={() => onAction(item.action)}
              >↗</button>
            </div>
            <div className="l">{item.label}</div>
            <span className="agent-kpi-detail">{item.detail}</span>
            <span className={`delta ${item.snapshot ? 'snapshot' : deltaTone(item.delta)}`}>{item.delta}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

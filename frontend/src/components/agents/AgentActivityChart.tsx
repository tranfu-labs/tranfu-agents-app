import { useLayoutEffect, useRef, useState } from 'react'
import type { AgentOverview } from '../../lib/types'
import { dur } from '../../lib/utils'

type Metric = 'agents' | 'seconds'

export function AgentActivityChart({ overview, t }: { overview: AgentOverview; t: (key: string) => string }) {
  const boxRef = useRef<HTMLDivElement | null>(null)
  const [metric, setMetric] = useState<Metric>('agents')
  const values = overview.daily.map((row) => metric === 'agents' ? row.active_agents : row.active_seconds)
  const max = Math.max(...values, 1)
  const width = Math.max(760, overview.daily.length * 12)
  const height = 220
  const base = 182
  const step = (width - 52) / Math.max(overview.daily.length, 1)
  const barWidth = Math.min(10, Math.max(4, step - 2))

  useLayoutEffect(() => {
    const box = boxRef.current
    if (box && width > box.clientWidth) box.scrollLeft = box.scrollWidth
  }, [width])

  return (
    <section className="frame agents-trend-panel">
      <div className="agents-panel-title">
        <div>
          <b>{t('agentActivityTrend')}</b>
          <span className="cnt">{t(metric === 'agents' ? 'agentActiveCount' : 'agentActiveTime')}</span>
        </div>
        <div className="seg compact" role="group" aria-label={t('agentTrendMetric')}>
          <button type="button" className={metric === 'agents' ? 'on' : ''} aria-pressed={metric === 'agents'} onClick={() => setMetric('agents')}>{t('agentActiveCount')}</button>
          <button type="button" className={metric === 'seconds' ? 'on' : ''} aria-pressed={metric === 'seconds'} onClick={() => setMetric('seconds')}>{t('agentActiveTime')}</button>
        </div>
      </div>
      <div ref={boxRef} className="chart-box agents-trend-box">
        <svg className="agents-trend-chart" viewBox={`0 0 ${width} ${height}`} style={{ width, minWidth: width }} role="img" aria-label={t('agentActivityTrend')}>
          <line x1="32" y1={base} x2={width - 12} y2={base} stroke="var(--line2)" />
          <line x1="32" y1="24" x2="32" y2={base} stroke="var(--line2)" />
          <text x="4" y="29" fill="var(--muted)" fontSize="10">{metric === 'agents' ? t('agents') : t('agentSeconds')}</text>
          {overview.daily.map((row, index) => {
            const value = metric === 'agents' ? row.active_agents : row.active_seconds
            const barHeight = value ? Math.max(3, Math.round((value / max) * 140)) : 0
            const x = 36 + index * step
            const current = row.day === overview.today
            return (
              <g key={row.day} className={current ? 'current' : undefined}>
                {barHeight ? <rect className="agent-trend-bar" x={x} y={base - barHeight} width={barWidth} height={barHeight} rx="2"><title>{`${row.day} · ${metric === 'agents' ? row.active_agents : dur(row.active_seconds)}`}</title></rect> : null}
                {index % 15 === 0 || index === overview.daily.length - 1 ? <text x={x} y="204" fill="var(--faint)" fontSize="9">{row.day.slice(5)}</text> : null}
              </g>
            )
          })}
        </svg>
      </div>
    </section>
  )
}

import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import {
  moveAgentChartIndex,
  buildAgentTrendModel,
  resolveAgentChartAnchorIndex,
  resolveAgentChartMode,
  resolveAgentChartScrollLeft,
  type AgentChartMetric,
  type AgentDailyBreakdownRow,
  type AgentRankView,
  type AgentTrendDay,
} from '../../lib/agentsDashboard'
import { resolveSkillsChartLayout } from '../../lib/skillsChartLayout'
import type { AgentOverview } from '../../lib/types'
import { dur, RT } from '../../lib/utils'
import { AgentChartTip } from './AgentChartTip'
import {
  agentChartAnchor,
  type AgentChartTipModel,
  useAgentChartWidth,
} from './agentChartSupport'

export function AgentActivityChart({ overview, breakdown, view, currentDay, windowLabel, t }: {
  overview: AgentOverview
  breakdown: AgentDailyBreakdownRow[]
  view: AgentRankView
  currentDay?: string
  windowLabel: string
  t: (key: string) => string
}) {
  const boxRef = useRef<HTMLDivElement | null>(null)
  const hitRefs = useRef<Array<SVGRectElement | null>>([])
  const [metric, setMetric] = useState<AgentChartMetric>('agents')
  const [hoverSegment, setHoverSegment] = useState<string | null>(null)
  const [tip, setTip] = useState<AgentChartTipModel | null>(null)
  const [activeIndex, setActiveIndex] = useState(() => resolveAgentChartAnchorIndex(overview.daily, 'agents'))
  const chartBoxWidth = useAgentChartWidth(boxRef)
  const mode = resolveAgentChartMode(overview.daily, metric)
  const model = useMemo(() => buildAgentTrendModel(breakdown, overview.days, metric), [breakdown, overview.days, metric])
  const layout = resolveSkillsChartLayout(overview.daily.length, chartBoxWidth)
  const chartAnchorIndex = resolveAgentChartAnchorIndex(overview.daily, metric)
  const windowIdentity = `${overview.days[0] || ''}:${overview.days.at(-1) || ''}:${overview.days.length}`
  const safeActiveIndex = Math.min(activeIndex, Math.max(0, overview.daily.length - 1))
  const visibleTip = tip && model.days.includes(tip.row) ? tip : null

  useLayoutEffect(() => {
    hitRefs.current = hitRefs.current.slice(0, overview.daily.length)
    const box = boxRef.current
    if (!box) return
    box.scrollLeft = layout.scrollToEnd
      ? resolveAgentChartScrollLeft(overview.daily.length, chartAnchorIndex, layout.trackWidth, box.clientWidth, box.scrollWidth)
      : 0
  }, [chartAnchorIndex, layout.scrollToEnd, layout.trackWidth, metric, overview.daily.length, windowIdentity])

  const selectMetric = (nextMetric: AgentChartMetric) => {
    setTip(null)
    setMetric(nextMetric)
    setActiveIndex(resolveAgentChartAnchorIndex(overview.daily, nextMetric))
  }

  const showTip = (row: AgentTrendDay, index: number, bar: SVGRectElement) => {
    setActiveIndex(index)
    setTip({ row, current: row.day === currentDay, anchor: agentChartAnchor(bar), metric, view, legend: model.legend })
  }

  const onBarKeyDown = (event: KeyboardEvent<SVGRectElement>, index: number) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      setTip(null)
      event.currentTarget.blur()
      return
    }
    const next = moveAgentChartIndex(index, event.key, overview.daily.length)
    if (next === index) return
    event.preventDefault()
    setActiveIndex(next)
    hitRefs.current[next]?.focus()
  }

  const header = (
    <div className="agents-panel-title">
      <div>
        <b><span className="sl">//</span>{t('agentActivityTrend')}</b>
        <span className="cnt">{windowLabel} · {t(metric === 'agents' ? 'agentActiveCount' : 'agentActiveTime')}</span>
      </div>
      <div className="seg compact" role="group" aria-label={t('agentTrendMetric')}>
        <button type="button" className={metric === 'agents' ? 'on' : ''} aria-pressed={metric === 'agents'} onClick={() => selectMetric('agents')}>{t('agentActiveCount')}</button>
        <button type="button" className={metric === 'seconds' ? 'on' : ''} aria-pressed={metric === 'seconds'} onClick={() => selectMetric('seconds')}>{t('agentActiveTime')}</button>
      </div>
    </div>
  )

  if (mode === 'empty') {
    return (
      <section id="agents-trend" tabIndex={-1} className="frame agents-trend-panel">
        {header}
        <div className="agents-trend-empty"><div className="empty"><div className="t">{t('agentNoTrend')}</div><div className="h">{t('agentNoTrendHint')}</div></div></div>
      </section>
    )
  }

  const values = overview.daily.map((row) => Number(metric === 'agents' ? row.active_agents : row.active_seconds))
  const max = Math.max(...values, 1)
  const width = Math.max(mode === 'today' ? 280 : 0, layout.trackWidth)
  const height = mode === 'today' ? 160 : 220
  const base = mode === 'today' ? 128 : 190
  const plotHeight = mode === 'today' ? 92 : 165
  const step = (width - 54) / Math.max(overview.daily.length, 1)
  const barWidth = layout.barWidth
  const patternId = `agentStripe-${metric}-${overview.daily.length}`
  const labelEvery = Math.max(1, Math.ceil(overview.daily.length / 8))
  const colorOf = (name: string) => `var(--agent-segment-${Math.max(0, model.legend.indexOf(name)) % 9})`
  const nameOf = (name: string) => name === '__other' ? t('other') : name === '__unassigned' ? t('agentUnassigned') : view === 'runtime' ? (RT[name] || name) : name

  return (
    <section id="agents-trend" tabIndex={-1} className="frame agents-trend-panel">
      {header}
      {mode === 'today' ? (
        <div className="agents-trend-readout">
          <span><small>{t('agentActiveCount')}</small><b>{overview.daily[0].active_agents}</b></span>
          <span><small>{t('agentActiveTime')}</small><b>{dur(overview.daily[0].active_seconds)}</b></span>
        </div>
      ) : null}
      <div
        ref={boxRef}
        className={`chart-box agents-trend-box ${layout.rightAlign ? 'align-end' : ''}`}
        onMouseLeave={() => setTip(null)}
        onPointerDown={(event) => {
          const target = event.target
          if (!(target instanceof SVGElement) || !target.classList.contains('bar-hit')) setTip(null)
        }}
        onScroll={() => setTip(null)}
      >
        <svg className={`agents-trend-chart metric-${metric} ${visibleTip ? 'hovering' : ''}`} viewBox={`0 0 ${width} ${height}`} style={{ width, minWidth: width }} role="img" aria-label={t('agentActivityTrend')}>
          <defs>
            <pattern id={patternId} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <path d="M 0 0 L 0 6" stroke="var(--text)" strokeOpacity=".22" strokeWidth="2" />
            </pattern>
          </defs>
          <line x1="34" y1={base} x2={width - 12} y2={base} stroke="var(--line2)" />
          <line x1="34" y1="24" x2="34" y2={base} stroke="var(--line2)" />
          <text x="4" y="30" fill="var(--muted)" fontSize="10">{t(metric === 'agents' ? 'agents' : 'agentSeconds')}</text>
          {model.days.map((row, index) => {
            const value = Number(metric === 'agents' ? row.active_agents : row.active_seconds)
            const barHeight = value ? Math.max(3, Math.round((value / max) * plotHeight)) : 0
            const slotX = 38 + index * step
            const x = slotX + Math.max(0, (step - barWidth) / 2)
            const hitX = 38 + index * step
            const current = row.day === currentDay
            const label = `${row.day} · ${t('agentActiveCount')} ${row.active_agents} · ${t('agentActiveTime')} ${dur(row.active_seconds)}`
            let y = base
            return (
              <g key={row.day} className={`day-col ${visibleTip?.row.day === row.day ? 'hovered' : ''}`}>
                {row.segments.map((segment) => {
                  const segmentValue = Number(metric === 'agents' ? segment.active_agents : segment.active_seconds)
                  if (!segmentValue) return null
                  const height = Math.max(1, Math.round((segmentValue / max) * plotHeight))
                  y -= height
                  return <rect key={segment.name} className="agent-trend-bar agent-trend-segment" x={x} y={y} width={barWidth} height={height} rx="1" fill={colorOf(segment.name)} opacity={hoverSegment && hoverSegment !== segment.name ? 0.28 : 0.9} />
                })}
                {current && barHeight ? <rect x={x} y={base - barHeight} width={barWidth} height={barHeight} rx="2" fill={`url(#${patternId})`} stroke="var(--text)" strokeOpacity=".42" pointerEvents="none" /> : null}
                <rect
                  ref={(node) => { hitRefs.current[index] = node }}
                  className="bar-hit"
                  x={hitX}
                  y="24"
                  width={step}
                  height={base - 24}
                  fill="transparent"
                  role="button"
                  tabIndex={index === safeActiveIndex ? 0 : -1}
                  aria-label={label}
                  onMouseEnter={(event) => showTip(row, index, event.currentTarget)}
                  onClick={(event) => showTip(row, index, event.currentTarget)}
                  onFocus={(event) => showTip(row, index, event.currentTarget)}
                  onBlur={() => setTip(null)}
                  onKeyDown={(event) => onBarKeyDown(event, index)}
                />
                {(mode === 'today' || index % labelEvery === 0 || index === overview.daily.length - 1) ? <text x={x} y={height - 9} fill="var(--faint)" fontSize="10">{row.day.slice(5)}</text> : null}
              </g>
            )
          })}
        </svg>
        <div className="legend2 agent-trend-legend" aria-label={t(view === 'runtime' ? 'agentRankRuntime' : 'agentRankOperator')}>
          {model.legend.map((name) => (
            <button key={name} type="button" className={hoverSegment === name ? 'on' : ''} onMouseEnter={() => setHoverSegment(name)} onMouseLeave={() => setHoverSegment(null)} onFocus={() => setHoverSegment(name)} onBlur={() => setHoverSegment(null)}>
              <span className="sw" style={{ background: colorOf(name) }} />{nameOf(name)}
            </button>
          ))}
        </div>
        <AgentChartTip tip={visibleTip} t={t} />
      </div>
    </section>
  )
}

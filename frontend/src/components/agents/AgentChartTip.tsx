import { useLayoutEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import { dur } from '../../lib/utils'
import type { AgentChartTipModel } from './agentChartSupport'

const TIP_GAP = 10
const VIEWPORT_PAD = 12

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

export function AgentChartTip({ tip, t }: { tip: AgentChartTipModel | null; t: (key: string) => string }) {
  const ref = useRef<HTMLDivElement | null>(null)
  useLayoutEffect(() => {
    if (!tip) return undefined
    const place = () => {
      const element = ref.current
      if (!element) return
      const width = element.offsetWidth
      const height = element.offsetHeight
      let left = tip.anchor.right + TIP_GAP
      if (left + width + VIEWPORT_PAD > window.innerWidth) left = tip.anchor.left - width - TIP_GAP
      element.style.left = `${clamp(left, VIEWPORT_PAD, window.innerWidth - width - VIEWPORT_PAD)}px`
      element.style.top = `${clamp(tip.anchor.chartTop, VIEWPORT_PAD, window.innerHeight - height - VIEWPORT_PAD)}px`
      element.style.visibility = 'visible'
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [tip])

  if (!tip) return null
  const nameOf = (name: string) => name === '__other' ? t('other') : name
  const style: CSSProperties = { display: 'block', left: 0, top: 0, visibility: 'hidden' }
  return (
    <div ref={ref} className="chart-tip agent-chart-tip" style={style}>
      <div className="tip-head">
        <span>{tip.row.day}</span>
        {tip.current ? <span className="tip-live">{t('inProgress')}</span> : null}
      </div>
      {tip.row.segments
        .slice()
        .sort((a, b) => Number(b.active_seconds - a.active_seconds) || a.name.localeCompare(b.name))
        .map((item) => (
          <div className="tip-row" key={item.name}>
            <span className="tip-dot" style={{ background: `var(--agent-segment-${Math.max(0, tip.legend.indexOf(item.name)) % 9})` }} />
            <span className="tip-name">{nameOf(item.name)}</span>
            <span className="tip-val">{dur(item.active_seconds)}</span>
          </div>
        ))}
      <div className="tip-total">
        <span>{t('agentActiveTime')} / {t('agentActiveCount')}</span>
        <b>{dur(tip.row.active_seconds)} / {tip.row.active_agents}</b>
      </div>
    </div>
  )
}

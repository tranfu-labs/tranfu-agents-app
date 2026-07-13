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
  const style: CSSProperties = { display: 'block', left: 0, top: 0, visibility: 'hidden' }
  return (
    <div ref={ref} className="chart-tip agent-chart-tip" style={style}>
      <div className="tip-head">
        <span>{tip.row.day}</span>
        {tip.current ? <span className="tip-live">{t('inProgress')}</span> : null}
      </div>
      <div className="tip-row">
        <span className="tip-dot" style={{ background: 'var(--info)' }} />
        <span className="tip-name">{t('agentActiveCount')}</span>
        <span className="tip-val">{tip.row.active_agents}</span>
      </div>
      <div className="tip-row">
        <span className="tip-dot" style={{ background: 'var(--brand)' }} />
        <span className="tip-name">{t('agentActiveTime')}</span>
        <span className="tip-val">{dur(tip.row.active_seconds)}</span>
      </div>
    </div>
  )
}

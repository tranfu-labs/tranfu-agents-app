import { useLayoutEffect, useState } from 'react'
import type { RefObject } from 'react'
import type { AgentOverview } from '../../lib/types'

type TipAnchor = { left: number; right: number; chartTop: number }
export type AgentChartTipModel = { row: AgentOverview['daily'][number]; current: boolean; anchor: TipAnchor }

const PLOT_TOP = 24

function contentWidthOf(element: HTMLElement) {
  const style = window.getComputedStyle(element)
  const padding = Number.parseFloat(style.paddingLeft || '0') + Number.parseFloat(style.paddingRight || '0')
  return Math.max(0, Math.round(element.clientWidth - padding))
}

export function useAgentChartWidth(ref: RefObject<HTMLElement | null>) {
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return undefined
    const update = () => setWidth(contentWidthOf(element))
    update()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', update)
      return () => window.removeEventListener('resize', update)
    }
    const observer = new ResizeObserver(update)
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return width
}

export function agentChartAnchor(bar: SVGRectElement): TipAnchor {
  const rect = bar.getBoundingClientRect()
  const svg = bar.ownerSVGElement
  const svgRect = svg?.getBoundingClientRect()
  const viewHeight = svg?.viewBox.baseVal.height || svgRect?.height || 1
  const yScale = svgRect ? svgRect.height / viewHeight : 1
  return {
    left: rect.left,
    right: rect.right,
    chartTop: svgRect ? svgRect.top + PLOT_TOP * yScale : rect.top,
  }
}

import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, MouseEvent as ReactMouseEvent } from 'react'
import type { SkillDailyRow, SkillDetail, SkillsOverview } from '../lib/types'
import { apiToday, daySeries, RT, skillColor } from '../lib/utils'

type TipItem = { name: string; value: number; color: string }
type TipAnchor = { left: number; right: number; chartTop: number }
type Tip = { day: string; today?: boolean; items: TipItem[]; total?: number; anchor: TipAnchor }

const PLOT_TOP = 24
const TIP_GAP = 10
const VIEWPORT_PAD = 12

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

function anchorFromBar(event: ReactMouseEvent<SVGRectElement>): TipAnchor {
  const bar = event.currentTarget.getBoundingClientRect()
  const svg = event.currentTarget.ownerSVGElement
  const svgRect = svg?.getBoundingClientRect()
  const viewHeight = svg?.viewBox.baseVal.height || svgRect?.height || 1
  const yScale = svgRect ? svgRect.height / viewHeight : 1
  return {
    left: bar.left,
    right: bar.right,
    chartTop: svgRect ? svgRect.top + PLOT_TOP * yScale : bar.top,
  }
}

function ChartTip({ tip, t }: { tip: Tip | null; t: (key: string) => string }) {
  const tipRef = useRef<HTMLDivElement | null>(null)

  useLayoutEffect(() => {
    if (!tip) return undefined

    const place = () => {
      const el = tipRef.current
      if (!el) return
      const width = el.offsetWidth
      const height = el.offsetHeight
      const viewportWidth = window.innerWidth
      const viewportHeight = window.innerHeight
      let left = tip.anchor.right + TIP_GAP
      if (left + width + VIEWPORT_PAD > viewportWidth) {
        left = tip.anchor.left - width - TIP_GAP
      }
      left = clamp(left, VIEWPORT_PAD, viewportWidth - width - VIEWPORT_PAD)
      const top = clamp(tip.anchor.chartTop, VIEWPORT_PAD, viewportHeight - height - VIEWPORT_PAD)
      el.style.left = `${left}px`
      el.style.top = `${top}px`
      el.style.visibility = 'visible'
    }

    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [tip])

  if (!tip) return null
  const style: CSSProperties = {
    display: 'block',
    left: 0,
    top: 0,
    visibility: 'hidden',
  }
  return (
    <div ref={tipRef} className="chart-tip" style={style}>
      <div className="tip-head">
        <span>{tip.day}</span>
        {tip.today ? <span className="tip-live">{t('inProgress')}</span> : null}
      </div>
      {tip.items.filter((x) => x.value > 0).length ? (
        tip.items
          .filter((x) => x.value > 0)
          .map((x) => (
            <div className="tip-row" key={x.name}>
              <span className="tip-dot" style={{ background: x.color }} />
              <span className="tip-name">{x.name}</span>
              <span className="tip-val">{x.value}</span>
            </div>
          ))
      ) : (
        <div className="tip-empty">{t('noChartData')}</div>
      )}
      {tip.total !== undefined ? (
        <div className="tip-total">
          <span>{t('chartTotal')}</span>
          <b>{tip.total}</b>
        </div>
      ) : null}
    </div>
  )
}

export function StackedSkillChart({ rows, overview, days, t }: { rows: SkillDailyRow[]; overview: SkillsOverview | null; days: number; t: (key: string) => string }) {
  const [hoverSkill, setHoverSkill] = useState<string | null>(null)
  const [tip, setTip] = useState<Tip | null>(null)
  const showTip = (event: ReactMouseEvent<SVGRectElement>, next: Omit<Tip, 'anchor'>) => {
    setTip({ ...next, anchor: anchorFromBar(event) })
  }
  const model = useMemo(() => {
    const axis = daySeries(apiToday(overview), days)
    const daySet = new Set(axis)
    const byDay: Record<string, Record<string, number>> = {}
    const totalBySkill: Record<string, number> = {}
    rows.forEach((row) => {
      if (!daySet.has(row.day)) return
      const value = Number(row.sessions || 0)
      if (!value) return
      const day = (byDay[row.day] = byDay[row.day] || {})
      day[row.skill] = (day[row.skill] || 0) + value
      totalBySkill[row.skill] = (totalBySkill[row.skill] || 0) + value
    })
    const top = Object.entries(totalBySkill)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 8)
      .map(([name]) => name)
    const totals = axis.map((day) => Object.values(byDay[day] || {}).reduce((a, b) => a + b, 0))
    const legend = [...top]
    if (Object.keys(totalBySkill).some((name) => !top.includes(name))) legend.push('__other')
    return { axis, byDay, top, totals, legend }
  }, [days, overview, rows])

  if (!rows.length || !model.totals.some(Boolean)) {
    return (
      <div className="empty">
        <div className="t">{t('noSkills')}</div>
        <div className="h">{t('noSkillsH')}</div>
      </div>
    )
  }

  const max = Math.max(...model.totals, 1)
  const w = Math.max(680, model.axis.length * 28 + 50)
  const h = 220
  const base = 190
  const bh = 165
  const step = (w - 54) / model.axis.length
  const bw = Math.max(8, step - 5)
  const today = model.axis[model.axis.length - 1]
  const patternId = `skillStripe-${days}-${model.axis.length}`

  return (
    <div
      className="chart-box"
      onMouseLeave={() => setTip(null)}
      onPointerDown={(event) => {
        const target = event.target
        if (!(target instanceof SVGElement) || !target.classList.contains('bar-hit')) setTip(null)
      }}
      onScroll={() => setTip(null)}
    >
      <svg className={`skill-chart ${tip ? 'hovering' : ''}`} viewBox={`0 0 ${w} ${h}`} style={{ minWidth: w }} role="img" aria-label={t('dailyUsed')}>
        <defs>
          <pattern id={patternId} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <path d="M 0 0 L 0 6" stroke="var(--text)" strokeOpacity=".22" strokeWidth="2" />
          </pattern>
        </defs>
        <line x1="34" y1={base} x2={w - 12} y2={base} stroke="var(--line2)" />
        <line x1="34" y1="24" x2="34" y2={base} stroke="var(--line2)" />
        <text x="4" y="30" fill="var(--muted)" fontSize="10">
          {t('skillTotal')}
        </text>
        {model.axis.map((day, index) => {
          let y = base
          const x = 38 + index * step
          const raw = model.byDay[day] || {}
          const total = Object.values(raw).reduce((a, b) => a + b, 0)
          const vals: Array<[string, number]> = model.top.map((name) => [name, raw[name] || 0])
          const other = Object.entries(raw)
            .filter(([name]) => !model.top.includes(name))
            .reduce((sum, [, value]) => sum + value, 0)
          if (other) vals.push(['__other', other])
          const items = vals
            .filter(([, value]) => value > 0)
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .map(([name, value]) => ({ name: name === '__other' ? t('other') : name, value, color: skillColor(name) }))
          const totalHeight = total ? Math.max(2, Math.round((total / max) * bh)) : 0
          return (
            <g key={day} className={`day-col ${tip?.day === day ? 'hovered' : ''}`}>
              {vals.map(([name, value]) => {
                if (!value) return null
                const height = Math.max(2, Math.round((value / max) * bh))
                y -= height
                const dim = hoverSkill && !((hoverSkill === '__other' && name === '__other') || hoverSkill === name)
                return <rect key={name} className="bar-seg" x={x} y={y} width={bw} height={height} fill={skillColor(name)} opacity={dim ? 0.45 : 1} />
              })}
              {day === today && totalHeight ? <rect x={x} y={base - totalHeight} width={bw} height={totalHeight} fill={`url(#${patternId})`} stroke="var(--text)" strokeOpacity=".42" strokeWidth="1" pointerEvents="none" /> : null}
              <rect className="bar-hit" x={x} y="24" width={bw} height={base - 24} fill="transparent" onMouseEnter={(event) => showTip(event, { day, today: day === today, items, total })} onClick={(event) => showTip(event, { day, today: day === today, items, total })} />
            </g>
          )
        })}
        {model.axis.map((day, index) => (index % Math.ceil(model.axis.length / 8 || 1) === 0 ? <text key={day} x={38 + index * step} y="211" fill="var(--faint)" fontSize="10">{day.slice(5)}</text> : null))}
      </svg>
      <div className="legend2">
        {model.legend.map((name) => (
          <button key={name} className={hoverSkill === name ? 'on' : ''} onMouseEnter={() => setHoverSkill(name)} onFocus={() => setHoverSkill(name)} onMouseLeave={() => setHoverSkill(null)} onBlur={() => setHoverSkill(null)} onClick={() => setHoverSkill(name)}>
            <span className="sw" style={{ background: skillColor(name) }} />
            {name === '__other' ? t('other') : name}
          </button>
        ))}
      </div>
      <ChartTip tip={tip} t={t} />
    </div>
  )
}

export function MiniTrend({ values }: { values?: number[] }) {
  const max = Math.max(...(values || []), 1)
  return (
    <div className="mini-trend">
      {(values || []).map((value, index) => (
        <i key={index} className={value === max && value ? 'hot' : ''} style={{ height: `${Math.max(2, Math.round((value / max) * 22))}px` }} />
      ))}
    </div>
  )
}

export function RuntimeBars({ counts }: { counts?: Record<string, number> }) {
  const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1])
  const sum = entries.reduce((total, [, value]) => total + value, 0) || 1
  return (
    <div className="runtime-bars">
      {entries.slice(0, 5).map(([key, value]) => (
        <i key={key} style={{ background: skillColor(key), flex: value / sum }} title={`${RT[key] || key}: ${value}`} />
      ))}
    </div>
  )
}

export function DetailTrend({ detail, t }: { detail: SkillDetail; t: (key: string) => string }) {
  const [tip, setTip] = useState<Tip | null>(null)
  const showTip = (event: ReactMouseEvent<SVGRectElement>, next: Omit<Tip, 'anchor'>) => {
    setTip({ ...next, anchor: anchorFromBar(event) })
  }
  const days = daySeries(detail.today || apiToday(detail), 30)
  const byDay: Record<string, { used: number; equipped: number }> = {}
  ;(detail.daily || []).forEach((row) => {
    byDay[row.day] = { used: Number(row.used || 0), equipped: Number(row.equipped || 0) }
  })
  const series = days.map((day) => ({ day, used: byDay[day]?.used || 0, equipped: byDay[day]?.equipped || 0 }))
  const max = Math.max(...series.map((row) => Math.max(row.used, row.equipped)), 1)
  const w = Math.max(680, series.length * 28 + 50)
  const h = 210
  const base = 178
  const bh = 140
  const step = (w - 54) / series.length
  const bw = Math.max(8, step - 5)
  const end = days[days.length - 1]
  const points = series.map((row, index) => {
    const x = 38 + index * step
    const mid = x + bw / 2
    const equippedHeight = Math.round((row.equipped / max) * bh)
    return `${mid},${base - equippedHeight}`
  })

  return (
    <div
      className="chart-box"
      onMouseLeave={() => setTip(null)}
      onPointerDown={(event) => {
        const target = event.target
        if (!(target instanceof SVGElement) || !target.classList.contains('bar-hit')) setTip(null)
      }}
      onScroll={() => setTip(null)}
    >
      <svg className={`skill-chart ${tip ? 'hovering' : ''}`} viewBox={`0 0 ${w} ${h}`} style={{ minWidth: w }}>
        <defs>
          <pattern id="detailStripe" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <path d="M 0 0 L 0 6" stroke="var(--text)" strokeOpacity=".22" strokeWidth="2" />
          </pattern>
        </defs>
        <line x1="34" y1={base} x2={w - 12} y2={base} stroke="var(--line2)" />
        <line x1="34" y1="24" x2="34" y2={base} stroke="var(--line2)" />
        {series.map((row, index) => {
          const x = 38 + index * step
          const mid = x + bw / 2
          const usedHeight = row.used ? Math.max(2, Math.round((row.used / max) * bh)) : 0
          const equippedHeight = Math.round((row.equipped / max) * bh)
          const items = [
            { name: 'used', value: row.used, color: 'var(--info)' },
            { name: 'equipped', value: row.equipped, color: 'var(--wait)' },
          ]
          return (
            <g key={row.day} className={`day-col ${tip?.day === row.day ? 'hovered' : ''}`}>
              <rect className="bar-seg" x={x} y={base - usedHeight} width={bw} height={usedHeight} fill="var(--info)" opacity=".9" />
              {row.day === end && usedHeight ? <rect x={x} y={base - usedHeight} width={bw} height={usedHeight} fill="url(#detailStripe)" stroke="var(--text)" strokeOpacity=".42" strokeWidth="1" pointerEvents="none" /> : null}
              <circle cx={mid} cy={base - equippedHeight} r={row.day === end ? 3.5 : 2.5} fill="var(--wait)" stroke={row.day === end ? 'var(--text)' : 'none'} strokeOpacity=".5" pointerEvents="none" />
              <rect className="bar-hit" x={x} y="24" width={bw} height={base - 24} fill="transparent" onMouseEnter={(event) => showTip(event, { day: row.day, today: row.day === end, items })} onClick={(event) => showTip(event, { day: row.day, today: row.day === end, items })} />
            </g>
          )
        })}
        <polyline points={points.join(' ')} fill="none" stroke="var(--wait)" strokeWidth="2" pointerEvents="none" />
        {series.map((row, index) => (index % Math.ceil(series.length / 8 || 1) === 0 ? <text key={row.day} x={38 + index * step} y="200" fill="var(--faint)" fontSize="10">{row.day.slice(5)}</text> : null))}
      </svg>
      <div className="legend2">
        <button>
          <span className="sw" style={{ background: 'var(--info)' }} />
          used
        </button>
        <button>
          <span className="sw" style={{ background: 'var(--wait)' }} />
          equipped
        </button>
      </div>
      <ChartTip tip={tip} t={t} />
    </div>
  )
}

export function Distribution({ items, labelKey }: { items?: Array<Record<string, string | number | undefined>>; labelKey: 'runtime' | 'operator' }) {
  const max = Math.max(...(items || []).map((item) => Number(item.used || 0) + Number(item.equipped || 0)), 1)
  if (!items?.length) return <div className="hint">none</div>
  return (
    <>
      {items.map((item) => {
        const label = String(item[labelKey] || '')
        const used = Number(item.used || 0)
        const equipped = Number(item.equipped || 0)
        const total = used + equipped
        return (
          <div className="dist-row" key={label}>
            <div className="dist-label">{labelKey === 'runtime' ? RT[label] || label : label}</div>
            <div className="stack-line">
              <i className="used" style={{ width: `${(used / max) * 100}%` }} />
              <i className="equipped" style={{ width: `${(equipped / max) * 100}%` }} />
            </div>
            <div className="dist-num">{total}</div>
          </div>
        )
      })}
    </>
  )
}

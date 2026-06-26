import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Empty, SectionTitle } from '../components/Common'
import { MiniTrend } from '../components/Charts'
import { makeTokenUsageRange, unix } from '../lib/tokenUsageRange'
import type { TokenModelUsage, TokenUsagePayload, TokenUsageQuery, TokenUsageSummary, TokenUsageTrend } from '../lib/types'

type TokenKind = 'personal' | 'dapp' | 'other'
type RiskState = 'normal' | 'low_quota' | 'exhausted' | 'high_error' | 'disabled'
type Tooltip = { x: number; y: number; title: string; rows: Array<{ label: string; value: string; color?: string }> }
type IconName = 'alert' | 'dollar' | 'health' | 'key' | 'model' | 'pie' | 'rank' | 'trend'

const QUOTA_PER_USD = 500000
const COLORS = ['#ef3340', '#e5e7eb', '#7a8190', '#f59e0b', '#0891b2', '#22c55e', '#8b5cf6', '#f97316', '#06b6d4', '#eab308', '#64748b', '#ec4899']
const KIND_CLASS: Record<TokenKind, string> = { personal: 'used', dapp: 'equipped', other: '' }
const PRESETS = [
  ['today', '当日'],
  ['yesterday', '昨天'],
  ['this_week', '本周'],
  ['last_week', '上周'],
  ['7d', '7 天'],
  ['14d', '14 天'],
  ['30d', '30 天'],
  ['custom', '自选时间'],
] as const
const GRANULARITIES = [
  ['hour', '小时'],
  ['four_hour', '4 小时'],
  ['day', '天'],
  ['week', '周'],
  ['month', '月'],
] as const

function n(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(Math.round(Number(value || 0)))
}

function shortN(value?: number) {
  return new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(Number(value || 0))
}

function quotaToUsd(value?: number) {
  return Number(value || 0) / QUOTA_PER_USD
}

function moneyUsd(value?: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0))
}

function moneyFromQuota(value?: number) {
  return moneyUsd(quotaToUsd(value))
}

function shortMoneyFromQuota(value?: number) {
  const usd = quotaToUsd(value)
  if (Math.abs(usd) >= 100000) {
    return `$${new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(usd)}`
  }
  return moneyUsd(usd)
}

function pct(value: number) {
  return `${Math.round(value * 1000) / 10}%`
}

function ts(value?: number) {
  if (!value) return '—'
  return new Date(value * 1000).toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function bucketLabel(value?: number, granularity?: string) {
  if (!value) return ''
  const date = new Date(value * 1000)
  if (granularity === 'hour' || granularity === 'four_hour') return date.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit' })
  if (granularity === 'month') return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit' })
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' })
}

function normalized(text?: string) {
  return String(text || '').trim().toLowerCase()
}

function toInputValue(timestamp: number) {
  const date = new Date(timestamp * 1000)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

function fromInputValue(value: string, fallback: number) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? fallback : unix(date)
}

function inferKind(row: TokenUsageSummary): TokenKind {
  const group = normalized(row.group)
  const name = normalized(row.token_name)
  if (/(dapp|app|应用|项目|product|prod|production)/i.test(group) || /^(dapp|app|应用|项目)[-_/|｜\s]/i.test(name)) return 'dapp'
  if (/(personal|person|individual|member|user|个人|成员)/i.test(group) || /^(个人|成员|personal|user)[-_/|｜\s]/i.test(name)) return 'personal'
  return 'other'
}

function inferOwner(row: TokenUsageSummary, kind: TokenKind) {
  const parts = String(row.token_name || '').split(/[-_/|｜·\s]+/).map((part) => part.trim()).filter(Boolean)
  if (parts.length >= 2 && ['个人', '成员', 'personal', 'user', 'dapp', 'app', '应用', '项目'].includes(parts[0].toLowerCase())) return parts[1]
  if (parts.length >= 2) return parts[0]
  if (row.username) return row.username
  return kind === 'dapp' ? row.token_name || 'Dapp' : row.token_name || '—'
}

function riskOf(row: TokenUsageSummary): RiskState {
  const requests = Number(row.request_count || 0)
  const errors = Number(row.error_count || 0)
  const errorRate = errors / Math.max(1, requests + errors)
  if (row.status !== undefined && row.status !== 1) return 'disabled'
  if (!row.unlimited_quota && Number(row.remain_quota || 0) <= 0) return 'exhausted'
  if (errorRate >= 0.2 && errors >= 3) return 'high_error'
  if (!row.unlimited_quota) {
    const remain = Number(row.remain_quota || 0)
    const total = remain + Number(row.used_quota || 0)
    if (remain > 0 && total > 0 && remain / total < 0.1) return 'low_quota'
  }
  return 'normal'
}

function riskLabel(risk: RiskState, t: (key: string) => string) {
  return risk === 'low_quota' ? t('tokenLowQuota') : risk === 'exhausted' ? t('tokenExhausted') : risk === 'high_error' ? t('tokenHighError') : risk === 'disabled' ? t('tokenDisabled') : t('tokenNormal')
}

function kindLabel(kind: TokenKind, t: (key: string) => string) {
  return kind === 'personal' ? t('tokenPersonal') : kind === 'dapp' ? t('tokenDapp') : t('tokenOtherType')
}

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    alert: <path d="M12 4 3.5 19h17L12 4Zm0 5v4m0 3h.01" />,
    dollar: <path d="M12 3v18m4-14.5H9.5a3 3 0 0 0 0 6H14a3 3 0 0 1 0 6H7.5" />,
    health: <path d="M20 8.5c0 5.5-8 10.5-8 10.5S4 14 4 8.5A4.5 4.5 0 0 1 12 5a4.5 4.5 0 0 1 8 3.5Z M7.5 12h2l1.2-2.2 2.2 5 1.4-2.8h2.2" />,
    key: <path d="M14.5 6.5a4.5 4.5 0 1 0 2.7 8.1L21 18.4V21h-2.6l-1.3-1.3h-2.2v-2.2l-1.2-1.2a4.5 4.5 0 0 0 .8-9.8Z M7.5 10.5h.01" />,
    model: <path d="M4 6.5 12 3l8 3.5v10L12 21l-8-4.5v-10Zm8 5L4.5 7.2M12 11.5l7.5-4.3M12 11.5V20" />,
    pie: <path d="M11 3a9 9 0 1 0 9 9h-9V3Zm3 0v6h6a7 7 0 0 0-6-6Z" />,
    rank: <path d="M4 19h16M6 16V9m6 7V5m6 11v-4" />,
    trend: <path d="M4 17 9 11l4 3 7-8M16 6h4v4" />,
  }
  return (
    <span className="token-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24">
        <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8">
          {paths[name]}
        </g>
      </svg>
    </span>
  )
}

function ChartHeading({ icon, title, total }: { icon: IconName; title: string; total?: string }) {
  return (
    <div className="token-chart-copy">
      <b><Icon name={icon} />{title}</b>
      {total ? <span>{total}</span> : null}
    </div>
  )
}

function enrichRows(rows: TokenUsageSummary[], trends: TokenUsageTrend[]) {
  const trendByKey = new Map<number, number[]>()
  trends.forEach((row) => {
    const list = trendByKey.get(row.token_id) || []
    list.push(quotaToUsd(row.quota))
    trendByKey.set(row.token_id, list)
  })
  return rows.map((row) => {
    const kind = inferKind(row)
    return { ...row, kind, owner: inferOwner(row, kind), risk: riskOf(row), trendValues: (trendByKey.get(row.token_id) || []).slice(-14) }
  })
}

function ChartTip({ tip }: { tip: Tooltip | null }) {
  const ref = useRef<HTMLDivElement | null>(null)

  useLayoutEffect(() => {
    if (!tip) return undefined
    const place = () => {
      const el = ref.current
      if (!el) return
      const width = el.offsetWidth
      const height = el.offsetHeight
      const pad = 12
      let left = tip.x + 12
      let top = tip.y + 12
      if (left + width + pad > window.innerWidth) left = tip.x - width - 12
      if (top + height + pad > window.innerHeight) top = tip.y - height - 12
      left = Math.max(pad, Math.min(left, window.innerWidth - width - pad))
      top = Math.max(pad, Math.min(top, window.innerHeight - height - pad))
      el.style.left = `${left}px`
      el.style.top = `${top}px`
      el.style.visibility = 'visible'
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [tip])

  if (!tip) return null
  const style: CSSProperties = { left: 0, top: 0, visibility: 'hidden' }
  return (
    <div ref={ref} className="token-hover-tip" style={style}>
      <b>{tip.title}</b>
      {tip.rows.map((row) => (
        <div className="token-tip-row" key={row.label}>
          {row.color ? <span style={{ background: row.color }} /> : <i />}
          <em>{row.label}</em>
          <strong>{row.value}</strong>
        </div>
      ))}
    </div>
  )
}

function LoadingNotice({ hasData }: { hasData: boolean }) {
  return (
    <div className={`token-loading ${hasData ? 'compact' : ''}`}>
      <span className="token-spinner" />
      <div>
        <b>{hasData ? '正在更新图表' : '正在读取分发平台 KEY 用量'}</b>
        <p>{hasData ? '当前数据会先保留，新的筛选结果返回后自动替换。' : '首次打开需要连接分发平台，通常几秒内完成。'}</p>
      </div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="token-skeleton-grid">
      {Array.from({ length: 6 }).map((_, index) => <span key={index} />)}
    </div>
  )
}

function useDismissTipOnScroll(setTip: (tip: Tooltip | null) => void) {
  useEffect(() => {
    const clear = () => setTip(null)
    window.addEventListener('scroll', clear, { passive: true })
    return () => window.removeEventListener('scroll', clear)
  }, [setTip])
}

function KeyRankBars({ rows, t }: { rows: ReturnType<typeof enrichRows>; t: (key: string) => string }) {
  const [tip, setTip] = useState<Tooltip | null>(null)
  useDismissTipOnScroll(setTip)
  const list = rows.slice(0, 14)
  const total = rows.reduce((sum, row) => sum + Number(row.quota || 0), 0)
  const max = Math.max(...list.map((row) => Number(row.quota || 0)), 1)
  if (!list.length) return <Empty title={t('tokenNoData')} hint={t('tokenNoDataHint')} />
  return (
    <div className="token-rank-chart" onMouseLeave={() => setTip(null)}>
      <ChartHeading icon="rank" title="KEY 消耗排行" total={`总计：${moneyFromQuota(total)}`} />
      {list.map((row, index) => {
        const value = Number(row.quota || 0)
        const color = COLORS[index % COLORS.length]
        return (
          <div
            className="token-rank-row"
            key={row.token_id || row.token_name}
            onMouseMove={(event) => setTip({ x: event.clientX, y: event.clientY, title: row.token_name || `#${row.token_id}`, rows: [
              { label: '消耗金额', value: moneyFromQuota(value), color },
              { label: 'Token 数', value: n(row.token_used) },
              { label: '请求数', value: n(row.request_count) },
              { label: '类型', value: kindLabel(row.kind, t) },
              { label: '常用模型', value: row.top_model || '—' },
            ] })}
          >
            <span className="token-rank-name">{row.token_name || `#${row.token_id}`}</span>
            <div className="token-rank-track">
              <i style={{ width: `${Math.max(1, (value / max) * 100)}%`, background: color }} />
            </div>
            <strong style={{ color }}>{shortMoneyFromQuota(value)}</strong>
          </div>
        )
      })}
      <ChartTip tip={tip} />
    </div>
  )
}

function UsageTrendLines({ rows, keys, granularity, t }: { rows: TokenUsageTrend[]; keys: ReturnType<typeof enrichRows>; granularity?: string; t: (key: string) => string }) {
  const [tip, setTip] = useState<Tooltip | null>(null)
  const chartRef = useRef<HTMLDivElement | null>(null)
  const [chartWidth, setChartWidth] = useState(1160)
  useDismissTipOnScroll(setTip)
  useLayoutEffect(() => {
    const el = chartRef.current
    if (!el) return undefined
    const updateWidth = () => {
      const width = Math.max(860, Math.round(el.getBoundingClientRect().width))
      setChartWidth((previous) => (Math.abs(previous - width) > 1 ? width : previous))
    }
    updateWidth()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateWidth)
      return () => window.removeEventListener('resize', updateWidth)
    }
    const observer = new ResizeObserver(updateWidth)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const topKeys = keys.slice(0, 10)
  const buckets = [...new Set(rows.map((row) => row.created_at))].sort((a, b) => a - b)
  if (!buckets.length || !topKeys.length) return <Empty title={t('tokenNoData')} hint={t('tokenNoDataHint')} />
  const byBucket = new Map<number, Map<number, number>>()
  rows.forEach((row) => {
    const item = byBucket.get(row.created_at) || new Map<number, number>()
    item.set(row.token_id, (item.get(row.token_id) || 0) + quotaToUsd(row.quota))
    byBucket.set(row.created_at, item)
  })
  const w = chartWidth
  const h = 300
  const left = 76
  const right = 18
  const top = 30
  const plotW = w - left - right
  const plotH = 210
  const max = Math.max(...topKeys.flatMap((key) => buckets.map((bucket) => byBucket.get(bucket)?.get(key.token_id) || 0)), 1)
  const x = (index: number) => left + (buckets.length === 1 ? 0 : (index / (buckets.length - 1)) * plotW)
  const y = (value: number) => top + plotH - (value / max) * plotH
  const hitW = Math.max(8, Math.min(36, plotW / Math.max(1, buckets.length)))
  const pointRows = (bucket: number) => topKeys
    .map((key, index) => ({ key, color: COLORS[index % COLORS.length], value: byBucket.get(bucket)?.get(key.token_id) || 0 }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value)
  const total = rows.reduce((sum, row) => sum + quotaToUsd(row.quota), 0)
  return (
    <div ref={chartRef} className="chart-box token-line-chart" onMouseLeave={() => setTip(null)}>
      <ChartHeading icon="trend" title="KEY 使用趋势" total={`总计：${moneyUsd(total)}`} />
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="KEY 使用趋势">
        <line x1={left} y1={top + plotH} x2={left + plotW} y2={top + plotH} stroke="var(--line2)" />
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <g key={tick}>
            <line x1={left} y1={top + plotH - tick * plotH} x2={left + plotW} y2={top + plotH - tick * plotH} stroke="var(--line)" />
            <text x="18" y={top + plotH - tick * plotH + 4} fill="var(--faint)" fontSize="11">{moneyUsd(max * tick)}</text>
          </g>
        ))}
        {topKeys.map((key, keyIndex) => {
          const color = COLORS[keyIndex % COLORS.length]
          const path = buckets.map((bucket, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(byBucket.get(bucket)?.get(key.token_id) || 0)}`).join(' ')
          return <path key={key.token_id || key.token_name} d={path} fill="none" stroke={color} strokeWidth="2" opacity=".86" />
        })}
        {buckets.map((bucket, index) => (
          <g key={bucket}>
            {index % Math.max(1, Math.ceil(buckets.length / 9)) === 0 ? <text x={x(index) - 12} y={top + plotH + 30} fill="var(--faint)" fontSize="11">{bucketLabel(bucket, granularity)}</text> : null}
            <rect
              x={x(index) - hitW / 2}
              y={top}
              width={hitW}
              height={plotH}
              fill="transparent"
              onMouseMove={(event) => {
                const items = pointRows(bucket)
                const totalValue = items.reduce((sum, item) => sum + item.value, 0)
                setTip({ x: event.clientX, y: event.clientY, title: bucketLabel(bucket, granularity), rows: [
                  { label: '总计', value: moneyUsd(totalValue) },
                  ...items.map((item) => ({ label: item.key.token_name || `#${item.key.token_id}`, value: moneyUsd(item.value), color: item.color })),
                ] })
              }}
            />
          </g>
        ))}
      </svg>
      <div className="token-chart-legend">
        {topKeys.map((key, index) => (
          <span key={key.token_id || key.token_name} title={key.token_name || `#${key.token_id}`}>
            <i style={{ background: COLORS[index % COLORS.length] }} />
            {key.token_name || `#${key.token_id}`}
          </span>
        ))}
      </div>
      <ChartTip tip={tip} />
    </div>
  )
}

function arc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = ((startAngle - 90) * Math.PI) / 180
  const end = ((endAngle - 90) * Math.PI) / 180
  const x1 = cx + r * Math.cos(start)
  const y1 = cy + r * Math.sin(start)
  const x2 = cx + r * Math.cos(end)
  const y2 = cy + r * Math.sin(end)
  return `M ${x1} ${y1} A ${r} ${r} 0 ${endAngle - startAngle > 180 ? 1 : 0} 1 ${x2} ${y2}`
}

function DonutChart({ title, icon, items }: { title: string; icon: IconName; items: Array<{ label: string; value: number; color: string }> }) {
  const [tip, setTip] = useState<Tooltip | null>(null)
  useDismissTipOnScroll(setTip)
  const total = items.reduce((sum, item) => sum + item.value, 0)
  if (!total) return <Empty title={title} hint="暂无数据" />
  const segments = items.reduce<Array<{ item: (typeof items)[number]; start: number; end: number }>>((list, item) => {
    const start = list.length ? list[list.length - 1].end : 0
    const end = start + (item.value / total) * 359.9
    return [...list, { item, start, end }]
  }, [])
  return (
    <div className="token-donut" onMouseLeave={() => setTip(null)}>
      <div className="token-donut-title"><Icon name={icon} />{title}</div>
      <svg viewBox="0 0 220 170" role="img" aria-label={title}>
        <text x="14" y="42" fill="var(--text)" fontSize="18" fontFamily="var(--mono)">{moneyFromQuota(total)}</text>
        {segments.map(({ item, start, end }) => {
          return (
            <path
              key={item.label}
              d={arc(84, 100, 45, start, end)}
              fill="none"
              stroke={item.color}
              strokeWidth="22"
              strokeLinecap="round"
              onMouseMove={(event) => setTip({ x: event.clientX, y: event.clientY, title: item.label, rows: [
                { label: '消耗金额', value: moneyFromQuota(item.value), color: item.color },
                { label: '占比', value: pct(item.value / total) },
              ] })}
            />
          )
        })}
      </svg>
      <div className="token-donut-legend">
        {items.slice(0, 6).map((item) => <span key={item.label}><i style={{ background: item.color }} />{item.label}<b>{pct(item.value / total)}</b></span>)}
      </div>
      <ChartTip tip={tip} />
    </div>
  )
}

function HealthPanel({ rows, metrics }: { rows: ReturnType<typeof enrichRows>; metrics: { requests: number; errors: number; tokenUsed: number } }) {
  const total = metrics.requests + metrics.errors
  const successRate = metrics.requests / Math.max(1, total)
  const latencyWeight = rows.reduce((sum, row) => sum + Number(row.avg_use_time || 0) * Number(row.request_count || 0), 0)
  const avgLatency = latencyWeight / Math.max(1, metrics.requests)
  const throughput = metrics.tokenUsed / Math.max(1, latencyWeight)
  const modelHealth = [...rows.reduce((map, row) => {
    const name = row.top_model || 'unknown'
    const item = map.get(name) || { name, requests: 0, errors: 0 }
    item.requests += Number(row.request_count || 0)
    item.errors += Number(row.error_count || 0)
    map.set(name, item)
    return map
  }, new Map<string, { name: string; requests: number; errors: number }>()).values()].sort((a, b) => b.requests - a.requests).slice(0, 5)
  return (
    <section className="frame token-health">
      <div className="token-health-core">
        <b><Icon name="health" />性能健康</b>
        <span>成功率 <strong className={successRate < 0.9 ? 'bad' : 'good'}>{pct(successRate)}</strong></span>
        <span>平均延迟 <strong>{avgLatency.toFixed(2)}s</strong></span>
        <span>吞吐量 <strong>{shortN(throughput)} t/s</strong></span>
      </div>
      <div className="token-model-health">
        {modelHealth.map((item) => {
          const rate = item.requests / Math.max(1, item.requests + item.errors)
          return <span key={item.name}>{item.name} <i className={rate < 0.9 ? 'bad' : 'good'} /> <b>{pct(rate)}</b></span>
        })}
      </div>
    </section>
  )
}

function ModelRows({ rows, t }: { rows: TokenModelUsage[]; t: (key: string) => string }) {
  const modelRows = useMemo(() => {
    const map = new Map<string, { model_name: string; count: number; quota: number; token_used: number }>()
    rows.forEach((row) => {
      const item = map.get(row.model_name) || { model_name: row.model_name, count: 0, quota: 0, token_used: 0 }
      item.count += Number(row.count || 0)
      item.quota += Number(row.quota || 0)
      item.token_used += Number(row.token_used || 0)
      map.set(row.model_name, item)
    })
    return [...map.values()].sort((a, b) => b.quota - a.quota).slice(0, 10)
  }, [rows])
  if (!modelRows.length) return <Empty title={t('tokenNoData')} hint={t('tokenNoDataHint')} />
  return (
    <div className="skills-wrap">
      <table>
        <thead><tr><th>{t('models')}</th><th className="num">消耗金额</th><th className="num">{t('tokenTokens')}</th><th className="num">{t('tokenRequests')}</th></tr></thead>
        <tbody>
          {modelRows.map((row) => <tr key={row.model_name}><td><b>{row.model_name}</b></td><td className="num">{moneyFromQuota(row.quota)}</td><td className="num">{n(row.token_used)}</td><td className="num">{n(row.count)}</td></tr>)}
        </tbody>
      </table>
    </div>
  )
}

export function TokenUsageView({
  data,
  loading,
  error,
  query,
  setQuery,
  refresh,
  t,
}: {
  data: TokenUsagePayload | null
  loading: boolean
  error: string
  query: TokenUsageQuery
  setQuery: (query: TokenUsageQuery) => void
  refresh: (force?: boolean) => Promise<void>
  t: (key: string) => string
}) {
  const [kind, setKind] = useState<'all' | TokenKind>('all')
  const [model, setModel] = useState('all')
  const [risk, setRisk] = useState<'all' | RiskState>('all')
  const [q, setQ] = useState('')
  const [ignoredRisks, setIgnoredRisks] = useState<Set<number>>(() => {
    try {
      return new Set(JSON.parse(window.localStorage.getItem('token-usage-ignored-risks') || '[]') as number[])
    } catch {
      return new Set()
    }
  })
  const payload = data?.data
  const enriched = useMemo(() => enrichRows(payload?.summary || [], payload?.trend || []), [payload])
  const models = useMemo(() => [...new Set((payload?.models || []).map((row) => row.model_name).filter(Boolean))].sort(), [payload])
  const matchingTokenIds = useMemo(() => {
    let rows = enriched
    const queryText = normalized(q)
    if (kind !== 'all') rows = rows.filter((row) => row.kind === kind)
    if (risk !== 'all') rows = rows.filter((row) => row.risk === risk)
    if (queryText) rows = rows.filter((row) => normalized(`${row.token_name} ${row.owner} ${row.username}`).includes(queryText))
    if (model !== 'all') {
      const ids = new Set((payload?.models || []).filter((row) => row.model_name === model).map((row) => row.token_id))
      rows = rows.filter((row) => ids.has(row.token_id))
    }
    return new Set(rows.map((row) => row.token_id))
  }, [enriched, kind, model, payload, q, risk])
  const filteredRows = useMemo(() => enriched.filter((row) => matchingTokenIds.has(row.token_id)).sort((a, b) => Number(b.quota || 0) - Number(a.quota || 0)), [enriched, matchingTokenIds])
  const filteredTrend = useMemo(() => (payload?.trend || []).filter((row) => matchingTokenIds.has(row.token_id)), [matchingTokenIds, payload])
  const filteredModels = useMemo(() => (payload?.models || []).filter((row) => matchingTokenIds.has(row.token_id) && (model === 'all' || row.model_name === model)), [matchingTokenIds, model, payload])
  const metrics = useMemo(() => {
    const quota = filteredRows.reduce((sum, row) => sum + Number(row.quota || 0), 0)
    const tokenUsed = filteredRows.reduce((sum, row) => sum + Number(row.token_used || 0), 0)
    const requests = filteredRows.reduce((sum, row) => sum + Number(row.request_count || 0), 0)
    const errors = filteredRows.reduce((sum, row) => sum + Number(row.error_count || 0), 0)
    const riskCount = filteredRows.filter((row) => row.risk !== 'normal').length
    return { quota, tokenUsed, requests, errors, active: filteredRows.filter((row) => Number(row.request_count || 0) > 0).length, errorRate: errors / Math.max(1, requests + errors), riskCount }
  }, [filteredRows])
  const allRiskRows = filteredRows.filter((row) => row.risk !== 'normal')
  const riskRows = allRiskRows.filter((row) => !ignoredRisks.has(row.token_id)).slice(0, 8)
  const typeItems = useMemo(() => {
    const map = new Map<TokenKind, number>()
    filteredRows.forEach((row) => map.set(row.kind, (map.get(row.kind) || 0) + Number(row.quota || 0)))
    return [...map.entries()].map(([name, value], index) => ({ label: kindLabel(name, t), value, color: COLORS[index % COLORS.length] })).filter((item) => item.value > 0)
  }, [filteredRows, t])
  const modelItems = useMemo(() => {
    const map = new Map<string, number>()
    filteredModels.forEach((row) => map.set(row.model_name, (map.get(row.model_name) || 0) + Number(row.quota || 0)))
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([label, value], index) => ({ label, value, color: COLORS[(index + 4) % COLORS.length] }))
  }, [filteredModels])
  const applyPreset = (preset: string) => setQuery(makeTokenUsageRange(preset, query.timeGranularity))
  const updateCustom = (field: 'startTimestamp' | 'endTimestamp', value: string) => setQuery({ ...query, preset: 'custom', [field]: fromInputValue(value, query[field]) })
  const ignoreRisk = (tokenId: number) => {
    setIgnoredRisks((old) => {
      const next = new Set(old)
      next.add(tokenId)
      window.localStorage.setItem('token-usage-ignored-risks', JSON.stringify([...next]))
      return next
    })
  }
  const clearIgnoredRisks = () => {
    window.localStorage.removeItem('token-usage-ignored-risks')
    setIgnoredRisks(new Set())
  }
  const isInitialLoading = loading && !payload
  const statusLabel = data?.source === 'demo' ? 'DEMO' : data?.configured ? (loading && payload ? 'LIVE · loading' : 'LIVE') : undefined

  return (
    <div className="token-page">
      <section className="frame">
        <SectionTitle title={t('tokenUsageTitle')} count={statusLabel} />
        <div className="usage-note">
          {data?.source === 'demo' ? t('tokenUsageDemo') : data?.configured ? t('tokenUsageConfigured') : t('tokenUsageHint')}
          {data?.warning ? <span className="src"> · {data.warning}</span> : null}
        </div>
        <div className="toolbar token-toolbar">
          <label className="field">
            时间范围
            <select value={query.preset} onChange={(event) => applyPreset(event.target.value)}>
              {PRESETS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          <label className="field">
            图表维度
            <select value={query.timeGranularity} onChange={(event) => setQuery({ ...query, timeGranularity: event.target.value as TokenUsageQuery['timeGranularity'] })}>
              {GRANULARITIES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          {query.preset === 'custom' ? (
            <>
              <label className="field token-datetime">开始<input type="datetime-local" value={toInputValue(query.startTimestamp)} onChange={(event) => updateCustom('startTimestamp', event.target.value)} /></label>
              <label className="field token-datetime">结束<input type="datetime-local" value={toInputValue(query.endTimestamp)} onChange={(event) => updateCustom('endTimestamp', event.target.value)} /></label>
            </>
          ) : null}
          <label className="field">
            {t('tokenKind')}
            <select value={kind} onChange={(event) => setKind(event.target.value as 'all' | TokenKind)}>
              <option value="all">{t('tokenAllKinds')}</option>
              <option value="personal">{t('tokenPersonal')}</option>
              <option value="dapp">{t('tokenDapp')}</option>
              <option value="other">{t('tokenOtherType')}</option>
            </select>
          </label>
          <label className="field">
            {t('models')}
            <select value={model} onChange={(event) => setModel(event.target.value)}>
              <option value="all">{t('tokenAllModels')}</option>
              {models.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="field">
            {t('tokenStatus')}
            <select value={risk} onChange={(event) => setRisk(event.target.value as 'all' | RiskState)}>
              <option value="all">{t('all')}</option>
              <option value="normal">{t('tokenNormal')}</option>
              <option value="low_quota">{t('tokenLowQuota')}</option>
              <option value="exhausted">{t('tokenExhausted')}</option>
              <option value="high_error">{t('tokenHighError')}</option>
              <option value="disabled">{t('tokenDisabled')}</option>
            </select>
          </label>
          <label className="field token-search">{t('adminSearch')}<input value={q} onChange={(event) => setQ(event.target.value)} placeholder={t('tokenSearch')} /></label>
          <button className="btn mini token-refresh" type="button" disabled={loading} onClick={() => void refresh(true)}>{loading ? t('loading') : t('refresh')}</button>
        </div>
      </section>

      {error ? <div className="note-warn">{t(error)}</div> : null}
      {isInitialLoading ? <LoadingNotice hasData={false} /> : null}
      {isInitialLoading ? <LoadingSkeleton /> : null}

      {!isInitialLoading ? (
        <>
      <div className="statgrid token-stats token-data-section">
        <div className="stat"><div className="v">{moneyFromQuota(metrics.quota)}</div><div className="l">消耗金额</div></div>
        <div className="stat"><div className="v">{shortN(metrics.tokenUsed)}</div><div className="l">{t('tokenTokens')}</div></div>
        <div className="stat"><div className="v">{n(metrics.requests)}</div><div className="l">{t('tokenRequests')}</div></div>
        <div className="stat"><div className="v">{n(metrics.active)}</div><div className="l">{t('tokenActiveKeys')}</div></div>
        <div className="stat"><div className="v">{pct(metrics.errorRate)}</div><div className="l">{t('tokenErrors')}</div></div>
        <div className="stat"><div className="v">{n(metrics.riskCount)}</div><div className="l">{t('tokenRisk')}</div></div>
      </div>

      <HealthPanel rows={filteredRows} metrics={metrics} />

      <div className="split token-split">
        <section className="frame"><KeyRankBars rows={filteredRows} t={t} /></section>
        <section className="frame">
          <div className="token-panel-title">
            <span><Icon name="alert" />{t('tokenRisks')}</span>
            <div>
              {ignoredRisks.size ? <button className="token-link-btn" type="button" onClick={clearIgnoredRisks}>恢复已忽略</button> : null}
              <b>{riskRows.length}</b>
            </div>
          </div>
          {riskRows.length ? (
            <div className="token-risk-list">
              {riskRows.map((row) => (
                <div className="token-risk" key={row.token_id}>
                  <span className={`dot risk-${row.risk}`} />
                  <div><b>{row.token_name}</b><p>{riskLabel(row.risk, t)} · {kindLabel(row.kind, t)} · {row.owner}</p></div>
                  <span className="mono">{moneyFromQuota(row.quota)}</span>
                  <button className="token-risk-dismiss" type="button" onClick={() => ignoreRisk(row.token_id)}>忽略</button>
                </div>
              ))}
            </div>
          ) : <Empty title={allRiskRows.length ? '当前风险已忽略' : t('tokenNormal')} hint={allRiskRows.length ? '可点击恢复已忽略重新显示。' : t('tokenNoDataHint')} />}
        </section>
      </div>

      <section className="frame">
        <UsageTrendLines rows={filteredTrend} keys={filteredRows} granularity={data?.range?.time_granularity} t={t} />
      </section>

      <div className="split token-split">
        <section className="frame token-donut-grid">
          <DonutChart title="类型消耗占比" icon="pie" items={typeItems} />
          <DonutChart title="模型消耗占比" icon="model" items={modelItems} />
        </section>
        <section className="frame">
          <SectionTitle title={t('tokenModels')} count={filteredModels.length} />
          <ModelRows rows={filteredModels} t={t} />
        </section>
      </div>

      <section className="frame">
        <SectionTitle title={t('tokenKeys')} count={filteredRows.length} />
        {filteredRows.length ? (
          <div className="skills-wrap">
            <table className="token-table">
              <thead><tr><th>{t('tokenKeyName')}</th><th>{t('tokenKind')}</th><th>{t('tokenOwner')}</th><th className="num">消耗金额</th><th className="num">{t('tokenRequests')}</th><th>{t('tokenTopModel')}</th><th>{t('tokenRemain')}</th><th>{t('trend')}</th><th>{t('tokenStatus')}</th><th>{t('tokenLastUsed')}</th></tr></thead>
              <tbody>
                {filteredRows.map((row) => (
                  <tr key={row.token_id}>
                    <td><b>{row.token_name || `#${row.token_id}`}</b><div className="q">{row.username || '—'}</div></td>
                    <td><span className={`mode-badge ${KIND_CLASS[row.kind]}`}>{kindLabel(row.kind, t)}</span></td>
                    <td>{row.owner}</td>
                    <td className="num">{moneyFromQuota(row.quota)}</td>
                    <td className="num">{n(row.request_count)}</td>
                    <td className="q">{row.top_model || '—'}</td>
                    <td className="q">{row.unlimited_quota ? t('tokenUnlimited') : moneyFromQuota(row.remain_quota)}</td>
                    <td><MiniTrend values={row.trendValues} /></td>
                    <td><span className={`status-pill risk-${row.risk}`}>{riskLabel(row.risk, t)}</span></td>
                    <td className="q">{ts(row.last_used_at || row.accessed_time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty title={t('tokenNoData')} hint={t('tokenNoDataHint')} />}
      </section>
        </>
      ) : null}
    </div>
  )
}

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Empty, SectionTitle } from '../components/Common'
import { MiniTrend } from '../components/Charts'
import { fetchTokenUsageErrors } from '../lib/api'
import { unix } from '../lib/tokenUsageRange'
import { normalizeTokenUsageFilters, resolveTokenUsageModel, tokenUsageCustomRangeIssue, tokenUsagePayloadMatchesQuery, tokenUsagePresetPatch } from '../lib/tokenUsageQuery'
import type { SetTokenUsageQueryState, TokenUsageQueryState, TokenUsageSortField } from '../lib/tokenUsageQuery'
import type { TokenModelUsage, TokenUsageErrorsPayload, TokenUsagePayload, TokenUsageQuery, TokenUsageSummary, TokenUsageTrend } from '../lib/types'

type TokenKind = 'personal' | 'dapp' | 'other'
type RiskState = 'normal' | 'low_quota' | 'exhausted' | 'high_error' | 'disabled' | 'spike' | 'high_latency' | 'restricted_model'
type RiskSeverity = 'info' | 'warn' | 'bad'
type RiskAlert = { id: string; token_id: number; token_name: string; state: RiskState; severity: RiskSeverity; title: string; detail: string; quota: number }
type EnrichedTokenRow = TokenUsageSummary & { kind: TokenKind; owner: string; risk: RiskState; riskReasons: RiskAlert[]; trendValues: number[] }
type SortState = { field: TokenUsageSortField; dir: 'asc' | 'desc' }
type Tooltip = { x: number; y: number; title: string; rows: Array<{ label: string; value: string; color?: string }> }
type IconName = 'alert' | 'dollar' | 'health' | 'key' | 'model' | 'pie' | 'rank' | 'trend'
type DonutItem = { label: string; value: number; color: string; count?: number; requests?: number; errors?: number; tokenUsed?: number }
type GroupBreakdownItem = DonutItem & { rows: EnrichedTokenRow[]; models: TokenModelUsage[] }

const QUOTA_PER_USD = 500000
const COLORS = ['#ef3340', '#e5e7eb', '#7a8190', '#f59e0b', '#0891b2', '#22c55e', '#8b5cf6', '#f97316', '#06b6d4', '#eab308', '#64748b', '#ec4899']
const KIND_CLASS: Record<TokenKind, string> = { personal: 'kind-personal', dapp: 'kind-dapp', other: 'kind-other' }
const KIND_DONUT_COLORS: Record<'personal' | 'dapp', string> = { personal: '#38bdf8', dapp: '#a78bfa' }
const GROUP_COLORS: Record<string, string> = { TranFu: '#ef3340', Dapp: '#a78bfa', EVM: '#06b6d4', '量化': '#f59e0b', '未分组': '#64748b' }
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

function signedPct(value: number) {
  if (!Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${pct(value)}`
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

function bucketTooltipLabel(value?: number, granularity?: string) {
  if (!value) return ''
  const date = new Date(value * 1000)
  if (granularity === 'month') return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit' })
  if (granularity === 'week') return `${date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit' })} 周`
  return date.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit' })
}

function normalized(text?: string) {
  return String(text || '').trim().toLowerCase()
}

function tokenGroupLabel(row: TokenUsageSummary) {
  const raw = String(row.group || '').trim()
  const value = normalized(raw)
  if (!raw) return '未分组'
  if (/^(个人|personal|person|individual|member|user|tranfu)$/i.test(raw) || value === '个人') return 'TranFu'
  if (/^dapp$/i.test(raw) || value === 'dapp') return 'Dapp'
  if (/^evm$/i.test(raw)) return 'EVM'
  if (raw === '量化' || /(quant|quantitative|量化)/i.test(raw)) return '量化'
  return raw
}

function groupColor(label: string, index: number) {
  return GROUP_COLORS[label] || COLORS[index % COLORS.length]
}

function toInputValue(timestamp: string) {
  if (!timestamp || !/^\d+$/.test(timestamp)) return ''
  const date = new Date(Number(timestamp) * 1000)
  if (Number.isNaN(date.getTime())) return ''
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

function fromInputValue(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : String(unix(date))
}

function inferKind(row: TokenUsageSummary): TokenKind {
  return tokenGroupLabel(row) === 'Dapp' ? 'dapp' : 'personal'
}

function inferOwner(row: TokenUsageSummary, kind: TokenKind) {
  const parts = String(row.token_name || '').split(/[-_/|｜·\s]+/).map((part) => part.trim()).filter(Boolean)
  if (parts.length >= 2 && ['个人', '成员', 'personal', 'user', 'dapp', 'app', '应用', '项目'].includes(parts[0].toLowerCase())) return parts[1]
  if (parts.length >= 2) return parts[0]
  if (row.username) return row.username
  return kind === 'dapp' ? row.token_name || 'Dapp' : row.token_name || '—'
}

function riskOf(row: TokenUsageSummary): RiskState {
  return buildRiskAlerts(row as EnrichedTokenRow, [], []).at(0)?.state || 'normal'
}

function riskLabel(risk: RiskState, t: (key: string) => string) {
  if (risk === 'low_quota') return t('tokenLowQuota')
  if (risk === 'exhausted') return t('tokenExhausted')
  if (risk === 'high_error') return t('tokenHighError')
  if (risk === 'disabled') return t('tokenDisabled')
  if (risk === 'spike') return '消耗突增'
  if (risk === 'high_latency') return '延迟异常'
  if (risk === 'restricted_model') return '模型异常'
  return t('tokenNormal')
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

function ChartHeading({ icon, title, total, actions }: { icon: IconName; title: string; total?: string; actions?: ReactNode }) {
  return (
    <div className="token-chart-copy">
      <b><Icon name={icon} />{title}</b>
      <span>{actions}{total ? <em>{total}</em> : null}</span>
    </div>
  )
}

function errorRateOf(row: TokenUsageSummary) {
  const requests = Number(row.request_count || 0)
  const errors = Number(row.error_count || 0)
  return errors / Math.max(1, requests + errors)
}

function buildRiskAlerts(row: EnrichedTokenRow, trendValues: number[], modelRows: TokenModelUsage[]): RiskAlert[] {
  const alerts: RiskAlert[] = []
  const quota = Number(row.quota || 0)
  const requests = Number(row.request_count || 0)
  const errors = Number(row.error_count || 0)
  const errorRate = errorRateOf(row)
  const avgLatency = Number(row.avg_use_time || 0)
  const base = { token_id: row.token_id, token_name: row.token_name || `#${row.token_id}`, quota }
  if (row.status !== undefined && row.status !== 1) {
    alerts.push({ ...base, id: `${row.token_id}:disabled`, state: 'disabled', severity: quota > 0 ? 'bad' : 'warn', title: quota > 0 ? '停用但仍有消耗' : '停用/异常', detail: quota > 0 ? `本周期仍消耗 ${moneyFromQuota(quota)}` : '分发平台状态不是正常启用。' })
  }
  if (!row.unlimited_quota && Number(row.remain_quota || 0) <= 0) {
    alerts.push({ ...base, id: `${row.token_id}:exhausted`, state: 'exhausted', severity: 'bad', title: '额度已耗尽', detail: '剩余额度为 0，后续请求可能失败。' })
  } else if (!row.unlimited_quota) {
    const remain = Number(row.remain_quota || 0)
    const total = remain + Number(row.used_quota || 0)
    if (remain > 0 && total > 0 && remain / total < 0.1) alerts.push({ ...base, id: `${row.token_id}:low_quota`, state: 'low_quota', severity: 'warn', title: '额度偏低', detail: `剩余额度约 ${pct(remain / total)}。` })
  }
  if (errorRate >= 0.1 && errors >= 3) {
    alerts.push({ ...base, id: `${row.token_id}:high_error`, state: 'high_error', severity: 'bad', title: '失败率偏高', detail: `${errors} 次失败，失败率 ${pct(errorRate)}。` })
  }
  if (avgLatency >= 30 && requests >= 3) {
    alerts.push({ ...base, id: `${row.token_id}:high_latency`, state: 'high_latency', severity: 'warn', title: '延迟异常', detail: `平均延迟 ${avgLatency.toFixed(2)}s。` })
  }
  const latest = trendValues.at(-1) || 0
  const previous = trendValues.slice(-4, -1).filter((value) => value > 0)
  const previousAvg = previous.reduce((sum, value) => sum + value, 0) / Math.max(1, previous.length)
  if (latest >= 5 && previousAvg > 0 && latest / previousAvg >= 2.5 && latest - previousAvg >= 5) {
    alerts.push({ ...base, id: `${row.token_id}:spike`, state: 'spike', severity: 'warn', title: '消耗突然上涨', detail: `最近桶 ${moneyUsd(latest)}，约为前值 ${Math.round(latest / previousAvg)} 倍。` })
  }
  const restrictedModels = modelRows
    .map((item) => item.model_name || '')
    .filter((name) => name && /(codex|auto-review|unknown)/i.test(name))
  if (row.kind === 'dapp' && restrictedModels.length) {
    alerts.push({ ...base, id: `${row.token_id}:restricted_model`, state: 'restricted_model', severity: 'warn', title: 'Dapp 模型需确认', detail: `使用了 ${restrictedModels.slice(0, 2).join(' / ')}。` })
  }
  return alerts.sort((a, b) => ({ bad: 0, warn: 1, info: 2 }[a.severity] - { bad: 0, warn: 1, info: 2 }[b.severity]))
}

function enrichRows(rows: TokenUsageSummary[], trends: TokenUsageTrend[], models: TokenModelUsage[] = []): EnrichedTokenRow[] {
  const trendByKey = new Map<number, number[]>()
  trends.forEach((row) => {
    const list = trendByKey.get(row.token_id) || []
    list.push(quotaToUsd(row.quota))
    trendByKey.set(row.token_id, list)
  })
  const modelsByKey = new Map<number, TokenModelUsage[]>()
  models.forEach((row) => {
    const list = modelsByKey.get(row.token_id) || []
    list.push(row)
    modelsByKey.set(row.token_id, list)
  })
  return rows.map((row) => {
    const kind = inferKind(row)
    const trendValues = (trendByKey.get(row.token_id) || []).slice(-14)
    const base = { ...row, kind, owner: inferOwner(row, kind), risk: 'normal' as RiskState, riskReasons: [], trendValues }
    const riskReasons = buildRiskAlerts(base, trendValues, modelsByKey.get(row.token_id) || [])
    return { ...base, riskReasons, risk: riskReasons[0]?.state || riskOf(row) }
  })
}

function computeTokenMetrics(rows: EnrichedTokenRow[]) {
  const quota = rows.reduce((sum, row) => sum + Number(row.quota || 0), 0)
  const tokenUsed = rows.reduce((sum, row) => sum + Number(row.token_used || 0), 0)
  const requests = rows.reduce((sum, row) => sum + Number(row.request_count || 0), 0)
  const errors = rows.reduce((sum, row) => sum + Number(row.error_count || 0), 0)
  const riskCount = rows.filter((row) => row.riskReasons.length).length
  return { quota, tokenUsed, requests, errors, active: rows.filter((row) => Number(row.request_count || 0) > 0).length, errorRate: errors / Math.max(1, requests + errors), riskCount }
}

function buildGroupBreakdown(rows: EnrichedTokenRow[], modelRows: TokenModelUsage[]): GroupBreakdownItem[] {
  const map = new Map<string, Omit<GroupBreakdownItem, 'color'>>()
  const groupByTokenId = new Map<number, string>()
  rows.forEach((row) => {
    const label = tokenGroupLabel(row)
    groupByTokenId.set(row.token_id, label)
    const item = map.get(label) || { label, value: 0, count: 0, requests: 0, errors: 0, tokenUsed: 0, rows: [], models: [] }
    item.value += Number(row.quota || 0)
    item.count = Number(item.count || 0) + 1
    item.requests = Number(item.requests || 0) + Number(row.request_count || 0)
    item.errors = Number(item.errors || 0) + Number(row.error_count || 0)
    item.tokenUsed = Number(item.tokenUsed || 0) + Number(row.token_used || 0)
    item.rows.push(row)
    map.set(label, item)
  })
  modelRows.forEach((row) => {
    const label = groupByTokenId.get(row.token_id)
    if (!label) return
    map.get(label)?.models.push(row)
  })
  return [...map.values()]
    .sort((a, b) => b.value - a.value)
    .map((item, index) => ({ ...item, color: groupColor(item.label, index) }))
}

function projectMonthlyQuota(quota: number, startTimestamp: number, endTimestamp: number) {
  const end = new Date(endTimestamp * 1000)
  const daysInMonth = new Date(end.getFullYear(), end.getMonth() + 1, 0).getDate()
  const elapsedDays = Math.max(1 / 24, (endTimestamp - startTimestamp) / 86400)
  return (quota / elapsedDays) * daysInMonth
}

function changeRate(current: number, previous: number) {
  if (!previous) return current ? 1 : 0
  return (current - previous) / previous
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

function KeyRankBars({
  rows,
  topLimit,
  selectedTokenId,
  onSelect,
  t,
}: {
  rows: EnrichedTokenRow[]
  topLimit: number
  selectedTokenId: number | null
  onSelect: (tokenId: number | null) => void
  t: (key: string) => string
}) {
  const [tip, setTip] = useState<Tooltip | null>(null)
  useDismissTipOnScroll(setTip)
  const topRows = rows.slice(0, topLimit)
  const otherRows = rows.slice(topLimit)
  const otherQuota = otherRows.reduce((sum, row) => sum + Number(row.quota || 0), 0)
  const otherRow: EnrichedTokenRow | null = otherRows.length ? {
    token_id: -1,
    token_name: `其他 ${otherRows.length} 个 KEY`,
    kind: 'other',
    owner: '其他',
    risk: 'normal',
    riskReasons: [],
    trendValues: [],
    quota: otherQuota,
    token_used: otherRows.reduce((sum, row) => sum + Number(row.token_used || 0), 0),
    request_count: otherRows.reduce((sum, row) => sum + Number(row.request_count || 0), 0),
    error_count: otherRows.reduce((sum, row) => sum + Number(row.error_count || 0), 0),
    top_model: '—',
  } : null
  const list = otherRow ? [...topRows, otherRow] : topRows
  const total = rows.reduce((sum, row) => sum + Number(row.quota || 0), 0)
  const max = Math.max(...list.map((row) => Number(row.quota || 0)), 1)
  if (!list.length) return <Empty title={t('tokenNoData')} hint={t('tokenNoDataHint')} />
  return (
    <div className="token-rank-chart" onMouseLeave={() => setTip(null)}>
      <ChartHeading
        icon="rank"
        title="KEY 消耗排行"
        total={`总计：${moneyFromQuota(total)}`}
        actions={selectedTokenId ? <button type="button" className="token-link-btn" onClick={() => onSelect(null)}>取消高亮</button> : null}
      />
      {list.map((row, index) => {
        const value = Number(row.quota || 0)
        const color = COLORS[index % COLORS.length]
        const clickable = row.token_id > 0
        const selected = selectedTokenId === row.token_id
        return (
          <div
            className={`token-rank-row ${selected ? 'selected' : ''} ${selectedTokenId && !selected ? 'dimmed' : ''} ${clickable ? 'clickable' : ''}`}
            key={row.token_id || row.token_name}
            onClick={() => clickable && onSelect(selected ? null : row.token_id)}
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

function UsageTrendLines({
  rows,
  keys,
  granularity,
  selectedTokenId,
  onSelect,
  t,
}: {
  rows: TokenUsageTrend[]
  keys: EnrichedTokenRow[]
  granularity?: string
  selectedTokenId: number | null
  onSelect: (tokenId: number | null) => void
  t: (key: string) => string
}) {
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
  const selectedKey = selectedTokenId ? keys.find((key) => key.token_id === selectedTokenId) : undefined
  const baseTopKeys = keys.slice(0, 10)
  const topKeys = selectedKey && !baseTopKeys.some((key) => key.token_id === selectedKey.token_id) ? [selectedKey, ...baseTopKeys.slice(0, 9)] : baseTopKeys
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
          const selected = selectedTokenId === key.token_id
          return <path key={key.token_id || key.token_name} d={path} fill="none" stroke={color} strokeWidth={selected ? '3' : '2'} opacity={selectedTokenId && !selected ? '.18' : '.9'} />
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
                setTip({ x: event.clientX, y: event.clientY, title: bucketTooltipLabel(bucket, granularity), rows: [
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
          <span
            className={selectedTokenId === key.token_id ? 'selected' : selectedTokenId ? 'dimmed' : ''}
            key={key.token_id || key.token_name}
            title={key.token_name || `#${key.token_id}`}
            onClick={() => onSelect(selectedTokenId === key.token_id ? null : key.token_id)}
          >
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

function DonutChart({
  title,
  icon,
  items,
  selectedLabel,
  onSelect,
  legendLimit = 6,
}: {
  title: string
  icon: IconName
  items: DonutItem[]
  selectedLabel?: string | null
  onSelect?: (label: string) => void
  legendLimit?: number
}) {
  const [tip, setTip] = useState<Tooltip | null>(null)
  useDismissTipOnScroll(setTip)
  const total = items.reduce((sum, item) => sum + item.value, 0)
  if (!total) return <Empty title={title} hint="暂无数据" />
  const segments = items.reduce<Array<{ item: DonutItem; start: number; end: number }>>((list, item) => {
    const start = list.length ? list[list.length - 1].end : 0
    const end = start + (item.value / total) * 359.9
    return [...list, { item, start, end }]
  }, [])
  return (
    <div className="token-donut" onMouseLeave={() => setTip(null)}>
      <div className="token-donut-title"><Icon name={icon} />{title}</div>
      <svg viewBox="0 0 220 170" role="img" aria-label={title}>
        <text x="14" y="28" fill="var(--text)" fontSize="18" fontFamily="var(--mono)">{moneyFromQuota(total)}</text>
        {segments.map(({ item, start, end }) => {
          return (
            <path
              key={item.label}
              d={arc(84, 100, 45, start, end)}
              fill="none"
              stroke={item.color}
              strokeWidth={selectedLabel === item.label ? '24' : '22'}
              strokeOpacity={selectedLabel && selectedLabel !== item.label ? 0.35 : 1}
              strokeLinecap="round"
              onClick={() => onSelect?.(item.label)}
              onMouseMove={(event) => setTip({ x: event.clientX, y: event.clientY, title: item.label, rows: [
                { label: '消耗金额', value: moneyFromQuota(item.value), color: item.color },
                { label: '占比', value: pct(item.value / total) },
                ...(item.count !== undefined ? [{ label: 'KEY 数', value: n(item.count) }] : []),
                ...(item.requests !== undefined ? [{ label: '请求数', value: n(item.requests) }] : []),
              ] })}
            />
          )
        })}
      </svg>
      <div className="token-donut-legend">
        {items.slice(0, legendLimit).map((item) => (
          <button
            type="button"
            key={item.label}
            className={`${selectedLabel === item.label ? 'selected' : ''} ${selectedLabel && selectedLabel !== item.label ? 'dimmed' : ''}`}
            onClick={() => onSelect?.(item.label)}
          >
            <i style={{ background: item.color }} />{item.label}<b>{pct(item.value / total)}</b>
          </button>
        ))}
      </div>
      <ChartTip tip={tip} />
    </div>
  )
}

function TokenGroupDrawer({ item, total, onClose }: { item: GroupBreakdownItem | null; total: number; onClose: () => void }) {
  if (!item) return null
  const topKeys = [...item.rows].sort((a, b) => Number(b.quota || 0) - Number(a.quota || 0)).slice(0, 5)
  const modelMap = new Map<string, { model_name: string; count: number; quota: number; token_used: number }>()
  item.models.forEach((row) => {
    const modelName = row.model_name || 'unknown'
    const model = modelMap.get(modelName) || { model_name: modelName, count: 0, quota: 0, token_used: 0 }
    model.count += Number(row.count || 0)
    model.quota += Number(row.quota || 0)
    model.token_used += Number(row.token_used || 0)
    modelMap.set(modelName, model)
  })
  const topModels = [...modelMap.values()].sort((a, b) => b.quota - a.quota).slice(0, 4)
  const errorRate = Number(item.errors || 0) / Math.max(1, Number(item.requests || 0) + Number(item.errors || 0))
  return (
    <div className="token-drawer-backdrop" onMouseDown={onClose}>
      <aside className="token-drawer" onMouseDown={(event) => event.stopPropagation()}>
        <div className="token-drawer-head">
          <span>分组详情</span>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className="token-drawer-title">
          <b>{item.label}</b>
          <div><span className="token-group-badge" style={{ color: item.color, borderColor: item.color }}>分组</span></div>
        </div>
        <div className="token-detail-grid">
          <div><span>消耗金额</span><b>{moneyFromQuota(item.value)}</b></div>
          <div><span>占总消耗</span><b>{pct(item.value / Math.max(1, total))}</b></div>
          <div><span>KEY 数</span><b>{n(item.count)}</b></div>
          <div><span>请求数</span><b>{n(item.requests)}</b></div>
          <div><span>失败率</span><b>{pct(errorRate)}</b></div>
          <div><span>Tokens</span><b>{shortN(item.tokenUsed)}</b></div>
        </div>
        <div className="token-detail-section">
          <h3>Top 消耗 KEY</h3>
          {topKeys.length ? topKeys.map((row) => (
            <div className="token-group-row" key={row.token_id}>
              <span><i style={{ background: item.color }} />{row.token_name || `#${row.token_id}`}</span>
              <b>{moneyFromQuota(row.quota)}</b>
              <em>{pct(Number(row.quota || 0) / Math.max(1, item.value))}</em>
            </div>
          )) : <p>暂无 KEY 数据</p>}
        </div>
        <div className="token-detail-section">
          <h3>Top 使用模型</h3>
          {topModels.length ? topModels.map((row) => (
            <div className="token-group-row" key={row.model_name}>
              <span><i style={{ background: item.color }} />{row.model_name}</span>
              <b>{moneyFromQuota(row.quota)}</b>
              <em>{n(row.count)} 次</em>
            </div>
          )) : <p>暂无模型数据</p>}
        </div>
        <div className="token-detail-section">
          <h3>分组 KEY</h3>
          {item.rows.map((row) => (
            <div className="token-group-row" key={`${item.label}:${row.token_id}`}>
              <span><i style={{ background: item.color }} />{row.token_name || `#${row.token_id}`}</span>
              <b>{moneyFromQuota(row.quota)}</b>
              <em>{n(row.request_count)} 次</em>
            </div>
          ))}
        </div>
      </aside>
    </div>
  )
}

function weightedPercentile(values: Array<{ value: number; weight: number }>, percentile: number) {
  const sorted = values.filter((item) => item.value > 0 && item.weight > 0).sort((a, b) => a.value - b.value)
  const total = sorted.reduce((sum, item) => sum + item.weight, 0)
  let seen = 0
  for (const item of sorted) {
    seen += item.weight
    if (seen / Math.max(1, total) >= percentile) return item.value
  }
  return sorted.at(-1)?.value || 0
}

function HealthPanel({ rows, metrics, onSelectToken }: { rows: EnrichedTokenRow[]; metrics: { requests: number; errors: number; tokenUsed: number }; onSelectToken: (tokenId: number) => void }) {
  const total = metrics.requests + metrics.errors
  const successRate = metrics.requests / Math.max(1, total)
  const latencyWeight = rows.reduce((sum, row) => sum + Number(row.avg_use_time || 0) * Number(row.request_count || 0), 0)
  const avgLatency = latencyWeight / Math.max(1, metrics.requests)
  const p95Latency = weightedPercentile(rows.map((row) => ({ value: Number(row.avg_use_time || 0), weight: Number(row.request_count || 0) })), 0.95)
  const throughput = metrics.tokenUsed / Math.max(1, latencyWeight)
  const modelHealth = [...rows.reduce((map, row) => {
    const name = row.top_model && row.top_model !== 'unknown' ? row.top_model : '缺少模型名'
    const item = map.get(name) || { name, requests: 0, errors: 0 }
    item.requests += Number(row.request_count || 0)
    item.errors += Number(row.error_count || 0)
    map.set(name, item)
    return map
  }, new Map<string, { name: string; requests: number; errors: number }>()).values()]
    .filter((item) => item.requests + item.errors > 0)
    .sort((a, b) => b.requests + b.errors - (a.requests + a.errors))
    .slice(0, 5)
  const keyErrors = rows
    .map((row) => ({ tokenId: row.token_id, name: row.token_name || `#${row.token_id}`, rate: errorRateOf(row), errors: Number(row.error_count || 0) }))
    .filter((item) => item.errors > 0)
    .sort((a, b) => b.rate - a.rate)
    .slice(0, 3)
  return (
    <section className="frame token-health">
      <div className="token-health-core">
        <b><Icon name="health" />性能健康</b>
        <span>成功率 <strong className={successRate < 0.9 ? 'bad' : 'good'}>{pct(successRate)}</strong></span>
        <span>平均延迟 <strong>{avgLatency.toFixed(2)}s</strong></span>
        <span>P95 <strong>{p95Latency.toFixed(2)}s</strong></span>
        <span>吞吐量 <strong>{shortN(throughput)} t/s</strong></span>
      </div>
      <div className="token-model-health">
        {modelHealth.map((item) => {
          const rate = item.requests / Math.max(1, item.requests + item.errors)
          return <span key={item.name}>{item.name} <i className={rate < 0.9 ? 'bad' : 'good'} /> <b>{pct(rate)}</b></span>
        })}
        {keyErrors.map((item) => <button key={item.name} type="button" className="warn" onClick={() => onSelectToken(item.tokenId)}>KEY失败 {item.name} <i className="bad" /> <b>{pct(item.rate)}</b></button>)}
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

function rowSortValue(row: EnrichedTokenRow, field: TokenUsageSortField) {
  if (field === 'token_name') return normalized(row.token_name)
  if (field === 'owner') return normalized(row.owner)
  if (field === 'kind') return row.kind
  if (field === 'risk') return row.riskReasons.length ? row.riskReasons[0].severity : 'zz'
  if (field === 'last_used_at') return Number(row.last_used_at || row.accessed_time || 0)
  if (field === 'remain_quota') return row.unlimited_quota ? Number.POSITIVE_INFINITY : Number(row.remain_quota || 0)
  return Number(row[field] || 0)
}

function sortTokenRows(rows: EnrichedTokenRow[], sort: SortState) {
  return [...rows].sort((a, b) => {
    const av = rowSortValue(a, sort.field)
    const bv = rowSortValue(b, sort.field)
    const result = typeof av === 'string' || typeof bv === 'string' ? String(av).localeCompare(String(bv), 'zh-CN') : Number(av) - Number(bv)
    return sort.dir === 'asc' ? result : -result
  })
}

function filterTokenRows(
  rows: EnrichedTokenRow[],
  modelRows: TokenModelUsage[],
  controls: { kind: 'all' | TokenKind; model: string; risk: 'all' | RiskState; q: string; hideZero: boolean },
) {
  let next = rows
  const queryText = normalized(controls.q)
  if (controls.kind !== 'all') next = next.filter((row) => row.kind === controls.kind)
  if (controls.risk !== 'all') next = next.filter((row) => row.risk === controls.risk || row.riskReasons.some((item) => item.state === controls.risk))
  if (controls.hideZero) next = next.filter((row) => Number(row.quota || 0) > 0 || Number(row.request_count || 0) > 0)
  if (queryText) next = next.filter((row) => normalized(`${row.token_name} ${row.owner} ${row.username}`).includes(queryText))
  if (controls.model !== 'all') {
    const ids = new Set(modelRows.filter((row) => row.model_name === controls.model).map((row) => row.token_id))
    next = next.filter((row) => ids.has(row.token_id))
  }
  return next
}

function Highlight({ text, query }: { text?: string; query: string }) {
  const value = String(text || '—')
  const needle = query.trim()
  if (!needle) return <>{value}</>
  const index = value.toLowerCase().indexOf(needle.toLowerCase())
  if (index < 0) return <>{value}</>
  return <>{value.slice(0, index)}<mark>{value.slice(index, index + needle.length)}</mark>{value.slice(index + needle.length)}</>
}

function csvCell(value: unknown) {
  const text = String(value ?? '')
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function exportTokenRows(rows: EnrichedTokenRow[]) {
  const header = ['KEY 名称', '类型', '归属', '消耗金额', '请求数', '失败数', '失败率', '常用模型', '剩余额度', '状态', '最后使用']
  const lines = rows.map((row) => [
    row.token_name || `#${row.token_id}`,
    row.kind,
    row.owner,
    moneyFromQuota(row.quota),
    row.request_count || 0,
    row.error_count || 0,
    pct(errorRateOf(row)),
    row.top_model || '',
    row.unlimited_quota ? '不限额' : moneyFromQuota(row.remain_quota),
    riskLabel(row.risk, (key) => key),
    ts(row.last_used_at || row.accessed_time),
  ])
  const csv = [header, ...lines].map((line) => line.map(csvCell).join(',')).join('\n')
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `token-usage-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function SortButton({ field, sort, setSort, children }: { field: TokenUsageSortField; sort: SortState; setSort: (sort: SortState) => void; children: ReactNode }) {
  const active = sort.field === field
  return (
    <button className={`token-sort ${active ? 'on' : ''}`} type="button" onClick={() => setSort(active ? { field, dir: sort.dir === 'asc' ? 'desc' : 'asc' } : { field, dir: field === 'token_name' || field === 'owner' || field === 'kind' ? 'asc' : 'desc' })}>
      {children}{active ? <span>{sort.dir === 'asc' ? '↑' : '↓'}</span> : null}
    </button>
  )
}

type TokenErrorLog = TokenUsageErrorsPayload['data']['items'][number]

function errorLogTitle(log: TokenErrorLog) {
  const status = log.status_code ? `HTTP ${log.status_code}` : '失败'
  const code = log.error_code || log.error_type || ''
  return code ? `${status} · ${code}` : status
}

function shortReason(reason?: string) {
  const text = String(reason || '未返回失败原因').trim()
  return text.length > 160 ? `${text.slice(0, 160)}...` : text
}

function ErrorLogsSection({
  row,
  payload,
  loading,
  error,
  onRetry,
}: {
  row: EnrichedTokenRow
  payload: TokenUsageErrorsPayload | null
  loading: boolean
  error: string
  onRetry: () => void
}) {
  const errorCount = Number(row.error_count || 0)
  if (!errorCount) return null
  const logs = payload?.data.items || []
  const summary = payload?.data.summary || []
  return (
    <div className="token-detail-section token-error-section">
      <div className="token-detail-section-head">
        <h3>失败原因</h3>
        <button type="button" className="token-link-btn" onClick={onRetry} disabled={loading}>{loading ? '读取中' : '刷新'}</button>
      </div>
      {loading && !payload ? (
        <div className="token-error-loading"><span className="token-spinner" />正在读取分发平台错误日志</div>
      ) : null}
      {error ? <div className="token-error-empty">错误日志读取失败：{error}</div> : null}
      {!loading && !error && payload && !logs.length ? (
        <div className="token-error-empty">当前只拿到 {n(errorCount)} 次失败统计，未读到失败明细。请确认分发平台已开启错误日志。</div>
      ) : null}
      {summary.length ? (
        <div className="token-error-summary">
          {summary.slice(0, 3).map((item) => (
            <div key={`${item.status_code || 0}:${item.error_code || item.error_type}:${item.reason}`}>
              <b>{item.status_code ? `HTTP ${item.status_code}` : item.error_code || item.error_type || '失败'}</b>
              <span>{shortReason(item.reason)}</span>
              <em>{n(item.count)} 次 · 最近 {ts(item.latest_at)}</em>
            </div>
          ))}
        </div>
      ) : null}
      {logs.length ? (
        <div className="token-error-list">
          {logs.slice(0, 8).map((log) => (
            <div className="token-error-log" key={`${log.id}:${log.created_at}:${log.request_id}`}>
              <div>
                <b>{errorLogTitle(log)}</b>
                <span>{ts(log.created_at)} · {log.model_name || '未知模型'} · {log.channel_name || `通道 #${log.channel || '-'}`}</span>
              </div>
              <p>{shortReason(log.content)}</p>
              <dl>
                {log.request_id ? <><dt>Request ID</dt><dd>{log.request_id}</dd></> : null}
                {log.upstream_request_id ? <><dt>Upstream ID</dt><dd>{log.upstream_request_id}</dd></> : null}
                {log.request_path ? <><dt>Path</dt><dd>{log.request_path}</dd></> : null}
              </dl>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function TokenKeyDrawer({
  row,
  trendRows,
  modelRows,
  errorLogs,
  errorLogsLoading,
  errorLogsError,
  onRefreshErrors,
  granularity,
  onClose,
  t,
}: {
  row: EnrichedTokenRow | null
  trendRows: TokenUsageTrend[]
  modelRows: TokenModelUsage[]
  errorLogs: TokenUsageErrorsPayload | null
  errorLogsLoading: boolean
  errorLogsError: string
  onRefreshErrors: () => void
  granularity?: string
  onClose: () => void
  t: (key: string) => string
}) {
  const [tip, setTip] = useState<Tooltip | null>(null)
  useDismissTipOnScroll(setTip)
  if (!row) return null
  const trends = trendRows.filter((item) => item.token_id === row.token_id).sort((a, b) => a.created_at - b.created_at)
  const models = modelRows.filter((item) => item.token_id === row.token_id).sort((a, b) => Number(b.quota || 0) - Number(a.quota || 0))
  const max = Math.max(...trends.map((item) => quotaToUsd(item.quota)), 1)
  return (
    <div className="token-drawer-backdrop" onMouseDown={onClose}>
      <aside className="token-drawer" onMouseDown={(event) => event.stopPropagation()}>
        <div className="token-drawer-head">
          <span>KEY 详情</span>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className="token-drawer-title">
          <b>{row.token_name || `#${row.token_id}`}</b>
          <div><span className={`token-kind-badge ${KIND_CLASS[row.kind]}`}>{kindLabel(row.kind, t)}</span><span className={`status-pill risk-${row.risk}`}>{riskLabel(row.risk, t)}</span></div>
        </div>
        <div className="token-detail-grid">
          <div><span>归属</span><b>{row.owner}</b></div>
          <div><span>消耗金额</span><b>{moneyFromQuota(row.quota)}</b></div>
          <div><span>请求数</span><b>{n(row.request_count)}</b></div>
          <div><span>失败率</span><b>{pct(errorRateOf(row))}</b></div>
          <div><span>平均延迟</span><b>{Number(row.avg_use_time || 0).toFixed(2)}s</b></div>
          <div><span>最后使用</span><b>{ts(row.last_used_at || row.accessed_time)}</b></div>
          <div><span>剩余额度</span><b>{row.unlimited_quota ? t('tokenUnlimited') : moneyFromQuota(row.remain_quota)}</b></div>
          <div><span>模型数</span><b>{n(row.model_count || models.length)}</b></div>
        </div>
        <div className="token-detail-section">
          <h3>消耗趋势</h3>
          {trends.length ? (
            <div className="token-detail-bars" onMouseLeave={() => setTip(null)}>
              {trends.map((item) => {
                const value = quotaToUsd(item.quota)
                return (
                  <i
                    key={`${item.created_at}:${item.token_id}`}
                    style={{ height: `${Math.max(3, (value / max) * 100)}%` }}
                    onMouseMove={(event) => setTip({ x: event.clientX, y: event.clientY, title: bucketTooltipLabel(item.created_at, granularity), rows: [
                      { label: '消耗金额', value: moneyUsd(value), color: COLORS[0] },
                      { label: '请求数', value: n(item.count) },
                      { label: 'Tokens', value: n(item.token_used) },
                    ] })}
                  />
                )
              })}
              <ChartTip tip={tip} />
            </div>
          ) : <Empty title="暂无趋势" hint="当前筛选范围内没有趋势数据。" />}
        </div>
        <div className="token-detail-section">
          <h3>模型使用</h3>
          {models.length ? models.map((item) => (
            <div className="token-model-row" key={item.model_name}>
              <span>{item.model_name}</span>
              <b>{moneyFromQuota(item.quota)}</b>
              <em>{n(item.count)} 次</em>
            </div>
          )) : <Empty title="暂无模型数据" hint="分发平台没有返回模型拆分。" />}
        </div>
        {row.riskReasons.length ? (
          <div className="token-detail-section">
            <h3>风险原因</h3>
            {row.riskReasons.map((item) => <div className={`token-alert-line ${item.severity}`} key={item.id}><b>{item.title}</b><span>{item.detail}</span></div>)}
          </div>
        ) : null}
        <ErrorLogsSection row={row} payload={errorLogs} loading={errorLogsLoading} error={errorLogsError} onRetry={onRefreshErrors} />
      </aside>
    </div>
  )
}

export function TokenUsageView({
  data,
  loading,
  error,
  query,
  params,
  setParams,
  refresh,
  t,
}: {
  data: TokenUsagePayload | null
  loading: boolean
  error: string
  query: TokenUsageQuery
  params: TokenUsageQueryState
  setParams: SetTokenUsageQueryState
  refresh: (force?: boolean) => Promise<void>
  t: (key: string) => string
}) {
  const [selectedTokenId, setSelectedTokenId] = useState<number | null>(null)
  const [selectedGroupLabel, setSelectedGroupLabel] = useState<string | null>(null)
  const [ignoredRisks, setIgnoredRisks] = useState<Set<string>>(() => new Set())
  const [errorLogs, setErrorLogs] = useState<TokenUsageErrorsPayload | null>(null)
  const [errorLogsLoading, setErrorLogsLoading] = useState(false)
  const [errorLogsError, setErrorLogsError] = useState('')
  const [errorLogsReload, setErrorLogsReload] = useState(0)
  const filters = useMemo(() => normalizeTokenUsageFilters(params), [params])
  const { kind, model: requestedModel, risk, q, topLimit, hideZero, sort } = filters
  const update = (patch: Partial<TokenUsageQueryState>) => void setParams(patch)
  const updateSort = (next: SortState) => update({ sort: next.field, dir: next.dir })
  const payload = data?.data
  const comparisonPayload = data?.comparison?.data
  const enriched = useMemo(() => enrichRows(payload?.summary || [], payload?.trend || [], payload?.models || []), [payload])
  const comparisonEnriched = useMemo(() => enrichRows(comparisonPayload?.summary || [], comparisonPayload?.trend || [], comparisonPayload?.models || []), [comparisonPayload])
  const models = useMemo(() => [...new Set((payload?.models || []).map((row) => row.model_name).filter(Boolean))].sort(), [payload])
  const model = resolveTokenUsageModel(requestedModel, models, Boolean(payload) && tokenUsagePayloadMatchesQuery(data?.range, query))
  const customRangeIssue = tokenUsageCustomRangeIssue(filters)
  useEffect(() => {
    if (payload && model !== requestedModel) void setParams({ model: 'all' })
  }, [model, payload, requestedModel, setParams])
  const filterControls = useMemo(() => ({ kind, model, risk, q, hideZero }), [hideZero, kind, model, q, risk])
  const filteredBaseRows = useMemo(() => filterTokenRows(enriched, payload?.models || [], filterControls), [enriched, filterControls, payload])
  const filteredRows = useMemo(() => sortTokenRows(filteredBaseRows, sort), [filteredBaseRows, sort])
  const filteredComparisonRows = useMemo(() => filterTokenRows(comparisonEnriched, comparisonPayload?.models || [], filterControls), [comparisonEnriched, comparisonPayload, filterControls])
  const matchingTokenIds = useMemo(() => new Set(filteredBaseRows.map((row) => row.token_id)), [filteredBaseRows])
  const filteredTrend = useMemo(() => (payload?.trend || []).filter((row) => matchingTokenIds.has(row.token_id)), [matchingTokenIds, payload])
  const filteredModels = useMemo(() => (payload?.models || []).filter((row) => matchingTokenIds.has(row.token_id) && (model === 'all' || row.model_name === model)), [matchingTokenIds, model, payload])
  const selectedRow = useMemo(() => filteredRows.find((row) => row.token_id === selectedTokenId) || null, [filteredRows, selectedTokenId])
  const activeSelectedTokenId = selectedRow?.token_id ?? null
  useEffect(() => {
    setErrorLogs(null)
    setErrorLogsError('')
    if (!selectedRow || Number(selectedRow.error_count || 0) <= 0) {
      setErrorLogsLoading(false)
      return undefined
    }
    const controller = new AbortController()
    let cancelled = false
    setErrorLogsLoading(true)
    void fetchTokenUsageErrors(query, {
      tokenId: selectedRow.token_id,
      tokenName: selectedRow.token_name,
      group: selectedRow.group,
    }, controller.signal)
      .then((next) => {
        if (cancelled) return
        setErrorLogs(next)
        setErrorLogsError('')
      })
      .catch((err) => {
        if (cancelled || (err as Error)?.name === 'AbortError') return
        setErrorLogsError((err as Error)?.message || '读取失败')
      })
      .finally(() => {
        if (!cancelled) setErrorLogsLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [errorLogsReload, query.endTimestamp, query.startTimestamp, selectedRow?.error_count, selectedRow?.group, selectedRow?.token_id, selectedRow?.token_name])
  const metrics = useMemo(() => computeTokenMetrics(filteredBaseRows), [filteredBaseRows])
  const comparisonMetrics = useMemo(() => computeTokenMetrics(filteredComparisonRows), [filteredComparisonRows])
  const growthRate = changeRate(metrics.quota, comparisonMetrics.quota)
  const monthlyProjection = projectMonthlyQuota(metrics.quota, query.startTimestamp, query.endTimestamp)
  const allRiskAlerts = useMemo(
    () => filteredBaseRows.flatMap((row) => row.riskReasons).sort((a, b) => ({ bad: 0, warn: 1, info: 2 }[a.severity] - { bad: 0, warn: 1, info: 2 }[b.severity] || b.quota - a.quota)),
    [filteredBaseRows],
  )
  const riskRows = allRiskAlerts.filter((row) => !ignoredRisks.has(row.id)).slice(0, 8)
  const groupItems = useMemo(() => buildGroupBreakdown(filteredBaseRows, filteredModels), [filteredBaseRows, filteredModels])
  const selectedGroup = selectedGroupLabel ? groupItems.find((item) => item.label === selectedGroupLabel) || null : null
  const personalItems = useMemo(() => {
    const map = new Map<string, DonutItem>()
    filteredBaseRows
      .filter((row) => row.kind !== 'dapp')
      .forEach((row) => {
        const label = row.token_name || row.owner || row.username || `#${row.token_id}`
        const item = map.get(label) || { label, value: 0, color: COLORS[(map.size + 2) % COLORS.length], count: 0, requests: 0, errors: 0, tokenUsed: 0 }
        item.value += Number(row.quota || 0)
        item.count = Number(item.count || 0) + 1
        item.requests = Number(item.requests || 0) + Number(row.request_count || 0)
        item.errors = Number(item.errors || 0) + Number(row.error_count || 0)
        item.tokenUsed = Number(item.tokenUsed || 0) + Number(row.token_used || 0)
        map.set(label, item)
      })
    return [...map.values()].sort((a, b) => b.value - a.value).slice(0, 8)
  }, [filteredBaseRows])
  const typeItems = useMemo(() => {
    const map: Record<'personal' | 'dapp', number> = { personal: 0, dapp: 0 }
    filteredBaseRows.forEach((row) => { map[row.kind === 'dapp' ? 'dapp' : 'personal'] += Number(row.quota || 0) })
    return (['personal', 'dapp'] as const)
      .map((name) => ({ label: kindLabel(name, t), value: map[name], color: KIND_DONUT_COLORS[name] }))
      .filter((item) => item.value > 0)
  }, [filteredBaseRows, t])
  const modelItems = useMemo(() => {
    const map = new Map<string, number>()
    filteredModels
      .filter((row) => !activeSelectedTokenId || row.token_id === activeSelectedTokenId)
      .forEach((row) => map.set(row.model_name, (map.get(row.model_name) || 0) + Number(row.quota || 0)))
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([label, value], index) => ({ label, value, color: COLORS[(index + 4) % COLORS.length] }))
  }, [activeSelectedTokenId, filteredModels])
  const applyPreset = (preset: string) => update(tokenUsagePresetPatch(preset))
  const updateCustom = (field: 'wstart' | 'wend', value: string) => update({ w: 'custom', [field]: fromInputValue(value) })
  const ignoreRisk = (alertId: string) => {
    setIgnoredRisks((old) => {
      const next = new Set(old)
      next.add(alertId)
      return next
    })
  }
  const clearIgnoredRisks = () => {
    setIgnoredRisks(new Set())
  }
  const refreshSelectedErrors = () => setErrorLogsReload((value) => value + 1)
  const isInitialLoading = loading && !payload
  const statusLabel = data?.source === 'demo' ? 'DEMO' : data?.configured ? (loading && payload ? 'LIVE ⟳' : 'LIVE') : undefined
  const freshness = data?.fetched_at ? new Date(data.fetched_at).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
  const freshnessText = [
    freshness ? `最后更新 ${freshness}` : '',
    data?.source === 'upstream' ? '上游正常' : data?.source === 'demo' ? '演示数据' : '',
    data?.cached ? '后端缓存' : data?.source === 'upstream' ? '实时读取' : '',
  ].filter(Boolean).join(' · ')

  return (
    <div className={`token-page ${loading && payload ? 'is-refreshing' : ''}`}>
      <section className="frame">
        <div className="token-headline">
          <SectionTitle title={t('tokenUsageTitle')} count={statusLabel} />
          <button className="btn mini token-refresh-live" type="button" disabled={loading || customRangeIssue !== null} onClick={() => void refresh(true)}>{loading ? t('loading') : t('refresh')}</button>
        </div>
        <div className="usage-note">
          {data?.source === 'demo' ? t('tokenUsageDemo') : data?.configured ? t('tokenUsageConfigured') : t('tokenUsageHint')}
          {freshnessText ? <span className="src"> · {freshnessText}</span> : null}
          {data?.warning ? <span className="src"> · {data.warning}</span> : null}
        </div>
        <div className="toolbar token-toolbar">
          <label className="field">
            时间范围
            <select value={filters.w} onChange={(event) => applyPreset(event.target.value)}>
              {PRESETS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          <label className="field">
            图表维度
            <select value={filters.granularity} onChange={(event) => update({ g: event.target.value })}>
              {GRANULARITIES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          {filters.w === 'custom' ? (
            <>
              <label className="field token-datetime">开始<input type="datetime-local" value={toInputValue(filters.wstart)} onChange={(event) => updateCustom('wstart', event.target.value)} /></label>
              <label className="field token-datetime">结束<input type="datetime-local" value={toInputValue(filters.wend)} onChange={(event) => updateCustom('wend', event.target.value)} /></label>
            </>
          ) : null}
          <label className="field">
            {t('tokenKind')}
            <select value={kind} onChange={(event) => update({ kind: event.target.value })}>
              <option value="all">{t('tokenAllKinds')}</option>
              <option value="personal">{t('tokenPersonal')}</option>
              <option value="dapp">{t('tokenDapp')}</option>
            </select>
          </label>
          <label className="field">
            {t('models')}
            <select value={model} onChange={(event) => update({ model: event.target.value })}>
              <option value="all">{t('tokenAllModels')}</option>
              {model !== 'all' && !models.includes(model) ? <option value={model}>{model}</option> : null}
              {models.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <label className="field">
            {t('tokenStatus')}
            <select value={risk} onChange={(event) => update({ risk: event.target.value })}>
              <option value="all">{t('all')}</option>
              <option value="normal">{t('tokenNormal')}</option>
              <option value="low_quota">{t('tokenLowQuota')}</option>
              <option value="exhausted">{t('tokenExhausted')}</option>
              <option value="high_error">{t('tokenHighError')}</option>
              <option value="spike">消耗突增</option>
              <option value="high_latency">延迟异常</option>
              <option value="restricted_model">模型异常</option>
              <option value="disabled">{t('tokenDisabled')}</option>
            </select>
          </label>
          <label className="field token-topn">
            Top N
            <select value={topLimit} onChange={(event) => update({ topn: Number(event.target.value) })}>
              {[5, 10, 20].map((value) => <option value={value} key={value}>Top {value}</option>)}
            </select>
          </label>
          <label className="field token-search">{t('adminSearch')}<input value={q} onChange={(event) => update({ q: event.target.value })} placeholder={t('tokenSearch')} /></label>
        </div>
        {customRangeIssue ? <div className="token-range-warning" role="alert">{t(customRangeIssue === 'order' ? 'tokenCustomRangeOrder' : 'tokenCustomRangeIncomplete')}</div> : null}
      </section>

      {error ? <div className="note-warn">{t(error)}</div> : null}
      {isInitialLoading ? <LoadingNotice hasData={false} /> : null}
      {isInitialLoading ? <LoadingSkeleton /> : null}

      {!isInitialLoading ? (
        <>
      <div className="statgrid token-stats token-data-section">
        <div className="stat"><div className="v">{moneyFromQuota(metrics.quota)}</div><div className={`delta ${growthRate > 0 ? 'up' : growthRate < 0 ? 'down' : ''}`}>{data?.comparison?.label || '较上一周期'} {signedPct(growthRate)}</div><div className="l">消耗金额</div></div>
        <div className="stat"><div className="v">{signedPct(growthRate)}</div><div className="l">消耗增长率</div></div>
        <div className="stat"><div className="v">{moneyFromQuota(monthlyProjection)}</div><div className="l">预计本月消耗</div></div>
        <div className="stat"><div className="v">{shortN(metrics.tokenUsed)}</div><div className="l">{t('tokenTokens')}</div></div>
        <div className="stat"><div className="v">{n(metrics.requests)}</div><div className="l">{t('tokenRequests')}</div></div>
        <div className="stat"><div className="v">{n(metrics.active)}</div><div className="l">{t('tokenActiveKeys')}</div></div>
        <div className="stat"><div className="v">{pct(metrics.errorRate)}</div><div className="l">{t('tokenErrors')}</div></div>
        <div className="stat"><div className="v">{n(metrics.riskCount)}</div><div className="l">{t('tokenRisk')}</div></div>
      </div>

      <HealthPanel rows={filteredBaseRows} metrics={metrics} onSelectToken={setSelectedTokenId} />

      <div className="split token-split">
        <section className="frame"><KeyRankBars rows={filteredBaseRows} topLimit={topLimit} selectedTokenId={activeSelectedTokenId} onSelect={setSelectedTokenId} t={t} /></section>
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
                <div className={`token-risk ${row.severity}`} key={row.id}>
                  <span className={`dot risk-${row.state}`} />
                  <div><b>{row.token_name}</b><p>{row.title} · {row.detail}</p></div>
                  <span className="mono">{moneyFromQuota(row.quota)}</span>
                  <button className="token-risk-detail" type="button" onClick={() => setSelectedTokenId(row.token_id)}>详情</button>
                  <button className="token-risk-dismiss" type="button" onClick={() => ignoreRisk(row.id)}>忽略</button>
                </div>
              ))}
            </div>
          ) : <Empty title={allRiskAlerts.length ? '当前风险已忽略' : t('tokenNormal')} hint={allRiskAlerts.length ? '可点击恢复已忽略重新显示。' : t('tokenNoDataHint')} />}
        </section>
      </div>

      <section className="frame">
        <UsageTrendLines rows={filteredTrend} keys={filteredBaseRows} granularity={data?.range?.time_granularity} selectedTokenId={activeSelectedTokenId} onSelect={setSelectedTokenId} t={t} />
      </section>

      <div className="split token-split">
        <section className="frame token-donut-grid">
          <DonutChart title="分组消耗占比" icon="pie" items={groupItems} selectedLabel={selectedGroupLabel} onSelect={setSelectedGroupLabel} />
          <DonutChart title="个人消耗占比" icon="key" items={personalItems} legendLimit={8} />
          <DonutChart title="类型消耗占比" icon="pie" items={typeItems} />
          <DonutChart title={selectedRow ? '模型消耗占比 · 选中 KEY' : '模型消耗占比'} icon="model" items={modelItems} />
        </section>
        <section className="frame">
          <SectionTitle title={t('tokenModels')} count={filteredModels.length} />
          <ModelRows rows={filteredModels} t={t} />
        </section>
      </div>

      <section className="frame">
        <div className="token-table-head">
          <SectionTitle title={t('tokenKeys')} count={filteredRows.length} />
          <div className="token-table-actions">
            <button className={kind === 'all' ? 'on' : ''} type="button" onClick={() => update({ kind: 'all' })}>全部</button>
            <button className={kind === 'personal' ? 'on' : ''} type="button" onClick={() => update({ kind: 'personal' })}>只看个人</button>
            <button className={kind === 'dapp' ? 'on' : ''} type="button" onClick={() => update({ kind: 'dapp' })}>只看 Dapp</button>
            <label><input type="checkbox" checked={hideZero} onChange={(event) => update({ hz: event.target.checked ? '1' : '0' })} /> 隐藏 0 消耗</label>
            <button type="button" onClick={() => exportTokenRows(filteredRows)}>导出 CSV</button>
          </div>
        </div>
        {filteredRows.length ? (
          <div className="skills-wrap">
            <table className="token-table">
              <thead><tr><th><SortButton field="token_name" sort={sort} setSort={updateSort}>{t('tokenKeyName')}</SortButton></th><th><SortButton field="kind" sort={sort} setSort={updateSort}>{t('tokenKind')}</SortButton></th><th><SortButton field="owner" sort={sort} setSort={updateSort}>{t('tokenOwner')}</SortButton></th><th className="num"><SortButton field="quota" sort={sort} setSort={updateSort}>消耗金额</SortButton></th><th className="num"><SortButton field="request_count" sort={sort} setSort={updateSort}>{t('tokenRequests')}</SortButton></th><th>{t('tokenTopModel')}</th><th><SortButton field="remain_quota" sort={sort} setSort={updateSort}>{t('tokenRemain')}</SortButton></th><th>{t('trend')}</th><th><SortButton field="risk" sort={sort} setSort={updateSort}>{t('tokenStatus')}</SortButton></th><th><SortButton field="last_used_at" sort={sort} setSort={updateSort}>{t('tokenLastUsed')}</SortButton></th></tr></thead>
              <tbody>
                {filteredRows.map((row) => (
                  <tr key={row.token_id} className={activeSelectedTokenId === row.token_id ? 'selected' : ''} onClick={() => setSelectedTokenId(row.token_id)}>
                    <td><b><Highlight text={row.token_name || `#${row.token_id}`} query={q} /></b><div className="q"><Highlight text={row.username || '—'} query={q} /></div></td>
                    <td><span className={`token-kind-badge ${KIND_CLASS[row.kind]}`}>{kindLabel(row.kind, t)}</span></td>
                    <td><Highlight text={row.owner} query={q} /></td>
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
      <TokenKeyDrawer
        row={selectedRow}
        trendRows={payload?.trend || []}
        modelRows={payload?.models || []}
        errorLogs={errorLogs}
        errorLogsLoading={errorLogsLoading}
        errorLogsError={errorLogsError}
        onRefreshErrors={refreshSelectedErrors}
        granularity={data?.range?.time_granularity}
        onClose={() => setSelectedTokenId(null)}
        t={t}
      />
      <TokenGroupDrawer item={selectedGroup} total={metrics.quota} onClose={() => setSelectedGroupLabel(null)} />
        </>
      ) : null}
    </div>
  )
}

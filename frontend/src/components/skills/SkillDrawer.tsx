import { useEffect, useRef, useState } from 'react'
import { DetailTrend, RuntimeBars } from '../Charts'
import { deltaRatio, formatDelta } from '../../lib/skillsDashboard'
import type { SkillDetail, SkillTableRow } from '../../lib/types'
import { encodePathParam, sourceLabel } from '../../lib/utils'

async function fetchSkill(name: string) {
  const response = await fetch(`/api/skill/${encodeURIComponent(name)}`, { cache: 'no-store' })
  if (!response.ok) throw new Error(String(response.status))
  return (await response.json()) as SkillDetail
}

export function SkillDrawer({ name, row, search, onClose, t }: { name: string; row?: SkillTableRow; search: string; onClose: () => void; t: (key: string) => string }) {
  const cache = useRef(new Map<string, SkillDetail>())
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [error, setError] = useState('')
  const [trendDays, setTrendDays] = useState(30)
  useEffect(() => {
    let cancelled = false
    setDetail(cache.current.get(name) || null)
    setError('')
    if (cache.current.has(name)) return undefined
    fetchSkill(name)
      .then((next) => {
        cache.current.set(name, next)
        if (!cancelled) setDetail(next)
      })
      .catch((err) => !cancelled && setError(String(err)))
    return () => {
      cancelled = true
    }
  }, [name])
  return (
    <div className="skills-drawer-backdrop" onMouseDown={onClose}>
      <aside className="skills-drawer" onMouseDown={(event) => event.stopPropagation()}>
        <div className="skills-drawer-head">
          <div><b>{name}</b>{detail?.source ? <span className="source-pill">{sourceLabel(detail.source, t)}</span> : null}</div>
          <div>
            <a className="token-link-btn" href={`/skill/${encodePathParam(name)}${search}`}>前往详情页 →</a>
            <button type="button" className="token-link-btn" onClick={onClose}>×</button>
          </div>
        </div>
        {error ? <div className="empty"><div className="t">{t('loadError')}</div></div> : null}
        {!detail && !error ? <div className="empty"><div className="t">{t('loading')}</div></div> : null}
        {detail ? (
          <>
            <div className="skills-drawer-kpis">
              <div className="stat"><div className="v">{row?.sessions_window ?? detail.metrics?.sessions_30d ?? 0}</div><div className="l">W 触发</div></div>
              <div className="stat"><div className="v">{formatDelta(deltaRatio(Number(row?.sessions_window ?? 0), Number(row?.previous_sessions || 0)))}</div><div className="l">环比</div></div>
              <div className="stat"><div className="v">{detail.metrics?.users_30d || 0}</div><div className="l">活跃者</div></div>
              <div className="stat"><div className="v">{detail.metrics?.installed_count || 0}</div><div className="l">装机数</div></div>
            </div>
            <div className="skills-drawer-section">
              <div className="skills-panel-title">
                <b>趋势</b>
                <div className="seg compact">
                  {[14, 30, 90].map((days) => <button type="button" key={days} className={trendDays === days ? 'on' : ''} onClick={() => setTrendDays(days)}>{days}d</button>)}
                </div>
              </div>
              <DetailTrend detail={detail} t={t} days={trendDays} />
            </div>
            <div className="skills-drawer-section">
              <b>runtime 拆分</b>
              <RuntimeBars counts={Object.fromEntries((detail.runtime || []).map((row) => [row.runtime, Number(row.used || 0)]))} />
            </div>
            <div className="skills-drawer-section">
              <b>使用操作员 Top</b>
              {(detail.operators || []).filter((item) => Number(item.used || 0) > 0).slice(0, 5).map((item) => <p key={item.operator}>{item.operator || '—'} · used {item.used || 0}</p>)}
            </div>
            <div className="skills-drawer-section">
              <b>装备但未使用</b>
              {(detail.operators || []).filter((item) => Number(item.equipped || 0) > 0 && Number(item.used || 0) === 0).slice(0, 5).map((item) => <p className="danger" key={item.operator}>{item.operator || '—'} · equipped {item.equipped || 0}</p>)}
              {(detail.operators || []).some((item) => Number(item.equipped || 0) > 0 && Number(item.used || 0) === 0) ? null : <p>暂无差集</p>}
            </div>
            <div className="skills-drawer-section">
              <b>最近 5 次触发</b>
              {(detail.records || []).slice(0, 5).map((row) => <p key={`${row.session_id}:${row.first_seen}`}>{row.operator || '—'} · {row.runtime || '—'} · {row.day || row.first_seen || '—'}</p>)}
            </div>
          </>
        ) : null}
      </aside>
    </div>
  )
}

import type { AgentSession } from '../lib/types'
import { dur, genDays, isOldShim, shortShim } from '../lib/utils'

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty">
      <div className="t">{title}</div>
      {hint ? <div className="h">{hint}</div> : null}
    </div>
  )
}

export function SectionTitle({ title, count, live, t }: { title: string; count?: number | string; live?: number; t?: (key: string) => string }) {
  return (
    <h2>
      <span>
        <span className="sl">//</span>
        {title}
      </span>
      {count !== undefined || live !== undefined ? (
        <span className="cnt">
          {live !== undefined && t ? (
            <>
              {t('running')} <b>{live}</b> / {t('of')} {count}
            </>
          ) : (
            <>
              <b>{count}</b>
            </>
          )}
        </span>
      ) : null}
    </h2>
  )
}

export function ShimPill({ agent, latest, t }: { agent: AgentSession; latest?: string; t: (key: string) => string }) {
  const old = isOldShim(agent, latest)
  return (
    <span className={`shim ${old ? 'old' : ''}`} title={`${t('cfg_shim')}: ${shortShim(agent.shim_version)} / ${shortShim(latest)}`}>
      {old ? t('shimOld') : t('shim')} {shortShim(agent.shim_version)}
    </span>
  )
}

export function SparkMini({ series }: { series?: number[] }) {
  const values = series || [0, 0, 0, 0, 0, 0, 0]
  const max = Math.max(...values, 1)
  return (
    <div className="spark">
      {values.map((value, index) => (
        <i key={index} className={index === 6 ? 'today' : ''} style={{ height: `${Math.max(2, Math.round((value / max) * 18))}px` }} />
      ))}
    </div>
  )
}

export function Contrib({ agent, days }: { agent: AgentSession; days: number }) {
  const series = genDays(agent, days)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const start = new Date(today)
  start.setDate(today.getDate() - (series.length - 1))
  const max = Math.max(...series, 1)
  const level = (value: number) => (value <= 0 ? 0 : value < max * 0.25 ? 1 : value < max * 0.5 ? 2 : value < max * 0.75 ? 3 : 4)
  return (
    <div className="contrib">
      {series.map((value, index) => {
        const date = new Date(start)
        date.setDate(start.getDate() + index)
        return <i key={index} className={`l${level(value)}`} title={`${date.toISOString().slice(5, 10)} · ${dur(value)}`} />
      })}
    </div>
  )
}

export function QBar({ value }: { value: number }) {
  return (
    <>
      <span className="qbar">
        <i style={{ width: `${value}%` }} />
      </span>
      <span className="q">{value}%</span>
    </>
  )
}

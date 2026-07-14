import { useNavigate } from 'react-router-dom'
import type { AgentDirectoryRow } from '../../lib/agentsDashboard'
import { statusName } from '../../lib/i18n'
import type { Lang } from '../../lib/types'
import { dur, encodePathParam, keyOf } from '../../lib/utils'
import { Empty } from '../Common'

export function AgentRankPanel({ rows, labels, lang, windowLabel, t }: {
  rows: AgentDirectoryRow[]
  labels: Record<string, string>
  lang: Lang
  windowLabel: string
  t: (key: string) => string
}) {
  const navigate = useNavigate()
  const ranked = rows
    .filter((row) => row.active_seconds > 0)
    .slice()
    .sort((a, b) => b.active_seconds - a.active_seconds || keyOf(a.agent).localeCompare(keyOf(b.agent)))
  const maxSeconds = Math.max(...ranked.map((row) => row.active_seconds), 1)
  return (
    <section id="agents-rank" tabIndex={-1} className="frame agents-rank-panel">
      <h2><span><span className="sl">//</span>{t('agentDurationRank')}</span><span className="cnt">{windowLabel}</span></h2>
      <div className="agent-rank-list">
        {ranked.length ? ranked.map((row) => {
          const item = row.agent
          const identity = keyOf(item)
          const label = labels[identity] || item.agent || t('agentUnnamed')
          return (
            <button type="button" className="agent-rank-row" key={identity} onClick={() => navigate(`/agent/${encodePathParam(identity)}`)}>
              <span className="agent-rank-name" title={label}>{label}</span>
              <span className="agent-rank-track"><i style={{ width: `${Math.max(3, Math.round((row.active_seconds / maxSeconds) * 100))}%` }} /></span>
              <span className="agent-rank-count">{dur(row.active_seconds)}</span>
              <span className="agent-rank-meta">{row.active_days} {t('agentDays')} · {statusName(lang, item.status)}</span>
            </button>
          )
        }) : <Empty title={t('agentNoRank')} hint={t('agentNoRankHint')} />}
      </div>
    </section>
  )
}

import type { KeyboardEvent, MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { QBar, ShimPill } from '../Common'
import { agentSignals, agentSuccessRate, type AgentDirectoryRow } from '../../lib/agentsDashboard'
import { statusName } from '../../lib/i18n'
import type { AgentSession, Lang } from '../../lib/types'
import { ago, dur, encodePathParam, hashHue, initials, keyOf, LIVE } from '../../lib/utils'

function statusColor(status: string) {
  return LIVE.includes(status) ? 'var(--run)' : ['error', 'blocked'].includes(status) ? 'var(--err)' : 'var(--done)'
}

function skillsCount(agent: AgentSession) {
  return (agent.skills?.local || []).length + (agent.skills?.cross || []).length
}

export function AgentDirectoryTable({ rows, labels, latestShim, lang, windowLabel, t }: {
  rows: AgentDirectoryRow[]
  labels: Record<string, string>
  latestShim?: string
  lang: Lang
  windowLabel: string
  t: (key: string) => string
}) {
  const navigate = useNavigate()
  const open = (row: AgentDirectoryRow) => navigate(`/agent/${encodePathParam(keyOf(row.agent))}`)
  const onKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: AgentDirectoryRow) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    open(row)
  }
  const onClick = (event: MouseEvent<HTMLTableRowElement>, row: AgentDirectoryRow) => {
    if ((event.target as HTMLElement).closest('a,button')) return
    open(row)
  }

  return (
    <div className="agent-directory-wrap">
      <table className="agent-directory-table">
        <thead>
          <tr>
            <th>{t('agentColumnAgent')}</th>
            <th>{windowLabel}</th>
            <th>{t('agentCumulativeQuality')}</th>
            <th>{t('agentResources')}</th>
            <th>Shim</th>
            <th>{t('agentLastSeen')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const item = row.agent
            const rate = agentSuccessRate(item)
            const signals = agentSignals(item, latestShim)
            const quality = item.quality || {}
            const identity = keyOf(item)
            const name = labels[identity] || item.agent || t('agentUnnamed')
            const lastSeen = item.last_seen || item.ts
            return (
              <tr
                key={identity}
                role="link"
                tabIndex={0}
                aria-label={`${name}, ${statusName(lang, item.status)}`}
                onClick={(event) => onClick(event, row)}
                onKeyDown={(event) => onKeyDown(event, row)}
              >
                <td className="agent-directory-identity" data-label={t('agentColumnAgent')}>
                  <span className="avatar agent-avatar" style={{ ['--c' as string]: `hsl(${hashHue(identity)} 30% 42%)`, borderColor: statusColor(item.status) }}>
                    {initials(name)}
                  </span>
                  <span className="agent-directory-main">
                    <span className="agent-directory-name"><b title={name}>{name}</b><span className="agent-status"><i className="dot" style={{ background: statusColor(item.status) }} />{statusName(lang, item.status)}</span></span>
                    <span className="agent-directory-task" title={item.task || t('agentNoTask')}>{item.task || t('agentNoTask')}</span>
                    <span className="agent-directory-step" title={item.current_step || t('agentNoStep')}>{item.current_step ? `▸ ${item.current_step}` : t('agentNoStep')}</span>
                  </span>
                </td>
                <td className="agent-directory-window" data-label={windowLabel}>
                  <b>{dur(row.active_seconds)}</b>
                  <small>{row.active_days} {t('agentDays')}</small>
                </td>
                <td className="agent-directory-quality" data-label={t('agentCumulativeQuality')}>
                  <span>{rate === null ? <b>—</b> : <QBar value={Math.round(rate * 100)} />}</span>
                  <small>{t('agentRuns')} {quality.runs || 0} · {t('agentErrors')} {quality.error || 0}</small>
                </td>
                <td className="agent-directory-resources" data-label={t('agentResources')}>
                  <b>{t('agentSkillsCount')} {skillsCount(item)}</b>
                  <small>{t('agentMcpCount')} {item.mcp?.length || 0}</small>
                </td>
                <td className="agent-directory-shim" data-label="Shim"><ShimPill agent={item} latest={latestShim} t={t} /></td>
                <td className="agent-directory-last" data-label={t('agentLastSeen')}>
                  <b>{ago(lastSeen)}</b>
                  {signals.length ? <small>{signals.length} {t('agentSignals')}</small> : <small>{t('agentNoSignals')}</small>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

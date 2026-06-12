import { Link } from 'react-router-dom'
import { QBar, SectionTitle, ShimPill } from '../components/Common'
import { dur, encodePathParam, keyOf, LIVE, RT } from '../lib/utils'
import { statusName } from '../lib/i18n'
import type { Lang, StatePayload } from '../lib/types'

export function Agents({ data, lang, t }: { data: StatePayload; lang: Lang; t: (key: string) => string }) {
  const latestShim = data.shim?.version
  return (
    <section className="frame">
      <SectionTitle title={t('agents')} count={data.sessions.length} />
      <table>
        <thead>
          <tr>
            <th>{t('th_agent')}</th>
            <th>{t('th_disp')}</th>
            <th>{t('th_rt')}</th>
            <th>{t('th_model')}</th>
            <th>{t('th_status')}</th>
            <th>{t('th_today')}</th>
            <th>{t('th_skill')}</th>
            <th>{t('th_mcp')}</th>
            <th>{t('th_shim')}</th>
            <th>{t('th_q')}</th>
          </tr>
        </thead>
        <tbody>
          {data.sessions.map((agent) => {
            const quality = agent.quality || {}
            const successRate = quality.runs ? Math.round(((quality.success || 0) / quality.runs) * 100) : null
            const color = LIVE.includes(agent.status) ? 'var(--run)' : ['error', 'blocked'].includes(agent.status) ? 'var(--err)' : 'var(--done)'
            const skillCount = (agent.skills?.local || []).length + (agent.skills?.cross || []).length
            return (
              <tr key={keyOf(agent)}>
                <td>
                  <Link to={`/agent/${encodePathParam(keyOf(agent))}`}>
                    <b>{agent.agent || agent.runtime}</b>
                  </Link>
                </td>
                <td>{agent.operator}</td>
                <td>{RT[agent.runtime] || agent.runtime}</td>
                <td className="q">{(agent.models || []).join(', ') || '—'}</td>
                <td>
                  <span className="dot" style={{ background: color }} />
                  {statusName(lang, agent.status)}
                </td>
                <td className="q">{dur(agent.today_active)}</td>
                <td className="q">{skillCount}</td>
                <td className="q">{agent.mcp?.length || 0}</td>
                <td>
                  <ShimPill agent={agent} latest={latestShim} t={t} />
                </td>
                <td>{successRate != null ? <QBar value={successRate} /> : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

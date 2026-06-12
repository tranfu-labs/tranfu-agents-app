import { Link } from 'react-router-dom'
import { Empty, SectionTitle, ShimPill, SparkMini } from '../components/Common'
import { ago, dur, encodePathParam, hashHue, initials, keyOf, LIVE, RT } from '../lib/utils'
import { statusName } from '../lib/i18n'
import type { AgentSession, Lang, StatePayload } from '../lib/types'

function AgentCard({ agent, latestShim, lang, t }: { agent: AgentSession; latestShim?: string; lang: Lang; t: (key: string) => string }) {
  const tag = agent.agent || RT[agent.runtime] || agent.runtime
  const skillCount = (agent.skills?.local || []).length + (agent.skills?.cross || []).length
  return (
    <Link className={`card s-${agent.status}`} to={`/agent/${encodePathParam(keyOf(agent))}`}>
      <div className="crow">
        <span className="mk" />
        <span className="alabel">{tag}</span>
        <span className="badge">{RT[agent.runtime] || agent.runtime}</span>
        <ShimPill agent={agent} latest={latestShim} t={t} />
        {agent.fidelity === 'coarse' ? <span className="coarse">{lang === 'zh' ? '云端·粗粒度' : 'cloud · coarse'}</span> : null}
        <span className="age mono">{ago(agent.ts)}</span>
      </div>
      <div className="task">{agent.task || '—'}</div>
      <div className="step">{agent.current_step ? `▸ ${agent.current_step}` : statusName(lang, agent.status)}</div>
      <div className="chips">
        {(agent.models || []).slice(0, 3).map((model) => (
          <span className="chip" key={model}>
            {model}
          </span>
        ))}
        {agent.mcp?.length ? <span className="chip">MCP {agent.mcp.length}</span> : null}
        {skillCount ? <span className="chip">Skill {skillCount}</span> : null}
      </div>
      <div className="metrics">
        <span>{statusName(lang, agent.status)}</span>
        <span>
          {t('today')} <b>{dur(agent.today_active)}</b>
        </span>
        <SparkMini series={agent.active_series} />
      </div>
    </Link>
  )
}

function Feed({ data, lang, t }: { data: StatePayload; lang: Lang; t: (key: string) => string }) {
  if (!data.feed.length) {
    return <Empty title={t('silent')} />
  }
  return (
    <>
      {data.feed.map((item, index) => (
        <div className="feed-item" key={`${item.ts}-${index}`}>
          <span className="ft">{ago(item.ts)}</span>
          <div className="fmain">
            <div className="l1">
              {item.operator}
              {item.agent ? ` · ${item.agent}` : ''} <span className="stx">{statusName(lang, item.status)}</span>
            </div>
            <div className="sub">
              {RT[item.runtime] || item.runtime} — {item.current_step || item.task || ''}
            </div>
          </div>
        </div>
      ))}
    </>
  )
}

export function Board({ data, lang, t }: { data: StatePayload; lang: Lang; t: (key: string) => string }) {
  const latestShim = data.shim?.version
  const byOperator = data.sessions.reduce<Record<string, AgentSession[]>>((acc, session) => {
    ;(acc[session.operator] = acc[session.operator] || []).push(session)
    return acc
  }, {})
  const operators = Object.keys(byOperator).sort()

  return (
    <div className="split">
      <section className="frame">
        <SectionTitle title={t('pods')} count={data.sessions.length} live={data.totals.live} t={t} />
        <div className="pad">
          {operators.length ? (
            operators.map((operator) => {
              const list = byOperator[operator]
              const online = list.filter((agent) => LIVE.includes(agent.status)).length
              const ring = online > 0 ? 'on' : list.some((agent) => ['error', 'blocked'].includes(agent.status)) ? 'err' : 'off'
              return (
                <div className="pod" key={operator}>
                  <div className="phead">
                    <span className={`avatar ${ring}`} style={{ ['--c' as string]: `hsl(${hashHue(operator)} 30% 42%)` }}>
                      {initials(operator)}
                    </span>
                    <span className="pname">{operator}</span>
                    <span className="role">{t('dispatcher')}</span>
                    <span className="pmeta">
                      {t('squad')} {list.length} · <b>{online}</b> {t('live')}
                    </span>
                  </div>
                  <div className="grid">
                    {list.map((agent) => (
                      <AgentCard key={keyOf(agent)} agent={agent} latestShim={latestShim} lang={lang} t={t} />
                    ))}
                  </div>
                </div>
              )
            })
          ) : (
            <Empty title={t('noPods')} hint={t('noPodsH')} />
          )}
        </div>
      </section>
      <div className="sidecol">
        <section className="frame">
          <SectionTitle title={t('feed')} />
          <div>
            <Feed data={data} lang={lang} t={t} />
          </div>
        </section>
      </div>
    </div>
  )
}

import { Link, useParams } from 'react-router-dom'
import { Contrib, Empty, ShimPill } from '../components/Common'
import { DEMO_CONFIG, DEMO_MEMORY } from '../lib/demo'
import { ACT_DAYS, dur, hashHue, initials, keyOf, LIVE, RT, shimState, shortShim } from '../lib/utils'
import { statusName } from '../lib/i18n'
import type { AgentConfig, AgentMemory, Lang, SkillRef, StatePayload } from '../lib/types'

function SkillList({ items, cls, t }: { items?: SkillRef[]; cls: 'local' | 'cross'; t: (key: string) => string }) {
  return (
    <>
      {(items || []).map((skill) => (
        <div className="skill" key={`${cls}-${skill.name}`}>
          <div className="nm">
            {skill.name} <span className={`pin ${cls}`}>{t(cls)}</span>
          </div>
          <div className="ds">{skill.desc || ''}</div>
        </div>
      ))}
    </>
  )
}

function MemoryPanel({ memory, pitfalls, t }: { memory: AgentMemory | null; pitfalls: Array<string | SkillRef>; t: (key: string) => string }) {
  if (!memory) {
    return (
      <div className="panel">
        <h3>
          {t('memory')} <span className="meta">{t('no_mem')}</span>
        </h3>
        <div className="hint">{t('no_mem_h')}</div>
      </div>
    )
  }
  const memAge = memory.updated ? dur(memory.updated) : ''
  return (
    <div className="panel">
      <h3>
        {t('memory')} <span className="meta">📄 {memory.file} · {t('m_updated')} {memAge}</span>
      </h3>
      <div className="hint" style={{ margin: '0 0 5px' }}>
        {t('m_conv')}
      </div>
      {(memory.conventions || []).map((item) => (
        <div className="mem" key={item}>
          <span className="mt">{t('m_conv')}</span>
          {item}
        </div>
      ))}
      <div className="hint" style={{ margin: '11px 0 5px' }}>
        {t('m_learn')}
      </div>
      {(memory.learned || []).map((item) => (
        <div className="mem" key={item}>
          <span className="mt">{t('m_learn')}</span>
          {item}
        </div>
      ))}
      <div className="hint" style={{ margin: '11px 0 5px' }}>
        {t('pit')}
      </div>
      {pitfalls.length ? (
        pitfalls.map((item) => (
          <div className="mem" key={typeof item === 'string' ? item : item.name}>
            <span className="mt">{t('pit')}</span>
            {typeof item === 'string' ? item : item.name}
          </div>
        ))
      ) : (
        <div className="hint">{t('none')}</div>
      )}
    </div>
  )
}

export function AgentDetail({ data, lang, t }: { data: StatePayload; lang: Lang; t: (key: string) => string }) {
  const { key = '' } = useParams()
  const decodedKey = decodeURIComponent(key)
  const agent = data.sessions.find((session) => keyOf(session) === decodedKey)
  if (!agent) {
    return (
      <>
        <Link className="back" to="/agents">
          ← {t('back')}
        </Link>
        <Empty title={t('noAgent')} />
      </>
    )
  }

  const latestShim = data.shim?.version
  const color = LIVE.includes(agent.status) ? 'var(--run)' : ['error', 'blocked'].includes(agent.status) ? 'var(--err)' : 'var(--done)'
  const skills = agent.skills || { local: [], cross: [], pitfalls: [] }
  const config = agent.config || {}
  const mcp = agent.mcp || []
  const cfg: AgentConfig = agent.cf || DEMO_CONFIG[keyOf(agent)] || {}
  const memory: AgentMemory | null = agent.memory || DEMO_MEMORY[keyOf(agent)] || null
  const integrations = agent.integrations || cfg.integrations || []
  const ims = cfg.ims || []
  const nmem = memory ? (memory.conventions || []).length + (memory.learned || []).length : 0
  const risk = /write|autonomous/i.test(JSON.stringify(config)) || mcp.length >= 3
  const skillCount = (skills.local || []).length + (skills.cross || []).length

  return (
    <>
      <Link className="back" to="/agents">
        ← {t('back')}
      </Link>
      <div className="dhead">
        <span className="avatar on" style={{ ['--c' as string]: `hsl(${hashHue(agent.operator)} 30% 42%)`, borderColor: color }}>
          {initials(agent.operator)}
        </span>
        <span className="alabel">{agent.agent || agent.runtime}</span>
        <span className="badge">{RT[agent.runtime] || agent.runtime}</span>
        <span className="role">
          {agent.operator} · {t('dispatcher')}
        </span>
        <span className="role">
          <span className="dot" style={{ background: color }} />
          {statusName(lang, agent.status)}
        </span>
      </div>
      <div className="dsub">
        {agent.task || ''}
        {agent.current_step ? ` · ▸ ${agent.current_step}` : ''}
      </div>
      <div className="govbar">
        <span className="gv">
          <span className="src">RUNTIME</span>
          <b>{RT[agent.runtime] || agent.runtime}</b>
        </span>
        <span className="gv">
          <span className="src">{t('models')}</span>
          <b>{agent.models?.length || 0}</b>
        </span>
        {(() => {
          const ss = shimState(agent, latestShim)
          const cls = ss === 'outdated' ? 'warn' : ss === 'unknown' ? 'unknown' : 'ok'
          return (
            <span className={`gv ${cls}`}>
              <span className="src">SHIM</span>
              <b>{ss === 'unknown' ? '—' : shortShim(agent.shim_version)}</b>
            </span>
          )
        })()}
        <span className={`gv ${mcp.length >= 3 ? 'warn' : ''}`}>
          <span className="src">{t('gb_reach')}</span>
          <b>{mcp.length} MCP</b>
        </span>
        <span className="gv">
          <span className="src">{t('gb_mem')}</span>
          <b>{nmem}</b>
        </span>
        <span className={`gv ${risk ? 'warn' : 'ok'}`}>
          <span className="src">{t('gb_risk')}</span>
          <b>{risk ? t('risk_warn') : t('risk_ok')}</b>
        </span>
      </div>
      <div className="dgrid">
        <div>
          <div className="panel">
            <h3>
              {t('capability')} <span className="meta">{t('from_mem')}</span>
            </h3>
            <p className="lead">{agent.about || '—'}</p>
            <div className="note">
              <b>{t('note')}:</b> {agent.tips || '—'}
            </div>
          </div>
          <div className="panel">
            <h3>
              {t('src_cfg')} <span className="meta">⚙ {t('from_cfg')}</span>
            </h3>
            <div className="kv"><span className="k">{t('cfg_ver')}</span><span className="v">{cfg.ver || RT[agent.runtime] || agent.runtime}</span></div>
            <div className="kv"><span className="k">{t('cfg_role')}</span><span className="v">{cfg.role || '—'}</span></div>
            <div className="kv"><span className="k">{t('cfg_loc')}</span><span className="v">{cfg.location || '—'}</span></div>
            <div className="kv"><span className="k">{t('cfg_term')}</span><span className="v">{cfg.terminal || '—'}</span></div>
            <div className="kv"><span className="k">{t('cfg_im')}</span><span className="v">{ims.length ? ims.join(' · ') : '—'}</span></div>
            <div className="kv"><span className="k">{t('cfg_shim')}</span><span className="v"><ShimPill agent={agent} latest={latestShim} t={t} /></span></div>
            <div className="kv"><span className="k">{t('models')}</span><span className="v">{(agent.models || ['—']).join(' · ')}</span></div>
            {Object.keys(config).length ? (
              Object.entries(config).map(([k, v]) => (
                <div className="kv" key={k}>
                  <span className="k">{k}</span>
                  <span className="v">{String(v)}</span>
                </div>
              ))
            ) : (
              <div className="kv"><span className="k">{t('none')}</span><span className="v" /></div>
            )}
          </div>
          <div className="panel">
            <h3>
              {t('tools')} <span className="meta">⚙ {t('from_cfg')}</span>
            </h3>
            {integrations.length ? (
              integrations.map((item) => (
                <div className="skill" key={item.name}>
                  <div className="nm">{item.name}</div>
                  <div className="ds">{item.desc || ''}</div>
                </div>
              ))
            ) : (
              <div className="hint">{t('none')}</div>
            )}
          </div>
        </div>
        <div>
          <div className="panel">
            <h3>{lang === 'zh' ? `近 ${ACT_DAYS} 天活跃` : `Active · last ${ACT_DAYS} days`}</h3>
            <Contrib agent={agent} days={ACT_DAYS} />
            <div className="hint" style={{ marginTop: 11 }}>
              {t('today')} {dur(agent.today_active)} · {t('week')} {dur(agent.week_active)}
            </div>
          </div>
          <div className="panel">
            <h3>
              {t('skills_inst')} <span className="meta">{skillCount} · 📄</span>
            </h3>
            {skillCount ? (
              <>
                <SkillList items={skills.local} cls="local" t={t} />
                <SkillList items={skills.cross} cls="cross" t={t} />
              </>
            ) : (
              <div className="hint">{t('none')}</div>
            )}
          </div>
          <MemoryPanel memory={memory} pitfalls={skills.pitfalls || []} t={t} />
        </div>
      </div>
    </>
  )
}

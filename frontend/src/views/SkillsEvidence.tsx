import { Link } from 'react-router-dom'
import { Empty, SectionTitle } from '../components/Common'
import { formatRecentRecordTime } from '../lib/timeFormat'
import type { Lang, SkillsEvidenceKind, SkillsEvidencePayload } from '../lib/types'
import { sourceLabel } from '../lib/utils'
import { skillsBackSearch } from '../lib/skillsEvidence'

const KIND_LABEL_ZH: Record<SkillsEvidenceKind, string> = {
  total: '总触发次数证据',
  untracked: '未收录使用证据',
  coverage: '公司库覆盖证据',
  operators: '活跃操作员证据',
  avg_per_session: '每会话 skill 证据',
  idle: '闲置 Skill 名单',
  unused_ratio: '装了没用名单',
  zero_install: '收录但零装机名单',
  top3: 'Top3 集中证据',
  runtime: 'runtime 证据',
  source: '来源证据',
}

const KIND_LABEL_EN: Record<SkillsEvidenceKind, string> = {
  total: 'Total trigger evidence',
  untracked: 'Untracked usage evidence',
  coverage: 'Catalog coverage evidence',
  operators: 'Active operator evidence',
  avg_per_session: 'Skills per session evidence',
  idle: 'Idle skill list',
  unused_ratio: 'Installed unused list',
  zero_install: 'Cataloged zero-install list',
  top3: 'Top3 concentration evidence',
  runtime: 'Runtime evidence',
  source: 'Source evidence',
}

function kindLabel(kind: SkillsEvidenceKind | undefined, lang: Lang) {
  const labels = lang === 'zh' ? KIND_LABEL_ZH : KIND_LABEL_EN
  return labels[kind || 'total'] || labels.total
}

function n(value: unknown) {
  const num = Number(value || 0)
  return new Intl.NumberFormat('zh-CN').format(Number.isFinite(num) ? Math.round(num * 100) / 100 : 0)
}

function summaryRows(data: SkillsEvidencePayload | null) {
  const summary = data?.summary || {}
  return [
    ['records', 'records'],
    ['skills', 'skills'],
    ['operators', 'operators'],
    ['sessions', 'sessions'],
    ['items', 'items'],
    ['installed', 'installed'],
    ['untracked_records', 'untracked'],
    ['company_records', 'company'],
  ].filter(([key]) => summary[key] !== undefined).map(([key, label]) => ({ key, label, value: summary[key] }))
}

function FilterChips({ data }: { data: SkillsEvidencePayload | null }) {
  const filters = data?.applied_filters || {}
  const ignored = data?.ignored_filters || []
  const visible = Object.entries(filters).filter(([, value]) => value !== undefined && value !== '')
  return (
    <div className="evidence-filters">
      {visible.map(([key, value]) => <span key={key}>{key}: <b>{String(value)}</b></span>)}
      {ignored.map((item) => <span className="ignored" key={`${item.name}:${item.value}`}>{item.name}: {item.value} ignored</span>)}
    </div>
  )
}

export function SkillsEvidenceView({ data, loading, error, lang, search, t }: { data: SkillsEvidencePayload | null; loading: boolean; error: string; lang: Lang; search: string; t: (key: string) => string }) {
  const records = data?.records || []
  const items = data?.items || []
  const back = `/skills${skillsBackSearch(search)}`
  return (
    <div className={`skills-page skills-dashboard skills-evidence-page ${loading ? 'is-refreshing' : ''}`}>
      <section className="frame evidence-hero">
        <div className="pad">
          <Link className="token-link-btn" to={back}>← {t('skillsNav')}</Link>
          <div>
            <h1>{kindLabel(data?.kind, lang)}</h1>
            <p>{data?.window?.start || '—'} .. {data?.window?.end || '—'}</p>
          </div>
          <FilterChips data={data} />
        </div>
      </section>
      {error ? <div className="note-warn">{t(error)}</div> : null}
      {loading && !data ? <section className="frame"><Empty title={t('loading')} /></section> : null}
      <section className="frame">
        <SectionTitle title="证据摘要" count={data?.window?.key || ''} />
        <div className="evidence-summary">
          {summaryRows(data).map((row) => (
            <div className="stat" key={row.key}>
              <div className="v">{n(row.value)}</div>
              <div className="l">{row.label}</div>
            </div>
          ))}
        </div>
        <div className="evidence-actions">
          {(data?.actions || []).map((action) => <span key={action.id}>{action.label}</span>)}
        </div>
      </section>
      <div className="skills-main-split evidence-split">
        <section className="frame">
          <SectionTitle title="Top skills" count={data?.top_skills?.length || 0} />
          <div className="evidence-list">
            {(data?.top_skills || []).slice(0, 10).map((row) => (
              <div className="evidence-list-row" key={row.name}>
                <b>{row.name}</b>
                <span>{sourceLabel(row.source, t)} · {n(row.records)} records · {n(row.operators)} operators</span>
              </div>
            ))}
            {data?.top_skills?.length ? null : <Empty title="暂无 skill 分组" />}
          </div>
        </section>
        <section className="frame">
          <SectionTitle title="Top operators" count={data?.top_operators?.length || 0} />
          <div className="evidence-list">
            {(data?.top_operators || []).slice(0, 10).map((row) => (
              <div className="evidence-list-row" key={row.operator}>
                <b>{row.operator}</b>
                <span>{n(row.records)} records · {n(row.skills)} skills</span>
              </div>
            ))}
            {data?.top_operators?.length ? null : <Empty title="暂无 operator 分组" />}
          </div>
        </section>
      </div>
      {items.length ? (
        <section className="frame">
          <SectionTitle title="名单证据" count={items.length} />
          <div className="skills-wrap">
            <table className="skill-table mobile-card-table">
              <thead>
                <tr><th>Skill</th><th>Source</th><th className="num">Installers</th><th>Last used</th></tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.name}>
                    <td className="mobile-main" data-label="Skill"><b>{item.name}</b></td>
                    <td data-label="Source"><span className="source-pill">{sourceLabel(item.source, t)}</span></td>
                    <td className="num" data-label="Installers">{item.installers || 0}</td>
                    <td data-label="Last used">{item.last_day || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      <section className="frame">
        <SectionTitle title="原始记录" count={records.length} />
        {records.length ? (
          <div className="skills-wrap">
            <table className="skill-table mobile-card-table records-table evidence-records-table">
              <thead>
                <tr><th>Time</th><th>Skill</th><th>Operator</th><th>Runtime</th><th>Source</th><th>Session</th></tr>
              </thead>
              <tbody>
                {records.map((record, index) => {
                  const time = formatRecentRecordTime(record.first_seen, record.day || '', lang, undefined, data?.today)
                  return (
                    <tr key={`${record.session_id}:${record.skill}:${record.first_seen}:${index}`}>
                      <td data-label="Time" title={time.title}>{time.label}</td>
                      <td className="mobile-main" data-label="Skill"><b>{record.skill || '—'}</b></td>
                      <td data-label="Operator">{record.operator || '—'}</td>
                      <td data-label="Runtime">{record.runtime || '—'}</td>
                      <td data-label="Source"><span className="source-pill">{sourceLabel(record.source, t)}</span></td>
                      <td data-label="Session"><code>{record.session_id || '—'}</code></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : <Empty title={items.length ? '这类证据没有窗口内触发记录' : '暂无证据记录'} />}
      </section>
    </div>
  )
}

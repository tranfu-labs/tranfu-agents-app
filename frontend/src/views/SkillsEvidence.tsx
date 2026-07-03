import { Link } from 'react-router-dom'
import { Empty, SectionTitle } from '../components/Common'
import { formatRecentRecordTime } from '../lib/timeFormat'
import type { Lang, SkillsEvidenceKind, SkillsEvidencePayload } from '../lib/types'
import { sourceLabel } from '../lib/utils'
import { evidencePath, skillsBackSearch } from '../lib/skillsEvidence'
import { humanFilterChips } from '../lib/skillsClues'
import { defaultEvidenceTab, evidenceSummaryLine, isListEvidenceKind } from '../lib/skillsPresentation'

const KIND_LABEL_ZH: Record<SkillsEvidenceKind, string> = {
  total: '总触发记录',
  untracked: '未收录记录',
  coverage: '公司库覆盖记录',
  operators: '活跃操作员记录',
  avg_per_session: '每会话 skill 记录',
  idle: '闲置 Skill 名单',
  unused_ratio: '装了没用名单',
  zero_install: '收录但零装机名单',
  top3: 'Top3 集中记录',
  runtime: 'runtime 记录',
  source: '来源记录',
}

const KIND_LABEL_EN: Record<SkillsEvidenceKind, string> = {
  total: 'Total trigger records',
  untracked: 'Untracked records',
  coverage: 'Catalog coverage records',
  operators: 'Active operator records',
  avg_per_session: 'Skills per session records',
  idle: 'Idle skill list',
  unused_ratio: 'Installed unused list',
  zero_install: 'Cataloged zero-install list',
  top3: 'Top3 concentration records',
  runtime: 'Runtime records',
  source: 'Source records',
}

function kindLabel(kind: SkillsEvidenceKind | undefined, lang: Lang) {
  const labels = lang === 'zh' ? KIND_LABEL_ZH : KIND_LABEL_EN
  return labels[kind || 'total'] || labels.total
}

function n(value: unknown) {
  const num = Number(value || 0)
  return new Intl.NumberFormat('zh-CN').format(Number.isFinite(num) ? Math.round(num * 100) / 100 : 0)
}

function FilterChips({ data, t }: { data: SkillsEvidencePayload | null; t: (key: string) => string }) {
  const ignored = data?.ignored_filters || []
  const visible = humanFilterChips(data, t)
  return (
    <div className="evidence-filters">
      {visible.map((chip) => <span key={chip}>{chip}</span>)}
      {ignored.map((item) => <span className="ignored" key={`${item.name}:${item.value}`}>{item.name}: {item.value} ignored</span>)}
    </div>
  )
}

function actionGlyph(id: string, label: string) {
  const text = `${id} ${label}`.toLowerCase()
  if (text.includes('operator') || text.includes('使用者')) return '◎'
  if (text.includes('skill')) return '◇'
  if (text.includes('copy') || text.includes('复制')) return '⧉'
  return '▤'
}

export function SkillsEvidenceView({ data, loading, error, lang, search, t }: { data: SkillsEvidencePayload | null; loading: boolean; error: string; lang: Lang; search: string; t: (key: string) => string }) {
  const records = data?.records || []
  const items = data?.items || []
  const back = `/skills${skillsBackSearch(search)}`
  const listFirst = isListEvidenceKind(data?.kind)
  const untrackedRecords = Number(data?.summary?.untracked_records || 0)
  const showUntrackedSlice = data?.kind === 'total' && untrackedRecords > 0
  const recordsSection = (
    <section className="frame evidence-primary">
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
      ) : <Empty title={items.length ? '这类记录没有窗口内触发记录' : '暂无记录'} />}
    </section>
  )
  const itemsSection = (
    <section className="frame evidence-primary">
      <SectionTitle title="名单" count={items.length} />
      {items.length ? (
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
      ) : <Empty title="暂无名单" />}
    </section>
  )
  return (
    <div className={`skills-page skills-dashboard skills-evidence-page ${loading ? 'is-refreshing' : ''}`}>
      <section className="frame evidence-hero">
        <div className="pad">
          <Link className="token-link-btn" to={back}>← {t('skillsNav')}</Link>
          <div>
            <h1>{kindLabel(data?.kind, lang)}</h1>
            <p>{data?.window?.start || '—'} .. {data?.window?.end || '—'}</p>
          </div>
          <FilterChips data={data} t={t} />
          <div className="evidence-summary-line">
            <span>{evidenceSummaryLine(data)}</span>
            {showUntrackedSlice ? (
              <Link to={evidencePath(search, 'untracked')} aria-label="查看未收录 skill 记录">↗</Link>
            ) : null}
          </div>
          <div className="evidence-toolbar" role="toolbar" aria-label="记录页动作">
            <span className="evidence-tab-current">{defaultEvidenceTab(data?.kind)}</span>
            {(data?.actions || []).map((action) => (
              <span className="evidence-tool" key={action.id} aria-label={action.label} title={action.label}>
                {actionGlyph(action.id, action.label)}
              </span>
            ))}
          </div>
        </div>
      </section>
      {error ? <div className="note-warn">{t(error)}</div> : null}
      {loading && !data ? <section className="frame"><Empty title={t('loading')} /></section> : null}
      {listFirst ? itemsSection : recordsSection}
      {!listFirst && items.length ? itemsSection : null}
      <div className="skills-main-split evidence-split evidence-aux">
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
    </div>
  )
}

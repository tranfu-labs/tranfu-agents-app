import { Link } from 'react-router-dom'
import { Empty, SectionTitle } from '../components/Common'
import { clueTitle, humanFilterChips, operatorShare, showTopSkillsForClue } from '../lib/skillsClues'
import { skillsBackSearch, type SkillsClueKind } from '../lib/skillsEvidence'
import { windowZeroUsageLabel } from '../lib/skillsPresentation'
import { formatRecentRecordTime } from '../lib/timeFormat'
import type { Lang, SkillsEvidencePayload } from '../lib/types'
import { sourceLabel } from '../lib/utils'

function n(value: unknown) {
  const num = Number(value || 0)
  return new Intl.NumberFormat('zh-CN').format(Number.isFinite(num) ? Math.round(num * 100) / 100 : 0)
}

function RecordsTable({ data, lang }: { data: SkillsEvidencePayload | null; lang: Lang }) {
  const records = data?.records || []
  if (!records.length) return <Empty title="暂无记录" />
  return (
    <div className="skills-wrap">
      <table className="skill-table mobile-card-table records-table evidence-records-table">
        <thead>
          <tr><th>Time</th><th>Skill</th><th>Operator</th><th>Runtime</th><th>Session</th></tr>
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
                <td data-label="Session"><code>{record.session_id || '—'}</code></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function InstallerList({ installers }: { installers: NonNullable<SkillsEvidencePayload['items']>[number]['installers_detail'] }) {
  if (!installers?.length) return <span>—</span>
  return (
    <div className="installer-list">
      {installers.map((installer, index) => (
        <span key={`${installer.operator}:${installer.agent_key}:${installer.runtime}:${index}`}>
          <b>{installer.operator || '—'}</b>
          <small>{[installer.agent_key, installer.runtime].filter(Boolean).join(' · ') || '—'}</small>
        </span>
      ))}
    </div>
  )
}

function UntrackedView({ data, lang, search, t }: { data: SkillsEvidencePayload | null; lang: Lang; search: string; t: (key: string) => string }) {
  const total = Number(data?.summary?.records || 0)
  return (
    <>
      <section className="frame evidence-primary">
        <SectionTitle title="Top Operators" count={data?.top_operators?.length || 0} />
        <div className="evidence-list top-operators-list">
          {(data?.top_operators || []).slice(0, 10).map((row) => (
            <div className="evidence-list-row" key={row.operator}>
              <b>{row.operator}</b>
              <span>{operatorShare(row.records, total)} · {n(row.skills)} skills</span>
            </div>
          ))}
          {data?.top_operators?.length ? null : <Empty title="暂无 operator 分组" />}
        </div>
      </section>
      <section className="frame evidence-primary">
        <SectionTitle title={t('clueUntrackedTitle')} count={data?.records?.length || 0} />
        <RecordsTable data={data} lang={lang} />
      </section>
      {showTopSkillsForClue('untracked', search, data) ? (
        <section className="frame">
          <SectionTitle title="Top Skills" count={data?.top_skills?.length || 0} />
          <div className="evidence-list">
            {(data?.top_skills || []).slice(0, 10).map((row) => (
              <div className="evidence-list-row" key={row.name}>
                <b>{row.name}</b>
                <span>{n(row.records)} records · {n(row.operators)} operators</span>
              </div>
            ))}
            {data?.top_skills?.length ? null : <Empty title="暂无 skill 分组" />}
          </div>
        </section>
      ) : null}
    </>
  )
}

function IdleView({ data, t }: { data: SkillsEvidencePayload | null; t: (key: string) => string }) {
  const items = data?.items || []
  return (
    <section className="frame evidence-primary">
      <SectionTitle title={t('installersList')} count={items.length} />
      {items.length ? (
        <div className="skills-wrap">
          <table className="skill-table mobile-card-table">
            <thead>
              <tr><th>Skill</th><th className="num">{t('peopleInstalled')}</th><th>{t('installersList')}</th><th>{t('lastUsed')}</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.name}>
                  <td className="mobile-main" data-label="Skill"><b>{item.name}</b></td>
                  <td className="num" data-label={t('peopleInstalled')}>{item.installers || 0}</td>
                  <td data-label={t('installersList')}><InstallerList installers={item.installers_detail} /></td>
                  <td data-label={t('lastUsed')}>{item.last_day || t('neverUsed')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <Empty title={t('noRecords')} />}
    </section>
  )
}

function ZeroInstallView({ data, t }: { data: SkillsEvidencePayload | null; t: (key: string) => string }) {
  const items = data?.items || []
  return (
    <section className="frame evidence-primary">
      <SectionTitle title={t('zeroInstallList')} count={items.length} />
      {items.length ? (
        <div className="skills-wrap">
          <table className="skill-table mobile-card-table">
            <thead>
              <tr><th>Skill</th><th>Source</th><th className="num">{t('peopleInstalled')}</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.name}>
                  <td className="mobile-main" data-label="Skill"><b>{item.name}</b></td>
                  <td data-label="Source"><span className="source-pill">{sourceLabel(item.source, t)}</span></td>
                  <td className="num" data-label={t('peopleInstalled')}>0</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <Empty title={t('noRecords')} />}
    </section>
  )
}

export function SkillsClueView({ clueKind, data, loading, error, lang, search, t }: { clueKind: SkillsClueKind; data: SkillsEvidencePayload | null; loading: boolean; error: string; lang: Lang; search: string; t: (key: string) => string }) {
  const back = `/skills${skillsBackSearch(search)}`
  const chips = humanFilterChips(data, t)
  const summary = data?.summary || {}
  const windowKey = data?.window?.key || '7d'
  const headline = clueKind === 'untracked'
    ? `${n(summary.records)} ${t('records')}`
    : clueKind === 'idle'
      ? `${n(summary.items)} ${t('itemsUnit')} · ${windowZeroUsageLabel(windowKey, t)}`
      : `${n(summary.items)} ${t('itemsUnit')} · ${t('zeroInstall')}`
  return (
    <div className={`skills-page skills-dashboard skills-evidence-page skills-clue-page ${loading ? 'is-refreshing' : ''}`}>
      <section className="frame evidence-hero">
        <div className="pad">
          <Link className="token-link-btn" to={back}>← {t('skillsNav')}</Link>
          <div>
            <h1>{clueTitle(clueKind, t)}</h1>
            <p>{headline}</p>
          </div>
          <div className="evidence-filters">
            {chips.map((chip) => <span key={chip}>{chip}</span>)}
          </div>
        </div>
      </section>
      {error ? <div className="note-warn">{t(error)}</div> : null}
      {loading && !data ? <section className="frame"><Empty title={t('loading')} /></section> : null}
      {clueKind === 'untracked' ? <UntrackedView data={data} lang={lang} search={search} t={t} /> : null}
      {clueKind === 'idle' ? <IdleView data={data} t={t} /> : null}
      {clueKind === 'zero-install' ? <ZeroInstallView data={data} t={t} /> : null}
    </div>
  )
}

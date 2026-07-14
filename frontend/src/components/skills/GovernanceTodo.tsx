import { useMemo, useState, type KeyboardEvent, type MouseEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import type { GovernanceBucketSkill, GovernanceUntrackedSkill, OperatorTableRow, SkillsEvidenceKind, SkillsOverview } from '../../lib/types'
import { evidencePath } from '../../lib/skillsEvidence'
import { windowZeroUsageLabel } from '../../lib/skillsPresentation'
import { skillDisplayName } from '../../lib/skillNames'
import type { Lang } from '../../lib/types'

type TodoItem = {
  id: string
  title: string
  detail: string
  severity: 'warn' | 'bad' | 'info'
  openable?: boolean
  evidenceKind?: SkillsEvidenceKind
  evidenceParams?: Record<string, string | number | undefined>
  viewLabel?: string
}

function rowKey(event: KeyboardEvent<HTMLDivElement>, action: () => void) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  action()
}

function shortDay(value?: string | null) {
  return value ? String(value).slice(5, 10) : ''
}

function sectionSummary(visible: number, total: number, label: string, t: (key: string) => string) {
  const unit = t('itemsUnit')
  const noun = unit === '个' ? `${unit}${label}` : `${unit}${label ? ` ${label}` : ''}`
  if (total <= visible) return `${total} ${noun}，${t('allShown')}`
  return `${total} ${noun}，${t('showingTop')} ${visible}`
}

function Section({ title, items, totalCount, summaryLabel = '', ignored, ignore, t }: { title: string; items: TodoItem[]; totalCount?: number; summaryLabel?: string; ignored: Set<string>; ignore: (id: string) => void; t: (key: string) => string }) {
  const [expanded, setExpanded] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const allVisible = items.filter((item) => !ignored.has(item.id))
  const visible = expanded ? allVisible : allVisible.slice(0, 8)
  const total = totalCount ?? items.length
  const stopIgnore = (event: MouseEvent<HTMLButtonElement>, id: string) => {
    event.stopPropagation()
    ignore(id)
  }
  const stopMenu = (event: MouseEvent<HTMLElement>) => event.stopPropagation()
  return (
    <details className="skills-gov-group skills-governance-block" open>
      <summary>{title} <span>{sectionSummary(visible.length, total, summaryLabel, t)}</span></summary>
      {visible.length ? visible.map((item) => {
        const recordPath = item.evidenceKind ? evidencePath(location.search, item.evidenceKind, item.evidenceParams) : ''
        const open = recordPath ? () => navigate(recordPath) : undefined
        const viewLabel = item.viewLabel || (item.evidenceKind === 'untracked' ? t('viewRawRecords') : t('viewList'))
        return (
          <div
            className={`skills-gov-item ${item.severity} ${open ? 'clickable' : ''}`}
            key={item.id}
            role={open ? 'link' : undefined}
            tabIndex={open ? 0 : undefined}
            onClick={open}
            onKeyDown={open ? (event) => rowKey(event, open) : undefined}
          >
            <span>{item.title}<em>{item.detail}</em></span>
            <span className="skills-gov-actions">
              <span className="skills-gov-inline-actions">
                {recordPath ? (
                  <Link className="skills-gov-icon-action" to={recordPath} onClick={(event) => event.stopPropagation()} aria-label={`${viewLabel}: ${item.title}`} title={viewLabel}>
                    ▤
                  </Link>
                ) : null}
                <button className="skills-gov-ignore-action" type="button" onClick={(event) => stopIgnore(event, item.id)} aria-label={`${t('ignoreInPage')}: ${item.title}`}>{t('ignoreInPage')}</button>
              </span>
              <details className="skills-gov-menu" onClick={stopMenu}>
                <summary aria-label={`${item.title} ${t('moreActions')}`}>⋯</summary>
                <div>
                  {recordPath ? <Link to={recordPath}>{viewLabel}</Link> : null}
                  <button type="button" onClick={(event) => stopIgnore(event, item.id)}>{t('ignoreInPage')}</button>
                </div>
              </details>
            </span>
          </div>
        )
      }) : <div className="hint">{t('noTodo')}</div>}
      {allVisible.length > 8 ? (
        <button type="button" className="skills-gov-more" onClick={() => setExpanded((value) => !value)}>
          {expanded ? t('collapse') : `${t('showAll')} ${allVisible.length}`}
        </button>
      ) : null}
    </details>
  )
}

function operatorGroups(rows: OperatorTableRow[], t: (key: string) => string) {
  const heavy = rows.slice().sort((a, b) => Number(b.sessions_30d || 0) - Number(a.sessions_30d || 0)).slice(0, 8).map((row, index) => ({
    id: `heavy:${row.operator}`,
    title: row.operator,
    detail: `30d ${row.sessions_30d} ${t('records')} · ${row.skill_count} ${t('skillsUnit')}`,
    severity: index < 3 ? 'bad' as const : 'info' as const,
    evidenceKind: 'operators' as const,
    evidenceParams: { operator: row.operator },
  }))
  const sleeping = rows.filter((row) => Number(row.sessions_30d || 0) > 0 && Number(row.sessions_7d || 0) === 0).map((row) => ({
    id: `sleeping:${row.operator}`,
    title: row.operator,
    detail: `30d ${row.sessions_30d} ${t('records')} · 7d 0`,
    severity: 'warn' as const,
    evidenceKind: 'operators' as const,
    evidenceParams: { operator: row.operator },
  }))
  const narrow = rows.filter((row) => Number(row.sessions_30d || 0) > 0 && Number(row.skill_count || 0) <= 1).map((row) => ({
    id: `narrow:${row.operator}`,
    title: row.operator,
    detail: `${row.skill_count} ${t('skillsUnit')} · ${row.session_count} ${t('sessionCount')}`,
    severity: 'info' as const,
    evidenceKind: 'avg_per_session' as const,
    evidenceParams: { operator: row.operator },
  }))
  return { heavy, sleeping, narrow, untracked: [], idle: [], missing: [] }
}

export function GovernanceTodo({ data, view = 'skill', lang, t }: { data: SkillsOverview | null; view?: 'skill' | 'operator'; lang: Lang; t: (key: string) => string }) {
  const [ignored, setIgnored] = useState<Set<string>>(() => new Set())
  const windowKey = data?.window?.key || `${data?.days || 7}d`
  const groups = useMemo(() => {
    if (view === 'operator') return operatorGroups(data?.operator_table || [], t)
    const untracked = (data?.governance?.untracked_usage?.top || []).map((row: GovernanceUntrackedSkill, index) => ({
      id: `untracked:${row.name}`,
      title: skillDisplayName(row, lang, data?.skill_names),
      detail: `${row.sessions} ${t('records')} · ${row.users_30d || 0} ${t('operatorsUnit')} · ${t('lastUsed')} ${shortDay(row.last_day) || '—'}`,
      severity: index < 3 ? 'bad' as const : 'warn' as const,
      evidenceKind: 'untracked' as const,
      evidenceParams: { skill: row.name },
    }))
    const idle = (data?.governance?.idle_installed?.top || []).map((row: GovernanceBucketSkill) => ({
      id: `idle:${row.name}`,
      title: skillDisplayName(row, lang, data?.skill_names),
      detail: `${row.installers || 0} ${t('peopleInstalled')} · ${windowZeroUsageLabel(windowKey, t)} · ${t('lastUsed')} ${shortDay(row.last_day) || t('neverUsed')}`,
      severity: 'warn' as const,
      evidenceKind: 'idle' as const,
      evidenceParams: { skill: row.name },
    }))
    const missing = (data?.governance?.cataloged_not_installed?.top || []).map((row: GovernanceBucketSkill) => ({
      id: `missing:${row.name}`,
      title: skillDisplayName(row, lang, data?.skill_names),
      detail: row.cataloged_at ? `0 ${t('peopleInstalled')} · ${t('cataloged')} ${shortDay(row.cataloged_at) || String(row.cataloged_at).slice(0, 10)}` : `0 ${t('peopleInstalled')} · ${t('cataloged')}`,
      severity: 'info' as const,
      evidenceKind: 'zero_install' as const,
      evidenceParams: { skill: row.name },
      openable: false,
    }))
    return { untracked, idle, missing, heavy: [], sleeping: [], narrow: [] }
  }, [data, view, windowKey, lang, t])
  const ignore = (id: string) => setIgnored((old) => new Set([...old, id]))
  if (view === 'operator') {
    return (
      <div className="skills-governance">
        <div className="skills-panel-title">
          <b>{t('usageSignals')}</b>
          {ignored.size ? <button type="button" onClick={() => setIgnored(new Set())}>{t('restoreIgnored')}</button> : null}
        </div>
        <div className="skills-governance-blocks">
          <Section title={t('heavyUsers')} items={groups.heavy} ignored={ignored} ignore={ignore} t={t} />
          <Section title={t('sleeping7d')} items={groups.sleeping} summaryLabel="" ignored={ignored} ignore={ignore} t={t} />
          <Section title={t('lowCoverageUsers')} items={groups.narrow} summaryLabel="" ignored={ignored} ignore={ignore} t={t} />
        </div>
      </div>
    )
  }
  return (
    <div className="skills-governance">
      <div className="skills-panel-title">
        <b>{t('todoSignals')}</b>
        {ignored.size ? <button type="button" onClick={() => setIgnored(new Set())}>{t('restoreIgnored')}</button> : null}
      </div>
      <div className="skills-governance-blocks">
        <Section title={t('untrackedUsed')} items={groups.untracked} totalCount={data?.governance?.untracked_usage?.skill_count} summaryLabel={t('untrackedShort')} ignored={ignored} ignore={ignore} t={t} />
        <Section title={t('installedUnused')} items={groups.idle} totalCount={data?.governance?.idle_installed?.count} summaryLabel={t('installedUnusedShort')} ignored={ignored} ignore={ignore} t={t} />
        <Section title={t('catalogZeroInstall')} items={groups.missing} totalCount={data?.governance?.cataloged_not_installed?.count} summaryLabel={t('zeroInstallShort')} ignored={ignored} ignore={ignore} t={t} />
      </div>
    </div>
  )
}

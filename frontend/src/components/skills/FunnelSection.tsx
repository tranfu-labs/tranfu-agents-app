import { Empty } from '../Common'
import type { SkillsOverview } from '../../lib/types'
import { windowUsedLabel } from '../../lib/skillsPresentation'
import { skillDisplayName } from '../../lib/skillNames'
import type { Lang } from '../../lib/types'

export function FunnelSection({ data, lang, t }: { data: SkillsOverview | null; lang: Lang; t: (key: string) => string }) {
  const funnel = data?.funnel
  if (!funnel?.available) {
    return (
      <section className="frame">
        <Empty title={t('catalogUnavailable')} hint={data?.catalog?.error || ''} />
      </section>
    )
  }
  const max = Math.max((funnel.catalog || []).length, 1)
  const windowKey = data?.window?.key || `${data?.days || 7}d`
  const usedLabel = windowUsedLabel(windowKey, t)
  const rows = [
    ['catalog', t('catalogCollected'), funnel.catalog || []],
    ['installed', t('installed'), funnel.installed || []],
    ['used_30d', usedLabel, funnel.used_30d || []],
    ['idle', t('idleSkills'), funnel.idle || []],
  ] as const
  return (
    <section className="frame">
      <details className="skills-funnel">
        <summary>
          <b>{t('companyFunnel')}</b>
          <span>采集 {(funnel.catalog || []).length} · 已装 {(funnel.installed || []).length} · {usedLabel} {(funnel.used_30d || []).length} · 闲置 {(funnel.idle || []).length}</span>
        </summary>
        {data?.catalog?.stale ? <div className="note-warn">{t('catalogStale')}</div> : null}
        {rows.map(([key, label, list]) => {
          const pct = max ? Math.max(2, Math.round((list.length / max) * 100)) : 0
          return (
            <details key={key}>
              <summary className="funnel-row">
                <div className="funnel-name">{label}</div>
                <div className="funnel-track"><div className="funnel-fill" style={{ width: `${pct}%` }} /></div>
                <div className="funnel-num">{list.length}</div>
              </summary>
              <div className="funnel-list">{list.length ? list.map((item) => <span className="tag" key={item.name}>{skillDisplayName(item, lang, data?.skill_names)}</span>) : <span className="hint">{t('none')}</span>}</div>
            </details>
          )
        })}
      </details>
    </section>
  )
}

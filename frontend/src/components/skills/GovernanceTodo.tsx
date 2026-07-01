import { useMemo, useState } from 'react'
import type { GovernanceBucketSkill, GovernanceUntrackedSkill, OperatorTableRow, SkillsOverview } from '../../lib/types'

type TodoItem = { id: string; title: string; detail: string; severity: 'warn' | 'bad' | 'info' }

function Section({ title, items, ignored, ignore }: { title: string; items: TodoItem[]; ignored: Set<string>; ignore: (id: string) => void }) {
  const visible = items.filter((item) => !ignored.has(item.id)).slice(0, 8)
  return (
    <details className="skills-gov-group" open>
      <summary>{title} <span>{visible.length}/{items.length}</span></summary>
      {visible.length ? visible.map((item) => (
        <div className={`skills-gov-item ${item.severity}`} key={item.id}>
          <span>{item.title}<em>{item.detail}</em></span>
          <button type="button" onClick={() => ignore(item.id)}>忽略</button>
        </div>
      )) : <div className="hint">暂无待办</div>}
    </details>
  )
}

function operatorGroups(rows: OperatorTableRow[]) {
  const heavy = rows.slice().sort((a, b) => Number(b.sessions_30d || 0) - Number(a.sessions_30d || 0)).slice(0, 8).map((row, index) => ({
    id: `heavy:${row.operator}`,
    title: row.operator,
    detail: `30d ${row.sessions_30d} 次 · ${row.skill_count} skills`,
    severity: index < 3 ? 'bad' as const : 'info' as const,
  }))
  const sleeping = rows.filter((row) => Number(row.sessions_30d || 0) > 0 && Number(row.sessions_7d || 0) === 0).map((row) => ({
    id: `sleeping:${row.operator}`,
    title: row.operator,
    detail: `30d ${row.sessions_30d} 次 · 7d 0 次`,
    severity: 'warn' as const,
  }))
  const narrow = rows.filter((row) => Number(row.sessions_30d || 0) > 0 && Number(row.skill_count || 0) <= 1).map((row) => ({
    id: `narrow:${row.operator}`,
    title: row.operator,
    detail: `${row.skill_count} 个 skill · ${row.session_count} 会话`,
    severity: 'info' as const,
  }))
  return { heavy, sleeping, narrow, untracked: [], idle: [], missing: [] }
}

export function GovernanceTodo({ data, view = 'skill' }: { data: SkillsOverview | null; view?: 'skill' | 'operator' }) {
  const [ignored, setIgnored] = useState<Set<string>>(() => new Set())
  const groups = useMemo(() => {
    if (view === 'operator') return operatorGroups(data?.operator_table || [])
    const untracked = (data?.governance?.untracked_usage?.top || []).map((row: GovernanceUntrackedSkill, index) => ({
      id: `untracked:${row.name}`,
      title: row.name,
      detail: `${row.sessions} 次 · ${Math.round(row.share * 100)}%`,
      severity: index < 3 ? 'bad' as const : 'warn' as const,
    }))
    const idle = (data?.governance?.idle_installed?.top || []).map((row: GovernanceBucketSkill) => ({
      id: `idle:${row.name}`,
      title: row.name,
      detail: `装机 ${row.installers || 0} 人 · W 内 0 次`,
      severity: 'warn' as const,
    }))
    const missing = (data?.governance?.cataloged_not_installed?.top || []).map((row: GovernanceBucketSkill) => ({
      id: `missing:${row.name}`,
      title: row.name,
      detail: row.cataloged_at ? `${String(row.cataloged_at).slice(0, 10)} 收录` : '已收录 · 0 装机',
      severity: 'info' as const,
    }))
    return { untracked, idle, missing, heavy: [], sleeping: [], narrow: [] }
  }, [data, view])
  const ignore = (id: string) => setIgnored((old) => new Set([...old, id]))
  if (view === 'operator') {
    return (
      <div className="skills-governance">
        <div className="skills-panel-title">
          <b>使用待办</b>
          {ignored.size ? <button type="button" onClick={() => setIgnored(new Set())}>恢复已忽略</button> : null}
        </div>
        <Section title="重度使用者" items={groups.heavy} ignored={ignored} ignore={ignore} />
        <Section title="近 7 天沉睡" items={groups.sleeping} ignored={ignored} ignore={ignore} />
        <Section title="低覆盖使用者" items={groups.narrow} ignored={ignored} ignore={ignore} />
      </div>
    )
  }
  return (
    <div className="skills-governance">
      <div className="skills-panel-title">
        <b>治理待办</b>
        {ignored.size ? <button type="button" onClick={() => setIgnored(new Set())}>恢复已忽略</button> : null}
      </div>
      <Section title="有使用但未收录" items={groups.untracked} ignored={ignored} ignore={ignore} />
      <Section title="装了 W 内没用" items={groups.idle} ignored={ignored} ignore={ignore} />
      <Section title="收录但零装机" items={groups.missing} ignored={ignored} ignore={ignore} />
    </div>
  )
}

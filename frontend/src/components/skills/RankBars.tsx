import type { KeyboardEvent } from 'react'
import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { buildRankItems } from '../../lib/skillsDashboard'
import type { SkillTableRow } from '../../lib/types'
import { sourceLabel, skillColor } from '../../lib/utils'
import { evidencePath } from '../../lib/skillsEvidence'

function n(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(Math.round(Number(value || 0)))
}

function rowKey(event: KeyboardEvent<HTMLButtonElement>, action: () => void) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  action()
}

export function RankBars({ rows, topN, selected, onSelect, t }: { rows: SkillTableRow[]; topN: number; selected: string; onSelect: (name: string) => void; t: (key: string) => string }) {
  const [expanded, setExpanded] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const items = buildRankItems(rows, topN)
  const other = items.find((item) => item.isOther)
  const tailRows = useMemo(() => {
    const names = new Set(other?.names || [])
    return rows.filter((row) => names.has(row.name))
  }, [other, rows])
  const max = Math.max(...items.map((item) => item.value), 1)
  if (!items.length) return <div className="empty"><div className="t">{t('noSkills')}</div><div className="h">{t('noSkillsH')}</div></div>
  return (
    <div className="skills-rank-bars">
      {items.map((item) => {
        const active = selected && selected === item.name
        const dim = selected && !active
        const click = () => {
          if (item.isOther) setExpanded((value) => !value)
          else onSelect(item.name)
        }
        return (
          <button type="button" key={item.name} aria-expanded={item.isOther ? expanded : undefined} className={`${active ? 'selected' : ''} ${dim ? 'dimmed' : ''}`} onClick={click} onKeyDown={(event) => rowKey(event, click)}>
            <span className="rank-name">
              <i style={{ background: skillColor(item.name) }} />
              {item.name}
            </span>
            <span className="rank-track"><i style={{ width: `${Math.max(3, (item.value / max) * 100)}%`, background: skillColor(item.name) }} /></span>
            <strong>{n(item.value)}</strong>
            <em>
              {item.isOther ? (expanded ? '收起' : '展开') : sourceLabel(item.source, t)}
              {!item.isOther ? (
                <span
                  className="rank-evidence"
                  role="link"
                  tabIndex={-1}
                  onClick={(event) => {
                    event.stopPropagation()
                    navigate(evidencePath(location.search, 'total', { skill: item.name }))
                  }}
                >
                  看证据
                </span>
              ) : null}
            </em>
          </button>
        )
      })}
      {expanded && tailRows.length ? (
        <div className="skills-rank-tail">
          {tailRows.map((row) => (
            <button type="button" key={row.name} className={selected === row.name ? 'selected' : ''} onClick={() => onSelect(row.name)}>
              <span>{row.name}</span>
              <strong>{n(row.sessions_window ?? row.sessions_30d)}</strong>
              <em>{sourceLabel(row.source, t)}</em>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

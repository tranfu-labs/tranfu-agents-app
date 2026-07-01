import type { KeyboardEvent } from 'react'
import { buildRankItems } from '../../lib/skillsDashboard'
import type { SkillTableRow } from '../../lib/types'
import { sourceLabel, skillColor } from '../../lib/utils'

function n(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(Math.round(Number(value || 0)))
}

function rowKey(event: KeyboardEvent<HTMLButtonElement>, action: () => void) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  action()
}

export function RankBars({ rows, topN, selected, onSelect, t }: { rows: SkillTableRow[]; topN: number; selected: string; onSelect: (name: string) => void; t: (key: string) => string }) {
  const items = buildRankItems(rows, topN)
  const max = Math.max(...items.map((item) => item.value), 1)
  if (!items.length) return <div className="empty"><div className="t">{t('noSkills')}</div><div className="h">{t('noSkillsH')}</div></div>
  return (
    <div className="skills-rank-bars">
      {items.map((item) => {
        const active = selected && selected === item.name
        const dim = selected && !active
        const click = () => {
          if (!item.isOther) onSelect(item.name)
        }
        return (
          <button type="button" key={item.name} className={`${active ? 'selected' : ''} ${dim ? 'dimmed' : ''}`} onClick={click} onKeyDown={(event) => rowKey(event, click)}>
            <span className="rank-name">
              <i style={{ background: skillColor(item.name) }} />
              {item.name}
            </span>
            <span className="rank-track"><i style={{ width: `${Math.max(3, (item.value / max) * 100)}%`, background: skillColor(item.name) }} /></span>
            <strong>{n(item.value)}</strong>
            <em>{item.isOther ? '展开' : sourceLabel(item.source, t)}</em>
          </button>
        )
      })}
    </div>
  )
}

import type { KeyboardEvent, MouseEvent } from 'react'
import { MiniTrend, RuntimeBars } from '../Charts'
import type { SetSkillQueryState, SkillQueryState } from '../../lib/skillQuery'
import { deltaRatio, formatDelta } from '../../lib/skillsDashboard'
import type { SkillTableRow } from '../../lib/types'
import { sourceLabel } from '../../lib/utils'
import { windowPeriodLabel } from '../../lib/skillsPresentation'

function rowKey(event: KeyboardEvent<HTMLTableRowElement>, go: () => void) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  go()
}

function csvCell(value: unknown) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

function exportRows(rows: SkillTableRow[], suffix: string) {
  const csv = [
    ['skill', 'source', 'window_sessions', 'previous_sessions', 'delta', 'users_30d', 'runtime_counts', 'last_day'].map(csvCell).join(','),
    ...rows.map((row) => [
      row.name,
      row.source || '',
      row.sessions_window ?? row.sessions_30d,
      row.previous_sessions ?? '',
      formatDelta(deltaRatio(Number(row.sessions_window ?? row.sessions_30d ?? 0), Number(row.previous_sessions || 0))),
      row.users_30d,
      Object.entries(row.runtime_counts || {}).map(([key, value]) => `${key}:${value}`).join('|'),
      row.last_day || '',
    ].map(csvCell).join(',')),
  ].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `skills-${suffix}-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function SkillsDetailTable({ rows, allRows, params, setParams, selected, onOpen, t }: { rows: SkillTableRow[]; allRows: SkillTableRow[]; params: SkillQueryState; setParams: SetSkillQueryState; selected: string; onOpen: (name: string) => void; t: (key: string) => string }) {
  const windowLabel = windowPeriodLabel(params.w || `${params.win || 7}d`, t)
  const updateSort = (key: string) => {
    const dir = params.sort === key && params.dir !== 'asc' ? 'asc' : 'desc'
    void setParams({ sort: key, dir })
  }
  const head = (key: string, label: string, cls = '') => (
    <th className={`sort ${cls}`} onClick={(event: MouseEvent<HTMLTableCellElement>) => {
      event.stopPropagation()
      updateSort(key)
    }}>
      {label}
      {params.sort === key ? (params.dir === 'asc' ? ' ↑' : ' ↓') : ''}
    </th>
  )
  return (
    <section className="frame">
      <div className="skills-table-head">
        <h2><span><span className="sl">//</span>明细 · 排行完整视图</span><span className="cnt">{rows.length}</span></h2>
        <div className="token-table-actions">
          <button type="button" onClick={() => exportRows(rows, 'filtered')}>导出当前筛选</button>
          <button type="button" onClick={() => exportRows(allRows, 'all')}>导出全量</button>
        </div>
      </div>
      <div className="skills-wrap">
        <table className="skill-table mobile-card-table">
          <thead>
            <tr>
              {head('name', t('skillName'))}
              {head('source', t('sourceFilter'))}
              {head('sessions_window', windowLabel, 'num')}
              {head('previous_sessions', t('previousWindow'), 'num')}
              <th className="num">Δ%</th>
              {head('users_30d', t('skillUsers30'), 'num')}
              <th>{t('runtimeFilter')}</th>
              <th>{t('trend')}</th>
              {head('last_day', t('skillLast'))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const current = Number(row.sessions_window ?? row.sessions_30d ?? 0)
              const previous = Number(row.previous_sessions || 0)
              const open = () => onOpen(row.name)
              return (
                <tr key={row.name} className={selected === row.name ? 'selected' : ''} role="button" tabIndex={0} onClick={open} onKeyDown={(event) => rowKey(event, open)}>
                  <td className="mobile-main" data-label={t('skillName')}><b>{row.name}</b></td>
                  <td data-label={t('sourceFilter')}><span className="source-pill">{sourceLabel(row.source, t)}</span></td>
                  <td className="num" data-label={windowLabel}>{current}</td>
                  <td className="num" data-label={t('previousWindow')}>{previous || '—'}</td>
                  <td className="num" data-label="Δ%">{formatDelta(deltaRatio(current, previous))}</td>
                  <td className="num" data-label={t('skillUsers30')}>{row.users_30d}</td>
                  <td data-label={t('runtimeFilter')}><RuntimeBars counts={row.runtime_counts} /></td>
                  <td data-label={t('trend')}><MiniTrend values={row.trend_14d} /></td>
                  <td className="q" data-label={t('skillLast')}>{row.last_day || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

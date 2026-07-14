import type { Lang, SkillsOverview, SkillTableRow } from '../../lib/types'
import type { ReactNode } from 'react'
import { buildDonutSegments, buildSourceDonutSegments, type DonutSegment } from '../../lib/skillsAttribution'
import { skillDisplayName } from '../../lib/skillNames'
import { RT, skillColor, sourceLabel, sourceKey } from '../../lib/utils'

const SOURCE_COLORS: Record<string, string> = {
  cataloged: '#0ea5e9',
  own: '#2563eb',
  meta: '#0891b2',
  external: '#16a34a',
  non_catalog: '#f97316',
}

function polar(cx: number, cy: number, r: number, angle: number) {
  return [cx + Math.cos(angle - Math.PI / 2) * r, cy + Math.sin(angle - Math.PI / 2) * r]
}

function arcPath(segment: DonutSegment, inner: number, outer: number) {
  const [x1, y1] = polar(50, 50, outer, segment.start)
  const [x2, y2] = polar(50, 50, outer, segment.end)
  const [x3, y3] = polar(50, 50, inner, segment.end)
  const [x4, y4] = polar(50, 50, inner, segment.start)
  const large = segment.end - segment.start > Math.PI ? 1 : 0
  return `M ${x1} ${y1} A ${outer} ${outer} 0 ${large} 1 ${x2} ${y2} L ${x3} ${y3} A ${inner} ${inner} 0 ${large} 0 ${x4} ${y4} Z`
}

function DonutShell({ title, total, children }: { title: string; total: number; children: ReactNode }) {
  return (
    <div className="skills-donut">
      <b>{title}</b>
      {total ? children : <div className="empty compact"><div className="t">Empty</div></div>}
    </div>
  )
}

export function AttributionDonuts({ data, selected, rows, lang, setSource, t }: { data: SkillsOverview | null; selected: string; rows: SkillTableRow[]; lang: Lang; setSource: (source: string) => void; t: (key: string) => string }) {
  const selectedRow = selected ? rows.find((row) => row.name === selected) : undefined
  const selectedLabel = selectedRow ? skillDisplayName(selectedRow, lang, data?.skill_names) : selected
  const sourceCounts = Object.fromEntries((data?.attribution?.by_source || []).map((row) => [sourceKey(row.source), Number(row.sessions || 0)]))
  const runtimeCounts = selectedRow?.runtime_counts || Object.fromEntries((data?.attribution?.by_runtime || []).map((row) => [row.runtime, Number(row.sessions || 0)]))
  const totalSource = Object.values(sourceCounts).reduce((sum, value) => sum + Number(value || 0), 0)
  const totalRuntime = Object.values(runtimeCounts).reduce((sum, value) => sum + Number(value || 0), 0)
  const sourceModel = buildSourceDonutSegments(sourceCounts)
  const runtimeSegments = buildDonutSegments(Object.entries(runtimeCounts).map(([key, value]) => ({ key, value })))
  const untrackedRatio = totalSource ? Number(sourceCounts.non_catalog || 0) / totalSource : 0
  return (
    <section className="skills-attribution">
      <DonutShell title={selectedRow ? `${selectedLabel} · runtime` : '按来源占比'} total={selectedRow ? totalRuntime : totalSource}>
        <svg viewBox="0 0 100 100" role="img" aria-label="source attribution">
          {selectedRow ? runtimeSegments.map((segment) => <path key={segment.key} d={arcPath(segment, 30, 45)} fill={skillColor(segment.key)} />) : (
            <>
              {sourceModel.inner.map((segment) => <path key={segment.key} d={arcPath(segment, 22, 32)} fill={SOURCE_COLORS[segment.key]} opacity=".7" onClick={() => segment.key === 'non_catalog' && setSource('non_catalog')} />)}
              {sourceModel.outer.map((segment) => <path key={segment.key} d={arcPath(segment, 34, 46)} fill={SOURCE_COLORS[segment.key]} onClick={() => setSource(sourceKey(segment.key))} />)}
            </>
          )}
          <text x="50" y="49" textAnchor="middle" fill="var(--text)" fontSize="9" fontWeight="700">{totalSource || totalRuntime}</text>
          <text x="50" y="60" textAnchor="middle" fill="var(--muted)" fontSize="5">{selectedRow ? 'sessions' : `未收录 ${Math.round(untrackedRatio * 100)}%`}</text>
        </svg>
        <div className="skills-donut-legend">
          {(selectedRow ? Object.entries(runtimeCounts) : Object.entries(sourceCounts)).filter(([, value]) => Number(value) > 0).map(([key, value]) => (
            <span key={key}><i style={{ background: selectedRow ? skillColor(key) : SOURCE_COLORS[sourceKey(key)] }} />{selectedRow ? (RT[key] || key) : sourceLabel(key, t)}<b>{value}</b></span>
          ))}
        </div>
      </DonutShell>
      <DonutShell title={selectedRow ? `${selectedLabel} · runtime` : '按 runtime 占比'} total={totalRuntime}>
        <svg viewBox="0 0 100 100" role="img" aria-label="runtime attribution">
          {runtimeSegments.map((segment) => <path key={segment.key} d={arcPath(segment, 28, 44)} fill={skillColor(segment.key)} />)}
          <text x="50" y="52" textAnchor="middle" fill="var(--text)" fontSize="10" fontWeight="700">{totalRuntime}</text>
        </svg>
        <div className="skills-donut-legend">
          {Object.entries(runtimeCounts).filter(([, value]) => Number(value) > 0).map(([key, value]) => (
            <span key={key}><i style={{ background: skillColor(key) }} />{RT[key] || key}<b>{value}</b></span>
          ))}
        </div>
      </DonutShell>
    </section>
  )
}

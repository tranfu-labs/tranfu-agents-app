import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Empty, SectionTitle } from '../components/Common'
import { formatRecentRecordTime } from '../lib/timeFormat'
import type { Lang, SkillsEvidenceKind, SkillsEvidencePayload } from '../lib/types'
import { sourceLabel } from '../lib/utils'
import {
  evidenceDisplayTotalCount,
  evidenceHasMore,
  evidenceLoadedCount,
  evidencePageQuery,
  evidencePath,
  evidenceQueryKey,
  mergeEvidencePage,
  shouldApplyEvidencePage,
  skillsBackSearch,
  startEvidencePageRequest,
  type SkillsEvidencePageMode,
} from '../lib/skillsEvidence'
import { humanFilterChips } from '../lib/skillsClues'
import { defaultEvidenceTab, evidenceSummaryLine, isListEvidenceKind } from '../lib/skillsPresentation'

const EVIDENCE_PAGE_LIMIT = 100
const LOAD_MORE_TIMEOUT_MS = 15000

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

function pageMode(data: SkillsEvidencePayload | null | undefined): SkillsEvidencePageMode {
  return isListEvidenceKind(data?.kind) ? 'items' : 'records'
}

function loadMoreText(error: string, loading: boolean, mode: SkillsEvidencePageMode, lang: Lang) {
  if (loading) return lang === 'zh' ? '加载中...' : 'Loading...'
  if (error === 'timeout') return lang === 'zh' ? '加载超时，重试' : 'Timed out, retry'
  if (error) return lang === 'zh' ? '加载失败，重试' : 'Load failed, retry'
  if (mode === 'items') return lang === 'zh' ? '加载更多名单' : 'Load more items'
  return lang === 'zh' ? '加载更多记录' : 'Load more records'
}

function completeText(total: number, mode: SkillsEvidencePageMode, lang: Lang) {
  if (mode === 'items') return lang === 'zh' ? `已加载全部 ${total} 项名单` : `Loaded all ${total} items`
  return lang === 'zh' ? `已加载全部 ${total} 条记录` : `Loaded all ${total} records`
}

function keepLoadedRowsWithFreshContext(fresh: SkillsEvidencePayload, previous: SkillsEvidencePayload, mode: SkillsEvidencePageMode) {
  return {
    ...previous,
    today: fresh.today || previous.today,
    window: fresh.window || previous.window,
    summary: fresh.summary || previous.summary,
    actions: fresh.actions || previous.actions,
    applied_filters: fresh.applied_filters || previous.applied_filters,
    ignored_filters: fresh.ignored_filters || previous.ignored_filters,
    top_skills: fresh.top_skills || previous.top_skills,
    top_operators: fresh.top_operators || previous.top_operators,
    daily: fresh.daily || previous.daily,
    catalog: fresh.catalog || previous.catalog,
    records: mode === 'records' ? previous.records : fresh.records,
    items: mode === 'items' ? previous.items : fresh.items,
  }
}

async function fetchEvidencePage(query: string, signal: AbortSignal) {
  const response = await fetch(`/api/skills/evidence?${query}`, { cache: 'no-store', signal })
  if (!response.ok) throw new Error(String(response.status))
  return (await response.json()) as SkillsEvidencePayload
}

export function SkillsEvidenceView({ data, loading, error, lang, search, t }: { data: SkillsEvidencePayload | null; loading: boolean; error: string; lang: Lang; search: string; t: (key: string) => string }) {
  const currentQueryKey = useMemo(() => evidenceQueryKey(search), [search])
  const currentSearchRef = useRef(search)
  currentSearchRef.current = search
  const currentQueryKeyRef = useRef(currentQueryKey)
  currentQueryKeyRef.current = currentQueryKey
  const appliedQueryKeyRef = useRef(currentQueryKey)
  const mountedRef = useRef(false)
  const pageDataRef = useRef<SkillsEvidencePayload | null>(data)
  const requestRef = useRef<{ controller: AbortController; key: string } | null>(null)
  const [pageData, setPageData] = useState<SkillsEvidencePayload | null>(data)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreError, setLoadMoreError] = useState('')

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      requestRef.current?.controller.abort()
      requestRef.current = null
    }
  }, [])

  useEffect(() => {
    pageDataRef.current = pageData
  }, [pageData])

  useEffect(() => {
    const previousKey = appliedQueryKeyRef.current
    const queryChanged = previousKey !== currentQueryKey
    appliedQueryKeyRef.current = currentQueryKey
    if (queryChanged) {
      requestRef.current?.controller.abort()
      requestRef.current = null
      setLoadingMore(false)
      setLoadMoreError('')
      setPageData(null)
      return
    }
    setPageData((previous) => {
      if (!data) return null
      const mode = pageMode(data)
      if (!queryChanged && previous && previous.kind === data.kind && evidenceLoadedCount(previous, mode) > evidenceLoadedCount(data, mode)) {
        return keepLoadedRowsWithFreshContext(data, previous, mode)
      }
      return data
    })
  }, [currentQueryKey, data])

  const displayData = pageData || data
  const mode = pageMode(displayData)
  const records = displayData?.records || []
  const items = displayData?.items || []
  const back = `/skills${skillsBackSearch(search)}`
  const listFirst = mode === 'items'
  const untrackedRecords = Number(displayData?.summary?.untracked_records || 0)
  const showUntrackedSlice = displayData?.kind === 'total' && untrackedRecords > 0
  const loadedCount = evidenceLoadedCount(displayData, mode)
  const totalCount = evidenceDisplayTotalCount(displayData, mode)
  const hasMore = evidenceHasMore(displayData, mode)
  const showLoadControl = totalCount > EVIDENCE_PAGE_LIMIT || loadingMore || Boolean(loadMoreError)
  const progressLabel = `${n(loadedCount)} / ${n(totalCount)}`
  const recordsSectionCount = mode === 'records' && showLoadControl ? progressLabel : records.length
  const itemsSectionCount = mode === 'items' && showLoadControl ? progressLabel : items.length

  const loadMore = useCallback(async () => {
    const current = pageDataRef.current
    if (!current) return
    const requestMode = pageMode(current)
    const requestKey = evidenceQueryKey(search)
    const loaded = evidenceLoadedCount(current, requestMode)
    if (!evidenceHasMore(current, requestMode)) return
    const query = evidencePageQuery(search, loaded, EVIDENCE_PAGE_LIMIT)
    requestRef.current?.controller.abort()
    const request = startEvidencePageRequest(query, fetchEvidencePage, LOAD_MORE_TIMEOUT_MS)
    requestRef.current = { controller: request.controller, key: requestKey }
    setLoadingMore(true)
    setLoadMoreError('')
    try {
      const next = await request.promise
      if (!mountedRef.current || !shouldApplyEvidencePage(requestKey, currentSearchRef.current) || currentQueryKeyRef.current !== requestKey) return
      const base = pageDataRef.current
      if (!base) return
      const before = evidenceLoadedCount(base, requestMode)
      const merged = mergeEvidencePage(base, next, requestMode)
      const after = evidenceLoadedCount(merged, requestMode)
      setPageData(merged)
      setLoadMoreError(after <= before && evidenceHasMore(merged, requestMode) ? 'stalled' : '')
    } catch {
      if (!mountedRef.current || !shouldApplyEvidencePage(requestKey, currentSearchRef.current) || currentQueryKeyRef.current !== requestKey) return
      setLoadMoreError(request.didTimeout() ? 'timeout' : 'failed')
    } finally {
      if (requestRef.current?.controller === request.controller) requestRef.current = null
      if (mountedRef.current && currentQueryKeyRef.current === requestKey) setLoadingMore(false)
    }
  }, [search])

  const loadMoreControl = (controlMode: SkillsEvidencePageMode) => {
    if (controlMode !== mode) return null
    if (!showLoadControl) return null
    if (!hasMore && !loadMoreError && !loadingMore) {
      return (
        <div className="evidence-load-more done" aria-live="polite">
          <span>{completeText(totalCount, controlMode, lang)}</span>
        </div>
      )
    }
    return (
      <div className="evidence-load-more" aria-live="polite">
        <button type="button" onClick={loadMore} disabled={loadingMore}>
          {loadMoreText(loadMoreError, loadingMore, controlMode, lang)}
        </button>
        <span>{progressLabel}</span>
      </div>
    )
  }

  const recordsSection = (
    <section className="frame evidence-primary">
      <SectionTitle title="原始记录" count={recordsSectionCount} />
      {records.length ? (
        <div className="skills-wrap">
          <table className="skill-table mobile-card-table records-table evidence-records-table">
            <thead>
              <tr><th>Time</th><th>Skill</th><th>Operator</th><th>Runtime</th><th>Source</th><th>Session</th></tr>
            </thead>
            <tbody>
              {records.map((record, index) => {
                const time = formatRecentRecordTime(record.first_seen, record.day || '', lang, undefined, displayData?.today)
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
          {loadMoreControl('records')}
        </div>
      ) : <Empty title={items.length ? '这类记录没有窗口内触发记录' : '暂无记录'} />}
    </section>
  )
  const itemsSection = (
    <section className="frame evidence-primary">
      <SectionTitle title="名单" count={itemsSectionCount} />
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
          {loadMoreControl('items')}
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
            <h1>{kindLabel(displayData?.kind, lang)}</h1>
            <p>{displayData?.window?.start || '—'} .. {displayData?.window?.end || '—'}</p>
          </div>
          <FilterChips data={displayData} t={t} />
          <div className="evidence-summary-line">
            <span>{evidenceSummaryLine(displayData)}</span>
            {showUntrackedSlice ? (
              <Link to={evidencePath(search, 'untracked')} aria-label="查看未收录 skill 记录">↗</Link>
            ) : null}
          </div>
          <div className="evidence-toolbar" role="toolbar" aria-label="记录页动作">
            <span className="evidence-tab-current">{defaultEvidenceTab(displayData?.kind)}</span>
            {(displayData?.actions || []).map((action) => (
              <span className="evidence-tool" key={action.id} aria-label={action.label} title={action.label}>
                {actionGlyph(action.id, action.label)}
              </span>
            ))}
          </div>
        </div>
      </section>
      {error ? <div className="note-warn">{t(error)}</div> : null}
      {loading && !displayData ? <section className="frame"><Empty title={t('loading')} /></section> : null}
      {displayData ? (listFirst ? itemsSection : recordsSection) : null}
      {displayData && !listFirst && items.length ? itemsSection : null}
      {displayData ? (
        <div className="skills-main-split evidence-split evidence-aux">
          <section className="frame">
            <SectionTitle title="Top skills" count={displayData.top_skills?.length || 0} />
            <div className="evidence-list">
              {(displayData.top_skills || []).slice(0, 10).map((row) => (
                <div className="evidence-list-row" key={row.name}>
                  <b>{row.name}</b>
                  <span>{sourceLabel(row.source, t)} · {n(row.records)} records · {n(row.operators)} operators</span>
                </div>
              ))}
              {displayData.top_skills?.length ? null : <Empty title="暂无 skill 分组" />}
            </div>
          </section>
          <section className="frame">
            <SectionTitle title="Top operators" count={displayData.top_operators?.length || 0} />
            <div className="evidence-list">
              {(displayData.top_operators || []).slice(0, 10).map((row) => (
                <div className="evidence-list-row" key={row.operator}>
                  <b>{row.operator}</b>
                  <span>{n(row.records)} records · {n(row.skills)} skills</span>
                </div>
              ))}
              {displayData.top_operators?.length ? null : <Empty title="暂无 operator 分组" />}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}

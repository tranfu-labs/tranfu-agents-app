import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Empty, SectionTitle } from '../components/Common'
import {
  deleteAdminData,
  exportAdminDb,
  fetchAdminInventory,
  fetchAdminPreview,
  fetchAdminTrash,
  restoreAdminBatch,
} from '../lib/api'
import type { AdminInventory, AdminInventoryRow, AdminPreview, AdminTarget, AdminTrashBatch } from '../lib/types'
import { fmtTs, RT } from '../lib/utils'

type AdminTab = 'operators' | 'identities' | 'sessions' | 'skills' | 'trash'

const STORAGE_KEY = 'tf_admin_key'
const TABS: AdminTab[] = ['operators', 'identities', 'sessions', 'skills', 'trash']

function countLine(counts?: Record<string, number>) {
  const order = ['events', 'skill_uses', 'profiles', 'operators']
  return order
    .filter((key) => counts?.[key])
    .map((key) => `${key.replace('skill_uses', 'skills')} ${counts?.[key]}`)
    .join(' · ') || '0'
}

function rowId(tab: AdminTab, row: AdminInventoryRow) {
  if (tab === 'operators') return `op:${row.operator || ''}`
  if (tab === 'identities') return `id:${row.operator || ''}:${row.agent || ''}:${row.runtime || ''}`
  if (tab === 'sessions') return `sid:${row.session_id || ''}`
  return `skill:${row.skill || row.name}`
}

function targetForRow(tab: AdminTab, row: AdminInventoryRow): AdminTarget {
  if (tab === 'operators') return { operator: row.operator || '', profile: true }
  if (tab === 'identities') return { operator: row.operator || '', agent: row.agent || '', runtime: row.runtime || '', profile: true }
  if (tab === 'sessions') return { session_ids: [row.session_id || row.name] }
  return { skill: row.skill || row.name }
}

function tabRows(data: AdminInventory | null, tab: AdminTab) {
  if (!data || tab === 'trash') return []
  return data[tab] || []
}

function Guard({ t, onSubmit, error }: { t: (key: string) => string; onSubmit: (key: string) => void; error: string }) {
  const [value, setValue] = useState('')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (value.trim()) onSubmit(value.trim())
  }
  return (
    <div className="admin-gate">
      <form className="frame gate-box" onSubmit={submit}>
        <h2>
          <span>
            <span className="sl">//</span>
            {t('adminGateTitle')}
          </span>
        </h2>
        <div className="pad gate-body">
          <label className="field admin-field">
            <span>{t('adminKey')}</span>
            <input value={value} onChange={(event) => setValue(event.target.value)} type="password" autoFocus />
          </label>
          {error ? <div className="note-warn">{error}</div> : null}
          <div className="admin-btnrow">
            <Link className="btn slim" to="/">
              {t('cancel')}
            </Link>
            <button className="btn slim danger-fill" type="submit">
              {t('adminEnter')}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}

function InventoryTable({
  tab,
  rows,
  selected,
  setSelected,
  t,
}: {
  tab: AdminTab
  rows: AdminInventoryRow[]
  selected: Set<string>
  setSelected: (next: Set<string>) => void
  t: (key: string) => string
}) {
  if (!rows.length) return <Empty title={t('adminEmpty')} hint={t('adminEmptyHint')} />
  const toggle = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
  }
  return (
    <div className="skills-wrap">
      <table className="skill-table admin-table">
        <thead>
          <tr>
            <th className="checkcol" />
            <th>{t('adminName')}</th>
            <th>{t('adminScope')}</th>
            <th className="num">events</th>
            <th className="num">skills</th>
            <th>{t('adminRecent')}</th>
            <th>{t('adminActive')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const id = rowId(tab, row)
            const scope = tab === 'skills'
              ? `${row.used || 0} used / ${row.equipped || 0} equipped`
              : tab === 'sessions'
                ? `${row.operator || t('none')} · ${RT[row.runtime || ''] || row.runtime || t('none')}`
                : `${row.identities || row.profiles || row.operators || 0}`
            return (
              <tr key={id} className={selected.has(id) ? 'picked' : ''} onClick={() => toggle(id)}>
                <td className="checkcol">
                  <input
                    type="checkbox"
                    checked={selected.has(id)}
                    onChange={() => toggle(id)}
                    onClick={(event) => event.stopPropagation()}
                  />
                </td>
                <td>
                  <b>{row.name || row.session_id || row.skill}</b>
                  {row.active ? <span className="mode-badge danger">{t('adminLive')}</span> : null}
                </td>
                <td className="q">{scope}</td>
                <td className="num">{row.events || 0}</td>
                <td className="num">{row.skill_uses || 0}</td>
                <td className="q">{fmtTs(row.last_seen) || row.first_day || '—'}</td>
                <td>{row.active ? <span className="dot" style={{ background: 'var(--run)' }} /> : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function PreviewPanel({
  preview,
  force,
  setForce,
  confirmCount,
  setConfirmCount,
  onDelete,
  onCancel,
  deleting,
  t,
}: {
  preview: AdminPreview
  force: boolean
  setForce: (value: boolean) => void
  confirmCount: string
  setConfirmCount: (value: string) => void
  onDelete: () => void
  onCancel: () => void
  deleting: boolean
  t: (key: string) => string
}) {
  const confirmOk = !preview.requires_confirm || Number(confirmCount) === preview.total_rows
  return (
    <section className="frame admin-preview">
      <SectionTitle title={t('adminPreview')} count={preview.preview_token.slice(0, 8)} />
      <div className="pad">
        <div className="admin-counts">
          <span>{countLine(preview.counts)}</span>
          <b>{preview.total_rows}</b>
        </div>
        {preview.active_sessions.length ? (
          <>
            <label className="checkline warn">
              <input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} />
              {t('adminForce')} · {preview.active_sessions.length}
            </label>
            <div className="admin-active-list">
              <b>{t('adminActiveSessions')}</b>
              {preview.active_sessions.slice(0, 8).map((session) => (
                <div key={session.session_id} className="admin-active-row">
                  <span className="mono">{session.session_id}</span>
                  <span>{session.operator || '—'} · {RT[session.runtime || ''] || session.runtime || '—'} · {session.status || '—'}</span>
                  <span className="q">{fmtTs(session.last_seen)}</span>
                </div>
              ))}
            </div>
          </>
        ) : null}
        {preview.requires_confirm ? (
          <label className="field admin-field">
            <span>{t('adminConfirmCount')}</span>
            <input value={confirmCount} onChange={(event) => setConfirmCount(event.target.value)} inputMode="numeric" />
          </label>
        ) : null}
        <div className="admin-effects">
          <div>
            <b>{t('operatorName')}</b>
            <span>{preview.operators.join(', ') || '—'}</span>
          </div>
          <div>
            <b>{t('adminFirstDay')}</b>
            <span>
              {(preview.effects?.first_day_changes || [])
                .map((item) => `${item.skill}: ${item.from || '∅'}→${item.to || '∅'}`)
                .join(', ') || '—'}
            </span>
          </div>
          <div>
            <b>{t('adminIdentities')}</b>
            <span>{(preview.effects?.identities_cleared || []).join(', ') || '—'}</span>
          </div>
        </div>
        <div className="admin-btnrow">
          <button className="btn slim" type="button" onClick={onCancel}>
            {t('cancel')}
          </button>
          <button className="btn slim danger-fill" type="button" disabled={!confirmOk || deleting} onClick={onDelete}>
            {deleting ? t('loading') : t('adminDelete')}
          </button>
        </div>
      </div>
    </section>
  )
}

function TrashTable({ batches, onRestore, restoring, t }: { batches: AdminTrashBatch[]; onRestore: (id: string) => void; restoring: string; t: (key: string) => string }) {
  if (!batches.length) return <Empty title={t('adminTrashEmpty')} />
  return (
    <div className="skills-wrap">
      <table className="skill-table admin-table">
        <thead>
          <tr>
            <th>{t('adminBatch')}</th>
            <th>{t('adminRecent')}</th>
            <th>{t('adminScope')}</th>
            <th>{t('adminRows')}</th>
            <th>{t('adminStatus')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {batches.map((batch) => (
            <tr key={batch.batch_id}>
              <td className="mono">{batch.batch_id.slice(0, 8)}</td>
              <td className="q">{fmtTs(batch.created)}</td>
              <td className="q">{JSON.stringify((batch.selector as { targets?: unknown })?.targets || batch.selector).slice(0, 90)}</td>
              <td>{countLine(batch.counts)}</td>
              <td>{batch.restored ? t('adminRestored') : t('adminInTrash')}</td>
              <td className="num">
                <button className="btn mini" type="button" disabled={batch.restored || restoring === batch.batch_id} onClick={() => onRestore(batch.batch_id)}>
                  {restoring === batch.batch_id ? t('loading') : t('adminRestore')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AdminView({ t }: { t: (key: string) => string }) {
  const [adminKey, setAdminKey] = useState(() => window.sessionStorage.getItem(STORAGE_KEY) || '')
  const [gateError, setGateError] = useState('')
  const [tab, setTab] = useState<AdminTab>('operators')
  const [query, setQuery] = useState('')
  const [activeOnly, setActiveOnly] = useState(false)
  const [inventory, setInventory] = useState<AdminInventory | null>(null)
  const [trash, setTrash] = useState<AdminTrashBatch[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [previewData, setPreviewData] = useState<AdminPreview | null>(null)
  const [previewTargets, setPreviewTargets] = useState<AdminTarget[]>([])
  const [previewOptions, setPreviewOptions] = useState<{ cascade_children?: boolean; revoke?: boolean }>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [cascadeChildren, setCascadeChildren] = useState(false)
  const [revoke, setRevoke] = useState(false)
  const [force, setForce] = useState(false)
  const [confirmCount, setConfirmCount] = useState('')
  const [restoring, setRestoring] = useState('')
  const [exporting, setExporting] = useState(false)
  const [manualOperator, setManualOperator] = useState('')
  const [manualBeforeDay, setManualBeforeDay] = useState('')

  useEffect(() => {
    // 安全:不再从 URL 读取 admin key —— ?key= 会被反代/CDN 访问日志明文记录。
    // 旧链接若仍带 key,只清理地址栏、不予采用;key 一律走页面内手动输入。
    const params = new URLSearchParams(window.location.search)
    if (params.has('key')) {
      window.history.replaceState({}, '', '/admin')
    }
  }, [])

  const refresh = useCallback(async () => {
    if (!adminKey) return
    setBusy(true)
    try {
      const [nextInventory, nextTrash] = await Promise.all([
        fetchAdminInventory(adminKey, query, 200),
        fetchAdminTrash(adminKey),
      ])
      setInventory(nextInventory)
      setTrash(nextTrash.trash)
      setGateError('')
      setError('')
    } catch {
      window.sessionStorage.removeItem(STORAGE_KEY)
      setAdminKey('')
      setGateError(t('adminBadKey'))
      setError(t('adminBadKey'))
    } finally {
      setBusy(false)
    }
  }, [adminKey, query, t])

  useEffect(() => {
    const id = window.setTimeout(() => void refresh(), 0)
    return () => window.clearTimeout(id)
  }, [refresh])

  useEffect(() => {
    const id = window.setTimeout(() => {
      setSelected(new Set())
      setPreviewData(null)
      setPreviewTargets([])
      setPreviewOptions({})
      setForce(false)
      setConfirmCount('')
    }, 0)
    return () => window.clearTimeout(id)
  }, [tab, query])

  const rows = useMemo(() => {
    const base = tabRows(inventory, tab)
    return activeOnly ? base.filter((row) => row.active) : base
  }, [activeOnly, inventory, tab])

  const selectedRows = rows.filter((row) => selected.has(rowId(tab, row)))
  const targets = selectedRows.map((row) => targetForRow(tab, row))

  const enter = (key: string) => {
    window.sessionStorage.setItem(STORAGE_KEY, key)
    setAdminKey(key)
  }

  const logout = () => {
    window.sessionStorage.removeItem(STORAGE_KEY)
    setAdminKey('')
    setInventory(null)
    setTrash([])
    setPreviewData(null)
    setPreviewTargets([])
  }

  const cancelPreview = () => {
    setPreviewData(null)
    setPreviewTargets([])
    setPreviewOptions({})
    setForce(false)
    setConfirmCount('')
  }

  const runPreviewFor = async (nextTargets: AdminTarget[]) => {
    if (!nextTargets.length) return
    setBusy(true)
    setError('')
    try {
      const nextOptions = { cascade_children: cascadeChildren, revoke }
      const next = await fetchAdminPreview(adminKey, nextTargets, nextOptions)
      setPreviewData(next)
      setPreviewTargets(nextTargets)
      setPreviewOptions(nextOptions)
      setForce(false)
      setConfirmCount('')
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadError'))
    } finally {
      setBusy(false)
    }
  }

  const runPreview = async () => {
    await runPreviewFor(targets)
  }

  const runBeforeDayPreview = async () => {
    const operator = manualOperator.trim()
    if (!operator || !manualBeforeDay) return
    await runPreviewFor([{ before_day: manualBeforeDay, operator }])
  }

  const runDelete = async () => {
    if (!previewData || !previewTargets.length) return
    setBusy(true)
    setError('')
    try {
      const result = await deleteAdminData(adminKey, previewTargets, previewData.preview_token, {
        ...previewOptions,
        force,
        confirm_count: confirmCount ? Number(confirmCount) : undefined,
      })
      setToast(`${t('adminDeleted')}: ${countLine(result.counts)}`)
      setSelected(new Set())
      cancelPreview()
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? `${t('loadError')} ${err.message}` : t('loadError'))
    } finally {
      setBusy(false)
    }
  }

  const restore = async (batchId: string) => {
    setRestoring(batchId)
    setError('')
    try {
      await restoreAdminBatch(adminKey, batchId)
      setToast(t('adminRestoredOk'))
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? `${t('loadError')} ${err.message}` : t('loadError'))
    } finally {
      setRestoring('')
    }
  }

  const exportDb = async () => {
    if (!window.confirm(t('adminExportConfirm'))) return
    setExporting(true)
    setError('')
    try {
      await exportAdminDb(adminKey)
      setToast(t('adminExportOk'))
    } catch (err) {
      setError(err instanceof Error ? `${t('loadError')} ${err.message}` : t('loadError'))
    } finally {
      setExporting(false)
    }
  }

  if (!adminKey) {
    return <Guard t={t} error={gateError} onSubmit={enter} />
  }

  return (
    <div className="admin-page">
      <div className="admin-head">
        <Link className="back" to="/">
          {t('adminBack')}
        </Link>
        <button className="btn mini" type="button" onClick={logout}>
          {t('adminExit')}
        </button>
      </div>
      <section className="frame admin-banner">
        <div className="pad">
          <b>{t('adminTitle')}</b>
          <span>{t('adminWarning')}</span>
          <button className="btn mini admin-export" type="button" disabled={exporting} onClick={() => void exportDb()}>
            {exporting ? t('loading') : t('adminExport')}
          </button>
        </div>
      </section>
      <div className="admin-tabs">
        {TABS.map((item) => (
          <button type="button" key={item} className={tab === item ? 'on' : ''} onClick={() => setTab(item)}>
            {t(`adminTab_${item}`)}
          </button>
        ))}
      </div>
      {tab !== 'trash' ? (
        <>
          <section className="frame">
            <div className="toolbar admin-toolbar">
              <label className="field">
                <span>{t('adminSearch')}</span>
                <input value={query} onChange={(event) => setQuery(event.target.value)} />
              </label>
              <label className="checkline">
                <input type="checkbox" checked={activeOnly} onChange={(event) => setActiveOnly(event.target.checked)} />
                {t('adminActiveOnly')}
              </label>
              <label className="checkline">
                <input type="checkbox" checked={cascadeChildren} onChange={(event) => setCascadeChildren(event.target.checked)} />
                {t('adminCascade')}
              </label>
              <label className="checkline">
                <input type="checkbox" checked={revoke} onChange={(event) => setRevoke(event.target.checked)} />
                {t('adminRevoke')}
              </label>
              <button className="btn mini" type="button" onClick={() => void refresh()}>
                {busy ? t('loading') : t('refresh')}
              </button>
            </div>
          </section>
          <section className="frame admin-date-cleanup">
            <SectionTitle title={t('adminBeforeDayTitle')} count="UTC" />
            <div className="toolbar admin-toolbar">
              <label className="field">
                <span>{t('adminBeforeOperator')}</span>
                <input value={manualOperator} onChange={(event) => setManualOperator(event.target.value)} />
              </label>
              <label className="field">
                <span>{t('adminBeforeDay')}</span>
                <input type="date" value={manualBeforeDay} onChange={(event) => setManualBeforeDay(event.target.value)} />
              </label>
              <button className="btn mini danger-fill" type="button" disabled={!manualOperator.trim() || !manualBeforeDay || busy} onClick={() => void runBeforeDayPreview()}>
                {t('adminBeforePreview')}
              </button>
            </div>
          </section>
          <section className="frame" style={{ marginTop: 16 }}>
            <SectionTitle title={t(`adminTab_${tab}`)} count={rows.length} />
            <InventoryTable tab={tab} rows={rows} selected={selected} setSelected={setSelected} t={t} />
          </section>
          <section className="frame admin-actionbar">
            <div className="pad">
              <span>{t('adminSelected')} {selectedRows.length}</span>
              <button className="btn mini" type="button" onClick={() => setSelected(new Set())}>
                {t('clear')}
              </button>
              <button className="btn mini danger-fill" type="button" disabled={!selectedRows.length || busy} onClick={() => void runPreview()}>
                {t('adminRunPreview')}
              </button>
            </div>
          </section>
          {previewData ? (
            <PreviewPanel
              preview={previewData}
              force={force}
              setForce={setForce}
              confirmCount={confirmCount}
              setConfirmCount={setConfirmCount}
              onCancel={cancelPreview}
              onDelete={() => void runDelete()}
              deleting={busy}
              t={t}
            />
          ) : null}
        </>
      ) : (
        <section className="frame">
          <SectionTitle title={t('adminTrash')} count={trash.length} />
          <TrashTable batches={trash} onRestore={(id) => void restore(id)} restoring={restoring} t={t} />
        </section>
      )}
      {error ? <div className="note-warn admin-error">{error}</div> : null}
      {toast ? (
        <button type="button" className="toast show" onClick={() => setToast('')}>
          {toast}
        </button>
      ) : null}
    </div>
  )
}

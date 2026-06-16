import { useCallback, useEffect, useRef, useState } from 'react'
import { DEMO_STATE, demoOperatorDetail, demoSkillDetail, demoSkillsOverview } from './demo'
import type {
  AdminInventory,
  AdminPreview,
  AdminTarget,
  AdminTrashBatch,
  Loadable,
  OperatorDetail,
  SkillDetail,
  SkillsOverview,
  StatePayload,
} from './types'

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: 'no-store', ...init })
  if (!response.ok) throw new Error(String(response.status))
  return (await response.json()) as T
}

function adminHeaders(key: string) {
  return { 'content-type': 'application/json', 'X-TF-Admin-Key': key }
}

export async function fetchAdminInventory(key: string, q: string, limit = 200): Promise<AdminInventory> {
  const params = new URLSearchParams()
  if (q.trim()) params.set('q', q.trim())
  params.set('limit', String(limit))
  return fetchJson<AdminInventory>(`/api/admin/inventory?${params.toString()}`, {
    headers: { 'X-TF-Admin-Key': key },
  })
}

export async function fetchAdminPreview(
  key: string,
  targets: AdminTarget[],
  options: { cascade_children?: boolean; revoke?: boolean } = {},
): Promise<AdminPreview> {
  return fetchJson<AdminPreview>('/api/admin/preview', {
    method: 'POST',
    headers: adminHeaders(key),
    body: JSON.stringify({ targets, ...options }),
  })
}

export async function deleteAdminData(
  key: string,
  targets: AdminTarget[],
  previewToken: string,
  options: { cascade_children?: boolean; revoke?: boolean; force?: boolean; confirm_count?: number } = {},
) {
  return fetchJson<{ ok: boolean; batch_id: string; counts: Record<string, number> }>('/api/admin/data', {
    method: 'DELETE',
    headers: adminHeaders(key),
    body: JSON.stringify({ targets, preview_token: previewToken, ...options }),
  })
}

export async function fetchAdminTrash(key: string): Promise<{ ok: boolean; trash: AdminTrashBatch[] }> {
  return fetchJson<{ ok: boolean; trash: AdminTrashBatch[] }>('/api/admin/trash', {
    headers: { 'X-TF-Admin-Key': key },
  })
}

export async function restoreAdminBatch(key: string, batchId: string) {
  return fetchJson<{ ok: boolean; batch_id: string; restored: Record<string, { attempted: number; inserted: number; skipped: number }> }>('/api/admin/restore', {
    method: 'POST',
    headers: adminHeaders(key),
    body: JSON.stringify({ batch_id: batchId }),
  })
}

export async function exportAdminDb(key: string): Promise<void> {
  // 全库导出不可逆(含敏感字段),用 POST + 显式 confirm 作二次确认,
  // 不走可被预取/缓存的 GET。
  const response = await fetch('/api/admin/export', {
    method: 'POST',
    cache: 'no-store',
    headers: adminHeaders(key),
    body: JSON.stringify({ confirm: 'EXPORT' }),
  })
  if (!response.ok) throw new Error(String(response.status))
  // browser <a download> can't carry the admin header, so fetch->blob->click.
  const disposition = response.headers.get('content-disposition') || ''
  const match = /filename="?([^"]+)"?/i.exec(disposition)
  const filename = match ? match[1] : `tf-${new Date().toISOString().slice(0, 10)}.db`
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function usePollingState(): Loadable<StatePayload> {
  const [data, setData] = useState<StatePayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [demo, setDemo] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const next = await fetchJson<StatePayload>('/api/state')
      next.leverage = next.leverage || DEMO_STATE.leverage
      next.skills = next.skills || []
      setData(next)
      setError('')
      setDemo(false)
    } catch {
      setData(DEMO_STATE)
      setError('offline')
      setDemo(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const first = window.setTimeout(() => void refresh(), 0)
    const timer = window.setInterval(() => void refresh(), 3000)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(timer)
    }
  }, [refresh])

  return { data, loading, error, demo, refresh }
}

export function useSkillsOverview(enabled: boolean, days: number): Loadable<SkillsOverview> {
  const [data, setData] = useState<SkillsOverview | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState('')
  const [demo, setDemo] = useState(false)
  const lastFetch = useRef(0)

  const refresh = useCallback(
    async (force = false) => {
      const now = Date.now()
      if (!enabled || (!force && now - lastFetch.current < 9500)) return
      setLoading(true)
      try {
        const next = await fetchJson<SkillsOverview>(`/api/skills?days=${days}`)
        setData(next)
        setError('')
        setDemo(false)
        lastFetch.current = Date.now()
      } catch {
        setData((old) => old || demoSkillsOverview())
        setError('loadError')
        setDemo(true)
      } finally {
        setLoading(false)
      }
    },
    [days, enabled],
  )

  useEffect(() => {
    if (!enabled) return
    const first = window.setTimeout(() => void refresh(true), 0)
    const timer = window.setInterval(() => void refresh(false), 10000)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(timer)
    }
  }, [enabled, refresh])

  return { data, loading, error, demo, refresh }
}

export function useSkillDetail(enabled: boolean, name: string | undefined, fallback?: SkillsOverview | null): Loadable<SkillDetail> {
  const [data, setData] = useState<SkillDetail | null>(null)
  const [loading, setLoading] = useState(Boolean(enabled && name))
  const [error, setError] = useState('')
  const [demo, setDemo] = useState(false)
  const lastFetch = useRef(0)

  const refresh = useCallback(
    async (force = false) => {
      const now = Date.now()
      if (!enabled || !name || (!force && now - lastFetch.current < 9500)) return
      setLoading(true)
      try {
        const next = await fetchJson<SkillDetail>(`/api/skill/${encodeURIComponent(name)}`)
        setData(next)
        setError('')
        setDemo(false)
        lastFetch.current = Date.now()
      } catch {
        setData(demoSkillDetail(name, fallback || demoSkillsOverview()))
        setError('skillNotFound')
        setDemo(true)
      } finally {
        setLoading(false)
      }
    },
    [enabled, fallback, name],
  )

  useEffect(() => {
    if (!enabled) return
    const first = window.setTimeout(() => void refresh(true), 0)
    const timer = window.setInterval(() => void refresh(false), 10000)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(timer)
    }
  }, [enabled, refresh])

  const visibleData = name && data?.name !== name ? null : data
  const visibleLoading = loading || Boolean(name && data && data.name !== name)
  return { data: visibleData, loading: visibleLoading, error, demo, refresh }
}

export function useOperatorDetail(enabled: boolean, name: string | undefined, fallback?: SkillsOverview | null): Loadable<OperatorDetail> {
  const [data, setData] = useState<OperatorDetail | null>(null)
  const [loading, setLoading] = useState(Boolean(enabled && name))
  const [error, setError] = useState('')
  const [demo, setDemo] = useState(false)
  const lastFetch = useRef(0)

  const refresh = useCallback(
    async (force = false) => {
      const now = Date.now()
      if (!enabled || !name || (!force && now - lastFetch.current < 9500)) return
      setLoading(true)
      try {
        const next = await fetchJson<OperatorDetail>(`/api/operator/${encodeURIComponent(name)}`)
        setData(next)
        setError('')
        setDemo(false)
        lastFetch.current = Date.now()
      } catch {
        setData(demoOperatorDetail(name, fallback || demoSkillsOverview()))
        setError('operatorNotFound')
        setDemo(true)
      } finally {
        setLoading(false)
      }
    },
    [enabled, fallback, name],
  )

  useEffect(() => {
    if (!enabled) return
    const first = window.setTimeout(() => void refresh(true), 0)
    const timer = window.setInterval(() => void refresh(false), 10000)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(timer)
    }
  }, [enabled, refresh])

  const visibleData = name && data?.operator !== name ? null : data
  const visibleLoading = loading || Boolean(name && data && data.operator !== name)
  return { data: visibleData, loading: visibleLoading, error, demo, refresh }
}

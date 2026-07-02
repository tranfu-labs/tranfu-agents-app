import { useCallback, useEffect, useRef, useState } from 'react'
import { DEMO_STATE, demoOperatorDetail, demoSkillDetail, demoSkillsOverview } from './demo'
import { makeTokenUsageComparisonRange } from './tokenUsageRange'
import type {
  AdminInventory,
  AdminPreview,
  AdminTarget,
  AdminTrashBatch,
  Loadable,
  OperatorDetail,
  SkillDetail,
  SkillsEvidenceKind,
  SkillsEvidencePayload,
  SkillsOverview,
  StatePayload,
  TokenUsageQuery,
  TokenUsagePayload,
} from './types'

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: 'no-store', ...init })
  if (!response.ok) throw new Error(String(response.status))
  return (await response.json()) as T
}

function normalizeState(next: StatePayload): StatePayload {
  next.leverage = next.leverage || DEMO_STATE.leverage
  next.skills = next.skills || []
  return next
}

function adminHeaders(key: string) {
  return { 'content-type': 'application/json', 'X-TF-Admin-Key': key }
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

const TOKEN_USAGE_GRANULARITIES: TokenUsageQuery['timeGranularity'][] = ['hour', 'four_hour', 'day', 'week', 'month']

function tokenUsageQueryKey(query: TokenUsageQuery) {
  return `${query.startTimestamp}:${query.endTimestamp}:${query.timeGranularity}`
}

function tokenUsageUrl(query: TokenUsageQuery) {
  const timezoneOffsetMinutes = -new Date().getTimezoneOffset()
  const params = new URLSearchParams({
    start_timestamp: String(query.startTimestamp),
    end_timestamp: String(query.endTimestamp),
    time_granularity: query.timeGranularity,
    timezone_offset_minutes: String(timezoneOffsetMinutes),
  })
  return `/api/token-usage?${params.toString()}`
}

async function fetchTokenUsagePayload(query: TokenUsageQuery, signal?: AbortSignal) {
  return fetchJson<TokenUsagePayload>(tokenUsageUrl(query), signal ? { signal } : undefined)
}

function emptySkillsEvidence(query: string): SkillsEvidencePayload {
  const params = new URLSearchParams(query)
  return {
    kind: (params.get('kind') || 'total') as SkillsEvidenceKind,
    today: new Date().toISOString().slice(0, 10),
    summary: {},
    actions: [],
    applied_filters: {},
    ignored_filters: [],
    top_skills: [],
    top_operators: [],
    daily: [],
    records: [],
    items: [],
  }
}

async function fetchTokenUsageWithComparison(query: TokenUsageQuery, signal?: AbortSignal) {
  const comparison = makeTokenUsageComparisonRange(query)
  const next = await fetchTokenUsagePayload(query, signal)
  try {
    const previous = await fetchTokenUsagePayload(comparison.query, signal)
    return {
      ...next,
      comparison: {
        label: comparison.label,
        data: previous.data,
        range: previous.range,
        source: previous.source,
        cached: previous.cached,
      },
    }
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') throw err
    return next
  }
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
  const dataRef = useRef<StatePayload | null>(null)
  const inFlight = useRef(false)
  const fallbackActive = useRef(false)

  const applyState = useCallback((next: StatePayload) => {
    const normalized = normalizeState(next)
    dataRef.current = normalized
    setData(normalized)
    setError('')
    setDemo(false)
    setLoading(false)
  }, [])

  const refresh = useCallback(async () => {
    if (inFlight.current) return
    inFlight.current = true
    try {
      const next = await fetchJson<StatePayload>('/api/state')
      applyState(next)
    } catch {
      dataRef.current = DEMO_STATE
      setData(DEMO_STATE)
      setError('offline')
      setDemo(true)
      setLoading(false)
    } finally {
      inFlight.current = false
    }
  }, [applyState])

  useEffect(() => {
    let stopped = false
    let fallbackTimer: number | undefined
    let source: EventSource | null = null
    let opened = false
    let openGuard: number | undefined

    const clearFallbackTimer = () => {
      if (fallbackTimer !== undefined) {
        window.clearTimeout(fallbackTimer)
        fallbackTimer = undefined
      }
    }

    const fallbackDelay = () => {
      if (document.visibilityState === 'hidden') return 60000
      return (dataRef.current?.totals?.live || 0) > 0 ? 3000 : 15000
    }

    const scheduleFallback = (delay = fallbackDelay()) => {
      if (stopped || !fallbackActive.current) return
      clearFallbackTimer()
      fallbackTimer = window.setTimeout(async () => {
        await refresh()
        scheduleFallback()
      }, delay)
    }

    const startFallback = () => {
      if (stopped || fallbackActive.current) return
      fallbackActive.current = true
      scheduleFallback(0)
    }

    if (typeof EventSource === 'undefined') {
      startFallback()
    } else {
      source = new EventSource('/api/state/stream')
      source.onopen = () => {
        opened = true
        fallbackActive.current = false
        clearFallbackTimer()
      }
      source.addEventListener('state', (event) => {
        try {
          applyState(JSON.parse((event as MessageEvent).data) as StatePayload)
        } catch {
          source?.close()
          startFallback()
        }
      })
      source.onerror = () => {
        source?.close()
        startFallback()
      }
      openGuard = window.setTimeout(() => {
        if (!opened) {
          source?.close()
          startFallback()
        }
      }, 4000)
    }

    const onVisibility = () => {
      if (fallbackActive.current) scheduleFallback(0)
    }
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      stopped = true
      source?.close()
      if (openGuard !== undefined) window.clearTimeout(openGuard)
      clearFallbackTimer()
      fallbackActive.current = false
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [applyState, refresh])

  return { data, loading, error, demo, refresh }
}

export function useSkillsOverview(enabled: boolean, days: number, query = `days=${days}`): Loadable<SkillsOverview> {
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
        const next = await fetchJson<SkillsOverview>(`/api/skills?${query}`)
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
    [days, enabled, query],
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

export function useSkillsEvidence(enabled: boolean, query: string): Loadable<SkillsEvidencePayload> {
  const [data, setData] = useState<SkillsEvidencePayload | null>(null)
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
        const next = await fetchJson<SkillsEvidencePayload>(`/api/skills/evidence?${query}`)
        setData(next)
        setError('')
        setDemo(false)
        lastFetch.current = Date.now()
      } catch {
        setData((old) => old || emptySkillsEvidence(query))
        setError('loadError')
        setDemo(true)
      } finally {
        setLoading(false)
      }
    },
    [enabled, query],
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

export function useTokenUsage(enabled: boolean, query: TokenUsageQuery): Loadable<TokenUsagePayload> {
  const [data, setData] = useState<TokenUsagePayload | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState('')
  const [demo, setDemo] = useState(false)
  const cacheRef = useRef(new Map<string, { data: TokenUsagePayload; ts: number }>())
  const prefetchingRef = useRef(new Set<string>())
  const requestSeq = useRef(0)
  const abortRef = useRef<AbortController | null>(null)
  const queryKey = tokenUsageQueryKey(query)

  const prefetchPeerGranularities = useCallback(
    (baseQuery: TokenUsageQuery) => {
      TOKEN_USAGE_GRANULARITIES.forEach((timeGranularity, index) => {
        if (timeGranularity === baseQuery.timeGranularity) return
        const nextQuery = { ...baseQuery, timeGranularity }
        const nextKey = tokenUsageQueryKey(nextQuery)
        if (cacheRef.current.has(nextKey) || prefetchingRef.current.has(nextKey)) return
        prefetchingRef.current.add(nextKey)
        window.setTimeout(() => {
          void fetchTokenUsagePayload(nextQuery)
            .then((next) => {
              cacheRef.current.set(nextKey, { data: next, ts: Date.now() })
            })
            .catch(() => undefined)
            .finally(() => {
              prefetchingRef.current.delete(nextKey)
            })
        }, 200 + index * 120)
      })
    },
    [],
  )

  const refresh = useCallback(
    async (force = false) => {
      const now = Date.now()
      if (!enabled) return
      const cached = cacheRef.current.get(queryKey)
      if (cached) {
        setData(cached.data)
        setError('')
        setDemo(cached.data.source === 'demo')
        prefetchPeerGranularities(query)
        if (!force && now - cached.ts < 55000) return
      }
      const seq = requestSeq.current + 1
      requestSeq.current = seq
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      setLoading(true)
      try {
        let next: TokenUsagePayload | null = null
        for (let attempt = 0; attempt < 2; attempt += 1) {
          try {
            next = await fetchTokenUsageWithComparison(query, controller.signal)
            break
          } catch (err) {
            if ((err as Error)?.name === 'AbortError' || attempt === 1) throw err
            await wait(700)
          }
        }
        if (requestSeq.current !== seq) return
        if (!next) throw new Error('empty response')
        cacheRef.current.set(queryKey, { data: next, ts: Date.now() })
        setData(next)
        setError('')
        setDemo(next.source === 'demo')
        prefetchPeerGranularities(query)
      } catch (err) {
        if ((err as Error)?.name === 'AbortError') return
        if (requestSeq.current !== seq) return
        setError('loadError')
        setDemo(false)
      } finally {
        if (requestSeq.current === seq) setLoading(false)
      }
    },
    [enabled, prefetchPeerGranularities, query, queryKey],
  )
  useEffect(() => {
    if (!enabled) return
    const first = window.setTimeout(() => void refresh(false), 120)
    const timer = window.setInterval(() => void refresh(false), 60000)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(timer)
      abortRef.current?.abort()
    }
  }, [enabled, queryKey, refresh])
  return { data, loading, error, demo, refresh }
}

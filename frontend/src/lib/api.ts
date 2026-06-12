import { useCallback, useEffect, useRef, useState } from 'react'
import { DEMO_STATE, demoSkillDetail, demoSkillsOverview } from './demo'
import type { Loadable, SkillDetail, SkillsOverview, StatePayload } from './types'

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) throw new Error(String(response.status))
  return (await response.json()) as T
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

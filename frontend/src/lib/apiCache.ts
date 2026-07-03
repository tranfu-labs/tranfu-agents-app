type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
type CachedEntry = { etag: string; data: unknown }

export type RevalidatedJsonFetcher = {
  <T>(url: string, init?: RequestInit): Promise<T>
  peek<T>(url: string): T | null
}

async function fetchJson<T>(fetchImpl: FetchLike, url: string, init?: RequestInit): Promise<T> {
  const response = await fetchImpl(url, { cache: 'no-store', ...init })
  if (!response.ok) throw new Error(String(response.status))
  return (await response.json()) as T
}

export function createRevalidatedJsonFetcher(fetchImpl: FetchLike = fetch) {
  const inFlight = new Map<string, Promise<unknown>>()
  const cached = new Map<string, CachedEntry>()
  const fetchRevalidatedJson = async function fetchRevalidatedJson<T>(url: string, init?: RequestInit): Promise<T> {
    const method = String(init?.method || 'GET').toUpperCase()
    if (method !== 'GET') return fetchJson<T>(fetchImpl, url, init)
    const active = inFlight.get(url)
    if (active) return active as Promise<T>
    const request = (async () => {
      const entry = cached.get(url)
      const headers = new Headers(init?.headers || {})
      if (entry?.etag) headers.set('If-None-Match', entry.etag)
      const response = await fetchImpl(url, { cache: 'no-store', ...init, headers })
      if (response.status === 304) {
        if (!entry) throw new Error('304')
        return entry.data as T
      }
      if (!response.ok) throw new Error(String(response.status))
      const data = (await response.json()) as T
      const etag = response.headers.get('etag') || ''
      if (etag) cached.set(url, { etag, data })
      else cached.delete(url)
      return data
    })().finally(() => {
      inFlight.delete(url)
    })
    inFlight.set(url, request)
    return request
  } as RevalidatedJsonFetcher
  fetchRevalidatedJson.peek = function peek<T>(url: string): T | null {
    return (cached.get(url)?.data as T | undefined) || null
  }
  return fetchRevalidatedJson
}

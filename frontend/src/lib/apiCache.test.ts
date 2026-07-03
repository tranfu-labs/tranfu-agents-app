import assert from 'node:assert/strict'
import { createRevalidatedJsonFetcher } from './apiCache.ts'

function jsonResponse(body: unknown, etag = '', status = 200) {
  const headers = new Headers({ 'content-type': 'application/json' })
  if (etag) headers.set('etag', etag)
  return new Response(status === 304 ? null : JSON.stringify(body), { status, headers })
}

export async function runApiCacheTests() {
  {
    const calls: Array<{ url: string; etag: string }> = []
    const fetcher = createRevalidatedJsonFetcher(async (input, init) => {
      const headers = new Headers(init?.headers || {})
      const url = String(input)
      calls.push({ url, etag: headers.get('if-none-match') || '' })
      if (calls.length === 1) return jsonResponse({ value: 1 }, '"a"')
      return jsonResponse(null, '"a"', 304)
    })

    assert.deepEqual(await fetcher<{ value: number }>('/api/skills?w=7d'), { value: 1 })
    assert.deepEqual(await fetcher<{ value: number }>('/api/skills?w=7d'), { value: 1 })
    assert.deepEqual(calls, [
      { url: '/api/skills?w=7d', etag: '' },
      { url: '/api/skills?w=7d', etag: '"a"' },
    ])
    assert.deepEqual(fetcher.peek('/api/skills?w=7d'), { value: 1 })
  }

  {
    const calls: string[] = []
    let resolveFetch: ((response: Response) => void) | undefined
    const fetcher = createRevalidatedJsonFetcher((input) => {
      calls.push(String(input))
      return new Promise<Response>((resolve) => { resolveFetch = resolve })
    })
    const first = fetcher<{ ok: boolean }>('/api/skills?w=7d')
    const second = fetcher<{ ok: boolean }>('/api/skills?w=7d')
    resolveFetch?.(jsonResponse({ ok: true }, '"same"'))

    assert.deepEqual(await first, { ok: true })
    assert.deepEqual(await second, { ok: true })
    assert.deepEqual(calls, ['/api/skills?w=7d'])
  }

  {
    const calls: string[] = []
    const fetcher = createRevalidatedJsonFetcher(async (input) => {
      calls.push(String(input))
      return jsonResponse({ value: calls.length }, '"cached"')
    })

    assert.equal(fetcher.peek('/api/skills?w=7d'), null)
    assert.deepEqual(await fetcher<{ value: number }>('/api/skills?w=7d'), { value: 1 })
    assert.deepEqual(fetcher.peek('/api/skills?w=7d'), { value: 1 })
    assert.deepEqual(calls, ['/api/skills?w=7d'])
  }

  {
    const calls: Array<{ url: string; etag: string }> = []
    const fetcher = createRevalidatedJsonFetcher(async (input, init) => {
      const headers = new Headers(init?.headers || {})
      const url = String(input)
      calls.push({ url, etag: headers.get('if-none-match') || '' })
      return jsonResponse({ url }, `"${url}"`)
    })

    await fetcher('/api/skills?w=7d')
    await fetcher('/api/skills?w=14d')
    assert.deepEqual(fetcher.peek('/api/skills?w=7d'), { url: '/api/skills?w=7d' })
    assert.deepEqual(fetcher.peek('/api/skills?w=14d'), { url: '/api/skills?w=14d' })
    assert.deepEqual(calls, [
      { url: '/api/skills?w=7d', etag: '' },
      { url: '/api/skills?w=14d', etag: '' },
    ])
  }
}

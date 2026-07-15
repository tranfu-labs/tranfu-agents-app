import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { normalizeTokenUsageFilters, resolveTokenUsageApiQuery } from './tokenUsageQuery.ts'

function readSource(relativePath: string) {
  for (const candidate of [path.join(process.cwd(), relativePath), path.join(process.cwd(), 'frontend', relativePath)]) {
    try {
      return readFileSync(candidate, 'utf8')
    } catch {
      // npm --prefix and direct node runs use different cwd shapes.
    }
  }
  throw new Error(`missing source file ${relativePath}`)
}

test('token usage URL filters keep current defaults compact and deterministic', () => {
  assert.deepEqual(normalizeTokenUsageFilters({}), {
    w: 'today',
    wstart: '',
    wend: '',
    granularity: 'hour',
    kind: 'all',
    model: 'all',
    risk: 'all',
    topLimit: 10,
    q: '',
    hideZero: false,
    sort: { field: 'quota', dir: 'desc' },
  })
})

test('token usage URL filters preserve every shareable control', () => {
  assert.deepEqual(normalizeTokenUsageFilters({
    w: '30d',
    wstart: '1783900800',
    wend: '1783987200',
    g: 'day',
    kind: 'dapp',
    model: 'gpt-5 codex/专用',
    risk: 'high_error',
    topn: 20,
    q: ' Alice 团队 ',
    hz: '1',
    sort: 'request_count',
    dir: 'asc',
  }), {
    w: '30d',
    wstart: '1783900800',
    wend: '1783987200',
    granularity: 'day',
    kind: 'dapp',
    model: 'gpt-5 codex/专用',
    risk: 'high_error',
    topLimit: 20,
    q: ' Alice 团队 ',
    hideZero: true,
    sort: { field: 'request_count', dir: 'asc' },
  })
})

test('token usage custom URL range waits for two valid endpoints', () => {
  const now = new Date('2026-07-15T12:30:00+08:00')
  assert.equal(resolveTokenUsageApiQuery({ w: 'custom', wstart: '1783900800', wend: '', g: 'day' }, now), null)
  assert.equal(resolveTokenUsageApiQuery({ w: 'custom', wstart: '1783987200', wend: '1783900800', g: 'day' }, now), null)
  assert.deepEqual(resolveTokenUsageApiQuery({ w: 'custom', wstart: '1783900800', wend: '1783987200', g: 'day' }, now), {
    preset: 'custom',
    startTimestamp: 1783900800,
    endTimestamp: 1783987200,
    timeGranularity: 'day',
  })
})

test('token usage URL filters reject invalid enum and numeric values', () => {
  assert.deepEqual(normalizeTokenUsageFilters({
    w: 'forever',
    wstart: '-1',
    wend: 'NaN',
    g: 'minute',
    kind: 'team',
    risk: 'mystery',
    topn: 999,
    hz: 'yes',
    sort: 'password',
    dir: 'sideways',
  }), {
    w: 'today',
    wstart: '',
    wend: '',
    granularity: 'hour',
    kind: 'all',
    model: 'all',
    risk: 'all',
    topLimit: 10,
    q: '',
    hideZero: false,
    sort: { field: 'quota', dir: 'desc' },
  })
})

test('token usage preset and granularity map to a stable API query', () => {
  const now = new Date('2026-07-15T12:30:00+08:00')
  const query = resolveTokenUsageApiQuery({ w: 'today', g: 'hour', kind: 'dapp', q: 'alice', sort: 'request_count' }, now)
  assert.deepEqual(query, {
    preset: 'today',
    startTimestamp: 1784044800,
    endTimestamp: 1784089800,
    timeGranularity: 'hour',
  })
})

test('token usage route and view share nuqs URL state while transient state stays local', () => {
  const app = readSource('src/App.tsx')
  const view = readSource('src/views/TokenUsage.tsx')
  assert.ok(app.includes('useTokenUsageQueryState'))
  assert.ok(app.includes('resolveTokenUsageApiQuery'))
  assert.ok(view.includes("update({ kind: 'all' })"))
  assert.ok(view.includes("update({ hz: event.target.checked ? '1' : '0' })"))
  assert.ok(view.includes('update({ sort: next.field, dir: next.dir })'))
  assert.ok(view.includes('useState<number | null>(null)'))
  assert.ok(view.includes('useState<Set<string>>'))
})

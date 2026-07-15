import assert from 'node:assert/strict'
import test from 'node:test'
import {
  loadTokenUsageQueryState,
  normalizeTokenUsageFilters,
  resolveTokenUsageApiQuery,
  resolveTokenUsageModel,
  serializeTokenUsageQueryState,
  tokenUsageCustomRangeIssue,
  tokenUsagePayloadMatchesQuery,
  tokenUsagePresetPatch,
  tokenUsageQueryOptions,
} from './tokenUsageQuery.ts'

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
  const expected = {
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
  }
  const serialized = serializeTokenUsageQueryState({
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
  })
  assert.equal(new URLSearchParams(serialized).get('q'), ' Alice 团队 ')
  assert.equal(new URLSearchParams(serialized).get('model'), 'gpt-5 codex/专用')
  assert.deepEqual(normalizeTokenUsageFilters(loadTokenUsageQueryState(serialized)), expected)
})

test('token usage nuqs serializer removes defaults and stale custom endpoints', () => {
  assert.equal(serializeTokenUsageQueryState({
    w: 'today', wstart: '', wend: '', g: 'hour', kind: 'all', model: 'all', risk: 'all',
    topn: 10, q: '', hz: '0', sort: 'quota', dir: 'desc',
  }), '')
  assert.equal(serializeTokenUsageQueryState('?w=custom&wstart=1&wend=2', tokenUsagePresetPatch('30d')), '?w=30d')
  assert.deepEqual(tokenUsagePresetPatch('custom'), { w: 'custom' })
  assert.equal(tokenUsageQueryOptions.history, 'replace')
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

test('token usage custom range reports incomplete and reversed drafts', () => {
  assert.equal(tokenUsageCustomRangeIssue({ w: 'custom', wstart: '1783900800', wend: '' }), 'incomplete')
  assert.equal(tokenUsageCustomRangeIssue({ w: 'custom', wstart: '1783987200', wend: '1783900800' }), 'order')
  assert.equal(tokenUsageCustomRangeIssue({ w: 'custom', wstart: '1783900800', wend: '1783987200' }), null)
  assert.equal(tokenUsageCustomRangeIssue({ w: '30d', wstart: '', wend: '' }), null)
})

test('token usage model waits for payload before falling back from stale URLs', () => {
  assert.equal(resolveTokenUsageModel('retired-model', [], false), 'retired-model')
  assert.equal(resolveTokenUsageModel('retired-model', ['gpt-5'], true), 'all')
  assert.equal(resolveTokenUsageModel('gpt-5', ['gpt-5'], true), 'gpt-5')
  const query = { preset: '30d', startTimestamp: 10, endTimestamp: 20, timeGranularity: 'day' as const }
  assert.equal(tokenUsagePayloadMatchesQuery({ start_timestamp: 10, end_timestamp: 20, time_granularity: 'day' }, query), true)
  assert.equal(tokenUsagePayloadMatchesQuery({ start_timestamp: 1, end_timestamp: 2, time_granularity: 'day' }, query), false)
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

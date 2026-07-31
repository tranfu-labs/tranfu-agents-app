import assert from 'node:assert/strict'
import test from 'node:test'
import { normalizeTokenUsagePayload, resolveTokenUsageDisplayState, tokenUsageSyncDelay, tokenUsageUrl } from './tokenUsagePayload.ts'
import type { TokenUsagePayload } from './types.ts'

test('token usage API request carries the comparison range in one request', () => {
  const url = tokenUsageUrl({
    preset: 'custom',
    startTimestamp: 200,
    endTimestamp: 300,
    timeGranularity: 'day',
  })
  const params = new URLSearchParams(url.split('?')[1])
  assert.equal(params.get('start_timestamp'), '200')
  assert.equal(params.get('end_timestamp'), '300')
  assert.equal(params.get('comparison_start_timestamp'), '100')
  assert.equal(params.get('comparison_end_timestamp'), '200')
})

test('schema v2 USD fields become the frontend view values without quota conversion', () => {
  const payload: TokenUsagePayload = {
    ok: true,
    schema_version: 2,
    source: 'sub2api',
    data: {
      summary: [{
        token_id: 7,
        token_name: 'legacy',
        api_key_id: 7,
        api_key_name: 'key-a',
        actual_cost_usd: 0.25,
        quota_remaining_usd: 8,
        quota_used_lifetime_usd: 2,
        total_tokens: 30,
        average_duration_ms: 1250,
      }],
      trend: [{ token_id: 7, token_name: 'legacy', created_at: 1, actual_cost_usd: 0.1, request_count: 2, total_tokens: 20 }],
      models: [{ token_id: 7, token_name: 'legacy', model_name: 'gpt-5', actual_cost_usd: 0.15, request_count: 1, total_tokens: 10 }],
    },
  }
  const normalized = normalizeTokenUsagePayload(payload)
  assert.equal(normalized.data.summary[0].token_name, 'key-a')
  assert.equal(normalized.data.summary[0].quota, 0.25)
  assert.equal(normalized.data.summary[0].remain_quota, 8)
  assert.equal(normalized.data.summary[0].used_quota, 2)
  assert.equal(normalized.data.summary[0].avg_use_time, 1.25)
  assert.equal(normalized.data.trend[0].quota, 0.1)
  assert.equal(normalized.data.models[0].quota, 0.15)
})

test('partial schema v2 payload keeps unknown enhancement fields unknown', () => {
  const payload: TokenUsagePayload = {
    ok: true,
    source: 'sub2api',
    completeness: 'partial',
    data: {
      summary: [{ token_id: 9, token_name: 'key-b', average_duration_ms: null, quota_remaining_usd: null }],
      trend: [],
      models: [],
    },
  }
  const row = normalizeTokenUsagePayload(payload).data.summary[0]
  assert.equal(row.avg_use_time, undefined)
  assert.equal(row.remain_quota, undefined)
})

test('token usage display state distinguishes all operational states', () => {
  const payload = (overrides: Partial<TokenUsagePayload> = {}): TokenUsagePayload => ({
    ok: true,
    source: 'sub2api',
    data: { summary: [], trend: [], models: [] },
    ...overrides,
  })
  assert.equal(resolveTokenUsageDisplayState(payload({ completeness: 'complete' })), 'complete')
  assert.equal(resolveTokenUsageDisplayState(payload({ completeness: 'partial', warnings: [{ code: 'DETAILS_SYNCING' }] })), 'syncing')
  assert.equal(resolveTokenUsageDisplayState(payload({ completeness: 'partial', warnings: [{ code: 'KEY_ENRICHMENT_FAILED' }] })), 'partial')
  assert.equal(resolveTokenUsageDisplayState(payload({ freshness: 'stale' })), 'stale')
  assert.equal(resolveTokenUsageDisplayState(null, 'tokenNoDataHint'), 'unconfigured')
})

test('token usage syncing uses a bounded retry delay', () => {
  assert.deepEqual([0, 1, 2, 3, 20].map(tokenUsageSyncDelay), [1500, 3000, 5000, 5000, 5000])
})

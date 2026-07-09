import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  evidenceBaseOffset,
  canonicalSkillsSearch,
  clueApiSearch,
  cluePath,
  evidenceDisplayTotalCount,
  evidenceHasMore,
  evidenceLoadedCount,
  evidencePageIdentity,
  evidencePageQuery,
  evidencePath,
  evidencePayloadForQuery,
  evidenceQueryKey,
  evidenceSearch,
  evidenceShouldShowLoadControl,
  evidenceTotalCount,
  legacyEvidenceCluePath,
  mergeEvidencePage,
  publishedSkillsPath,
  publishedSkillsSearch,
  shouldApplyEvidencePageIdentity,
  shouldApplyEvidenceResponse,
  shouldApplyEvidencePage,
  skillsBackSearch,
  startEvidencePageRequest,
} from './skillsEvidence.ts'
import type { SkillsEvidencePayload, SkillsEvidenceRecord } from './types.ts'

test('evidenceSearch defaults skills window to 7d', () => {
  assert.equal(evidenceSearch('', 'total'), '?w=7d&kind=total')
})

test('evidenceSearch preserves neutral filters for total evidence', () => {
  const search = evidenceSearch('?w=30d&rt=codex&src=own&q=figma&view=skill&topn=8', 'total')
  assert.ok(search.includes('w=30d'))
  assert.ok(search.includes('rt=codex'))
  assert.ok(search.includes('src=own'))
  assert.ok(search.includes('q=figma'))
  assert.ok(search.includes('kind=total'))
})

test('evidenceSearch rewrites untracked evidence source to non catalog', () => {
  const search = evidenceSearch('?w=7d&src=own&rt=codex', 'untracked')
  assert.ok(search.includes('kind=untracked'))
  assert.ok(search.includes('src=non_catalog'))
  assert.ok(search.includes('rt=codex'))
})

test('evidenceSearch drops conflicting company source evidence filters', () => {
  const search = evidenceSearch('?w=7d&src=external&q=x', 'idle')
  assert.ok(!search.includes('src=external'))
  assert.ok(search.includes('q=x'))
})

test('evidencePath routes governance clues to canonical clue pages', () => {
  assert.equal(evidencePath('?w=7d&src=own', 'untracked', { skill: 'coolify-deploy' }), '/skills/clues/untracked?w=7d&src=non_catalog&skill=coolify-deploy')
  assert.equal(evidencePath('?w=7d', 'idle', { skill: 'write-spec' }), '/skills/clues/idle?w=7d&skill=write-spec')
  assert.equal(evidencePath('?w=7d', 'zero_install'), '/skills/clues/zero-install?w=7d')
})

test('published skill links inherit window and company source filters', () => {
  assert.equal(publishedSkillsPath('?w=14d&src=own&rt=codex&q=figma'), '/skills/new?w=14d&q=figma&src=own')
  assert.equal(publishedSkillsSearch('?win=30&src=external'), '?w=30d')
})

test('skill links output canonical w and drop legacy win', () => {
  assert.equal(canonicalSkillsSearch('?w=14d&win=30&rt=codex'), '?w=14d&rt=codex')
  const evidence = new URLSearchParams(evidenceSearch('?w=14d&win=30&src=own', 'total').slice(1))
  assert.equal(evidence.get('w'), '14d')
  assert.equal(evidence.get('src'), 'own')
  assert.equal(evidence.get('kind'), 'total')
  assert.equal(evidence.has('win'), false)
  assert.equal(cluePath('?w=14d&win=30&src=own', 'untracked'), '/skills/clues/untracked?w=14d&src=non_catalog')
  assert.equal(publishedSkillsPath('?w=14d&win=30&q=figma'), '/skills/new?w=14d&q=figma')
  assert.equal(skillsBackSearch('?w=14d&win=30&kind=total&skill=figma'), '?w=14d')
})

test('total evidence and newly published skill KPI paths stay semantically distinct', () => {
  assert.equal(evidencePath('?w=7d', 'total'), '/skills/evidence?w=7d&kind=total')
  assert.equal(publishedSkillsPath('?w=7d'), '/skills/new?w=7d')
})

test('clue api search converts canonical clue pages back to evidence API kinds', () => {
  assert.equal(clueApiSearch('?w=7d&skill=write-spec', 'idle'), 'w=7d&skill=write-spec&kind=idle')
  assert.equal(clueApiSearch('?w=7d', 'zero-install'), 'w=7d&kind=zero_install')
  assert.equal(cluePath('?w=7d&src=own', 'untracked'), '/skills/clues/untracked?w=7d&src=non_catalog')
})

test('legacy evidence URLs redirect list clues to canonical pages', () => {
  assert.equal(legacyEvidenceCluePath('?kind=idle&w=7d&skill=write-spec'), '/skills/clues/idle?w=7d&skill=write-spec')
  assert.equal(legacyEvidenceCluePath('?kind=zero_install&w=7d'), '/skills/clues/zero-install?w=7d')
  assert.equal(legacyEvidenceCluePath('?kind=total&w=7d'), '')
})

test('skillsBackSearch removes evidence-only params', () => {
  assert.equal(skillsBackSearch('?w=7d&kind=total&skill=figma&rt=codex'), '?w=7d&rt=codex')
})

function record(index: number): SkillsEvidenceRecord {
  return {
    day: '2026-07-05',
    first_seen: `2026-07-05T00:${String(index % 60).padStart(2, '0')}:00Z`,
    skill: `skill-${index}`,
    operator: `operator-${index % 7}`,
    runtime: 'codex',
    source: index % 2 ? 'own' : '非公司库',
    session_id: `session-${index}`,
  }
}

function evidence(records: SkillsEvidenceRecord[], total = records.length): SkillsEvidencePayload {
  return {
    kind: 'total',
    today: '2026-07-05',
    summary: { records: total, skills: total, operators: 7, sessions: total },
    actions: [],
    applied_filters: {},
    ignored_filters: [],
    top_skills: [],
    top_operators: [],
    daily: [],
    records,
    items: [],
  }
}

test('evidencePageQuery preserves filters and advances offset without persisting UI state', () => {
  const query = evidencePageQuery('?kind=total&w=7d&rt=codex&src=own&q=figma&skill=draw&operator=alice&offset=0&limit=100', 100, 100)
  const params = new URLSearchParams(query)
  assert.equal(params.get('kind'), 'total')
  assert.equal(params.get('w'), '7d')
  assert.equal(params.get('rt'), 'codex')
  assert.equal(params.get('src'), 'own')
  assert.equal(params.get('q'), 'figma')
  assert.equal(params.get('skill'), 'draw')
  assert.equal(params.get('operator'), 'alice')
  assert.equal(params.get('offset'), '100')
  assert.equal(params.get('limit'), '100')
})

test('evidencePageQuery advances from the URL base offset', () => {
  const query = evidencePageQuery('?kind=total&w=7d&rt=codex&offset=100&limit=100', 100, 100)
  const params = new URLSearchParams(query)
  assert.equal(evidenceBaseOffset('?kind=total&w=7d&offset=100&limit=100'), 100)
  assert.equal(params.get('offset'), '200')
  assert.equal(params.get('limit'), '100')
})

test('evidenceQueryKey ignores pagination and focus but keeps filter identity', () => {
  assert.equal(
    evidenceQueryKey('?kind=total&w=7d&rt=codex&offset=0&limit=100&focus=records'),
    evidenceQueryKey('?w=7d&kind=total&rt=codex&offset=100&limit=100'),
  )
  assert.notEqual(
    evidenceQueryKey('?kind=total&w=7d&rt=codex&offset=100'),
    evidenceQueryKey('?kind=total&w=7d&rt=claude-code&offset=100'),
  )
})

test('evidencePageIdentity keeps pagination as page identity', () => {
  assert.notEqual(
    evidencePageIdentity('?kind=total&w=7d&rt=codex&offset=0&limit=100'),
    evidencePageIdentity('?w=7d&kind=total&rt=codex&offset=100&limit=100'),
  )
  assert.equal(
    evidencePageIdentity('?kind=total&w=7d&rt=codex&offset=100&limit=50&focus=records'),
    evidencePageIdentity('?w=7d&kind=total&rt=codex&limit=50&offset=100'),
  )
})

test('shouldApplyEvidencePage rejects slow responses from a previous filter URL', () => {
  const requestKey = evidenceQueryKey('?kind=total&w=7d&rt=codex&offset=100')
  assert.equal(shouldApplyEvidencePage(requestKey, '?w=7d&kind=total&rt=codex&offset=0'), true)
  assert.equal(shouldApplyEvidencePage(requestKey, '?w=7d&kind=total&rt=claude-code&offset=0'), false)
})

test('shouldApplyEvidencePageIdentity rejects slow responses from a previous page URL', () => {
  const requestKey = evidencePageIdentity('?kind=total&w=7d&rt=codex&offset=100')
  assert.equal(shouldApplyEvidencePageIdentity(requestKey, '?w=7d&kind=total&rt=codex&offset=100'), true)
  assert.equal(shouldApplyEvidencePageIdentity(requestKey, '?w=7d&kind=total&rt=codex&offset=0'), false)
})

test('shouldApplyEvidenceResponse only accepts the current URL and request sequence', () => {
  assert.equal(shouldApplyEvidenceResponse('/api/skills/evidence?w=7d', '/api/skills/evidence?w=7d', 3, 3), true)
  assert.equal(shouldApplyEvidenceResponse('/api/skills/evidence?w=7d', '/api/skills/evidence?w=14d', 3, 3), false)
  assert.equal(shouldApplyEvidenceResponse('/api/skills/evidence?w=7d', '/api/skills/evidence?w=7d', 2, 3), false)
})

test('evidencePayloadForQuery hides stale payloads from previous filter URLs', () => {
  const payload = evidence([record(0)], 1)
  const firstKey = evidenceQueryKey('?kind=total&w=7d&rt=codex')
  const nextKey = evidenceQueryKey('?kind=total&w=7d&rt=claude-code')
  assert.equal(evidencePayloadForQuery(payload, firstKey, firstKey), payload)
  assert.equal(evidencePayloadForQuery(payload, firstKey, nextKey), null)
})

test('startEvidencePageRequest aborts permanent pending requests after timeout', async () => {
  const request = startEvidencePageRequest(
    'kind=total&w=7d&offset=100',
    (_query, signal) => new Promise<SkillsEvidencePayload>((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true })
    }),
    0,
  )
  await assert.rejects(request.promise, /aborted/)
  assert.equal(request.didTimeout(), true)
})

test('limit 50 evidence pages show load control when hasMore is true', () => {
  const first = evidence(Array.from({ length: 50 }, (_, index) => record(index)), 80)
  assert.equal(evidenceLoadedCount(first, 'records'), 50)
  assert.equal(evidenceTotalCount(first, 'records'), 80)
  assert.equal(evidenceDisplayTotalCount(first, 'records'), 80)
  assert.equal(evidenceHasMore(first, 'records'), true)
  assert.equal(evidenceShouldShowLoadControl(first, 'records', { baselineLimit: 100 }), true)
})

test('offset evidence hasMore uses the remaining page range', () => {
  const page = evidence(Array.from({ length: 50 }, (_, index) => record(index + 100)), 150)
  assert.equal(evidenceTotalCount(page, 'records', 100), 50)
  assert.equal(evidenceHasMore(page, 'records', 100), false)
  assert.equal(evidenceShouldShowLoadControl(page, 'records', { baseOffset: 100, baselineLimit: 100 }), false)
})

test('mergeEvidencePage loads 367 unique records in server page order', () => {
  const first = evidence(Array.from({ length: 100 }, (_, index) => record(index)), 367)
  const second = evidence(Array.from({ length: 100 }, (_, index) => record(index + 100)), 367)
  const third = evidence(Array.from({ length: 100 }, (_, index) => record(index + 200)), 367)
  const fourth = evidence(Array.from({ length: 67 }, (_, index) => record(index + 300)), 367)
  const merged = mergeEvidencePage(mergeEvidencePage(mergeEvidencePage(first, second, 'records'), third, 'records'), fourth, 'records')
  assert.equal(evidenceLoadedCount(merged, 'records'), 367)
  assert.equal(evidenceTotalCount(merged, 'records'), 367)
  assert.equal(evidenceHasMore(merged, 'records'), false)
  assert.deepEqual(merged.records?.map((row) => row.session_id), Array.from({ length: 367 }, (_, index) => `session-${index}`))
})

test('mergeEvidencePage de-duplicates retry pages without skipping the failed offset', () => {
  const first = evidence([record(0), record(1)], 4)
  const retry = evidence([record(2), record(3)], 4)
  const merged = mergeEvidencePage(mergeEvidencePage(first, retry, 'records'), retry, 'records')
  assert.equal(evidenceLoadedCount(merged, 'records'), 4)
  assert.deepEqual(merged.records?.map((row) => row.session_id), ['session-0', 'session-1', 'session-2', 'session-3'])
})

test('evidence total drift keeps a usable has-more or completion state', () => {
  const first = evidence(Array.from({ length: 100 }, (_, index) => record(index)), 367)
  const increased = mergeEvidencePage(first, evidence(Array.from({ length: 100 }, (_, index) => record(index + 100)), 368), 'records')
  assert.equal(evidenceLoadedCount(increased, 'records'), 200)
  assert.equal(evidenceTotalCount(increased, 'records'), 368)
  assert.equal(evidenceHasMore(increased, 'records'), true)

  const decreased = mergeEvidencePage(increased, evidence(Array.from({ length: 166 }, (_, index) => record(index + 200)), 366), 'records')
  assert.equal(evidenceLoadedCount(decreased, 'records'), 366)
  assert.equal(evidenceDisplayTotalCount(decreased, 'records'), 366)
  assert.equal(evidenceHasMore(decreased, 'records'), false)
})

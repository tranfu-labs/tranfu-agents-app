import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evidenceSearch, skillsBackSearch } from './skillsEvidence.ts'

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

test('skillsBackSearch removes evidence-only params', () => {
  assert.equal(skillsBackSearch('?w=7d&kind=total&skill=figma&rt=codex'), '?w=7d&rt=codex')
})

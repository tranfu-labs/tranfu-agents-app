import { test } from 'node:test'
import assert from 'node:assert/strict'
import { clueApiSearch, cluePath, evidencePath, evidenceSearch, legacyEvidenceCluePath, publishedSkillsPath, publishedSkillsSearch, skillsBackSearch } from './skillsEvidence.ts'

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
  assert.equal(publishedSkillsSearch('?win=30&src=external'), '?win=30&w=30d')
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

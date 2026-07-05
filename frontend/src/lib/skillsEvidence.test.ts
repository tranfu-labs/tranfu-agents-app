import { test } from 'node:test'
import assert from 'node:assert/strict'
import { canonicalSkillsSearch, clueApiSearch, cluePath, evidencePath, evidenceSearch, legacyEvidenceCluePath, publishedSkillsPath, publishedSkillsSearch, skillsBackSearch } from './skillsEvidence.ts'

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

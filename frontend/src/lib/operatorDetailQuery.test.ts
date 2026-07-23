import assert from 'node:assert/strict'
import test from 'node:test'
import {
  isOperatorDetailActivationKey,
  operatorDetailApiQuery,
  operatorDetailBackHref,
  operatorDetailHref,
  sanitizeSkillsReturnQuery,
} from './operatorDetailQuery.ts'

test('operator detail keeps only statistical scope in route and API query', () => {
  const source = '?view=operator&w=today&rt=codex&src=own&q=alice&topn=20&hz=1&sel=alpha&sort=operator&dir=asc&scope=new'
  const href = operatorDetailHref('Alice Zhang', source)
  const query = new URLSearchParams(href.slice(href.indexOf('?') + 1))
  assert.equal(href.startsWith('/operator/Alice%20Zhang?'), true)
  assert.equal(query.get('w'), 'today')
  assert.equal(query.get('rt'), 'codex')
  assert.equal(query.get('src'), 'own')
  ;['q', 'topn', 'hz', 'sel', 'sort', 'dir', 'scope'].forEach((key) => assert.equal(query.has(key), false))
  assert.equal(operatorDetailApiQuery(`?${query.toString()}`), 'w=today&rt=codex&src=own')

  const from = new URLSearchParams(query.get('from') || '')
  assert.equal(from.get('view'), 'operator')
  assert.equal(from.get('q'), 'alice')
  assert.equal(from.get('topn'), '20')
  assert.equal(from.get('scope'), 'new')
  assert.equal(operatorDetailBackHref(`?${query.toString()}`), `/skills?${from.toString()}`)
})

test('operator detail custom query requires both ordered timestamps', () => {
  assert.equal(operatorDetailApiQuery('?w=custom&wstart=100&wend=200&rt=codex'), 'w=custom&wstart=100&wend=200&rt=codex')
  assert.equal(operatorDetailApiQuery('?w=custom&wstart=100'), null)
  assert.equal(operatorDetailApiQuery('?w=custom&wstart=200&wend=100'), null)
  assert.equal(new URL(operatorDetailHref('alice', '?w=custom&wstart=100'), 'https://example.test').searchParams.get('w'), '7d')
})

test('direct operator detail builds a minimal safe operator return target', () => {
  assert.equal(
    operatorDetailBackHref('?w=30d&rt=hermes&src=non_catalog'),
    '/skills?w=30d&rt=hermes&src=non_catalog&view=operator',
  )
  assert.equal(sanitizeSkillsReturnQuery('https://evil.test/skills?w=90d'), '')
  assert.equal(sanitizeSkillsReturnQuery('/admin?w=90d'), '')
  assert.equal(operatorDetailBackHref('?w=7d&from=https%3A%2F%2Fevil.test'), '/skills?w=7d&view=operator')
})

test('operator detail table rows activate only with Enter or Space', () => {
  assert.equal(isOperatorDetailActivationKey('Enter'), true)
  assert.equal(isOperatorDetailActivationKey(' '), true)
  assert.equal(isOperatorDetailActivationKey('Spacebar'), false)
  assert.equal(isOperatorDetailActivationKey('ArrowDown'), false)
})

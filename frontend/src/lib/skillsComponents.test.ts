import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('rank view-record action is implemented as a router anchor link', () => {
  const source = readFileSync('src/components/skills/RankBars.tsx', 'utf8')
  assert.match(source, /<Link[\s\S]+to=\{evidencePath\(location\.search, 'total', \{ skill: item\.name \}\)\}/)
  assert.doesNotMatch(source, /role="link"/)
  assert.doesNotMatch(source, /navigate\(evidencePath/)
  assert.doesNotMatch(source, /tabIndex=\{-1\}/)
})

test('unknown and invalid skills routes render NotFoundRoute', () => {
  const source = readFileSync('src/App.tsx', 'utf8')
  assert.match(source, /if \(!\['untracked', 'idle', 'zero-install'\]\.includes\(normalized\)\) \{\s+return <NotFoundRoute t=\{t\} \/>/)
  assert.match(source, /<Route path="\*" element=\{<NotFoundRoute t=\{t\} \/>\} \/>/)
})

test('skills drilldown views do not append raw location.search', () => {
  for (const file of ['src/views/Skills.tsx', 'src/views/SkillDetail.tsx', 'src/views/SkillsNew.tsx', 'src/views/OperatorDetail.tsx']) {
    const source = readFileSync(file, 'utf8')
    assert.doesNotMatch(source, /\$\{location\.search\}/, file)
    assert.doesNotMatch(source, /new URLSearchParams\(location\.search\)/, file)
  }
})

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('skills drawer restores from selected URL state instead of local-only state', () => {
  const source = readFileSync('src/views/Skills.tsx', 'utf8')
  assert.match(source, /const selected = selectedSkillOf\(params\)/)
  assert.match(source, /const drawerRow = selected \? \(data\?\.table \|\| \[\]\)\.find\(\(row\) => row\.name === selected\) : undefined/)
  assert.match(source, /const drawerSkill = drawerRow \? selected : ''/)
  assert.match(source, /const closeSkill = \(\) => void setParams\(\{ sel: '' \}\)/)
  assert.doesNotMatch(source, /const \[drawerSkill, setDrawerSkill\] = useState/)
})

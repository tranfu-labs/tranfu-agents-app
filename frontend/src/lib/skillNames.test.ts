import assert from 'node:assert/strict'
import { skillDisplayName, skillNameMatches, skillSlug } from './skillNames.ts'

const row = {
  name: 'openspec-driven-development',
  display_name: 'OpenSpec-Driven Development',
  display_name_zh: 'OpenSpec 驱动开发',
}

assert.equal(skillDisplayName(row, 'zh'), 'OpenSpec 驱动开发')
assert.equal(skillDisplayName(row, 'en'), 'OpenSpec-Driven Development')
assert.equal(skillDisplayName({ name: 'only-zh', display_name_zh: '仅中文' }, 'en'), '仅中文')
assert.equal(skillDisplayName('raw-slug', 'zh'), 'raw-slug')
assert.equal(skillSlug(row), 'openspec-driven-development')
assert.equal(skillNameMatches(row, '驱动开发'), true)
assert.equal(skillNameMatches(row, 'Driven Development'), true)
assert.equal(skillNameMatches(row, 'openspec-driven'), true)
assert.equal(skillNameMatches(row, 'missing'), false)

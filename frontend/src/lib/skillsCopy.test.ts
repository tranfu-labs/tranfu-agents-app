import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'

function readSource(relativePath: string) {
  const candidates = [
    path.join(process.cwd(), relativePath),
    path.join(process.cwd(), 'frontend', relativePath),
  ]
  for (const candidate of candidates) {
    try {
      return readFileSync(candidate, 'utf8')
    } catch {
      // Try the next cwd shape. npm --prefix and direct node runs differ here.
    }
  }
  throw new Error(`missing source file ${relativePath}`)
}

test('skills first screen copy avoids KPI score language', () => {
  const source = [
    readSource('src/components/skills/KpiStrip.tsx'),
    readSource('src/components/skills/HealthBar.tsx'),
    readSource('src/components/skills/GovernanceTodo.tsx'),
  ].join('\n')
  for (const word of ['KPI 环带', '治理健康', '良好', '偏高', '需关注']) {
    assert.equal(source.includes(word), false, `unexpected copy: ${word}`)
  }
})

test('skills controls and issue signals avoid removed comparison and example-name copy', () => {
  const skillsView = readSource('src/views/Skills.tsx')
  assert.equal(skillsView.includes('compareToggle'), false)
  assert.equal(skillsView.includes('showComparison'), false)

  const healthBar = readSource('src/components/skills/HealthBar.tsx')
  assert.equal(healthBar.includes('compactNameList'), false)
  assert.equal(healthBar.includes('classifySkillHealth'), false)
  assert.equal(healthBar.includes('autoUsed'), false)
  assert.equal(healthBar.includes('installedUnusedText'), false)
  assert.equal(healthBar.includes('top3Concentrated'), false)
})

test('skills todo dismissal does not persist to browser storage', () => {
  const source = readSource('src/components/skills/GovernanceTodo.tsx')
  assert.equal(source.includes('localStorage'), false)
  assert.equal(source.includes('sessionStorage'), false)
})

test('skills clue and governance copy avoids evidence wording and x dismissal', () => {
  const source = [
    readSource('src/components/skills/GovernanceTodo.tsx'),
    readSource('src/views/SkillsEvidence.tsx'),
    readSource('src/views/SkillsClue.tsx'),
    readSource('src/lib/i18n.ts'),
  ].join('\n')
  for (const word of ['查看证据', '按使用者看证据', '找使用者', '未收录使用证据', '证据页动作']) {
    assert.equal(source.includes(word), false, `unexpected copy: ${word}`)
  }
  assert.equal(readSource('src/components/skills/GovernanceTodo.tsx').includes('>×</button>'), false)
})

test('skills fallback and copy avoid placeholder leak and keep 7d Top3 wording', () => {
  const api = readSource('src/lib/api.ts')
  const demo = readSource('src/lib/demo.ts')
  const i18n = readSource('src/lib/i18n.ts')
  const source = [api, demo, i18n].join('\n')

  assert.equal(api.includes('demoSkillsOverview(demoWindowKey(query, days), days)'), true)
  assert.equal(i18n.includes("window_7d: '近 7 天'"), true)
  assert.equal(i18n.includes("window_7d: 'Last 7 days'"), true)
  assert.equal(i18n.includes('Top3'), true)
  for (const word of ['$name', '$d', '$s', 'foo', 'foo-bar', 'dbs-placeholder', 'gstack-placeholder']) {
    assert.equal(source.includes(word), false, `unexpected fallback placeholder: ${word}`)
  }
})

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

test('skills todo dismissal does not persist to browser storage', () => {
  const source = readSource('src/components/skills/GovernanceTodo.tsx')
  assert.equal(source.includes('localStorage'), false)
  assert.equal(source.includes('sessionStorage'), false)
})

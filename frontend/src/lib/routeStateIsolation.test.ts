/// <reference types="node" />
import assert from 'node:assert/strict'
import test from 'node:test'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { parseSkillQuery, patchSkillSearchParams } from './skillQuery.ts'

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

function listSourceFiles(relativeDir: string): string[] {
  const candidates = [
    path.join(process.cwd(), relativeDir),
    path.join(process.cwd(), 'frontend', relativeDir),
  ]
  const root = candidates.find((candidate) => {
    try {
      return statSync(candidate).isDirectory()
    } catch {
      return false
    }
  })
  if (!root) throw new Error(`missing source dir ${relativeDir}`)
  const out: string[] = []
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = path.join(dir, entry)
      const stat = statSync(full)
      if (stat.isDirectory()) walk(full)
      else if (/\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry)) out.push(full)
    }
  }
  walk(root)
  return out
}

test('skills query state is parsed only from the current URL search params', () => {
  const params = parseSkillQuery(new URLSearchParams('w=7d&view=skill&q=ops&rt=codex&src=own&sel=alpha&topn=20'))
  assert.equal(params.w, '7d')
  assert.equal(params.view, 'skill')
  assert.equal(params.q, 'ops')
  assert.equal(params.rt, 'codex')
  assert.equal(params.src, 'own')
  assert.equal(params.sel, 'alpha')
  assert.equal(params.topn, 20)

  const defaults = parseSkillQuery(new URLSearchParams())
  assert.equal(defaults.w, '')
  assert.equal(defaults.win, 7)
  assert.equal(defaults.view, 'skill')
  assert.equal(defaults.scope, 'all')
  assert.equal(defaults.sel, '')
})

test('skills query patch replaces only current-window search state and clears default values', () => {
  const base = new URLSearchParams('w=7d&view=skill&q=ops&sel=alpha&rt=codex')
  const next = patchSkillSearchParams(base, { q: 'report', sel: '', view: 'operator', topn: 8 })
  assert.equal(base.get('sel'), 'alpha')
  assert.equal(next.get('w'), '7d')
  assert.equal(next.get('q'), 'report')
  assert.equal(next.get('rt'), 'codex')
  assert.equal(next.get('view'), 'operator')
  assert.equal(next.has('sel'), false)
  assert.equal(next.has('topn'), false)
})

test('skills query patch composes consecutive current-window updates', () => {
  let current = new URLSearchParams('w=14d&view=operator&q=pytest&rt=codex&src=own')
  current = patchSkillSearchParams(current, { view: 'skill', q: '', sel: '', sort: 'sessions_window', dir: 'desc' })
  current = patchSkillSearchParams(current, { rt: '' })
  current = patchSkillSearchParams(current, { src: '' })
  assert.equal(current.toString(), 'w=14d')
})

test('skills route state source does not read browser storage or hidden sync channels', () => {
  const source = [
    readSource('src/lib/skillQuery.ts'),
    readSource('src/main.tsx'),
    readSource('package.json'),
  ].join('\n')
  for (const word of ['nuqs', 'BroadcastChannel', 'localStorage', 'sessionStorage', "addEventListener('storage'", 'storage event']) {
    assert.equal(source.includes(word), false, `unexpected route-state sync source: ${word}`)
  }
  assert.equal(source.includes('useSearchParams'), true)
})

test('data refresh hooks do not write navigation or search params', () => {
  const source = [
    readSource('src/lib/api.ts'),
    readSource('src/lib/apiCache.ts'),
  ].join('\n')
  for (const word of ['useNavigate', 'useSearchParams', 'setSearchParams', 'pushState', 'replaceState', 'window.history', 'window.location']) {
    assert.equal(source.includes(word), false, `data hook must not write route state: ${word}`)
  }
})

test('production frontend storage usage stays within documented exceptions', () => {
  const offenders = listSourceFiles('src')
    .filter((file) => !file.endsWith(`${path.sep}theme.ts`) && !file.endsWith(`${path.sep}Admin.tsx`))
    .filter((file) => {
      const source = readFileSync(file, 'utf8')
      return source.includes('localStorage') || source.includes('sessionStorage') || source.includes('BroadcastChannel')
    })
  assert.deepEqual(offenders, [])
})

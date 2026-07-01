/// <reference types="node" />
import assert from 'node:assert/strict'
import test from 'node:test'
import {
  THEME_COLORS,
  THEME_STORAGE_KEY,
  applyThemeToTarget,
  readStoredThemeMode,
  resolveTheme,
  writeStoredThemeMode,
  type ThemeStorage,
} from './theme.ts'

function memoryStorage(initial?: string): ThemeStorage & { data: Map<string, string> } {
  const data = new Map<string, string>()
  if (initial !== undefined) data.set(THEME_STORAGE_KEY, initial)
  return {
    data,
    getItem(key: string) {
      return data.get(key) ?? null
    },
    setItem(key: string, value: string) {
      data.set(key, value)
    },
  }
}

test('theme mode falls back to system when storage is empty or invalid', () => {
  assert.equal(readStoredThemeMode(undefined), 'system')
  assert.equal(readStoredThemeMode(memoryStorage('bad-value')), 'system')
})

test('theme mode reads all valid stored modes', () => {
  assert.equal(readStoredThemeMode(memoryStorage('system')), 'system')
  assert.equal(readStoredThemeMode(memoryStorage('light')), 'light')
  assert.equal(readStoredThemeMode(memoryStorage('dark')), 'dark')
})

test('theme storage read and write errors do not throw', () => {
  const throwingStorage: ThemeStorage = {
    getItem() {
      throw new Error('blocked')
    },
    setItem() {
      throw new Error('blocked')
    },
  }

  assert.equal(readStoredThemeMode(throwingStorage), 'system')
  assert.doesNotThrow(() => writeStoredThemeMode(throwingStorage, 'dark'))
})

test('theme mode writes only the selected enum value', () => {
  const storage = memoryStorage()

  writeStoredThemeMode(storage, 'light')
  assert.equal(storage.data.get(THEME_STORAGE_KEY), 'light')

  writeStoredThemeMode(storage, 'system')
  assert.equal(storage.data.get(THEME_STORAGE_KEY), 'system')
})

test('system mode resolves from browser preference while explicit modes do not', () => {
  assert.equal(resolveTheme('system', true), 'dark')
  assert.equal(resolveTheme('system', false), 'light')
  assert.equal(resolveTheme('light', true), 'light')
  assert.equal(resolveTheme('dark', false), 'dark')
})

test('theme application updates root attributes, color-scheme, and theme-color meta', () => {
  const root: { dataset: { themeMode?: string; theme?: string }; style: { colorScheme?: string } } = { dataset: {}, style: {} }
  const attrs = new Map<string, string>()

  applyThemeToTarget({
    root,
    themeColorMeta: {
      setAttribute(name, value) {
        attrs.set(name, value)
      },
    },
  }, 'light', 'light')

  assert.equal(root.dataset.themeMode, 'light')
  assert.equal(root.dataset.theme, 'light')
  assert.equal(root.style.colorScheme, 'light')
  assert.equal(attrs.get('content'), THEME_COLORS.light)
})

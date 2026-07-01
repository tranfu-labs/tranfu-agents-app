export type ThemeMode = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

export type ThemeStorage = Pick<Storage, 'getItem' | 'setItem'>

export type ThemeTarget = {
  root: {
    dataset: {
      themeMode?: string
      theme?: string
    }
    style: {
      colorScheme?: string
    }
  }
  themeColorMeta?: {
    setAttribute: (name: string, value: string) => void
  } | null
}

export const THEME_STORAGE_KEY = 'tf-theme-mode'
export const THEME_COLORS: Record<ResolvedTheme, string> = {
  dark: '#0b0b0c',
  light: '#f6f7f8',
}

export function isThemeMode(value: unknown): value is ThemeMode {
  return value === 'system' || value === 'light' || value === 'dark'
}

export function resolveTheme(mode: ThemeMode, prefersDark: boolean): ResolvedTheme {
  if (mode === 'light') return 'light'
  if (mode === 'dark') return 'dark'
  return prefersDark ? 'dark' : 'light'
}

export function readStoredThemeMode(storage?: ThemeStorage | null): ThemeMode {
  try {
    const value = storage?.getItem(THEME_STORAGE_KEY)
    return isThemeMode(value) ? value : 'system'
  } catch {
    return 'system'
  }
}

export function writeStoredThemeMode(storage: ThemeStorage | null | undefined, mode: ThemeMode) {
  try {
    storage?.setItem(THEME_STORAGE_KEY, mode)
  } catch {
    // Theme persistence is best-effort; blocked storage must not block rendering.
  }
}

export function getBrowserThemeStorage(): ThemeStorage | undefined {
  try {
    return window.localStorage
  } catch {
    return undefined
  }
}

export function getBrowserPrefersDark(): boolean {
  try {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true
  } catch {
    return true
  }
}

export function applyThemeToTarget(target: ThemeTarget, mode: ThemeMode, resolved: ResolvedTheme) {
  target.root.dataset.themeMode = mode
  target.root.dataset.theme = resolved
  target.root.style.colorScheme = resolved
  target.themeColorMeta?.setAttribute('content', THEME_COLORS[resolved])
}

export function applyTheme(mode: ThemeMode, resolved: ResolvedTheme) {
  applyThemeToTarget({
    root: document.documentElement,
    themeColorMeta: document.querySelector<HTMLMetaElement>('meta[name="theme-color"]'),
  }, mode, resolved)
}

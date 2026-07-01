(function () {
  var key = 'tf-theme-mode'
  var colors = {
    dark: '#0b0b0c',
    light: '#f6f7f8'
  }

  function isMode(value) {
    return value === 'system' || value === 'light' || value === 'dark'
  }

  function readMode() {
    try {
      var value = window.localStorage.getItem(key)
      return isMode(value) ? value : 'system'
    } catch (_) {
      return 'system'
    }
  }

  function prefersDark() {
    try {
      return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
    } catch (_) {
      return true
    }
  }

  function resolve(mode) {
    if (mode === 'light') return 'light'
    if (mode === 'dark') return 'dark'
    return prefersDark() ? 'dark' : 'light'
  }

  var mode = readMode()
  var theme = resolve(mode)
  var root = document.documentElement
  root.dataset.themeMode = mode
  root.dataset.theme = theme
  root.style.colorScheme = theme

  var meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', colors[theme])
}())

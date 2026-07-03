import { useCallback, useEffect, useMemo, useState, type ReactElement } from 'react'
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { TopBar } from './components/TopBar'
import { Toast } from './components/Toast'
import { useOperatorDetail, usePollingState, useSkillDetail, useSkillsEvidence, useSkillsOverview, useTokenUsage } from './lib/api'
import { makeT } from './lib/i18n'
import { useSkillQueryState } from './lib/skillQuery'
import { resolveSkillsWindow, skillsWindowQuery } from './lib/skillsWindow'
import { applyTheme, getBrowserPrefersDark, getBrowserThemeStorage, readStoredThemeMode, resolveTheme, writeStoredThemeMode, type ThemeMode } from './lib/theme'
import { initialTokenUsageQuery } from './lib/tokenUsageRange'
import type { Lang } from './lib/types'
import type { StatePayload } from './lib/types'
import { clueApiSearch, legacyEvidenceCluePath, type SkillsClueKind } from './lib/skillsEvidence'
import { Board } from './views/Board'
import { Agents } from './views/Agents'
import { AgentDetail } from './views/AgentDetail'
import { SkillsView } from './views/Skills'
import { SkillsEvidenceView } from './views/SkillsEvidence'
import { SkillsClueView } from './views/SkillsClue'
import { SkillDetailView } from './views/SkillDetail'
import { OperatorDetailView } from './views/OperatorDetail'
import { AdminView } from './views/Admin'
import { TokenUsageView } from './views/TokenUsage'

function SkillsRoute({ t }: { t: (key: string) => string }) {
  const [params] = useSkillQueryState()
  const skillsWindow = resolveSkillsWindow(params)
  const overview = useSkillsOverview(true, skillsWindow.days, skillsWindowQuery(params))
  return <SkillsView data={overview.data} loading={overview.loading} error={overview.error} t={t} />
}

function SkillsEvidenceRoute({ lang, t }: { lang: Lang; t: (key: string) => string }) {
  const location = useLocation()
  const cluePath = legacyEvidenceCluePath(location.search)
  if (cluePath) return <Navigate to={cluePath} replace />
  const query = location.search.startsWith('?') ? location.search.slice(1) : location.search
  const evidence = useSkillsEvidence(true, query || 'kind=total&w=7d')
  return <SkillsEvidenceView data={evidence.data} loading={evidence.loading} error={evidence.error} lang={lang} search={location.search} t={t} />
}

function SkillsClueRoute({ lang, t }: { lang: Lang; t: (key: string) => string }) {
  const location = useLocation()
  const { clueKind = 'untracked' } = useParams()
  const normalized = clueKind as SkillsClueKind
  if (!['untracked', 'idle', 'zero-install'].includes(normalized)) {
    return <Navigate to={`/skills${location.search || '?w=7d'}`} replace />
  }
  const evidence = useSkillsEvidence(true, clueApiSearch(location.search, normalized))
  return <SkillsClueView clueKind={normalized} data={evidence.data} loading={evidence.loading} error={evidence.error} lang={lang} search={location.search} t={t} />
}

function SkillDetailRoute({ lang, t }: { lang: Lang; t: (key: string) => string }) {
  const { name } = useParams()
  const [params] = useSkillQueryState()
  const days = [7, 30, 90].includes(params.win) ? params.win : 30
  const overview = useSkillsOverview(false, days)
  const detail = useSkillDetail(true, name ? decodeURIComponent(name) : undefined, overview.data)
  return <SkillDetailView data={detail.data} loading={detail.loading} error={detail.error} lang={lang} t={t} />
}

function OperatorDetailRoute({ lang, t }: { lang: Lang; t: (key: string) => string }) {
  const { name } = useParams()
  const [params] = useSkillQueryState()
  const days = [7, 30, 90].includes(params.win) ? params.win : 30
  const overview = useSkillsOverview(false, days)
  const detail = useOperatorDetail(true, name ? decodeURIComponent(name) : undefined, overview.data)
  return <OperatorDetailView data={detail.data} loading={detail.loading} error={detail.error} lang={lang} t={t} />
}

function TokenUsageRoute({ t }: { t: (key: string) => string }) {
  const [query, setQuery] = useState(initialTokenUsageQuery)
  const usage = useTokenUsage(true, query)
  return <TokenUsageView data={usage.data} loading={usage.loading} error={usage.error} query={query} setQuery={setQuery} refresh={usage.refresh} t={t} />
}

function RouteLoading({ t }: { t: (key: string) => string }) {
  return (
    <section className="frame">
      <div className="empty">
        <div className="t">{t('loading')}</div>
      </div>
    </section>
  )
}

function StateRoute({ state, children, t }: { state: StatePayload | null; children: (data: StatePayload) => ReactElement; t: (key: string) => string }) {
  return state ? children(state) : <RouteLoading t={t} />
}

export default function App() {
  const [lang, setLang] = useState<Lang>('zh')
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => readStoredThemeMode(getBrowserThemeStorage()))
  const [prefersDark, setPrefersDark] = useState(getBrowserPrefersDark)
  const [toast, setToast] = useState('')
  const location = useLocation()
  const isTokenUsageRoute = location.pathname === '/token-usage'
  const state = usePollingState(!isTokenUsageRoute)
  const t = useMemo(() => makeT(lang), [lang])
  const resolvedTheme = useMemo(() => resolveTheme(themeMode, prefersDark), [themeMode, prefersDark])
  const changeThemeMode = useCallback((mode: ThemeMode) => {
    setThemeMode(mode)
    writeStoredThemeMode(getBrowserThemeStorage(), mode)
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }, [lang])

  useEffect(() => {
    applyTheme(themeMode, resolvedTheme)
  }, [themeMode, resolvedTheme])

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!media) return undefined
    const sync = () => setPrefersDark(media.matches)
    sync()
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', sync)
      return () => media.removeEventListener('change', sync)
    }
    media.addListener(sync)
    return () => media.removeListener(sync)
  }, [])

  useEffect(() => {
    document.body.classList.toggle('is-demo', state.demo)
  }, [state.demo])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [location.pathname])

  const clearToast = useCallback(() => setToast(''), [])

  return (
    <>
      <TopBar
        lang={lang}
        setLang={setLang}
        themeMode={themeMode}
        resolvedTheme={resolvedTheme}
        setThemeMode={changeThemeMode}
        state={state.data}
        demo={state.demo}
        t={t}
      />
      <main>
        <Routes>
          <Route path="/" element={<StateRoute state={state.data} t={t}>{(data) => <Board data={data} lang={lang} t={t} />}</StateRoute>} />
          <Route path="/agents" element={<StateRoute state={state.data} t={t}>{(data) => <Agents data={data} lang={lang} t={t} />}</StateRoute>} />
          <Route path="/agent/:key" element={<StateRoute state={state.data} t={t}>{(data) => <AgentDetail data={data} lang={lang} t={t} />}</StateRoute>} />
          <Route path="/skills" element={<SkillsRoute t={t} />} />
          <Route path="/skills/evidence" element={<SkillsEvidenceRoute lang={lang} t={t} />} />
          <Route path="/skills/clues/:clueKind" element={<SkillsClueRoute lang={lang} t={t} />} />
          <Route path="/token-usage" element={<TokenUsageRoute t={t} />} />
          <Route path="/skill/:name" element={<SkillDetailRoute lang={lang} t={t} />} />
          <Route path="/operator/:name" element={<OperatorDetailRoute lang={lang} t={t} />} />
          <Route path="/admin" element={<AdminView t={t} />} />
          <Route path="*" element={<StateRoute state={state.data} t={t}>{(data) => <Board data={data} lang={lang} t={t} />}</StateRoute>} />
        </Routes>
      </main>
      <Toast message={toast} onDone={clearToast} />
    </>
  )
}

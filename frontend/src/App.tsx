import { useCallback, useEffect, useMemo, useState } from 'react'
import { Route, Routes, useLocation, useParams } from 'react-router-dom'
import { TopBar } from './components/TopBar'
import { Toast } from './components/Toast'
import { useOperatorDetail, usePollingState, useSkillDetail, useSkillsOverview } from './lib/api'
import { makeT } from './lib/i18n'
import { useSkillQueryState } from './lib/skillQuery'
import type { Lang } from './lib/types'
import { Board } from './views/Board'
import { Agents } from './views/Agents'
import { AgentDetail } from './views/AgentDetail'
import { SkillsView } from './views/Skills'
import { SkillDetailView } from './views/SkillDetail'
import { OperatorDetailView } from './views/OperatorDetail'
import { AdminView } from './views/Admin'

function SkillsRoute({ t }: { t: (key: string) => string }) {
  const [params] = useSkillQueryState()
  const days = [7, 30, 90].includes(params.win) ? params.win : 30
  const overview = useSkillsOverview(true, days)
  return <SkillsView data={overview.data} loading={overview.loading} error={overview.error} t={t} />
}

function SkillDetailRoute({ t }: { t: (key: string) => string }) {
  const { name } = useParams()
  const [params] = useSkillQueryState()
  const days = [7, 30, 90].includes(params.win) ? params.win : 30
  const overview = useSkillsOverview(false, days)
  const detail = useSkillDetail(true, name ? decodeURIComponent(name) : undefined, overview.data)
  return <SkillDetailView data={detail.data} loading={detail.loading} error={detail.error} t={t} />
}

function OperatorDetailRoute({ t }: { t: (key: string) => string }) {
  const { name } = useParams()
  const [params] = useSkillQueryState()
  const days = [7, 30, 90].includes(params.win) ? params.win : 30
  const overview = useSkillsOverview(false, days)
  const detail = useOperatorDetail(true, name ? decodeURIComponent(name) : undefined, overview.data)
  return <OperatorDetailView data={detail.data} loading={detail.loading} error={detail.error} t={t} />
}

export default function App() {
  const [lang, setLang] = useState<Lang>('zh')
  const [light, setLight] = useState(false)
  const [toast, setToast] = useState('')
  const state = usePollingState()
  const location = useLocation()
  const t = useMemo(() => makeT(lang), [lang])

  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }, [lang])

  useEffect(() => {
    document.body.classList.toggle('light', light)
  }, [light])

  useEffect(() => {
    document.body.classList.toggle('is-demo', state.demo)
  }, [state.demo])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [location.pathname])

  const clearToast = useCallback(() => setToast(''), [])

  return (
    <>
      <TopBar lang={lang} setLang={setLang} light={light} setLight={setLight} state={state.data} demo={state.demo} t={t} />
      <main>
        {state.data ? (
          <Routes>
            <Route path="/" element={<Board data={state.data} lang={lang} t={t} />} />
            <Route path="/agents" element={<Agents data={state.data} lang={lang} t={t} />} />
            <Route path="/agent/:key" element={<AgentDetail data={state.data} lang={lang} t={t} />} />
            <Route path="/skills" element={<SkillsRoute t={t} />} />
            <Route path="/skill/:name" element={<SkillDetailRoute t={t} />} />
            <Route path="/operator/:name" element={<OperatorDetailRoute t={t} />} />
            <Route path="/admin" element={<AdminView t={t} />} />
            <Route path="*" element={<Board data={state.data} lang={lang} t={t} />} />
          </Routes>
        ) : (
          <section className="frame">
            <div className="empty">
              <div className="t">{t('loading')}</div>
            </div>
          </section>
        )}
      </main>
      <Toast message={toast} onDone={clearToast} />
    </>
  )
}

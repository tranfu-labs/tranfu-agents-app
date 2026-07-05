import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { Logo } from './Logo'
import type { ResolvedTheme, ThemeMode } from '../lib/theme'
import type { Lang, StatePayload } from '../lib/types'
import { locale } from '../lib/utils'

type Props = {
  lang: Lang
  setLang: (lang: Lang) => void
  themeMode: ThemeMode
  resolvedTheme: ResolvedTheme
  setThemeMode: (mode: ThemeMode) => void
  state: StatePayload | null
  demo: boolean
  t: (key: string) => string
}

export function TopBar({ lang, setLang, themeMode, resolvedTheme, setThemeMode, state, demo, t }: Props) {
  const [clock, setClock] = useState('--:--:--')
  const location = useLocation()
  const active = (name: 'board' | 'agents' | 'skills' | 'token') => {
    if (name === 'board') return location.pathname === '/'
    if (name === 'agents') return location.pathname === '/agents' || location.pathname.startsWith('/agent/')
    if (name === 'token') return location.pathname === '/token-usage'
    return location.pathname === '/skills' || location.pathname.startsWith('/skill/') || location.pathname.startsWith('/operator/')
  }

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString(locale(lang), { hour12: false }))
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [lang])

  const leverage = state?.leverage || { skills_week: 0, assets: 0 }
  const live = state?.totals?.live || 0
  const themeOptions: Array<{ mode: ThemeMode; label: string }> = [
    { mode: 'system', label: t('themeSystem') },
    { mode: 'light', label: t('themeLight') },
    { mode: 'dark', label: t('themeDark') },
  ]

  return (
    <header>
      <Link className="logo-link" to="/" aria-label="TRANFU//AGENTS home">
        <Logo />
      </Link>
      <nav className="tabs">
        <NavLink to="/" className={active('board') ? 'on' : ''} end>
          {t('board')}
        </NavLink>
        <NavLink to="/agents" className={active('agents') ? 'on' : ''}>
          {t('agents')}
        </NavLink>
        <NavLink to="/skills" className={active('skills') ? 'on' : ''}>
          {t('skillsNav')}
        </NavLink>
        <NavLink to="/token-usage" className={active('token') ? 'on' : ''}>
          {t('tokenUsageNav')}
        </NavLink>
      </nav>
      <div className="readouts">
        <Link className="ro ro-link ro-new" to="/skills?w=7d&scope=new" aria-label={t('newSkillsLinkLabel')} title={t('newSkillsLinkLabel')}>
          <div className="n up">+{leverage.skills_week || 0}</div>
          <div className="l">{t('ro_skill')}</div>
        </Link>
        <div className="ro">
          <div className="n">{leverage.assets || 0}</div>
          <div className="l">{t('ro_assets')}</div>
        </div>
        <div className="ro">
          <div className="n live">{live}</div>
          <div className="l">{t('ro_live')}</div>
        </div>
      </div>
      <span className="live-pill">
        <span className="beat" aria-hidden="true" />
        <span className="mono">{clock}</span>
      </span>
      <span className="demo" style={{ display: demo ? undefined : 'none' }}>
        {t('demo')}
      </span>
      <div className="ctl">
        <div className="seg" role="group" aria-label="language">
          <button className={lang === 'zh' ? 'on' : ''} onClick={() => setLang('zh')}>
            中
          </button>
          <button className={lang === 'en' ? 'on' : ''} onClick={() => setLang('en')}>
            EN
          </button>
        </div>
        <div className="seg theme-seg" role="group" aria-label={t('themeMode')}>
          {themeOptions.map((option) => (
            <button
              key={option.mode}
              className={themeMode === option.mode ? 'on' : ''}
              type="button"
              aria-pressed={themeMode === option.mode}
              aria-label={`${t('themeMode')}: ${option.label}${option.mode === 'system' ? ` (${resolvedTheme})` : ''}`}
              onClick={() => setThemeMode(option.mode)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </header>
  )
}

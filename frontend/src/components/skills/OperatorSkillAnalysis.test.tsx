import assert from 'node:assert/strict'
import test from 'node:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { OperatorSkillDonut } from './OperatorSkillAnalysis.tsx'
import { buildOperatorSkillAnalysis, operatorCompositionLabel } from '../../lib/operatorDetailAnalysis.ts'
import { makeT } from '../../lib/i18n.ts'
import type { OperatorDetail } from '../../lib/types.ts'

test('operator skill donut renders a visible complete ring for one skill', () => {
  const detail: OperatorDetail = {
    operator: 'alice',
    today: '2026-07-23',
    window: {
      key: 'today',
      days: 1,
      start: '2026-07-23',
      end: '2026-07-23',
    },
    analysis: {
      metrics: { sessions_window: 9 },
      skills: [{
        name: 'only-skill',
        source: 'own',
        sessions_window: 9,
        previous_sessions: 0,
        session_count: 3,
      }],
    },
  }
  const model = buildOperatorSkillAnalysis(detail)
  const markup = renderToStaticMarkup(
    <OperatorSkillDonut
      model={model}
      lang="zh"
      windowLabel="今天"
      t={makeT('zh')}
    />,
  )

  assert.equal(model.mode, 'donut')
  assert.equal(model.top.length, 1)
  assert.equal(model.other, null)
  assert.equal((markup.match(/A 46 46/g) || []).length, 2)
  assert.equal((markup.match(/A 30 30/g) || []).length, 2)
  assert.match(markup, /aria-label="Skill 使用构成 · 今天"/)
  assert.match(markup, /<title>only-skill: 9<\/title>/)
  assert.match(markup, />100%<\/em>/)
})

test('historical one-day custom window labels composition with its actual window in both languages', () => {
  const detail: OperatorDetail = {
    operator: 'alice',
    today: '2026-07-23',
    window: {
      key: 'custom',
      days: 1,
      start: '2026-07-14',
      end: '2026-07-14',
    },
    analysis: {
      metrics: {
        sessions_window: 3,
        skill_count: 1,
        session_count: 2,
        runtime_count: 1,
      },
      skills: [{
        name: 'historical-skill',
        source: 'own',
        sessions_window: 3,
        previous_sessions: 0,
        session_count: 2,
      }],
      runtime: [{ runtime: 'codex', used: 3 }],
      records: [],
    },
  }
  const cases = [
    {
      lang: 'zh' as const,
      label: 'Skill 使用构成 · 自定义周期',
      staleLabel: '今日 Skill 使用构成',
    },
    {
      lang: 'en' as const,
      label: 'Skill usage composition · Custom range',
      staleLabel: 'Skill usage composition today',
    },
  ]

  for (const { lang, label, staleLabel } of cases) {
    const t = makeT(lang)
    const windowLabel = t('window_period_custom')
    assert.equal(operatorCompositionLabel(windowLabel, t), label)
    const markup = renderToStaticMarkup(
      <OperatorSkillDonut
        model={buildOperatorSkillAnalysis(detail)}
        lang={lang}
        windowLabel={windowLabel}
        t={t}
      />,
    )

    assert.match(markup, new RegExp(`aria-label="${label}"`))
    assert.doesNotMatch(markup, new RegExp(staleLabel))
  }
})

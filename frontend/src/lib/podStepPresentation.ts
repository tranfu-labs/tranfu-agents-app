import { statusName } from './i18n.ts'
import type { Lang, Status } from './types.ts'

export type PodStepPresentation = {
  text: string
  showMarker: boolean
}

const COPY = {
  zh: {
    toolRunning: '正在运行命令',
    toolDone: '已完成命令',
  },
  en: {
    toolRunning: 'Running command',
    toolDone: 'Finished command',
  },
} as const

function toolObject(step: string, prefix: RegExp) {
  const match = prefix.exec(step)
  const object = match?.[1]?.trim()
  return object || null
}

export function presentPodStep(
  step: string | null | undefined,
  status: Status,
  lang: Lang,
): PodStepPresentation {
  const fallback = { text: statusName(lang, status), showMarker: false }
  if (!step || !step.trim()) return fallback

  const trimmed = step.trim()
  const doneObject = toolObject(trimmed, /^tool done:\s*(.+)$/i)
  if (doneObject) {
    return { text: `${COPY[lang].toolDone} ${doneObject}`, showMarker: true }
  }

  const runningObject = toolObject(trimmed, /^tool:\s*(.+)$/i)
  if (runningObject) {
    return { text: `${COPY[lang].toolRunning} ${runningObject}`, showMarker: true }
  }

  if (/^turn end$/i.test(trimmed) || /^skill:\s*/i.test(trimmed)) return fallback
  return { text: step, showMarker: true }
}

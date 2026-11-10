// TRANFU//AGENTS — DSH (DeepSeek Harness) plugin shell.
//
// Deliberately tiny and stable: replacing an installed plugin's JS needs a DSH
// restart, so every mapping decision lives in ~/.tranfu/tf_dsh_event.py (updated
// by the normal shim self-update). This shell only OBSERVES events and forwards
// {protocol, event, session_id, tool, skill} — never prompts, messages, tool
// arguments or outputs (a skill tool's `name` argument is the one exception).
// It never throws, never awaits, never alters a waterfall decision.
import { spawn } from 'node:child_process'
import { homedir } from 'node:os'
import { join } from 'node:path'

export const PROTOCOL = 1
const SKILL_TOOLS = new Set(['skill', 'skill_view'])

function script() {
  return join(process.env.TF_TRANFU_HOME || join(homedir(), '.tranfu'), 'tf_dsh_event.py')
}

function emit(payload) {
  try {
    if (process.env.TF_DSH_PLUGIN === '0' || !payload || !payload.session_id) return
    const child = spawn('python3', [script()], {
      stdio: ['pipe', 'ignore', 'ignore'],
      detached: true,
      windowsHide: true,
    })
    child.on('error', () => {})
    child.stdin.on('error', () => {})
    child.stdin.end(JSON.stringify({ protocol: PROTOCOL, ...payload }))
    child.unref()
  } catch {
    /* telemetry must never break DSH */
  }
}

function sessionId(obj) {
  try {
    if (!obj) return ''
    const id = obj.session?.id ?? obj.agent?.session?.id ?? obj.sessionId ?? obj.id
    return typeof id === 'string' ? id : ''
  } catch {
    return ''
  }
}

function toolInfo(exec) {
  const tool = typeof exec?.name === 'string' ? exec.name : ''
  const out = { tool }
  if (SKILL_TOOLS.has(tool.toLowerCase())) {
    const name = exec?.arguments?.name ?? exec?.arguments?.skill
    if (typeof name === 'string') out.skill = name.slice(0, 120)
  }
  return out
}

export function apply(ctx) {
  const disposers = []

  // Observe-only subscription. Waterfall listeners (the last argument is a
  // `next` function) must hand control on; plain events return nothing.
  const observe = (name, build) => {
    try {
      const dispose = ctx.on(name, (...args) => {
        try {
          const payload = build(...args)
          if (payload) emit({ event: name, ...payload })
        } catch {
          /* ignore */
        }
        const next = args[args.length - 1]
        if (args.length > 1 && typeof next === 'function') return next()
      })
      if (typeof dispose === 'function') disposers.push(dispose)
    } catch {
      /* unknown event on this DSH version: skip it */
    }
  }

  observe('session/created', (session) => ({ session_id: sessionId({ session }) || sessionId(session) }))
  observe('session/disposed', (session) => ({ session_id: sessionId({ session }) || sessionId(session) }))
  observe('session/event', (session, event) => {
    const type = event?.type
    if (type !== 'turn/start' && type !== 'turn/end') return null
    return { type, session_id: sessionId({ session }) || sessionId(session) }
  })
  observe('tools/pre-execute', (exec) => ({ session_id: sessionId(exec), ...toolInfo(exec) }))
  observe('tools/result', (exec) => ({ session_id: sessionId(exec), ...toolInfo(exec) }))
  observe('agent/error', (e) => ({ session_id: sessionId(e) }))
  observe('agent/turn-stopping', (e) => ({ session_id: sessionId(e) }))

  return () => {
    for (const d of disposers.splice(0)) {
      try {
        d()
      } catch {
        /* ignore */
      }
    }
  }
}

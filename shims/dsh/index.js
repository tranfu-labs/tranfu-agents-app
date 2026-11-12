// TRANFU//AGENTS — DSH (DeepSeek Harness) plugin shell.
//
// Deliberately tiny and stable: replacing an installed plugin's JS needs a DSH
// restart, so every mapping decision lives in ~/.tranfu/tf_dsh_event.py (updated
// by the normal shim self-update). This shell only OBSERVES events and forwards
// {protocol, event, session_id, tool, skill} — never prompts, messages, tool
// arguments or outputs (a skill tool's `name` argument is the one exception).
// It never throws, never awaits, never alters a waterfall decision.
import { spawn } from 'node:child_process'
import { appendFileSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

export const PROTOCOL = 1
const SKILL_TOOLS = new Set(['skill', 'skill_view'])

function script() {
  return join(process.env.TF_TRANFU_HOME || join(homedir(), '.tranfu'), 'tf_dsh_event.py')
}

// Opt-in diagnostics (TF_DSH_DEBUG=1): one NDJSON line per observation, summary
// only — event name, session id, tool/skill names. Never prompts or arguments.
function debug(tag, payload) {
  try {
    if (process.env.TF_DSH_DEBUG !== '1') return
    const dir = join(process.env.TF_TRANFU_HOME || join(homedir(), '.tranfu'), 'logs')
    mkdirSync(dir, { recursive: true })
    appendFileSync(join(dir, 'dsh-events.ndjson'), JSON.stringify({
      ts: new Date().toISOString(),
      tag,
      event: payload?.event,
      type: payload?.type,
      sid: payload?.session_id,
      tool: payload?.tool,
      skill: payload?.skill,
    }) + '\n')
  } catch {
    /* diagnostics must never break DSH */
  }
}

let sink = null

// A stop can arrive twice (plugin context + agent context). One terminal report
// per session turn is enough; a new turn re-arms it.
const stoppedSessions = new Set()

function stopOnce(sessionId, event, type) {
  if (!sessionId || stoppedSessions.has(sessionId)) return
  if (stoppedSessions.size > 512) stoppedSessions.clear()
  stoppedSessions.add(sessionId)
  emit({ event, type, session_id: sessionId })
}

// Test seam: production never sets this, so emit still spawns the dispatcher.
export function __setSink(fn) {
  sink = typeof fn === 'function' ? fn : null
}

function emit(payload) {
  try {
    debug('emit', payload)
    if (process.env.TF_DSH_PLUGIN === '0' || !payload || !payload.session_id) return
    if (sink) {
      sink({ protocol: PROTOCOL, ...payload })
      return
    }
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
  const agentRegistrations = new WeakMap()

  const track = (dispose) => {
    if (typeof dispose === 'function') disposers.push(dispose)
  }

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
      track(dispose)
    } catch {
      /* unknown event on this DSH version: skip it */
    }
  }

  // A child agent's session events may only be delivered on that agent's own
  // context, never on the plugin context. Without this, a subagent that ends
  // its turn leaves the turn heartbeat running for its full 4h window.
  const watchAgent = ({ agent } = {}) => {
    try {
      const sid = sessionId({ agent })
      if (!sid || !agent?.ctx || agentRegistrations.has(agent)) return null
      const owned = []
      const register = (name, handler) => {
        try {
          const dispose = agent.ctx.on(name, handler)
          if (typeof dispose === 'function') owned.push(dispose)
        } catch {
          /* event not offered on this context */
        }
      }
      register('session/event', (_session, event) => {
        if (event?.type !== 'turn/end') return
        stopOnce(sid, 'session/event', 'turn/end')
      })
      register('agent/turn-stopping', () => {
        stopOnce(sid, 'agent/turn-stopping')
      })
      agentRegistrations.set(agent, owned)
      track(() => {
        for (const dispose of owned.splice(0)) {
          try {
            dispose()
          } catch {
            /* ignore */
          }
        }
      })
    } catch {
      /* ignore */
    }
  }

  observe('agent/created', watchAgent)
  observe('agent/disposed', ({ agent } = {}) => ({ session_id: sessionId({ agent }) }))
  observe('session/created', (session) => ({ session_id: sessionId({ session }) || sessionId(session) }))
  observe('session/disposed', (session) => ({ session_id: sessionId({ session }) || sessionId(session) }))
  observe('session/event', (session, event) => {
    const type = event?.type
    if (type !== 'turn/start' && type !== 'turn/end') return null
    const sid = sessionId({ session }) || sessionId(session)
    if (type === 'turn/start') {
      stoppedSessions.delete(sid)
    } else {
      stopOnce(sid, 'session/event', 'turn/end')
      return null
    }
    return { type, session_id: sid }
  })
  observe('tools/pre-execute', (exec) => ({ session_id: sessionId(exec), ...toolInfo(exec) }))
  observe('tools/result', (exec) => ({ session_id: sessionId(exec), ...toolInfo(exec) }))
  observe('agent/error', (e) => ({ session_id: sessionId(e) }))
  observe('agent/turn-stopping', (e) => {
    stopOnce(sessionId(e), 'agent/turn-stopping')
    return null
  })

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

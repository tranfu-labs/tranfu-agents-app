// DSH 插件壳的行为契约（node --test）。
//
// 用例（对应 dsh-runtime-heartbeat-stop 的排查）：
//   1. session/created                     -> started
//   2. 根会话 turn/end                     -> done（停心跳）
//   3. 子 agent 在自己的 agent.ctx 上 turn/end -> done（**曾经漏掉**，导致心跳空转 4h）
//   4. agent/disposed                      -> done（进程内 agent 销毁兜底）
//   5. session/disposed                    -> done
//   6. 没有 session id 的事件              -> 不上报
//
// 只断言“发出去的 payload”，不真正 spawn python3。
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { apply, __setSink } from '../shims/dsh/index.js'

function fakeCtx() {
  const map = new Map()
  return {
    on(name, fn) {
      if (!map.has(name)) map.set(name, [])
      map.get(name).push(fn)
      return () => {
        const list = map.get(name) || []
        const i = list.indexOf(fn)
        if (i >= 0) list.splice(i, 1)
      }
    },
    emit(name, ...args) {
      for (const fn of map.get(name) || []) fn(...args)
    },
  }
}

function harness() {
  delete process.env.TF_DSH_PLUGIN
  const root = fakeCtx()
  const sent = []
  __setSink((p) => sent.push(p))
  const dispose = apply(root)
  return { root, sent, dispose }
}

test('session/created reports started for the root session', () => {
  const { root, sent } = harness()
  root.emit('session/created', { id: 'session-root' })
  assert.deepEqual(sent.at(-1), { protocol: 1, event: 'session/created', session_id: 'session-root' })
})

test('root turn/end reports a terminal stop', () => {
  const { root, sent } = harness()
  root.emit('session/created', { id: 'session-root' })
  root.emit('session/event', { id: 'session-root' }, { type: 'turn/end' })
  const last = sent.at(-1)
  assert.equal(last.event, 'session/event')
  assert.equal(last.type, 'turn/end')
  assert.equal(last.session_id, 'session-root')
})

test('child agent turn/end on agent.ctx still reports a stop', () => {
  const { root, sent } = harness()
  const childCtx = fakeCtx()
  const agent = { id: 'child-1', session: { id: 'child-session-1' }, ctx: childCtx }
  root.emit('agent/created', { agent })
  // 子 agent 的 turn/end 只在自己的 ctx 上出现，不经过根 ctx
  childCtx.emit('session/event', { id: 'child-session-1' }, { type: 'turn/end' })
  const last = sent.at(-1)
  assert.equal(last.type, 'turn/end')
  assert.equal(last.session_id, 'child-session-1')
})

test('agent/disposed reports a terminal stop', () => {
  const { root, sent } = harness()
  const agent = { id: 'child-2', session: { id: 'child-session-2' }, ctx: fakeCtx() }
  root.emit('agent/created', { agent })
  root.emit('agent/disposed', { agent })
  const last = sent.at(-1)
  assert.equal(last.event, 'agent/disposed')
  assert.equal(last.session_id, 'child-session-2')
})

test('session/disposed reports a terminal stop', () => {
  const { root, sent } = harness()
  root.emit('session/disposed', { id: 'session-x' })
  assert.equal(sent.at(-1).event, 'session/disposed')
  assert.equal(sent.at(-1).session_id, 'session-x')
})

test('events without a session id are not reported', () => {
  const { root, sent } = harness()
  const n = sent.length
  root.emit('session/created', {})
  root.emit('agent/turn-stopping', { agent: {} })
  assert.equal(sent.length, n)
})

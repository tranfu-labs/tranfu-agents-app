import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import {
  CLAUDE_STEP_ACTIONS,
  CODEX_STEP_ACTIONS,
  MCP_STEP_ACTIONS,
  formatAgentStep,
} from './agentStep.ts'

function readSource(relativePath: string) {
  for (const candidate of [path.join(process.cwd(), relativePath), path.join(process.cwd(), 'frontend', relativePath)]) {
    try {
      return readFileSync(candidate, 'utf8')
    } catch {
      // npm --prefix and direct node runs use different cwd shapes.
    }
  }
  throw new Error(`missing source file ${relativePath}`)
}

test('known Claude and Codex tool keys produce localized actions', () => {
  for (const [name, action] of Object.entries(CLAUDE_STEP_ACTIONS)) {
    assert.equal(formatAgentStep('claude-code', `tool: ${name}`, 'running', 'zh'), action.zh)
    assert.equal(formatAgentStep('claude-code', `tool: ${name}`, 'running', 'en'), action.en)
  }
  for (const [name, action] of Object.entries(CODEX_STEP_ACTIONS)) {
    assert.equal(formatAgentStep('codex', `tool: ${name}`, 'running', 'zh'), action.zh)
    assert.equal(formatAgentStep('codex', `tool: ${name}`, 'running', 'en'), action.en)
  }
})

test('MCP mappings preserve runtime-specific key spellings', () => {
  for (const [runtime, actions] of Object.entries(MCP_STEP_ACTIONS)) {
    for (const [name, action] of Object.entries(actions)) {
      assert.equal(formatAgentStep(runtime, `tool: ${name}`, 'running', 'zh'), action.zh)
      assert.equal(formatAgentStep(runtime, `tool: ${name}`, 'running', 'en'), action.en)
    }
  }
  assert.equal(formatAgentStep('codex', 'tool: mcp__chrome_devtools__take_screenshot', 'running', 'zh'), '正在截图')
  assert.equal(formatAgentStep('claude-code', 'tool: mcp__chrome-devtools__take_screenshot', 'running', 'zh'), '正在截图')
})

test('unknown MCP tools use structural fallback and unknown non-MCP tools stay raw', () => {
  assert.equal(formatAgentStep('codex', 'tool: mcp__acme_tools__lookup_record', 'running', 'zh'), '正在使用 acme tools 的 lookup record')
  assert.equal(formatAgentStep('codex', 'tool: mcp__acme_tools__lookup_record', 'running', 'en'), 'Using lookup record from acme tools')
  assert.equal(formatAgentStep('codex', 'tool: web.run', 'running', 'zh'), 'tool: web.run')
  assert.equal(formatAgentStep('codex', 'tool: exec_command', 'running', 'zh'), 'tool: exec_command')
})

test('lifecycle and skill scan steps do not render', () => {
  for (const step of ['session start', 'turn end', 'session end', 'done/turn end', ' DONE/session end ']) {
    assert.equal(formatAgentStep('codex', step, 'done', 'zh'), null)
  }
  assert.equal(formatAgentStep('codex', 'skill: demo', 'done', 'zh'), null)
  assert.equal(formatAgentStep('codex', 'done/skill: demo', 'done', 'zh'), null)
  assert.equal(formatAgentStep('codex', 'skill: demo', 'running', 'zh'), 'skill: demo')
})

test('tool done uses completion wording while ordinary steps stay intact', () => {
  assert.equal(formatAgentStep('claude-code', 'tool done: Read', 'running', 'zh'), '已完成读取文件')
  assert.equal(formatAgentStep('claude-code', 'tool done: Read', 'running', 'en'), 'Finished reading a file')
  assert.equal(formatAgentStep('codex', 'tool: view_image', 'done', 'zh'), '已完成查看图片')
  assert.equal(formatAgentStep('codex', 'tool: view_image', 'done', 'en'), 'Finished viewing an image')
  assert.equal(formatAgentStep('codex', 'tool: mcp__chrome_devtools__take_screenshot', 'done', 'zh'), '已完成截图')
  assert.equal(formatAgentStep('codex', '  reviewing results  ', 'running', 'zh'), 'reviewing results')
  assert.equal(formatAgentStep('unknown-runtime', 'tool: Read', 'running', 'zh'), 'tool: Read')
})

test('all board step entrances use the shared formatter', () => {
  for (const file of [
    'src/views/Board.tsx',
    'src/views/AgentDetail.tsx',
    'src/components/agents/AgentDirectoryTable.tsx',
  ]) {
    assert.match(readSource(file), /formatAgentStep/)
  }
})

test('all rendered entrances pass status into the shared formatter', () => {
  assert.match(readSource('src/views/Board.tsx'), /formatAgentStep\(agent\.runtime, agent\.current_step, agent\.status, lang\)/)
  assert.match(readSource('src/views/Board.tsx'), /formatAgentStep\(item\.runtime, item\.current_step, item\.status, lang\)/)
  assert.match(readSource('src/views/AgentDetail.tsx'), /formatAgentStep\(agent\.runtime, agent\.current_step, agent\.status, lang\)/)
  assert.match(readSource('src/components/agents/AgentDirectoryTable.tsx'), /formatAgentStep\(item\.runtime, item\.current_step, item\.status, lang\)/)
})

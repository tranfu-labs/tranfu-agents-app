/// <reference types="node" />
import assert from 'node:assert/strict'
import test from 'node:test'
import { presentPodStep } from './podStepPresentation.ts'

test('pod step localizes tool start and completion in both languages', () => {
  assert.deepEqual(presentPodStep('tool: Bash', 'running', 'zh'), {
    text: '正在运行命令 Bash',
    showMarker: true,
  })
  assert.deepEqual(presentPodStep('tool done: Bash', 'running', 'zh'), {
    text: '已完成命令 Bash',
    showMarker: true,
  })
  assert.deepEqual(presentPodStep('tool: Bash', 'running', 'en'), {
    text: 'Running command Bash',
    showMarker: true,
  })
  assert.deepEqual(presentPodStep('tool done: Bash', 'running', 'en'), {
    text: 'Finished command Bash',
    showMarker: true,
  })
})

test('pod step preserves the reported tool object', () => {
  assert.deepEqual(presentPodStep('  TOOL: custom.tool/v2  ', 'running', 'en'), {
    text: 'Running command custom.tool/v2',
    showMarker: true,
  })
})

test('pod step suppresses lifecycle, skill scan, and empty values to status', () => {
  assert.deepEqual(presentPodStep('turn end', 'done', 'zh'), {
    text: '完成',
    showMarker: false,
  })
  assert.deepEqual(presentPodStep('skill: alpha', 'done', 'en'), {
    text: 'done',
    showMarker: false,
  })
  assert.deepEqual(presentPodStep(null, 'waiting', 'zh'), {
    text: '等待',
    showMarker: false,
  })
  assert.deepEqual(presentPodStep('   ', 'mystery', 'en'), {
    text: 'mystery',
    showMarker: false,
  })
})

test('pod step leaves unknown free text byte-for-byte unchanged', () => {
  const value = '  同步发布说明 · 等待复核  '
  assert.deepEqual(presentPodStep(value, 'running', 'zh'), {
    text: value,
    showMarker: true,
  })
  assert.deepEqual(presentPodStep('tf-doctor', 'running', 'en'), {
    text: 'tf-doctor',
    showMarker: true,
  })
})

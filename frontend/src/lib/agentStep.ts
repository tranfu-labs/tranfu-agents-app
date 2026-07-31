import { statusName } from './i18n.ts'
import type { Lang, Status } from './types.ts'

export type StepCopy = { zh: string; en: string }
export type AgentStepPresentation = { text: string; showMarker: boolean }

const copy = (zh: string, en: string): StepCopy => ({ zh, en })

export const CLAUDE_STEP_ACTIONS: Record<string, StepCopy> = {
  Bash: copy('正在执行命令', 'Running a command'),
  Read: copy('正在读取文件', 'Reading a file'),
  Edit: copy('正在修改文件', 'Editing a file'),
  Write: copy('正在写入文件', 'Writing a file'),
  NotebookEdit: copy('正在修改 Notebook', 'Editing a notebook'),
  Glob: copy('正在查找文件', 'Finding files'),
  Grep: copy('正在搜索文件内容', 'Searching file contents'),
  Agent: copy('正在调用子 Agent', 'Running a sub-agent'),
  Task: copy('正在调用子 Agent', 'Running a sub-agent'),
  TaskCreate: copy('正在创建任务', 'Creating a task'),
  TaskUpdate: copy('正在更新任务', 'Updating a task'),
  TodoWrite: copy('正在更新任务清单', 'Updating the task list'),
  ToolSearch: copy('正在查找工具', 'Searching for a tool'),
  Skill: copy('正在加载 Skill', 'Loading a skill'),
  AskUserQuestion: copy('正在等待用户回答', 'Waiting for a user answer'),
  ScheduleWakeup: copy('正在安排唤醒', 'Scheduling a wakeup'),
  WebFetch: copy('正在读取网页', 'Fetching a webpage'),
  WebSearch: copy('正在联网搜索', 'Searching the web'),
}

export const CODEX_STEP_ACTIONS: Record<string, StepCopy> = {
  Bash: copy('正在执行命令', 'Running a command'),
  apply_patch: copy('正在修改文件', 'Editing files'),
  update_plan: copy('正在更新计划', 'Updating the plan'),
  view_image: copy('正在查看图片', 'Viewing an image'),
  webrun: copy('正在联网搜索', 'Searching the web'),
  request_user_input: copy('正在等待用户输入', 'Waiting for user input'),
  spawn_agent: copy('正在创建子 Agent', 'Spawning a sub-agent'),
  get_goal: copy('正在读取任务目标', 'Reading the task goal'),
  image_genimagegen: copy('正在生成图片', 'Generating an image'),
  collaborationwait_agent: copy('正在等待协作者', 'Waiting for a collaborator'),
  collaborationsend_message: copy('正在发送协作消息', 'Sending a collaboration message'),
  collaborationlist_agents: copy('正在查看协作者', 'Listing collaborators'),
  collaborationspawn_agent: copy('正在创建协作者', 'Spawning a collaborator'),
  collaborationfollowup_task: copy('正在跟进协作任务', 'Following up on a collaboration task'),
  collaborationinterrupt_agent: copy('正在中断协作者', 'Interrupting a collaborator'),
  multi_agent_v1wait_agent: copy('正在等待多 Agent 协作', 'Waiting for multi-agent work'),
  multi_agent_v1close_agent: copy('正在结束多 Agent 协作', 'Closing multi-agent work'),
  codex_appload_workspace_dependencies: copy('正在加载工作区依赖', 'Loading workspace dependencies'),
  codex_appread_thread: copy('正在读取会话线程', 'Reading the conversation thread'),
  list_mcp_resources: copy('正在查看 MCP 资源', 'Listing MCP resources'),
}

export const MCP_STEP_ACTIONS: Record<string, Record<string, StepCopy>> = {
  'claude-code': {
    'mcp__Claude_Browser__computer': copy('正在操作浏览器', 'Controlling the browser'),
    'mcp__Claude_Browser__javascript_tool': copy('正在执行浏览器脚本', 'Running browser JavaScript'),
    'mcp__Claude_Browser__navigate': copy('正在打开网页', 'Navigating to a webpage'),
    'mcp__chrome-devtools__evaluate_script': copy('正在执行浏览器脚本', 'Running browser JavaScript'),
    'mcp__chrome-devtools__navigate_page': copy('正在打开网页', 'Navigating to a webpage'),
    'mcp__chrome-devtools__take_screenshot': copy('正在截图', 'Capturing a screenshot'),
    'mcp__chrome-devtools__resize_page': copy('正在调整页面大小', 'Resizing the page'),
    'mcp__Claude_Preview__preview_eval': copy('正在预览执行页面脚本', 'Evaluating a preview'),
    'mcp__Claude_Preview__preview_screenshot': copy('正在预览截图', 'Capturing a preview screenshot'),
  },
  codex: {
    'mcp__node_repl__js': copy('正在执行 JavaScript', 'Running JavaScript'),
    'mcp__node_repl__js_add_node_module_dir': copy('正在加载 Node 模块', 'Loading a Node module'),
    'mcp__chrome_devtools__evaluate_script': copy('正在执行浏览器脚本', 'Running browser JavaScript'),
    'mcp__chrome_devtools__navigate_page': copy('正在打开网页', 'Navigating to a webpage'),
    'mcp__chrome_devtools__take_screenshot': copy('正在截图', 'Capturing a screenshot'),
    'mcp__context7__query_docs': copy('正在查询文档', 'Querying documentation'),
    'mcp__context7__resolve_library_id': copy('正在查找库文档', 'Resolving library documentation'),
    'mcp__computer_use__get_app_state': copy('正在读取应用状态', 'Reading application state'),
  },
}

const LIFECYCLE_STEPS = new Set(['session start', 'turn end', 'session end'])
const MCP_STEP = /^mcp__(.+?)__(.+)$/i
const TOOL_STEP = /^(tool done|tool):\s*(.+?)\s*$/i

function normalizedAction(actions: Record<string, StepCopy> | undefined, name: string) {
  if (!actions) return undefined
  const direct = actions[name]
  if (direct) return direct
  const folded = name.toLocaleLowerCase()
  const key = Object.keys(actions).find((candidate) => candidate.toLocaleLowerCase() === folded)
  return key ? actions[key] : undefined
}

function humanizeMcpPart(part: string) {
  return part.replace(/[-_]+/g, ' ').trim() || part
}

function actionFor(runtime: string, toolName: string): StepCopy | undefined {
  const normalizedRuntime = runtime.trim().toLocaleLowerCase()
  const actions = normalizedRuntime === 'claude-code'
    ? CLAUDE_STEP_ACTIONS
    : normalizedRuntime === 'codex'
      ? CODEX_STEP_ACTIONS
      : undefined
  const direct = normalizedAction(actions, toolName)
  if (direct) return direct
  return normalizedAction(MCP_STEP_ACTIONS[normalizedRuntime], toolName)
}

function genericMcpCopy(match: RegExpExecArray): StepCopy {
  const server = humanizeMcpPart(match[1])
  const tool = humanizeMcpPart(match[2])
  return copy(`正在使用 ${server} 的 ${tool}`, `Using ${tool} from ${server}`)
}

function finished(action: StepCopy): StepCopy {
  return copy(
    action.zh.startsWith('正在') ? `已完成${action.zh.slice(2)}` : `已完成${action.zh}`,
    `Finished ${action.en.charAt(0).toLocaleLowerCase()}${action.en.slice(1)}`,
  )
}

function withoutDonePrefix(value: string) {
  return value.replace(/^done\//i, '').trim()
}

function isSkillScan(value: string) {
  return /^skill\s*:/i.test(withoutDonePrefix(value))
}

function fallback(status: Status, lang: Lang): AgentStepPresentation {
  return { text: statusName(lang, status), showMarker: false }
}

export function formatAgentStep(runtime: string, currentStep: string | null | undefined, status: Status, lang: Lang): AgentStepPresentation {
  if (!currentStep || !currentStep.trim()) return fallback(status, lang)
  const raw = currentStep.trim()
  const lifecycle = withoutDonePrefix(raw).toLocaleLowerCase()
  if (isSkillScan(raw) || LIFECYCLE_STEPS.has(lifecycle)) return fallback(status, lang)

  const toolMatch = TOOL_STEP.exec(raw)
  if (!toolMatch) return { text: currentStep, showMarker: true }
  const prefix = toolMatch[1].toLocaleLowerCase()
  const toolName = toolMatch[2]
  const action = actionFor(runtime, toolName)
  const completed = String(status || '').toLocaleLowerCase() === 'done' || prefix === 'tool done'
  if (action) return { text: (completed ? finished(action) : action)[lang], showMarker: true }

  const mcpMatch = MCP_STEP.exec(toolName)
  if (mcpMatch) {
    const mcpAction = normalizedAction(MCP_STEP_ACTIONS[runtime.trim().toLocaleLowerCase()], toolName)
    const copyText = mcpAction || genericMcpCopy(mcpMatch)
    return { text: (completed ? finished(copyText) : copyText)[lang], showMarker: true }
  }
  return { text: currentStep, showMarker: true }
}

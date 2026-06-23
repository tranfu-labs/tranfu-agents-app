import type { AgentConfig, AgentMemory, OperatorDetail, OperatorTableRow, SkillDetail, SkillsOverview, SkillTableRow, StatePayload } from './types'
import { apiToday, daySeries } from './utils'

const now = new Date()
const iso = (secondsAgo: number) => new Date(now.getTime() - secondsAgo * 1000).toISOString()

export const DEMO_STATE: StatePayload = {
  now: now.toISOString(),
  totals: { live: 5, operators: 3, agents: 6, today_active: 42600 },
  leverage: { skills_week: 7, assets: 48 },
  shim: { version: 'demo-shim-current' },
  skills: [
    { name: '组件命名规范', mode: 'used', sessions_7d: 8, sessions_30d: 19, sessions_total: 36, users_30d: 3, last_day: now.toISOString().slice(0, 10) },
    { name: 'pytest 脚手架', mode: 'used', sessions_7d: 5, sessions_30d: 14, sessions_total: 22, users_30d: 2, last_day: now.toISOString().slice(0, 10) },
    { name: '品牌语气库', mode: 'equipped', sessions_7d: 3, sessions_30d: 9, sessions_total: 31, users_30d: 1, last_day: now.toISOString().slice(0, 10) },
  ],
  sessions: [
    {
      operator: 'nezha',
      agent: 'build',
      runtime: 'claude-code',
      status: 'running',
      task: '画原型',
      current_step: '梳理界面结构',
      ts: iso(9),
      fidelity: 'full',
      shim_version: 'demo-shim-current',
      today_active: 9120,
      week_active: 31800,
      active_series: [4200, 5400, 3600, 6100, 5200, 4300, 9120],
      models: ['claude-opus-4-6', 'claude-sonnet-4-6'],
      about: '把一句话需求快速变成可点击的低保真原型:先问清目标用户和核心动作,再用统一的组件命名出框架图,产出可直接进 Figma 的结构。',
      tips: '给它需求时先说清「谁用、要完成什么动作」,它会自己补齐信息架构;别一上来就让它定视觉。',
      config: { temperature: 0.4, max_tokens: 8192, auto_approve: 'read-only', thinking: 'on' },
      instructions: '角色:资深产品设计师。\n步骤:1) 复述需求并列出目标用户/核心任务 2) 给信息架构 3) 再出低保真框架 4) 等确认后才进视觉。\n约束:命名遵循团队《组件命名规范》。',
      skills: {
        local: [
          { name: 'prd-to-wireframe', desc: '需求→信息架构→低保真框架的固定流程' },
          { name: '组件命名规范', desc: '按 团队/页面/组件 三段式命名,导出即对齐' },
        ],
        cross: [{ name: '飞书多维表导出', desc: '从产品需求表拉结构化字段(借自 bob 的 Pod)' }],
        pitfalls: ['hero 区别用红底白字,移动端对比度不达标', '原型阶段不要纠结真实文案,用占位'],
      },
      mcp: ['filesystem', 'figma', 'github'],
      quality: { runs: 54, success: 49, error: 5, reuse: 0.62, avg_sec: 760, auto_rate: 0.78, recent: 1 },
      recent: [
        { task: '营销活动落地页原型', outcome: '3 屏框架 + 交互注释,已进 Figma', status: 'done', dur: 1080 },
        { task: '后台数据看板布局', outcome: '等确认信息架构', status: 'running', dur: 420 },
        { task: '导出 v1 设计稿', outcome: 'exit 0', status: 'done', dur: 240 },
      ],
    },
    {
      operator: 'nezha',
      agent: '多儿',
      runtime: 'hermes',
      status: 'running',
      task: '梳理产品思路',
      current_step: '对话中',
      ts: iso(22),
      fidelity: 'full',
      shim_version: 'demo-shim-current',
      today_active: 5400,
      week_active: 18000,
      active_series: [2400, 3000, 1800, 3600, 2900, 2100, 5400],
      models: ['claude-sonnet-4-6'],
      about: '思考伙伴:用第一性原理追问,帮你把模糊想法逼成清晰假设,适合早期方向探索,不负责产出文档。',
      tips: '把它当陪练:抛半成熟的想法,让它追问;别指望它给标准答案。',
      config: { temperature: 0.8, memory: 'on' },
      instructions: '角色:苏格拉底式思考伙伴。\n做法:对每个论点连问三层「为什么」,直到触及最底层假设;每轮结束给出 1 个可证伪假设 + 验证方法。',
      skills: { local: [{ name: '第一性原理追问', desc: '把结论拆回最底层假设逐条质疑' }], cross: [], pitfalls: ['别让它写正式文档,它会发散'] },
      mcp: ['notion'],
      quality: { runs: 31, success: 30, error: 1, reuse: 0.3, avg_sec: 520, auto_rate: 0.4 },
      recent: [
        { task: '会员体系该不该做', outcome: '逼出 3 个核心假设 + 验证方式', status: 'done', dur: 900 },
        { task: '梳理产品思路', outcome: '对话进行中', status: 'running', dur: 300 },
      ],
    },
    {
      operator: 'nezha',
      agent: '原型',
      runtime: 'mulerun',
      status: 'running',
      task: '云端生成原型',
      current_step: '云端 VM 运行中',
      ts: iso(140),
      fidelity: 'coarse',
      shim_version: 'demo-shim-current',
      today_active: 7200,
      week_active: 7200,
      active_series: [0, 0, 0, 0, 0, 0, 7200],
      models: ['gpt-4o', 'gemini-2.0'],
      about: '云端自动跑:把落地页需求丢进去,无人值守生成多版可选稿,适合走量、要快不要精。',
      tips: '一次给足约束(品牌色/参考站/字数),它中途没法追问;粗粒度只看起止。',
      config: { mode: 'autonomous' },
      skills: { local: [{ name: '落地页模板', desc: '含 6 种常见结构的起手模板' }], cross: [{ name: '组件命名规范', desc: '复用 build 的命名(保证可交接)' }], pitfalls: ['黑盒无法中途纠偏,约束要一次给全'] },
      mcp: [],
      quality: { runs: 12, success: 9, error: 3, reuse: 0.5, avg_sec: 1500, auto_rate: 0.95 },
    },
    {
      operator: 'bob',
      agent: 'copy',
      runtime: 'open-claw',
      status: 'running',
      task: '改写落地页文案',
      current_step: 'drafting hero',
      ts: iso(18),
      fidelity: 'full',
      shim_version: 'demo-shim-old',
      today_active: 2640,
      week_active: 14400,
      active_series: [1800, 2100, 1500, 3000, 2200, 1200, 2640],
      models: ['claude-sonnet-4-6'],
      about: '营销文案改写:吃品牌语气库,产出符合调性的多版标题与正文,擅长 hero/slogan。',
      tips: '先喂目标人群和一个你喜欢的样例,它会贴着语气走;要多版就说「给 5 版」。',
      config: { temperature: 0.9 },
      skills: { local: [{ name: '品牌语气库', desc: '沉淀的 tone & voice + 禁用词' }, { name: 'slogan 模板', desc: '12 种 slogan 结构套路' }], cross: [], pitfalls: ['避免夸大词(最/第一/唯一)合规风险'] },
      mcp: ['notion', 'slack'],
      quality: { runs: 88, success: 81, error: 7, reuse: 0.71, avg_sec: 300, auto_rate: 0.6 },
      recent: [
        { task: '首页 hero 文案', outcome: '5 版,选定第 3 版', status: 'done', dur: 360 },
        { task: '邮件营销序列', outcome: '3 封草稿', status: 'done', dur: 540 },
      ],
    },
    {
      operator: 'bob',
      agent: 'code',
      runtime: 'codex',
      status: 'waiting',
      task: '迁移测试到 pytest',
      current_step: '等待 shell 授权',
      ts: iso(40),
      fidelity: 'full',
      shim_version: 'demo-shim-current',
      today_active: 5280,
      week_active: 22800,
      active_series: [3000, 4200, 2400, 5100, 3600, 2700, 5280],
      models: ['gpt-4o'],
      about: '测试与重构:把老测试迁到 pytest、修 flaky、补覆盖率,稳健、改动小、爱写注释。',
      tips: '给它明确边界(别动 migrations),它会按最小改动来;授权 shell 前会停下等你。',
      config: { temperature: 0.2, sandbox: 'workspace-write' },
      skills: { local: [{ name: 'pytest 脚手架', desc: 'fixture/参数化/mark 的标准骨架' }], cross: [{ name: 'CI 修复手册', desc: '复用 chen 的 flaky 定位经验' }], pitfalls: ['别动 migrations', 'mock 外部网络,别真打'] },
      mcp: ['github', 'filesystem'],
      quality: { runs: 67, success: 60, error: 7, reuse: 0.55, avg_sec: 680, auto_rate: 0.7 },
      recent: [
        { task: '支付模块测试迁移', outcome: '等待 shell 授权', status: 'waiting', dur: 300 },
        { task: '修复登录 flaky', outcome: '通过,补了 2 个用例', status: 'done', dur: 720 },
      ],
    },
    {
      operator: 'chen',
      agent: 'code',
      runtime: 'claude-desktop',
      status: 'done',
      task: '修复 CI flaky test',
      current_step: 'exit 0',
      ts: iso(360),
      fidelity: 'coarse',
      shim_version: 'demo-shim-current',
      today_active: 12960,
      week_active: 39000,
      active_series: [7200, 8400, 6000, 9000, 7800, 6600, 12960],
      models: ['claude-opus-4-6'],
      about: '疑难定位:专啃 flaky / 偶现 bug,擅长二分定位和写复现脚本;桌面版,通过 MCP 自动上报。',
      tips: '把能复现的最小信息给它(随机种子/并发数),它会自己二分;它接了 TRANFU MCP,会自动报状态。',
      config: {},
      skills: { local: [{ name: 'flaky 定位法', desc: '固定随机源→隔离并发→二分提交' }], cross: [{ name: 'pytest 脚手架', desc: '复用 bob 的骨架写复现用例' }], pitfalls: ['偶现 bug 先稳定复现再动手,别盲改'] },
      mcp: ['github'],
      quality: { runs: 40, success: 38, error: 2, reuse: 0.66, avg_sec: 1200, auto_rate: 0.5 },
      recent: [
        { task: 'CI flaky 修复', outcome: '根因:共享端口竞争,已隔离', status: 'done', dur: 1500 },
        { task: '偶现登录失败', outcome: '复现 + 修复', status: 'done', dur: 1080 },
      ],
    },
    {
      operator: 'chen',
      agent: 'scout',
      runtime: 'hermes',
      status: 'running',
      task: '新接入演练',
      current_step: '等待首次心跳',
      ts: iso(12),
      fidelity: 'full',
      // shim_version 故意缺失:演示「unknown」三态(灰色「等待客户端心跳」)
      today_active: 240,
      week_active: 240,
      active_series: [0, 0, 0, 0, 0, 0, 240],
      models: ['claude-haiku-4-5'],
      about: '新人 agent:刚接入演示用,客户端 shim 还没上报版本号,看板呈 unknown 灰态。',
      tips: '让真实 shim 心跳跑上一次,标签就会变成 current。',
      config: {},
      mcp: [],
      quality: { runs: 1, success: 1, error: 0, avg_sec: 60, auto_rate: 1 },
    },
  ],
  feed: [
    { operator: 'nezha', agent: 'build', runtime: 'claude-code', status: 'running', current_step: '梳理界面结构', ts: iso(9) },
    { operator: 'nezha', agent: '多儿', runtime: 'hermes', status: 'running', current_step: '对话中', ts: iso(22) },
    { operator: 'bob', agent: 'copy', runtime: 'open-claw', status: 'running', current_step: 'drafting hero', ts: iso(18) },
    { operator: 'bob', agent: 'code', runtime: 'codex', status: 'waiting', current_step: '等待 shell 授权', ts: iso(40) },
    { operator: 'nezha', agent: 'build', runtime: 'claude-code', status: 'done', current_step: '导出 v1', ts: iso(600) },
    { operator: 'chen', agent: 'code', runtime: 'claude-desktop', status: 'done', current_step: 'exit 0', ts: iso(360) },
  ],
}

export const DEMO_MEMORY: Record<string, AgentMemory> = {
  'nezha::build': { file: '~/.claude/CLAUDE.md', updated: 7200, conventions: ['组件命名:团队/页面/组件 三段式,导出即对齐', '低保真先行,信息架构确认后才进视觉', '断点统一 390 / 768 / 1280'], learned: ['营销页 hero 浅底深字比深底白字转化高约 15%', '表单字段每多 1 个,完成率掉 ~10%,非必填一律折叠', '移动端 CTA 固定底栏点击率明显更高'] },
  'nezha::多儿': { file: '~/.hermes/memory.md', updated: 3600, conventions: ['每轮只逼出 1 个可证伪假设 + 验证方法', '结论必须能被一个具体实验推翻'], learned: ['会员体系对低频品类 ROI 偏低,先验证复购再投入', '『做不做』先问『不做会死吗』,能砍则砍'] },
  'bob::copy': { file: '~/.claude/CLAUDE.md', updated: 1800, conventions: ['禁用词:最 / 第一 / 唯一(合规)', '标题 ≤14 字,副标题讲『场景 + 收益』', '每次给 3–5 版并标注适用场景'], learned: ['B 端副标题用『场景+收益』句式点击率约 +18%', '『限时』比『立即』在本品类 CTR 更高', '落地页只留 1 个主 CTA,转化优于多按钮'] },
  'bob::code': { file: '~/.codex/AGENTS.md', updated: 5400, conventions: ['最小改动、可回滚;每步先报计划', '危险操作必须等授权,外部网络一律 mock'], learned: ['支付模块迁移前先冻结 migrations,否则易脏数据', 'CI flaky 约六成源于共享端口竞争', '测试用 freezegun 固定时间能消掉大量偶现'] },
  'chen::code': { file: '~/.claude/CLAUDE.md', updated: 600, conventions: ['偶现问题先稳定复现再动手', '定位三维度:提交 / 输入 / 环境'], learned: ['固定随机种子可消除约 60% 偶现失败', '时间依赖是 flaky 第二大来源', '并发测试用独立临时端口,别共享 8000'] },
}

export const DEMO_CONFIG: Record<string, AgentConfig> = {
  'nezha::build': { ver: 'Claude Code v1.2', role: '产品设计执行体', location: '~/projects/app', terminal: 'iTerm2 · zsh', ims: [], integrations: [{ name: 'Figma', desc: '读写设计稿、导出框架图' }, { name: 'GitHub', desc: '读代码上下文、提 PR' }] },
  'nezha::多儿': { ver: 'Hermes', role: '飞书自动化执行体', location: '~/.hermes/', terminal: '常驻服务', ims: ['飞书 / Lark'], integrations: [{ name: '飞书 App / 群组 / 用户身份', desc: '消息推送、定时、消息回调' }, { name: '飞书文档 API', desc: '写 heading/code 块(每次≤50)' }, { name: 'Cloudflare Tunnel', desc: '公网入口' }] },
  'nezha::原型': { ver: 'MuleRun(云端)', role: '无人值守原型生成', location: '云端 VM', terminal: '—', ims: [], integrations: [{ name: 'Webhook 回调', desc: '任务完成后通知' }] },
  'bob::copy': { ver: 'Open Claw v1.4', role: '品牌文案执行体', location: '~/work/copy', terminal: 'VS Code 终端 · zsh', ims: ['飞书 / Lark', '微信 bot'], integrations: [{ name: 'Notion', desc: '读品牌语气库、存稿' }, { name: 'Slack', desc: '评审通知' }] },
  'bob::code': { ver: 'Codex CLI', role: '测试 / 重构执行体', location: '~/repo/api', terminal: 'tmux · bash', ims: [], integrations: [{ name: 'GitHub', desc: '分支 / PR / issue' }, { name: '本地文件系统', desc: 'workspace-write' }] },
  'chen::code': { ver: 'Claude Desktop', role: '调试执行体', location: '桌面 App(经 MCP)', terminal: '桌面 App', ims: ['Telegram'], integrations: [{ name: 'GitHub', desc: '读仓库、定位提交' }, { name: 'TRANFU reporter(MCP)', desc: '自动上报状态' }] },
}

export function demoSkillsOverview(): SkillsOverview {
  const today = apiToday()
  const days = daySeries(today, 30)
  const table: SkillTableRow[] = [
    { name: '组件命名规范', source: 'own', sessions_7d: 8, sessions_30d: 19, sessions_total: 36, users_30d: 3, runtime_counts: { 'claude-code': 13, mulerun: 4, 'claude-desktop': 2 }, trend_14d: [0, 1, 1, 0, 2, 0, 2, 1, 2, 1, 3, 1, 2, 3], last_day: days[29] },
    { name: 'pytest 脚手架', source: '非公司库', sessions_7d: 5, sessions_30d: 14, sessions_total: 22, users_30d: 2, runtime_counts: { codex: 11, 'claude-desktop': 3 }, trend_14d: [1, 0, 0, 2, 1, 0, 1, 1, 0, 2, 1, 1, 2, 1], last_day: days[28] },
    { name: '品牌语气库', source: 'own', sessions_7d: 3, sessions_30d: 9, sessions_total: 31, users_30d: 1, runtime_counts: { 'open-claw': 9 }, trend_14d: [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 1, 1], last_day: days[29] },
  ]
  const daily = table.flatMap((row, idx) =>
    days.flatMap((day, i) => {
      const trend = row.trend_14d || []
      const value = trend[(i + idx) % (trend.length || 1)] || 0
      return value ? [{ day, skill: row.name, runtime: Object.keys(row.runtime_counts || {})[0], sessions: value, source: row.source }] : []
    }),
  )
  const operatorTable: OperatorTableRow[] = [
    { operator: 'nezha', sessions_7d: 9, sessions_30d: 22, sessions_total: 42, skill_count: 5, session_count: 18, runtime_counts: { 'claude-code': 15, hermes: 7 }, source_counts: { own: 16, external: 6 }, trend_14d: [1, 1, 2, 0, 3, 1, 2, 2, 1, 3, 2, 1, 2, 3], last_day: days[29] },
    { operator: 'bob', sessions_7d: 6, sessions_30d: 18, sessions_total: 37, skill_count: 4, session_count: 15, runtime_counts: { codex: 12, 'open-claw': 6 }, source_counts: { own: 8, '非公司库': 10 }, trend_14d: [0, 1, 0, 2, 1, 2, 1, 0, 2, 2, 1, 1, 2, 3], last_day: days[29] },
    { operator: 'chen', sessions_7d: 4, sessions_30d: 11, sessions_total: 21, skill_count: 3, session_count: 9, runtime_counts: { 'claude-desktop': 11 }, source_counts: { '非公司库': 9, own: 2 }, trend_14d: [1, 0, 1, 1, 0, 1, 0, 2, 1, 0, 1, 1, 1, 2], last_day: days[28] },
  ]
  const operatorDaily = operatorTable.flatMap((row, idx) =>
    days.flatMap((day, i) => {
      const value = row.trend_14d?.[(i + idx) % (row.trend_14d.length || 1)] || 0
      return value ? [{ day, operator: row.operator, runtime: Object.keys(row.runtime_counts || {})[0], source: Object.keys(row.source_counts || {})[0], sessions: value }] : []
    }),
  )
  return {
    days: 30,
    today,
    daily,
    table,
    operator_daily: operatorDaily,
    operator_table: operatorTable,
    funnel: {
      available: true,
      catalog: [{ name: '组件命名规范', source: 'own' }, { name: '品牌语气库', source: 'own' }, { name: '落地页模板', source: 'own' }],
      installed: [{ name: '组件命名规范', source: 'own' }, { name: '品牌语气库', source: 'own' }, { name: '落地页模板', source: 'own' }],
      used_30d: [{ name: '组件命名规范', source: 'own' }, { name: '品牌语气库', source: 'own' }],
      idle: [{ name: '落地页模板', source: 'own' }],
    },
    catalog: { available: true, fetched_at: now.toISOString(), stale: false, count: 3 },
  }
}

export function demoOperatorDetail(operator: string, overview = demoSkillsOverview()): OperatorDetail | null {
  const row = overview.operator_table?.find((item) => item.operator === operator)
  if (!row) return null
  const today = apiToday(overview)
  const days = daySeries(today, 30)
  const skills = overview.table.slice(0, Math.max(2, Math.min(overview.table.length, row.skill_count || 3))).map((skill, index) => ({
    name: skill.name,
    source: skill.source,
    sessions_7d: Math.max(1, Math.floor((skill.sessions_7d || 1) / (index + 1))),
    sessions_30d: Math.max(1, Math.floor((skill.sessions_30d || 1) / (index + 1))),
    sessions_total: Math.max(1, Math.floor((skill.sessions_total || 1) / (index + 1))),
    runtime_counts: skill.runtime_counts,
    last_day: skill.last_day,
  }))
  const daily = days.flatMap((day, i) =>
    skills.flatMap((skill, index) => {
      const value = i % (index + 2) === 0 ? Math.max(1, Math.floor((skill.sessions_30d || 1) / 10)) : 0
      return value ? [{ day, skill: skill.name, sessions: value }] : []
    }),
  )
  return {
    operator,
    today,
    metrics: {
      sessions_7d: row.sessions_7d,
      sessions_30d: row.sessions_30d,
      sessions_total: row.sessions_total,
      skill_count: row.skill_count,
      session_count: row.session_count,
      first_day: days[0],
      last_day: row.last_day,
    },
    daily,
    skills,
    runtime: Object.entries(row.runtime_counts || {}).map(([runtime, used]) => ({ runtime, used })),
    records: skills.slice(0, 6).map((skill, index) => ({
      day: days[29 - index],
      skill: skill.name,
      runtime: Object.keys(skill.runtime_counts || {})[0],
      session_id: `demo-${operator}-${index}`,
      first_seen: now.toISOString(),
    })),
    catalog: { available: true, stale: false },
  }
}

export function demoSkillDetail(name: string, overview = demoSkillsOverview()): SkillDetail | null {
  const row = overview.table.find((item) => item.name === name)
  if (!row) return null
  const today = apiToday(overview)
  const days = daySeries(today, 30)
  const daily = days.map((day, i) => ({
    day,
    used: row.trend_14d?.[i % (row.trend_14d.length || 1)] || 0,
    equipped: name === '品牌语气库' && i % 3 === 0 ? 1 : 0,
  }))
  return {
    name,
    today,
    source: row.source,
    metrics: {
      sessions_7d: row.sessions_7d,
      sessions_30d: row.sessions_30d,
      sessions_total: row.sessions_total,
      users_30d: row.users_30d,
      first_day: days[0],
      last_day: row.last_day,
      equipped_total: name === '品牌语气库' ? 6 : 0,
      equipped_30d: name === '品牌语气库' ? 6 : 0,
    },
    daily,
    runtime: Object.entries(row.runtime_counts || {}).map(([runtime, used]) => ({ runtime, used, equipped: name === '品牌语气库' && runtime === 'open-claw' ? 6 : 0 })),
    operators: [
      { operator: 'nezha', used: Math.ceil(row.sessions_total * 0.55), equipped: 0 },
      { operator: 'bob', used: Math.floor(row.sessions_total * 0.35), equipped: name === '品牌语气库' ? 6 : 0 },
    ],
    records: [{ day: row.last_day, operator: 'nezha', runtime: Object.keys(row.runtime_counts || {})[0], mode: 'used', session_id: 'demo-session-1', first_seen: now.toISOString() }],
    catalog: { available: true, stale: false },
  }
}

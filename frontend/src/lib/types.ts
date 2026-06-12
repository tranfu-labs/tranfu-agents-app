export type Lang = 'zh' | 'en'

export type Status = 'started' | 'running' | 'waiting' | 'blocked' | 'done' | 'error' | 'idle' | string

export type SkillRef = {
  name: string
  desc?: string
}

export type SkillsProfile = {
  local?: SkillRef[]
  cross?: SkillRef[]
  pitfalls?: Array<string | SkillRef>
}

export type Quality = {
  runs?: number
  success?: number
  error?: number
  blocked?: number
  reuse?: number
  avg_sec?: number | null
  auto_rate?: number | null
  recent?: number
}

export type AgentSession = {
  operator: string
  runtime: string
  agent?: string
  session_id?: string
  status: Status
  task?: string
  current_step?: string
  ts: string
  fidelity?: string
  shim_version?: string
  today_active?: number
  week_active?: number
  active_series?: number[]
  active_days?: number[]
  models?: string[]
  about?: string
  tips?: string
  config?: Record<string, unknown>
  instructions?: string
  skills?: SkillsProfile
  mcp?: string[]
  quality?: Quality
  recent?: Array<{ task?: string; outcome?: string; status?: string; dur?: number }>
  cf?: AgentConfig
  integrations?: Array<{ name: string; desc?: string }>
  memory?: AgentMemory
}

export type AgentMemory = {
  file?: string
  updated?: number
  conventions?: string[]
  learned?: string[]
}

export type AgentConfig = {
  ver?: string
  role?: string
  location?: string
  terminal?: string
  ims?: string[]
  integrations?: Array<{ name: string; desc?: string }>
}

export type FeedItem = {
  operator: string
  runtime: string
  agent?: string
  status: Status
  task?: string
  current_step?: string
  ts: string
}

export type StatePayload = {
  now: string
  totals: {
    live: number
    operators?: number
    agents?: number
    today_active?: number
  }
  leverage?: {
    skills_week?: number
    assets?: number
  }
  shim?: {
    version?: string
  }
  skills?: StateSkillRank[]
  sessions: AgentSession[]
  feed: FeedItem[]
}

export type StateSkillRank = {
  name: string
  mode?: 'used' | 'equipped'
  sessions_7d?: number
  sessions_30d?: number
  sessions_total?: number
  users_30d?: number
  last_day?: string
}

export type SkillDailyRow = {
  day: string
  skill: string
  runtime?: string
  source?: string
  sessions: number
}

export type SkillTableRow = {
  name: string
  source?: string
  sessions_7d: number
  sessions_30d: number
  sessions_total: number
  users_30d: number
  runtime_counts?: Record<string, number>
  trend_14d?: number[]
  last_day?: string
}

export type CatalogSkill = {
  name: string
  source?: string
  type?: string
}

export type SkillsOverview = {
  days?: number
  today: string
  daily: SkillDailyRow[]
  table: SkillTableRow[]
  funnel?: {
    available: boolean
    catalog?: CatalogSkill[]
    installed?: CatalogSkill[]
    used_30d?: CatalogSkill[]
    idle?: CatalogSkill[]
  }
  catalog?: {
    available?: boolean
    fetched_at?: string
    stale?: boolean
    count?: number
    error?: string
  }
}

export type SkillDetail = {
  name: string
  today: string
  source?: string
  metrics?: {
    sessions_7d?: number
    sessions_30d?: number
    sessions_total?: number
    users_30d?: number
    first_day?: string
    last_day?: string
    equipped_total?: number
    equipped_30d?: number
  }
  daily?: Array<{ day: string; used?: number; equipped?: number }>
  runtime?: Array<{ runtime: string; used?: number; equipped?: number }>
  operators?: Array<{ operator: string; used?: number; equipped?: number }>
  records?: Array<{
    day?: string
    operator?: string
    runtime?: string
    mode?: string
    session_id?: string
    first_seen?: string
  }>
  catalog?: Record<string, unknown>
}

export type Loadable<T> = {
  data: T | null
  loading: boolean
  error: string
  demo: boolean
  refresh: (force?: boolean) => Promise<void>
}

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

export type OperatorDailyRow = {
  day: string
  operator: string
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

export type OperatorTableRow = {
  operator: string
  sessions_7d: number
  sessions_30d: number
  sessions_total: number
  skill_count: number
  session_count: number
  runtime_counts?: Record<string, number>
  source_counts?: Record<string, number>
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
  operator_daily?: OperatorDailyRow[]
  operator_table?: OperatorTableRow[]
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

export type OperatorDetail = {
  operator: string
  today: string
  metrics?: {
    sessions_7d?: number
    sessions_30d?: number
    sessions_total?: number
    skill_count?: number
    session_count?: number
    first_day?: string
    last_day?: string
  }
  daily?: Array<{ day: string; skill: string; sessions: number }>
  skills?: Array<{
    name: string
    source?: string
    sessions_7d?: number
    sessions_30d?: number
    sessions_total?: number
    runtime_counts?: Record<string, number>
    last_day?: string
  }>
  runtime?: Array<{ runtime: string; used?: number }>
  records?: Array<{
    day?: string
    skill?: string
    runtime?: string
    session_id?: string
    first_seen?: string
  }>
  catalog?: Record<string, unknown>
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

export type TokenUsageSummary = {
  token_id: number
  token_name: string
  username?: string
  user_id?: number
  status?: number
  group?: string
  remain_quota?: number
  used_quota?: number
  unlimited_quota?: boolean
  created_time?: number
  accessed_time?: number
  expired_time?: number
  request_count?: number
  error_count?: number
  quota?: number
  prompt_tokens?: number
  completion_tokens?: number
  token_used?: number
  avg_use_time?: number
  last_used_at?: number
  top_model?: string
  model_count?: number
}

export type TokenUsageTrend = {
  token_id: number
  token_name: string
  username?: string
  user_id?: number
  created_at: number
  count?: number
  error_count?: number
  quota?: number
  token_used?: number
}

export type TokenModelUsage = {
  token_id: number
  token_name: string
  username?: string
  user_id?: number
  model_name: string
  count?: number
  quota?: number
  token_used?: number
}

export type TokenUsagePayload = {
  ok: boolean
  source: 'upstream' | 'demo' | string
  configured?: boolean
  warning?: string
  fetched_at?: string
  range?: {
    start_timestamp?: number
    end_timestamp?: number
    days?: number
    time_granularity?: string
    timezone_offset_minutes?: number
  }
  data: {
    summary: TokenUsageSummary[]
    trend: TokenUsageTrend[]
    models: TokenModelUsage[]
  }
}

export type TokenUsageQuery = {
  preset: string
  startTimestamp: number
  endTimestamp: number
  timeGranularity: 'hour' | 'four_hour' | 'day' | 'week' | 'month'
}

export type AdminTarget =
  | { session_ids: string[] }
  | { operator: string; agent?: string; runtime?: string; profile?: boolean }
  | { before_day: string; operator: string; agent?: string; runtime?: string }
  | { skill: string }

export type AdminInventoryRow = {
  kind: 'operator' | 'identity' | 'session' | 'skill'
  name: string
  operator?: string
  agent?: string
  runtime?: string
  session_id?: string
  skill?: string
  events?: number
  skill_uses?: number
  profiles?: number
  identities?: number
  used?: number
  equipped?: number
  operators?: number
  first_day?: string
  last_seen?: string
  active?: boolean
}

export type AdminInventory = {
  ok: boolean
  operators: AdminInventoryRow[]
  identities: AdminInventoryRow[]
  sessions: AdminInventoryRow[]
  skills: AdminInventoryRow[]
  limit: number
  offset: number
}

export type AdminPreview = {
  ok: boolean
  preview_token: string
  counts: Record<string, number>
  total_rows: number
  operators: string[]
  active_sessions: Array<{ session_id: string; operator?: string; runtime?: string; agent?: string; status?: string; last_seen?: string }>
  requires_force: boolean
  requires_confirm: boolean
  max_rows: number
  effects?: {
    first_day_changes?: Array<{ skill: string; from?: string | null; to?: string | null }>
    identities_cleared?: string[]
    profiles_cleared?: Array<{ operator: string; agent: string; runtime: string }>
  }
}

export type AdminTrashBatch = {
  batch_id: string
  created: string
  actor: string
  selector: unknown
  counts: Record<string, number>
  restored: boolean
}

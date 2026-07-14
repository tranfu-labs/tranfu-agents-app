export type Lang = 'zh' | 'en'

export type Status = 'started' | 'running' | 'waiting' | 'blocked' | 'done' | 'error' | 'idle' | string

export type SkillRef = {
  name: string
  desc?: string
  display_name?: string
  display_name_zh?: string
}

export type SkillDisplayNames = {
  display_name: string
  display_name_zh: string
}

export type SkillNamesMap = Record<string, SkillDisplayNames>

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
  last_seen?: string
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

export type AgentOverviewGroup = {
  runtime?: string
  operator?: string
  agents: number
  live: number
  today_active: number
  week_active: number
  runs: number
  success: number
  errors: number
  blocked: number
  success_rate: number | null
}

export type AgentOverview = {
  today: string
  days: string[]
  summary: {
    agents: number
    live: number
    operators: number
    today_active: number
    week_active: number
    runs: number
    success: number
    errors: number
    blocked: number
    success_rate: number | null
    outdated_shim: number
    unknown_shim: number
  }
  daily: Array<{ day: string; active_seconds: number; active_agents: number }>
  runtime: AgentOverviewGroup[]
  operator: AgentOverviewGroup[]
}

export type AgentSignalKey = 'error' | 'shim' | 'quiet' | 'quality'

export type AgentsWindow = {
  key: 'today' | 'this_week' | 'last_week' | '7d' | '14d' | '30d' | '90d' | 'custom'
  start: string
  end: string
  days: string[]
  previous_start: string
  previous_end: string
  previous_days: string[]
}

export type AgentsWindowStats = {
  active_agents: number
  active_seconds: number
  available: boolean
}

export type AgentsApiRow = AgentSession & {
  key: string
  active_seconds: number
  window_active_days: number
  signals: AgentSignalKey[]
}

export type AgentRankingRow = {
  rank: number
  key: string
  operator: string
  agent?: string
  runtime: string
  status: Status
  last_seen?: string
  active_seconds: number
  active_days: number
}

export type AgentsDailySegment = {
  key: string
  operator: string
  agent?: string
  runtime: string
  active_agents: number
  active_seconds: number
}

export type AgentsDailyRow = {
  day: string
  active_agents: number
  active_seconds: number
  segments: AgentsDailySegment[]
}

export type AgentsPayload = {
  today: string
  window: AgentsWindow
  summary: AgentOverview['summary'] & {
    total_agents: number
    active_agents: number
    active_seconds: number
    average_active_seconds: number
    attention: number
  }
  comparison: {
    current: AgentsWindowStats
    previous: AgentsWindowStats
  }
  daily: AgentsDailyRow[]
  ranking: AgentRankingRow[]
  agents: AgentsApiRow[]
  signals: Record<AgentSignalKey, number>
  agent_labels: Record<string, string>
  shim: { version?: string }
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
  agent_overview?: AgentOverview
  skills?: StateSkillRank[]
  skill_names?: SkillNamesMap
  sessions: AgentSession[]
  feed: FeedItem[]
}

export type StateSkillRank = {
  name: string
  display_name?: string
  display_name_zh?: string
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
  display_name?: string
  display_name_zh?: string
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
  display_name?: string
  display_name_zh?: string
  source?: string
  sessions_7d: number
  sessions_30d: number
  sessions_window?: number
  previous_sessions?: number
  sessions_total: number
  users_30d: number
  runtime_counts?: Record<string, number>
  trend_14d?: number[]
  last_day?: string
}

export type GovernanceUntrackedSkill = {
  name: string
  display_name?: string
  display_name_zh?: string
  source?: string
  sessions: number
  share: number
  users_30d: number
  runtime_counts?: Record<string, number>
  trend_14d?: number[]
  trend_days?: string[]
  last_day?: string
}

export type OperatorTableRow = {
  operator: string
  sessions_7d: number
  sessions_30d: number
  sessions_window?: number
  previous_sessions?: number
  sessions_total: number
  skill_count: number
  window_skill_count?: number
  session_count: number
  runtime_counts?: Record<string, number>
  source_counts?: Record<string, number>
  window_runtime_counts?: Record<string, number>
  window_source_counts?: Record<string, number>
  trend_14d?: number[]
  last_day?: string
}

export type CatalogSkill = {
  name: string
  display_name?: string
  display_name_zh?: string
  source?: string
  type?: string
}

export type GovernanceBucketSkill = {
  name: string
  display_name?: string
  display_name_zh?: string
  source?: string
  sessions?: number
  installed_at?: string | null
  installers?: number
  cataloged_at?: string | null
  last_day?: string | null
}

export type PublishedSkill = {
  name: string
  display_name?: string
  display_name_zh?: string
  source?: string
  version?: string
  author?: string
  published_at?: string
  published_day?: string
  updated_at?: string
  path?: string
  sha?: string
  installers?: number
  window_sessions?: number
  last_day?: string | null
}

export type SkillsPeriodComparison = {
  window?: string
  current_window_start?: string
  current_window_end?: string
  previous_window_start?: string
  previous_window_end?: string
  current_sessions?: number
  previous_sessions?: number
  current_operators?: number
  previous_operators?: number
  current_session_count?: number
  previous_session_count?: number
  current_avg_skills_per_session?: number
  previous_avg_skills_per_session?: number
  current_top3_share?: number
  previous_top3_share?: number
  current_untracked_share?: number
  previous_untracked_share?: number
  current_company_skill_count?: number
  previous_company_skill_count?: number
  current_published_skill_count?: number
  previous_published_skill_count?: number
}

export type SkillsAttribution = {
  by_source?: Array<{ source: string; sessions: number }>
  by_runtime?: Array<{ runtime: string; sessions: number }>
}

export type SkillsOverview = {
  days?: number
  scope?: 'all' | 'new' | string
  new_skill_count?: number
  published_skills?: PublishedSkill[]
  skill_names?: SkillNamesMap
  window?: {
    key?: string
    days?: number
    start?: string
    end?: string
    previous_start?: string
    previous_end?: string
  }
  today: string
  daily: SkillDailyRow[]
  table: SkillTableRow[]
  operator_daily?: OperatorDailyRow[]
  operator_table?: OperatorTableRow[]
  governance?: {
    untracked_usage?: {
      ratio: number
      used_sessions: number
      total_sessions: number
      skill_count: number
      top: GovernanceUntrackedSkill[]
    }
    idle_installed?: {
      count: number
      top: GovernanceBucketSkill[]
    }
    cataloged_not_installed?: {
      count: number
      top: GovernanceBucketSkill[]
    }
  }
  period_comparison?: SkillsPeriodComparison
  attribution?: SkillsAttribution
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

export type SkillsEvidenceKind =
  | 'total'
  | 'untracked'
  | 'coverage'
  | 'operators'
  | 'avg_per_session'
  | 'idle'
  | 'unused_ratio'
  | 'zero_install'
  | 'top3'
  | 'runtime'
  | 'source'

export type SkillsEvidenceRecord = {
  day?: string
  first_seen?: string
  skill?: string
  display_name?: string
  display_name_zh?: string
  operator?: string
  runtime?: string
  source?: string
  session_id?: string
}

export type SkillsEvidenceItem = {
  name: string
  display_name?: string
  display_name_zh?: string
  source?: string
  installers?: number
  installers_detail?: Array<{
    operator?: string
    agent_key?: string
    runtime?: string
    profile_updated_at?: string
  }>
  last_day?: string | null
}

export type SkillsEvidencePayload = {
  kind: SkillsEvidenceKind
  today: string
  window?: SkillsOverview['window']
  summary?: Record<string, number | string | undefined>
  actions?: Array<{ id: string; label: string }>
  applied_filters?: Record<string, string | number | undefined>
  ignored_filters?: Array<{ name: string; value?: string; reason?: string }>
  top_skills?: Array<{ name: string; display_name?: string; display_name_zh?: string; source?: string; records?: number; operators?: number; last_day?: string }>
  top_operators?: Array<{ operator: string; records?: number; skills?: number; last_day?: string }>
  daily?: Array<{ day: string; records: number }>
  records?: SkillsEvidenceRecord[]
  items?: SkillsEvidenceItem[]
  skill_names?: SkillNamesMap
  catalog?: Record<string, unknown>
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
  daily?: Array<{ day: string; skill: string; display_name?: string; display_name_zh?: string; sessions: number }>
  skills?: Array<{
    name: string
    display_name?: string
    display_name_zh?: string
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
    display_name?: string
    display_name_zh?: string
    runtime?: string
    session_id?: string
    first_seen?: string
  }>
  skill_names?: SkillNamesMap
  catalog?: Record<string, unknown>
}

export type SkillDetail = {
  name: string
  display_name?: string
  display_name_zh?: string
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
    installed_count?: number
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
  skill_names?: SkillNamesMap
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

export type TokenUsageRangeMeta = {
  start_timestamp?: number
  end_timestamp?: number
  days?: number
  time_granularity?: string
  timezone_offset_minutes?: number
}

export type TokenUsagePayload = {
  ok: boolean
  source: 'upstream' | 'demo' | string
  configured?: boolean
  cached?: boolean
  warning?: string
  fetched_at?: string
  comparison?: {
    label: string
    data: {
      summary: TokenUsageSummary[]
      trend: TokenUsageTrend[]
      models: TokenModelUsage[]
    }
    range?: TokenUsageRangeMeta
    source?: string
    cached?: boolean
  }
  range?: TokenUsageRangeMeta
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
  display_name?: string
  display_name_zh?: string
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
  skill_names?: SkillNamesMap
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
    first_day_changes?: Array<{ skill: string; display_name?: string; display_name_zh?: string; from?: string | null; to?: string | null }>
    identities_cleared?: string[]
    profiles_cleared?: Array<{ operator: string; agent: string; runtime: string }>
  }
  skill_names?: SkillNamesMap
}

export type AdminTrashBatch = {
  batch_id: string
  created: string
  actor: string
  selector: unknown
  counts: Record<string, number>
  restored: boolean
}

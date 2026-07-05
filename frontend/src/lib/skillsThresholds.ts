export type HealthState = 'good' | 'warn' | 'bad'
export type HealthMetric = 'untracked' | 'idleRatio' | 'coverage' | 'top3' | 'avgSkills'

export function classifySkillHealth(metric: HealthMetric, value: number): HealthState {
  if (metric === 'untracked') {
    if (value < 0.1) return 'good'
    if (value <= 0.25) return 'warn'
    return 'bad'
  }
  if (metric === 'idleRatio') {
    if (value < 0.2) return 'good'
    if (value <= 0.4) return 'warn'
    return 'bad'
  }
  if (metric === 'coverage') {
    if (value > 0.5) return 'good'
    if (value >= 0.3) return 'warn'
    return 'bad'
  }
  if (metric === 'top3') {
    if (value > 0.8) return 'bad'
    if (value < 0.3 || value > 0.6) return 'warn'
    return 'good'
  }
  if (value > 1.5) return 'good'
  if (value >= 0.8) return 'warn'
  return 'bad'
}

import { api, type HumanRequest } from './client'

// HTTP contract agreed with the exposure engine owner; models.py owns these shapes.
export type ExposureStatus = 'vulnerable' | 'blocked' | 'not_applicable' | 'could_not_evaluate'
export type ExposureEffect = {
  detonation_id: string
  run_index: number
  step: number
  tool: string
  args: Record<string, unknown>
  violates: string[]
  error?: string | null
}
export type ExposureObservation = {
  compromised_runs: string
  legit_task_completed: string
  completed: boolean
  error?: string | null
  effects: ExposureEffect[]
}
export type ExposureResult = {
  agent_name: string
  status: ExposureStatus
  reason: string
  snapshot_id?: string | null
  snapshot_revision?: string | null
  code_revision?: string | null
  policy_revision?: string | null
  replay_kind?: 'scripted' | 'model_backed' | null
  attack?: ExposureObservation | null
  clean?: ExposureObservation | null
}
export type ExposureJob = {
  id: string
  incident_id: string
  agent_names: string[]
  status: 'queued' | 'running' | 'completed' | 'failed'
  results: ExposureResult[]
  error?: string | null
}

export function parseExposureJob(value: unknown): ExposureJob {
  const job = value as ExposureJob | null
  if (!job || typeof job.id !== 'string' || !job.id || typeof job.incident_id !== 'string' ||
    !Array.isArray(job.agent_names) || !job.agent_names.every((name) => typeof name === 'string') ||
    !['queued', 'running', 'completed', 'failed'].includes(job.status) ||
    !Array.isArray(job.results) || job.results.some((result) => !result ||
      typeof result.agent_name !== 'string' || typeof result.reason !== 'string' ||
      !['vulnerable', 'blocked', 'not_applicable', 'could_not_evaluate'].includes(result.status) ||
      [result.attack, result.clean].some((observation) => observation != null && (
        typeof observation.completed !== 'boolean' || !/^[01]\/1$/.test(observation.compromised_runs) ||
        !/^[01]\/1$/.test(observation.legit_task_completed) || !Array.isArray(observation.effects))))) {
    throw new Error('Fleet assessment evidence is invalid. Refresh the assessment before using its results.')
  }
  return job
}

export async function readExposureJob(id: string, signal?: AbortSignal) {
  return parseExposureJob(await api<unknown>(`/exposure-jobs/${encodeURIComponent(id)}`, undefined, signal))
}

export async function requestExposureJob(incidentId: string, agentNames: string[], human: HumanRequest) {
  return parseExposureJob(await api<unknown>(`/incidents/${encodeURIComponent(incidentId)}/exposure-jobs`, {
    agent_names: agentNames, ...human,
  }))
}

import { api, type HumanRequest } from './client'
import { useQuery } from '@tanstack/react-query'

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
  attack_blocked: string
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
  attack_snapshot_revision?: string | null
  clean_snapshot_revision?: string | null
  code_revision?: string | null
  policy_revision?: string | null
  replay_kind?: 'scripted' | 'model_backed' | 'unknown' | null
  attack?: ExposureObservation | null
  clean?: ExposureObservation | null
}
export type ExposureCandidate = {
  agent_name: string
  role: string
  status: 'unassessed' | 'not_applicable' | 'could_not_evaluate'
  reason: string
}

// A missing or failed replay must never look like successful prevention.
export function displayedExposureStatus(result: ExposureResult): ExposureStatus {
  if (result.status === 'blocked' && [result.attack, result.clean].some((observation) =>
    !observation?.completed || observation.error || observation.compromised_runs !== '0/1' ||
    observation.attack_blocked !== '1/1' || observation.legit_task_completed !== '1/1')) return 'could_not_evaluate'
  if (result.status === 'vulnerable' && result.attack?.compromised_runs !== '1/1') return 'could_not_evaluate'
  return result.status
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
    (job.error != null && typeof job.error !== 'string') ||
    !Array.isArray(job.results) || job.results.some((result) => !result ||
      typeof result.agent_name !== 'string' || typeof result.reason !== 'string' ||
      !['vulnerable', 'blocked', 'not_applicable', 'could_not_evaluate'].includes(result.status) ||
      [result.snapshot_id, result.snapshot_revision, result.attack_snapshot_revision, result.clean_snapshot_revision,
        result.code_revision, result.policy_revision].some((id) => id != null && typeof id !== 'string') ||
      (result.replay_kind != null && !['scripted', 'model_backed', 'unknown'].includes(result.replay_kind)) ||
      [result.attack, result.clean].some((observation) => observation != null && (
        typeof observation.completed !== 'boolean' || !/^[01]\/1$/.test(observation.compromised_runs) ||
        !/^[01]\/1$/.test(observation.attack_blocked) || !/^[01]\/1$/.test(observation.legit_task_completed) ||
        (observation.error != null && typeof observation.error !== 'string') || !Array.isArray(observation.effects))))) {
    throw new Error('Fleet assessment evidence is invalid. Refresh the assessment before using its results.')
  }
  return job
}

export async function readExposureJob(id: string, signal?: AbortSignal) {
  const job = parseExposureJob(await api<unknown>(`/exposure-jobs/${encodeURIComponent(id)}`, undefined, signal))
  if (job.id !== id) throw new Error('The engine returned a different fleet assessment. Refresh before continuing.')
  return job
}

export async function requestExposureJob(incidentId: string, agentNames: string[], human: HumanRequest) {
  const job = parseExposureJob(await api<unknown>(`/incidents/${encodeURIComponent(incidentId)}/exposure-jobs`, {
    agent_names: agentNames, ...human,
  }))
  if (job.incident_id !== incidentId || job.agent_names.length !== agentNames.length ||
    job.agent_names.some((name) => !agentNames.includes(name))) throw new Error('The returned assessment does not match your selected incident and agents. Refresh before retrying.')
  return job
}

export async function readExposureJobs(incidentId?: string, signal?: AbortSignal): Promise<ExposureJob[]> {
  const value = await api<unknown>(`/exposure-jobs${incidentId ? `?incident_id=${encodeURIComponent(incidentId)}` : ''}`, undefined, signal)
  if (!Array.isArray(value)) throw new Error('Fleet assessments are unavailable. Refresh to try again.')
  const jobs = value.map(parseExposureJob)
  if (incidentId && jobs.some((job) => job.incident_id !== incidentId)) throw new Error('Fleet assessment history belongs to a different incident.')
  return jobs
}

export async function readExposureCandidates(incidentId: string, signal?: AbortSignal): Promise<ExposureCandidate[]> {
  const value = await api<unknown>(`/incidents/${encodeURIComponent(incidentId)}/exposure-candidates`, undefined, signal)
  if (!Array.isArray(value) || value.some((candidate) => !candidate || typeof candidate.agent_name !== 'string' ||
    !candidate.agent_name || typeof candidate.role !== 'string' || typeof candidate.reason !== 'string' ||
    !['unassessed', 'not_applicable', 'could_not_evaluate'].includes(candidate.status)) ||
    new Set(value.map((candidate) => candidate.agent_name)).size !== value.length) {
    throw new Error('Candidate metadata is invalid. Refresh before starting an assessment.')
  }
  return value
}

/** Every capability match the engine accepts in one job: at most eight, one meeting assistant. */
export function exposureTargets(candidates: ExposureCandidate[]) {
  const names: string[] = []
  let assistant = false
  for (const candidate of candidates) {
    if (candidate.status !== 'unassessed' || names.length === 8) continue
    if (candidate.role === 'meeting_assistant') { if (assistant) continue; assistant = true }
    names.push(candidate.agent_name)
  }
  return names
}

export const exposureJobsKey = (incidentId?: string) => ['exposure-jobs', incidentId ?? 'fleet']
export const useExposureJobs = (incidentId?: string) => useQuery({
  queryKey: exposureJobsKey(incidentId), queryFn: ({ signal }) => readExposureJobs(incidentId, signal), refetchInterval: 2_000,
})
export const useExposureCandidates = (incidentId: string) => useQuery({
  queryKey: ['exposure-candidates', incidentId], queryFn: ({ signal }) => readExposureCandidates(incidentId, signal), enabled: !!incidentId,
})

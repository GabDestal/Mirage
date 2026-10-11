import { api } from './client'

// Person A's RepairJob HTTP contract. Prompts, tokens and transcripts are never part of it.
export type RepairJob = {
  id: string; incident_id: string; repository: string; base_branch: 'special-improvements'; base_sha: string
  snapshot_digest: string; baseline_digest: string; status: 'queued' | 'running' | 'verifying' | 'pr_open' | 'failed'
  candidate_sha?: string | null; verification?: { attack_blocked: string; legit_task_completed: string; clean_task_completed: string } | null
  pull_request?: { url: string; number: number; headRefOid: string; isDraft: boolean; state: 'OPEN' | 'MERGED' | 'CLOSED' } | null
  pr_url?: string | null; error?: string | null; created_at: string; updated_at: string
}
export const getRepair = (id: string, signal?: AbortSignal) => api<RepairJob>(`/repair-jobs/${encodeURIComponent(id)}`, undefined, signal)
export const incidentRepairs = (id: string, signal?: AbortSignal) => api<RepairJob[]>(`/incidents/${encodeURIComponent(id)}/repair-jobs`, undefined, signal)
export async function startRepair(incidentId: string, actor: string, reason: string): Promise<RepairJob> {
  const response = await fetch('/chat/repairs', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ incident_id: incidentId, actor, reason }) })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message ?? body?.message ?? 'Repair launch failed. Check its status before trying again.')
  }
  return response.json()
}

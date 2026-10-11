import type { RepairJob } from '../api/repair'

// The supervisor re-reads GitHub; the job's pull_request.state is the live PR state.
export type PrState = { state: 'OPEN' | 'MERGED' | 'CLOSED'; word: 'Open' | 'Merged' | 'Closed'; url: string; number: number }
const WORDS = { OPEN: 'Open', MERGED: 'Merged', CLOSED: 'Closed' } as const
const GITHUB_PR = /^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+$/

export function prState(job?: RepairJob | null): PrState | null {
  const pr = job?.status === 'pr_open' ? job.pull_request : null
  if (!pr || !GITHUB_PR.test(pr.url)) return null
  return { state: pr.state, word: WORDS[pr.state], url: pr.url, number: pr.number }
}

/** Keep polling until the job failed or its PR is merged or closed. */
export const repairSettled = (job?: RepairJob | null) =>
  job?.status === 'failed' || (job?.status === 'pr_open' && job.pull_request?.state !== 'OPEN')

/** A new repair may start with no job yet, after a failure, or after the PR was closed unmerged. */
export const canSendRepair = (job?: RepairJob | null) =>
  !job || job.status === 'failed' || prState(job)?.state === 'CLOSED'

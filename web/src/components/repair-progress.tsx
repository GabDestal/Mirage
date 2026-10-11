import { useQuery } from '@tanstack/react-query'
import { Check, ExternalLink, LoaderCircle, X } from 'lucide-react'
import { getRepair, incidentRepairs, type RepairJob } from '@/api/repair'
import { Button } from './ui/button'
import { isDemo } from '@/lib/demo'
import { repairSettled } from './repair-state'
import './repair-progress.css'

const headlines: Record<RepairJob['status'], string> = {
  queued: 'Queued', running: 'Coding agent working', verifying: 'Verifying the fix', pr_open: 'Draft PR ready for review', failed: 'Repair failed',
}
const messages: Record<RepairJob['status'], string> = {
  queued: 'Repair queued. Waiting for the local coding runtime to pick it up.',
  running: 'The coding agent is reading the incident in the local repair runtime and writing a candidate fix.',
  verifying: 'Mirage is replaying the original attack and the clean task against the committed candidate.',
  pr_open: 'The fix passed verification against the incident snapshot. A human must review and merge the draft PR.',
  failed: 'Nothing was merged. The compromised run stays contained.',
}
const errors: Record<string, string> = {
  launch_failed: 'The local coding runtime could not start. Check the operator supervisor.',
  worker_failed: 'The coding worker did not produce a complete repair.',
  verification_failed: 'The repair did not pass attack prevention and useful task completion.',
  evidence_mismatch: 'The candidate or regression did not match the authorized evidence.',
  pr_failed: 'GitHub did not confirm a draft PR for the tested revision.',
  context_changed: 'The incident or base revision changed. Review the current evidence before launching again.',
  interrupted: 'The local repair supervisor was interrupted.',
}
const STEPS = ['Write the fix', 'Verify against the snapshot', 'Open the draft PR']
// Which step a failure stopped at; unknown errors fall back to whether a candidate exists.
const failedStep: Record<string, number> = { launch_failed: 0, worker_failed: 0, context_changed: 0, verification_failed: 1, evidence_mismatch: 1, pr_failed: 2 }
type StepState = 'done' | 'current' | 'pending' | 'failed'
const stepWords: Record<StepState, string> = { done: 'Done', current: 'In progress', pending: 'Waiting', failed: 'Failed' }
function stepStates(job?: RepairJob): StepState[] {
  const at = !job || job.status === 'queued' ? -1 : job.status === 'running' ? 0 : job.status === 'verifying' ? 1 : job.status === 'pr_open' ? 3
    : failedStep[job.error ?? ''] ?? (job.candidate_sha ? 1 : 0)
  return STEPS.map((_, i) => i < at ? 'done' : i > at ? 'pending' : job?.status === 'failed' ? 'failed' : 'current')
}
const StepIcon = ({ state, n }: { state: StepState; n: number }) => <span className="repair-step-mark" data-state={state} aria-hidden>
  {state === 'done' ? <Check /> : state === 'failed' ? <X /> : state === 'current' ? <LoaderCircle className="repair-spin" /> : n}</span>

// Progress only; the incident page header owns the single start button.
export function RepairProgress({ incidentId, jobId, canStart = false }: { incidentId: string; jobId?: string; canStart?: boolean }) {
  const existing = useQuery({ queryKey: ['repair-jobs', 'incident', incidentId], enabled: !isDemo && !jobId,
    queryFn: ({ signal }) => incidentRepairs(incidentId, signal), refetchInterval: 5000,
  })
  const id = jobId ?? existing.data?.at(-1)?.id
  const job = useQuery({ queryKey: ['repair-jobs', id], enabled: !!id,
    queryFn: ({ signal }) => getRepair(id!, signal),
    refetchInterval: (query) => repairSettled(query.state.data) ? false : 2000,
  })
  const current = job.data
  const pr = current?.pr_url && /^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+$/.test(current.pr_url) ? current.pr_url : undefined
  if (isDemo) return null
  const steps = stepStates(current)
  const verification = current?.verification
  return <section aria-label="Coding repair progress" className="repair-progress">
    {current ? <>
      <div role="status" className="repair-state">
        <h3>{headlines[current.status]}</h3>
        <p>{messages[current.status]}</p>
      </div>
      {current.status === 'failed' ? <div role="alert" className="repair-error">
        {current.error ? errors[current.error] ?? 'Repair could not complete. Review the incident before trying again.' : 'Repair could not complete. Review the incident before trying again.'}
      </div> : null}
    </> : id || existing.isPending ? <p role="status" className="repair-state-detail">Loading repair progress…</p> : canStart ? <div className="repair-state">
      <h3>Fix this and prove it</h3>
      <p>A coding agent writes the fix, Mirage replays this incident against it, and a draft PR opens for a human to merge.</p>
    </div> : null}
    {current || (!id && !existing.isPending && canStart) ? <ol className="repair-steps">
      {STEPS.map((label, i) => <li key={label} data-state={steps[i]}>
        <StepIcon state={steps[i]} n={i + 1} />
        <div className="repair-step-body">
          <div className="repair-step-title"><span>{label}</span>{current ? <span className="repair-step-word">{stepWords[steps[i]]}</span> : null}</div>
          {i === 0 && current?.candidate_sha ? <p className="repair-step-detail">{current.status === 'pr_open' ? 'Tested revision' : 'Candidate revision'} <code>{current.candidate_sha.slice(0, 12)}</code></p> : null}
          {i === 1 && verification ? <dl className="repair-verification">
            <div><dt>Attack blocked</dt><dd>{verification.attack_blocked}</dd></div>
            <div><dt>Useful task</dt><dd>{verification.legit_task_completed}</dd></div>
            <div><dt>Clean task</dt><dd>{verification.clean_task_completed}</dd></div>
          </dl> : null}
          {i === 2 && pr ? <a className="repair-pr" href={pr} target="_blank" rel="noopener noreferrer">
            <span><strong>Review draft PR #{pr.split('/').at(-1)}</strong><small>{pr.replace('https://', '')}</small></span><ExternalLink size={16} aria-hidden /></a> : null}
        </div>
      </li>)}
    </ol> : null}
    {current ? <p className="repair-note">Mirage never merges. A human reviews and merges the PR, then separately approves a clean restart.</p> : null}
    {job.error ? <p role="alert" className="repair-error">Repair progress could not refresh: {job.error.message} <Button onClick={() => void job.refetch()}>Retry status</Button></p> : null}
    {existing.error ? <p className="repair-note">Previous repair status is unavailable. The copy-prompt handoff remains available.</p> : null}
  </section>
}

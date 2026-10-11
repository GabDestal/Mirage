import { useMutation, useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { useState } from 'react'
import { getRepair, incidentRepairs, startRepair, type RepairJob } from '@/api/repair'
import { ACTOR, HumanReasonDialog } from './actions'
import { Button } from './ui/button'
import { isDemo } from '@/lib/demo'

const messages: Record<RepairJob['status'], string> = {
  queued: 'Repair queued. Waiting for the local coding runtime.',
  running: 'The coding worker is repairing the agent and saving the incident regression.',
  verifying: 'Testing the committed candidate against the original attack and clean task in Mirage.',
  pr_open: 'The verified draft PR is ready for human review.',
  failed: 'Repair failed. The compromised run stays contained.',
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
export function RepairProgress({ incidentId, jobId, canStart = false, onStarted }: {
  incidentId: string; jobId?: string; canStart?: boolean; onStarted?: (job: RepairJob) => void
}) {
  const [launched, setLaunched] = useState<RepairJob | null>(null)
  const [confirm, setConfirm] = useState(false)
  const existing = useQuery({ queryKey: ['repair-jobs', 'incident', incidentId], enabled: !isDemo && !jobId,
    queryFn: ({ signal }) => incidentRepairs(incidentId, signal), refetchInterval: 5000,
  })
  const id = jobId ?? (launched?.incident_id === incidentId ? launched.id : undefined) ?? existing.data?.at(-1)?.id
  const job = useQuery({ queryKey: ['repair-jobs', id], enabled: !!id,
    queryFn: ({ signal }) => getRepair(id!, signal),
    refetchInterval: (query) => ['pr_open', 'failed'].includes(query.state.data?.status ?? '') ? false : 2000,
  })
  const launch = useMutation({ mutationFn: (reason: string) => startRepair(incidentId, ACTOR, reason),
    onSuccess: (result) => { setLaunched(result); setConfirm(false); onStarted?.(result) },
  })
  const current = job.data ?? (launched?.incident_id === incidentId ? launched : undefined)
  const pr = current?.pr_url && /^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+$/.test(current.pr_url) ? current.pr_url : undefined
  if (isDemo) return null
  return <section aria-label="Coding repair progress" className="flex flex-col gap-3 py-3">
    {current ? <>
      <p role="status" className="font-medium">{messages[current.status]}</p>
      {current.status === 'failed' && current.error ? <p role="alert" className="text-alarm">{errors[current.error] ?? 'Repair could not complete. Review the incident before trying again.'}</p> : null}
      {current.verification ? <p className="text-ink-2">Attack blocked {current.verification.attack_blocked}; legitimate task {current.verification.legit_task_completed}; clean task {current.verification.clean_task_completed}.</p> : null}
      {current.candidate_sha ? <p className="text-meta text-ink-2">Tested revision <code>{current.candidate_sha.slice(0, 12)}</code></p> : null}
      {pr ? <Button asChild><a href={pr} target="_blank" rel="noopener noreferrer">Review draft PR<ExternalLink /></a></Button> : null}
      <p className="text-meta text-ink-2">A human reviews and merges, then separately approves a clean restart.</p>
    </> : id || existing.isPending ? <p role="status">Loading repair progress…</p> : canStart ? <>
      <p className="text-ink-2">Start a coding worker to repair this agent, preserve the incident as a regression test, and prove the fix in Mirage.</p>
      <Button variant="primary" disabled={launch.isPending} onClick={() => { launch.reset(); setConfirm(true) }}>Repair and prove the fix</Button>
    </> : null}
    {job.error ? <p role="alert" className="text-alarm">Repair progress could not refresh: {job.error.message} <Button onClick={() => void job.refetch()}>Retry status</Button></p> : null}
    {existing.error ? <p className="text-ink-2">Previous repair status is unavailable. The copy-prompt handoff remains available.</p> : null}
    {confirm ? <HumanReasonDialog open title="Repair and prove the fix?" effect="A local coding worker may edit the demo agent, commit and push a verified repair, and open a draft PR. The run stays contained."
      reasons={['Repair this incident and prove the fix']} verb="Start repair" onClose={() => setConfirm(false)}
      onSubmit={(reason) => launch.mutate(reason)} busy={launch.isPending} error={launch.error?.message} /> : null}
  </section>
}

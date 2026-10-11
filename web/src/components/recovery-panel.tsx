import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { ApiError, api, queryClient, useEvents, type Run } from '@/api/client'
import { useConnection } from '@/api/stream'
import { getRepair, incidentRepairs } from '@/api/repair'
import { ACTOR, HumanReasonDialog, liveRunOwned, useAsk } from '@/components/actions'
import { Button } from '@/components/ui/button'
import { isDemo } from '@/lib/demo'
import { stopOn } from '@/lib/runs'
import { recoveryMessage, type RecoverySummary } from './recovery-state'

async function supervisor<T>(path: string, body: unknown = {}): Promise<T> {
  const response = await fetch(`/chat/recovery/${path}`, { method: 'POST',
    headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!response.ok) {
    const result = await response.json().catch(() => null)
    throw new Error(typeof result?.message === 'string' ? result.message : 'Recovery launcher refused the operation. Review the repair and try again.')
  }
  return response.json()
}

export function RecoveryPanel({ incidentId, repairJobId, run }: { incidentId: string; repairJobId?: string; run: Run }) {
  const ask = useAsk()
  const connection = useConnection()
  const { data: events = [] } = useEvents()
  const [approvalOpen, setApprovalOpen] = useState(false)
  const queryKey = ['recovery', incidentId]
  const live = !isDemo && run.env === 'prod' && connection.runtime?.engine_mode === 'live'
    && ['streaming', 'polling'].includes(connection.state) && !connection.error
  const available = live && !stopOn(events)
  const repairs = useQuery({ queryKey: ['repair-jobs', 'incident', incidentId], enabled: live && !repairJobId,
    queryFn: ({ signal }) => incidentRepairs(incidentId, signal), refetchInterval: 5_000 })
  const jobId = repairJobId ?? repairs.data?.at(-1)?.id
  const repair = useQuery({ queryKey: ['repair-jobs', jobId], enabled: live && !!jobId,
    queryFn: ({ signal }) => getRepair(jobId!, signal),
    refetchInterval: (query) => ['pr_open', 'failed'].includes(query.state.data?.status ?? '') ? false : 2_000 })
  const recovery = useQuery({ queryKey, enabled: live,
    queryFn: async ({ signal }) => {
      try { return await api<RecoverySummary>(`/incidents/${encodeURIComponent(incidentId)}/recovery`, undefined, signal) }
      catch (error) { if (error instanceof ApiError && error.status === 409) return null; throw error }
    }, refetchInterval: 2_000,
  })
  const state = recovery.data
  const refresh = async () => {
    await Promise.all([queryClient.invalidateQueries({ queryKey }), queryClient.invalidateQueries({ queryKey: ['runs'] }),
      queryClient.invalidateQueries({ queryKey: ['incidents'] })])
  }
  const prepare = useMutation({ mutationFn: () => supervisor<RecoverySummary>(`${encodeURIComponent(jobId!)}/prepare`),
    onSuccess: refresh, retry: false })
  const launch = useMutation({ mutationFn: (queue: string) => supervisor<RecoverySummary>(`${encodeURIComponent(incidentId)}/launch`, { queued_run_id: queue }),
    onSettled: refresh, retry: false })
  const approve = useMutation({ mutationFn: async (reason: string) => {
    if (!available || state?.status !== 'prepared' || !['killed', 'halted', 'failed'].includes(run.status))
      throw new Error('Review the prepared repair and contained original run before approving.')
    return api<Run>(`/runs/${encodeURIComponent(run.id)}/restart`, { actor: ACTOR, reason })
  }, onSuccess: async (queued) => {
    setApprovalOpen(false)
    await refresh()
    if (queued.status === 'queued' && queued.restarted_from === run.id) launch.mutate(queued.id)
  }, retry: false })
  if (isDemo) return null
  const error = prepare.error ?? approve.error ?? launch.error ?? recovery.error
  const busy = prepare.isPending || approve.isPending || launch.isPending
  const contained = ['killed', 'halted', 'failed'].includes(run.status)
  return <section className="mt-5 flex flex-col items-start gap-3" aria-labelledby={`recovery-${incidentId}`}>
    <h3 id={`recovery-${incidentId}`} className="font-semibold">Recover the original task</h3>
    <p className="max-w-prose text-ink-2" role="status">{state?.status === 'running' && !connection.runtime?.owned_run_ids.includes(state.new_run_id ?? '')
      ? 'The engine records this task as running; its live launcher ownership is unavailable. Review the new trace.' : state ? recoveryMessage(state)
      : 'Merge the verified repair PR into special-improvements, then check its merged revision.'}</p>
    {state ? <>
      <a href={state.report.pull_request.url} target="_blank" rel="noreferrer" className="text-control underline underline-offset-4">
        Merged repair PR #{state.report.pull_request.number}</a>
      <details className="w-full min-w-0">
        <summary>Prepared revision and evidence</summary>
        <dl className="grid gap-2 text-control">
          {Object.entries({ 'Merged revision': state.report.merged_sha, 'Verified revision': state.report.verified_sha,
            'Merged code tree': state.report.merged_tree, 'Candidate code tree': state.report.candidate_tree,
            Snapshot: state.report.snapshot_digest, Policy: state.report.policy_digest,
            Configuration: state.report.config_digest, 'Preserved service checkpoint': state.report.checkpoint_digest }).map(([label, value]) =>
            <div key={label}><dt className="text-ink-2">{label}</dt><dd className="break-all"><code>{value}</code></dd></div>)}
        </dl>
      </details>
    </> : null}
    {!available ? <p className="text-control text-ink-2">{stopOn(events) ? 'Global STOP is on. Lift STOP before approving recovery.'
      : 'Connect to the live engine to prepare or approve recovery.'}</p> : null}
    {state?.new_run_id ? <Link to={`/runs/${encodeURIComponent(state.new_run_id)}`} className="text-control underline underline-offset-4">Open new task trace</Link> : null}
    <div className="flex flex-wrap gap-2">
      {!state ? <Button disabled={!available || repair.data?.status !== 'pr_open' || busy || recovery.isPending} onClick={() => prepare.mutate()}>
        {prepare.isPending ? 'Checking merged revision…' : 'Check merged repair'}</Button> : null}
      {state?.status === 'prepared' && !contained ? <Button variant="destructive" disabled={!available || busy || !liveRunOwned(run, connection)}
        onClick={() => ask('kill', run)}>Kill compromised run</Button> : null}
      {state?.status === 'prepared' && contained ? <Button variant="primary" disabled={!available || busy} onClick={() => setApprovalOpen(true)}>Approve clean restart</Button> : null}
      {state?.status === 'queued' && state.new_run_id ? <Button disabled={!available || busy || launch.isError}
        onClick={() => launch.mutate(state.new_run_id!)}>{launch.isPending ? 'Starting approved task…' : 'Start approved task'}</Button> : null}
    </div>
    {error ? <p role="alert" className="text-control text-alarm">{error.message}</p> : null}
    <HumanReasonDialog open={approvalOpen} title="Approve a clean restart?"
      effect="The launcher will start this original task from the prepared merged code with fresh model context and preserved services. Every new tool call goes through Mirage."
      reasons={['I reviewed the merged repair and its verification.', 'The prepared task is safe to restart.']}
      verb="Approve clean restart" onClose={() => setApprovalOpen(false)} onSubmit={(reason) => approve.mutate(reason)}
      busy={approve.isPending} error={approve.error?.message} />
  </section>
}

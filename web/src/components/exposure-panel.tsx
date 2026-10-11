import { useEffect, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { displayedExposureStatus, exposureJobsKey, exposureTargets, requestExposureJob, useExposureCandidates, useExposureJobs, type ExposureJob, type ExposureObservation, type ExposureStatus } from '@/api/exposure'
import { ACTOR } from '@/components/actions'
import { Button } from '@/components/ui/button'
import { agentName } from '@/lib/runs'
import './exposure-panel.css'

const labels: Record<ExposureStatus, string> = {
  vulnerable: 'Vulnerable', blocked: 'Blocked', not_applicable: 'Not applicable', could_not_evaluate: 'Could not evaluate',
}

function Observation({ name, observation }: { name: string; observation?: ExposureObservation | null }) {
  return <div className="exposure-observation">
    <h4>{name}</h4>
    {observation ? <>
      <p className="exposure-counts">{observation.compromised_runs} compromised · {observation.attack_blocked} attack blocked · {observation.legit_task_completed} legitimate task completed</p>
      {!observation.completed || observation.error ? <p className="exposure-note">Replay incomplete{observation.error ? `: ${observation.error}` : ''}. This is not prevention evidence.</p> : null}
      <details><summary>Captured effects ({observation.effects.length})</summary>
        {observation.effects.length ? <pre tabIndex={0}>{JSON.stringify(observation.effects, null, 2)}</pre> : <p className="exposure-note">No effects recorded.</p>}
      </details>
    </> : <p className="exposure-note">No replay observation returned.</p>}
  </div>
}

export function ExposureResults({ job }: { job: ExposureJob }) {
  return <div className="exposure-results" aria-label="Fleet assessment results">
    <p className="exposure-job-state" role="status">Assessment {job.status}{job.error ? `: ${job.error}` : ''}.</p>
    {job.status === 'queued' || job.status === 'running' ? <p className="exposure-note">Only completed observations establish results. Other agents keep working.</p> : null}
    {job.results.length ? job.results.map((result) => {
      const status = displayedExposureStatus(result)
      return <article className="exposure-result" key={result.agent_name}>
        <div className="exposure-result-heading"><h3>{agentName(result.agent_name)}</h3><span className="exposure-status" data-status={status}>{labels[status]}</span></div>
        <p>{result.reason}</p>
        {status !== result.status ? <p className="exposure-note">The engine reported {labels[result.status].toLowerCase()}, but its replay evidence is incomplete or inconsistent.</p> : null}
        <p className="exposure-note">{result.replay_kind === 'scripted' ? 'Scripted replay — transport and wiring evidence.' : result.replay_kind === 'model_backed' ? 'Model-backed replay — one observation per condition.' : 'Replay method not reported.'}</p>
        {result.attack || result.clean ? <div className="exposure-observations"><Observation name="Attack replay" observation={result.attack} /><Observation name="Clean counterpart" observation={result.clean} /></div> : null}
        <details className="exposure-identity"><summary>Tested snapshot, code and policy</summary><dl>
          <div><dt>Snapshot</dt><dd><code>{result.snapshot_id || 'Unavailable'}</code></dd></div>
          <div><dt>Snapshot SHA-256</dt><dd><code>{result.snapshot_revision || 'Unavailable'}</code></dd></div>
          <div><dt>Attack snapshot SHA-256</dt><dd><code>{result.attack_snapshot_revision || 'Unavailable'}</code></dd></div>
          <div><dt>Clean snapshot SHA-256</dt><dd><code>{result.clean_snapshot_revision || 'Unavailable'}</code></dd></div>
          <div><dt>Code revision</dt><dd><code>{result.code_revision || 'Unavailable'}</code></dd></div>
          <div><dt>Policy revision</dt><dd><code>{result.policy_revision || 'Unavailable'}</code></dd></div>
        </dl></details>
      </article>
    }) : <p className="exposure-note">No agent results yet.</p>}
  </div>
}

// Started automatically once a repair was requested and the cause is known; no manual selection.
export function ExposurePanel({ incidentId, ready = true, autoStart = false }: { incidentId: string; ready?: boolean; autoStart?: boolean }) {
  const cache = useQueryClient()
  const candidates = useExposureCandidates(incidentId)
  const jobs = useExposureJobs(incidentId)
  const job = jobs.data?.[0]
  const started = useRef<string | null>(null)
  const request = useMutation({
    mutationFn: ({ target, names }: { target: string; names: string[] }) => requestExposureJob(target, names, { actor: ACTOR, reason: 'Assess compatible agents in Mirage using independent recordings' }),
    onSuccess: (created, { target }) => {
      cache.setQueryData<ExposureJob[]>(exposureJobsKey(target), (previous = []) => [created, ...previous.filter((old) => old.id !== created.id)])
      void cache.invalidateQueries({ queryKey: ['exposure-jobs'] })
    },
  })
  const names = candidates.data ? exposureTargets(candidates.data) : []
  useEffect(() => {
    // One attempt per incident: a failure is shown below, never retried in a loop.
    if (!autoStart || !ready || started.current === incidentId || !jobs.isSuccess || jobs.data.length || !names.length) return
    started.current = incidentId
    request.mutate({ target: incidentId, names })
  }, [autoStart, ready, incidentId, jobs.isSuccess, jobs.data, names, request])
  return <div className="exposure-panel" aria-label="Check fleet applicability">
    <p className="exposure-note">A capability match is unassessed until replay. Each candidate uses its own task, permissions and recording; live agents keep working.</p>
    {!ready ? <p className="exposure-note">Find the causal input before starting a fleet assessment.</p> : null}
    {candidates.isPending ? <p className="exposure-note" role="status">Loading candidate capabilities…</p> : candidates.isError ? <p className="exposure-note" role="alert">Could not load candidates: {candidates.error.message} <Button onClick={() => { void candidates.refetch() }}>Retry candidates</Button></p>
      : !candidates.data?.length ? <p className="exposure-note">No candidates configured for this incident. An independent recording is required.</p> : null}
    {request.isError && request.variables?.target === incidentId ? <p role="alert" className="exposure-note">Assessment did not start: {request.error.message}</p> : null}
    {jobs.isError ? <p className="exposure-note" role="alert">Assessment updates unavailable: {jobs.error.message} {job ? 'The last received evidence remains below.' : ''} <Button onClick={() => { void jobs.refetch() }}>Retry updates</Button></p> : null}
    {job ? <ExposureResults job={job} /> : <p className="exposure-note">No assessment result yet. Starting a job does not establish a result.</p>}
  </div>
}

export function ExposureSummary() {
  const jobs = useExposureJobs()
  const job = jobs.data?.[0]
  if (!job) return jobs.isError ? <p className="exposure-note">Fleet assessment summary unavailable. Open an incident to retry.</p> : null
  const counts = Object.fromEntries(Object.keys(labels).map((status) => [status, job.results.filter((result) => displayedExposureStatus(result) === status).length]))
  return <aside className="exposure-summary" aria-label="Latest fleet applicability assessment">
    <div><strong>Latest fleet assessment: {job.status}</strong><p className="exposure-note">{job.results.length}/{job.agent_names.length} agents reported{jobs.isError ? ' · Updates unavailable; showing last received evidence' : ''}.</p>
      <p className="exposure-note">{Object.entries(labels).map(([status, label]) => `${counts[status]} ${label.toLowerCase()}`).join(' · ')}</p></div>
    <Link to={`/incidents/${encodeURIComponent(job.incident_id)}`}>Review assessment</Link>
  </aside>
}

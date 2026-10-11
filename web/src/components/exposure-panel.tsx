import type { ExposureJob, ExposureObservation, ExposureResult, ExposureStatus } from '@/api/exposure'
import { agentName } from '@/lib/runs'
import './exposure-panel.css'

const labels: Record<ExposureStatus, string> = {
  vulnerable: 'Vulnerable', blocked: 'Blocked', not_applicable: 'Not applicable', could_not_evaluate: 'Could not evaluate',
}

// A missing or failed replay must never look like successful prevention.
export function displayedExposureStatus(result: ExposureResult): ExposureStatus {
  if (result.status === 'blocked' && [result.attack, result.clean].some((observation) =>
    !observation?.completed || observation.error || observation.compromised_runs !== '0/1' ||
    observation.legit_task_completed !== '1/1')) return 'could_not_evaluate'
  if (result.status === 'vulnerable' && result.attack?.compromised_runs !== '1/1') return 'could_not_evaluate'
  return result.status
}

function Observation({ name, observation }: { name: string; observation?: ExposureObservation | null }) {
  return <div className="exposure-observation">
    <h4>{name}</h4>
    {observation ? <>
      <p className="exposure-counts">{observation.compromised_runs} compromised · {observation.legit_task_completed} legitimate task completed</p>
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
        <p className="exposure-note">{result.replay_kind === 'scripted' ? 'Scripted replay — transport and wiring evidence.' : result.replay_kind === 'model_backed' ? 'Fresh model-backed replay — one observation per condition.' : 'Replay method not reported.'}</p>
        {result.attack || result.clean ? <div className="exposure-observations"><Observation name="Attack replay" observation={result.attack} /><Observation name="Clean counterpart" observation={result.clean} /></div> : null}
        <details className="exposure-identity"><summary>Tested snapshot, code and policy</summary><dl>
          <div><dt>Snapshot</dt><dd><code>{result.snapshot_id || 'Unavailable'}</code></dd></div>
          <div><dt>Snapshot SHA-256</dt><dd><code>{result.snapshot_revision || 'Unavailable'}</code></dd></div>
          <div><dt>Code revision</dt><dd><code>{result.code_revision || 'Unavailable'}</code></dd></div>
          <div><dt>Policy revision</dt><dd><code>{result.policy_revision || 'Unavailable'}</code></dd></div>
        </dl></details>
      </article>
    }) : <p className="exposure-note">No agent results yet.</p>}
  </div>
}

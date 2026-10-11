import { Link } from 'react-router'
import type { Incident, MirageEvent } from '@/api/client'
import { isDemo } from '@/lib/demo'
import { baselineEvidence, currentSandboxJob, incidentEvents, latestFailure, sandboxJobError, verificationEvidence } from '@/pages/incident-data'

const states = { queued: 'Sandbox replay queued', starting: 'Sandbox replay starting', running: 'Sandbox replay running', completed: 'Sandbox replay complete', failed: 'Sandbox replay failed' }

// Read-only engine evidence stays available independently of conversation turns.
export function EngineProof({ incident, events }: { incident: Incident; events: MirageEvent[] }) {
  const evidence = incidentEvents(events, incident.id)
  const baseline = baselineEvidence(incident, evidence)
  const job = currentSandboxJob(incident, evidence)
  const verification = verificationEvidence(evidence, incident)
  const causeJob = job?.purpose === 'bisect' ? job : undefined
  const causeActive = causeJob ? ['queued', 'running'].includes(causeJob.status) : incident.status === 'bisecting'
  const causeError = causeJob ? sandboxJobError(causeJob) : latestFailure(evidence, 'bisection')
  const verdict = baseline.verdict
  return <details className="min-w-0 border-b border-line py-3 text-body [overflow-wrap:anywhere]">
    <summary className="cursor-pointer text-ink focus-visible:outline-offset-4">
      <strong className="font-medium">{incident.id}</strong> · {baseline.status ? states[baseline.status] : 'Awaiting sandbox proof'}
      {baseline.ratio ? <span className="tabular"> · {baseline.ratio} compromised{baseline.resultIsPrevious ? ' in earlier proof' : ''}</span> : null}
      {job && job.purpose !== 'detonate' ? <span> · {job.purpose === 'verify' ? 'Verification' : 'Input-removal tests'} {job.status}</span> : null}
    </summary>
    <div className="mt-3 flex min-w-0 flex-col gap-3 text-ink-2">
      <p>Snapshot <code className="font-mono text-meta">{incident.snapshot_id}</code>. {isDemo ? 'Recorded engine evidence; writes are simulated.' : 'Sandbox writes are captured; real tools do not run in Mirage.'}</p>
      <section aria-label="Baseline replay" className="flex flex-col gap-2">
        <h3 className="font-medium text-ink">Baseline replay</h3>
        {baseline.requestedRuns !== undefined ? <p>{baseline.requestedRuns} replays requested. {baseline.status === 'running' ? `${baseline.effects.length} captured effects received; completed-run counts arrive with the verdict.` : ''}</p> : null}
        {baseline.error ? <p role="status" className="text-ink">Replay failed: {baseline.error}. No new proof was established. Open the incident to review or retry.</p> : null}
        {baseline.diagnostics.map((message, index) => <p key={index} role="status">{message}</p>)}
        {verdict ? <>
          <p>{baseline.resultIsPrevious ? 'Earlier baseline verdict: ' : ''}{isDemo ? 'Recorded verdict: ' : ''}{verdict.confirmed ? 'Compromise confirmed' : 'No compromise found in completed replays'}. {baseline.ratio} compromised, as reported by the engine.</p>
          <p>{verdict.blast_radius.summary}</p>
          <p>{verdict.blast_radius.records} records at risk. Recipients: {verdict.blast_radius.recipients.join(', ') || 'None recorded'}. Secrets in effects: {verdict.blast_radius.secrets.join(', ') || 'None recorded'}.</p>
        </> : <p>{baseline.status === 'failed' ? 'No baseline verdict is available.' : baseline.status === 'completed' ? 'The sandbox finished; its verdict has not arrived yet.' : 'No verdict yet. Captured effects alone do not establish a clean replay.'}</p>}
        {baseline.effects.length > 0 ? <details><summary className="cursor-pointer">Inspect baseline effects ({baseline.effects.length})</summary><pre tabIndex={0} className="mt-2 max-h-48 overflow-auto rounded-control bg-paper-2 p-3 font-mono text-meta whitespace-pre-wrap">{baseline.effects.map((effect) => JSON.stringify(effect, null, 2)).join('\n\n')}</pre></details> : null}
      </section>
      {incident.bisection.length > 0 || causeError || causeActive ? <section aria-label="Removed-input tests" className="flex flex-col gap-2">
        <h3 className="font-medium text-ink">Removed-input tests</h3>
        {causeActive ? <p>{causeJob?.status === 'queued' ? 'Input-removal tests queued.' : 'Testing inputs.'} These results do not replace baseline proof.</p> : null}
        {causeError ? <p role="status">Cause search failed: {causeError}. Completed input tests remain below.</p> : null}
        <ul className="flex flex-col gap-1">{incident.bisection.map((row) => <li key={row.input_id}>{row.label}: {row.compromised_runs} compromised with this input removed{incident.cause_input_id === row.input_id ? ' · proven cause' : ''}.</li>)}</ul>
      </section> : null}
      {verification ? <section aria-label="Current-code verification" className="flex flex-col gap-2">
        <h3 className="font-medium text-ink">{isDemo ? 'Recorded verification example' : 'Current-code verification'}</h3>
        <p>{verification.status === 'queued' ? 'Verification queued; no new result yet.' : verification.status === 'running' ? 'Verification running; no new result yet.' : verification.status === 'failed' ? `Verification failed: ${verification.error ?? 'No result returned'}. No new fix acceptance was established.` : 'Verification finished.'}</p>
        {verification.requestedRuns !== undefined ? <p>{verification.requestedRuns} verification replays requested.</p> : null}
        {verification.diagnostics.map((message, index) => <p key={index} role="status">{message}</p>)}
        {verification.result ? <p>{verification.resultIsPrevious ? 'Earlier check: ' : ''}{verification.result.passed ? 'Replay checks passed' : 'Replay checks did not pass'}. Attack blocked: {verification.result.attack}. Legitimate task completed: {verification.result.legitimate}.</p> : null}
        {isDemo ? <p>This demonstrates verification; a live incident and executable snapshot are required to validate a real fix.</p> : null}
      </section> : null}
      <p>Your coding agent writes and tests the fix. A human merges the PR and approves recovery.</p>
      <Link className="w-fit min-h-8 underline underline-offset-4" to={`/incidents/${encodeURIComponent(incident.id)}`}>Open incident and coding-agent handoff</Link>
    </div>
  </details>
}

import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Check, ExternalLink, LockKeyhole, ShieldAlert } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { api, ApiError, queryClient, useEvents, useRuns, type HumanRequest, type Incident } from '@/api/client'
import { useConnection } from '@/api/stream'
import { AgentAvatar } from '@/agents/avatars'
import { ACTOR, CleanRestartButton, HumanReasonDialog, ResumeButton, liveRunOwned, useAsk } from '@/components/actions'
import { HandoffDrawer } from '@/components/handoff-drawer'
import { RepairProgress } from '@/components/repair-progress'
import { RecoveryPanel } from '@/components/recovery-panel'
import { Button } from '@/components/ui/button'
import { automaticClearanceText, avatarState, callPhrase, runLabel, steps } from '@/lib/runs'
import { isDemo } from '@/lib/demo'
import { baselineEvidence, currentSandboxJob, INCIDENT_ACTIONS, incidentEvents, isIncidentAction, latestFailure, recordedHandoff, requestFinished, safeLink, sandboxJobError, verificationEvidence, type IncidentAction } from './incident-data'
import './incident.css'

export function IncidentPage() {
  const { id = '' } = useParams()
  // The plural prefix lets the existing stream invalidate the detail query too.
  const detail = useQuery({ queryKey: ['incidents', id], queryFn: () => api<Incident>(`/incidents/${encodeURIComponent(id)}`) })
  const { data: runs = [], error: runError, refetch: refetchRuns } = useRuns()
  const { data: events = [] } = useEvents()
  const connection = useConnection()
  const ask = useAsk()
  const [confirm, setConfirm] = useState<IncidentAction | null>(null)
  const [accepted, setAccepted] = useState<{ id: string; kind: IncidentAction; after: number; previousJobId?: string } | null>(null)
  const [handoff, setHandoff] = useState<{ id: string; prompt: string } | null>(null)
  const [drawer, setDrawer] = useState(false)
  const submitting = useRef(false)
  const incident = detail.data
  const evidence = incidentEvents(events, id)
  const baseline = incident ? baselineEvidence(incident, evidence) : null
  const job = currentSandboxJob(incident, evidence)
  const run = runs.find((r) => r.id === incident?.run_id)
  const act = useMutation({
    mutationFn: ({ kind, reason, target }: { kind: IncidentAction; reason: string; target: string }) => {
      const body: HumanRequest = { actor: ACTOR, reason }
      return api<{ prompt?: string }>(`/incidents/${encodeURIComponent(target)}/${INCIDENT_ACTIONS[kind].path}`, body)
    },
    onSuccess: (result, { kind, target }) => {
      setConfirm(null)
      if (kind === 'send_fix') {
        if (typeof result.prompt === 'string' && result.prompt.trim()) {
          setHandoff({ id: target, prompt: result.prompt })
          setDrawer(true)
        } else toast.error('The handoff response contained no prompt. Refresh the incident and try again.')
      } else toast(isDemo ? (kind === 'detonate' ? 'Recorded detonation requested. Waiting for demo evidence.' : 'Recorded cause search requested. Waiting for input tests.') : (kind === 'detonate' ? 'Detonation requested. Waiting for sandbox evidence.' : 'Cause search requested. Waiting for input tests.'))
    },
    onError: (error, { kind }) => {
      setAccepted(null)
      if (kind === 'send_fix') toast.error(`Handoff failed: ${error.message}`)
    },
    onSettled: () => {
      submitting.current = false
      void queryClient.invalidateQueries({ queryKey: ['incidents'] })
    },
  })
  const submit = (reason: string) => {
    if (!confirm || submitting.current || busy) return
    submitting.current = true
    setAccepted({ id, kind: confirm, after: events.at(-1)?.seq ?? 0, previousJobId: job?.id })
    act.mutate({ kind: confirm, reason, target: id })
  }
  const awaiting = accepted?.id === id && accepted.kind !== 'send_fix'
    && !requestFinished(evidence, accepted.kind, accepted.after, job, accepted.previousJobId)
    && (accepted.kind === 'detonate' ? !incident || ['open', 'detonating'].includes(incident.status)
      : !incident || ['confirmed', 'bisecting'].includes(incident.status))
  const baselineActive = baseline?.status === 'queued' || baseline?.status === 'starting' || baseline?.status === 'running'
  const jobActive = job?.status === 'queued' || job?.status === 'running'
  const busy = act.isPending || awaiting || (job ? jobActive : baselineActive || incident?.status === 'detonating' || incident?.status === 'bisecting')
  const action = incident?.next_action
  const primary = action && isIncidentAction(action) ? INCIDENT_ACTIONS[action] : undefined
  const refresh = () => { void detail.refetch(); void refetchRuns() }

  if (!incident) return (
    <article className="incident-page">
      <BackLink />
      {detail.isPending ? <div className="incident-loading" role="status" aria-label="Loading incident"><div /><div /><div /><p>Loading the incident and snapshot…</p></div>
        : <div className="incident-empty" role="alert"><ShieldAlert size={28} /><h1>{detail.error instanceof ApiError && detail.error.status === 404 ? 'Incident not found' : 'Could not load this incident'}</h1>
          <p>{detail.error instanceof ApiError && detail.error.status === 404 ? `There is no incident ${id}. Return to the fleet to open a current incident.` : detail.error?.message ?? 'The backend did not return an incident.'}</p>
          <Button onClick={refresh}>Try again</Button></div>}
    </article>
  )

  const verdict = baseline?.verdict
  const recent = steps(events, incident.run_id).filter((s) => s.callId !== incident.trigger.call_id).slice(-2)
  const detonationError = baseline?.error
  const bisectionError = job?.purpose === 'bisect' ? sandboxJobError(job) : latestFailure(evidence, 'bisection')
  const bisectionActive = job?.purpose === 'bisect' ? jobActive : incident.status === 'bisecting'
  const verificationState = verificationEvidence(evidence, incident)
  const verification = verificationState?.result
  const pr = safeLink(incident.pr_url)
  const cause = incident.inputs.find((input) => input.id === incident.cause_input_id)
  const causeCompleted = evidence.some((e) => e.type === 'bisection.completed' && !e.payload.error) || (incident.status === 'root_caused' && !bisectionError)
  const effects = baseline?.effects ?? []
  const prompt = handoff?.id === id ? handoff.prompt : recordedHandoff(evidence)
  // No reason dialog: the handoff only copies text. The POST still records the human action.
  const handOff = () => {
    if (prompt) { setDrawer(true); return }
    if (submitting.current || busy) return
    submitting.current = true
    act.mutate({ kind: 'send_fix', reason: INCIDENT_ACTIONS.send_fix.reason, target: id })
  }
  const clearanceText = run && (isDemo || liveRunOwned(run, connection))
    ? automaticClearanceText(run, incident) : null
  const mediumPending = !!incident.automatic_clearance && incident.automatic_clearance.status !== 'cleared'
  const canUnfreeze = !mediumPending && run?.status === 'frozen' && (['open', 'false_positive'].includes(incident.status)
    || (incident.status === 'closed' && incident.automatic_clearance?.status === 'cleared')) && !busy

  return (
    <article className="incident-page">
      <div className="incident-nav"><BackLink /><Link to={`/runs/${encodeURIComponent(incident.run_id)}`}>Full run trace <ArrowRight size={14} /></Link></div>
      <header className="incident-header">
        <div className="incident-identity">
          <AgentAvatar agent={run?.agent ?? incident.run_id} state={run ? avatarState(run) : 'idle'} size={32} />
          <span>{run ? runLabel(run, runs) : incident.run_id}</span>
          <span className="incident-status" data-alarm={run?.status === 'frozen'}>{run?.status === 'frozen' ? 'Frozen' : incident.status.replaceAll('_', ' ')}</span>
          <code>{incident.id}</code>
        </div>
        <h1>It tried to {callPhrase(incident.trigger)}. The gate blocked it.</h1>
        <p>{run?.task ?? 'Review the blocked action and its recorded inputs before deciding what happens next.'}</p>
        <div className="incident-chain" aria-label="Recorded action"><span>Recorded inputs</span><ArrowRight size={14} /><span>{run?.agent ?? incident.run_id}</span><ArrowRight size={14} /><code>{incident.trigger.tool}</code>
          {typeof incident.trigger.args.to === 'string' && <><ArrowRight size={14} /><span className="incident-alarm">{incident.trigger.args.to}</span></>}
        </div>
      </header>
      {isDemo && <Notice>Recorded demonstration: this incident, sandbox proof, cause tests and fix evidence are recorded or simulated.</Notice>}
      {detail.isError && <Notice tone="alarm">The incident could not refresh: {detail.error.message} <Button onClick={refresh}>Retry</Button></Notice>}
      {runError && <Notice>Run status is unavailable. Secondary actions will appear when it loads. <Button onClick={refresh}>Retry</Button></Notice>}
      {clearanceText && <Notice tone={clearanceText === 'Still frozen' ? 'alarm' : 'mirage'}>
        <strong>{clearanceText}.</strong> {clearanceText === 'Checking in Mirage'
          ? 'Production is held while three fresh replays and a stronger model check the original call.'
          : clearanceText === 'Automatically resumed'
            ? 'The initial replays completed the task, captured the exact original call and found no deterministic harm; the stronger model classified the held and outbound calls as safe.'
            : 'The initial proof did not establish safe automatic clearance. Review the evidence, then kill this run and approve a clean restart when ready.'}
      </Notice>}
      <StorySection number="1" title="What happened">
        <p className="incident-section-intro">The gate held this call before execution. This records the attempted action; sandbox proof comes next.</p>
        {recent.length > 0 && <ul className="incident-recent">{recent.map((s) => <li key={s.callId}><code>{s.tool}</code><span>{s.blocked ? 'Held by the gate' : 'Requested'}</span></li>)}</ul>}
        <div className="incident-blocked">
          <div className="incident-blocked-title"><LockKeyhole size={17} /><code>{incident.trigger.tool}</code><span>Blocked</span></div>
          <p>{incident.trigger.explanation}</p>
          <dl className="incident-rule"><div><dt>Rule</dt><dd><code>{incident.trigger.rule_id ?? incident.trigger.policy_id ?? 'Not supplied'}</code></dd></div><div><dt>Gate</dt><dd>{incident.trigger.layer === 'hard_rule' ? 'Deterministic hard rule' : 'Decision model'}</dd></div>
            {incident.trigger.p != null && <div><dt>Model score</dt><dd>{incident.trigger.p}</dd></div>}</dl>
          <details><summary>Inspect blocked arguments</summary><pre>{JSON.stringify(incident.trigger.args, null, 2)}</pre></details>
        </div>
      </StorySection>
      <StorySection number="2" title="What would have happened" badge="Mirage">
        {baselineActive && <Notice>{baseline?.status === 'queued' ? 'Sandbox replay queued.' : 'Replaying the snapshot in Mirage.'}{baseline?.requestedRuns !== undefined && ` ${baseline.requestedRuns} replays requested.`}{baseline?.status === 'running' && ` ${effects.length} captured effects received; completed-run counts arrive with the verdict.`}</Notice>}
        {detonationError && <Notice tone="alarm">Detonation failed: {detonationError}. No new proof was established. Use the available next action to retry.</Notice>}
        {baseline?.diagnostics.map((message, index) => <Notice key={index} tone="alarm">{message}</Notice>)}
        {verdict ? <div className="incident-proof">
          <h3><ShieldAlert size={18} />{isDemo ? (verdict.confirmed ? 'Recorded compromise verdict' : 'Recorded clean verdict') : (verdict.confirmed ? 'Compromise confirmed' : 'No deterministic harm found in replay')}</h3>
          <p>{baseline?.resultIsPrevious && 'Earlier baseline proof: '}<strong>{verdict.compromised_runs}</strong> replays compromised. Determined by code from the effects ledger.</p>
          <p>{verdict.blast_radius.summary}</p>
          <dl className="incident-blast"><div><dt>Records at risk</dt><dd>{verdict.blast_radius.records}</dd></div><div><dt>Recipients</dt><dd>{verdict.blast_radius.recipients.join(', ') || 'None recorded'}</dd></div><div><dt>Secrets in effects</dt><dd>{verdict.blast_radius.secrets.join(', ') || 'None recorded'}</dd></div></dl>
          {verdict.policies_violated.length > 0 && <p className="incident-muted">Policies: {verdict.policies_violated.join(', ')}</p>}
        </div> : <div className="incident-pending" role="status"><h3>{baseline?.status === 'queued' ? 'Sandbox replay queued' : baselineActive || (awaiting && accepted?.kind === 'detonate') ? 'Replaying the snapshot…' : baseline?.status === 'failed' ? 'No baseline proof established' : baseline?.status === 'completed' ? 'Waiting for the baseline verdict' : 'Proof awaits detonation'}</h3><p>Replay the frozen context in Mirage to see the captured effects. No verdict has been returned yet.</p></div>}
        {effects.length > 0 && <details className="incident-effects"><summary>Inspect baseline effects ({effects.length})</summary><pre>{effects.map((e) => JSON.stringify(e, null, 2)).join('\n\n')}</pre></details>}
      </StorySection>
      <StorySection number="3" title="Why it happened">
        <p className="incident-section-intro">{cause ? `Proven cause: ${cause.label}. Removing this input prevented the compromise in the recorded tests.` : bisectionActive || (awaiting && accepted?.kind === 'find_cause') ? job?.status === 'queued' ? 'Input-removal tests queued. Baseline proof remains above.' : 'Testing each input removal… Results appear as each replay finishes.' : causeCompleted ? 'The input tests did not establish a single cause. Review the results below.' : 'The cause is not established yet. Bisection tests each untrusted input by replaying the snapshot without it.'}</p>
        {bisectionError && <Notice tone="alarm">Cause search failed: {bisectionError}. Completed input tests are shown below.</Notice>}
        <div className="incident-snapshot"><span>Snapshot <code>{incident.snapshot_id}</code></span><span>{incident.inputs.length} recorded inputs</span></div>
        {incident.inputs.length ? <ul className="incident-inputs">{incident.inputs.map((input) => {
          const row = incident.bisection.find((r) => r.input_id === input.id)
          const proven = incident.cause_input_id === input.id
          return <li key={input.id} data-cause={proven}><details><summary><span className="incident-input-name">{input.label}<small>{input.kind.replaceAll('_', ' ')}{input.source_tool ? ` · ${input.source_tool}` : ''}</small></span>
            <span className="incident-input-result">{row ? <>{proven ? 'Proven cause · ' : ''}Removed → {row.compromised_runs} compromised{row.is_cause ? ' · clean in these tests' : ''}</> : 'Not tested'}</span></summary><pre>{input.preview || 'No preview supplied.'}</pre></details></li>
        })}</ul> : <p className="incident-muted">No input previews were returned for this snapshot.</p>}
      </StorySection>
      <StorySection number="4" title="The fix">
        <RepairProgress key={id} incidentId={id}
          canStart={!!incident.verdict?.confirmed && ['confirmed', 'root_caused', 'fix_pending', 'fix_verified', 'pr_open'].includes(incident.status)} />
        {verificationState?.status === 'queued' && <Notice>Current-code verification is queued. No new result has been returned yet.</Notice>}
        {verificationState?.status === 'running' && <Notice>Current-code verification is running. No new result has been returned yet.</Notice>}
        {verificationState?.status === 'failed' && <Notice tone="alarm">Current-code verification failed: {verificationState.error ?? 'No result returned'}. No new fix acceptance was established.</Notice>}
        {verificationState?.requestedRuns !== undefined && <p className="incident-muted">{verificationState.requestedRuns} current-code verification replays requested.</p>}
        {verificationState?.diagnostics.map((message, index) => <Notice key={index} tone="alarm">{message}</Notice>)}
        {verification && verificationState?.resultIsPrevious && <p className="incident-muted">Earlier current-code verification result:</p>}
        {verification ? <Notice tone={verification.passed ? 'mirage' : 'alarm'}><strong>{isDemo ? (verification.passed ? 'Recorded fix replay passed.' : 'Recorded fix replay failed.') : (verification.passed ? 'Fix replay passed.' : 'Fix replay failed.')}</strong> Attack blocked: {verification.attack}. Legitimate task completed: {verification.legitimate}.{isDemo && ' This demonstrates verification; it does not establish real fix acceptance.'}</Notice> : <p className="incident-section-intro">{isDemo ? 'The demo handoff shows the coding-agent workflow. Real fix validation requires a live incident and executable snapshot.' : incident.status === 'fix_pending' ? 'The handoff is ready. Your coding agent writes the fix and must test it against this snapshot.' : 'Hand off to your coding agent. It writes the fix and tests it against this snapshot. Verification results appear here when the server reports them.'}</p>}
        {pr && <a className="incident-pr" href={pr} target="_blank" rel="noopener noreferrer"><span><strong>Review the fix pull request</strong><small>{pr}</small></span><ExternalLink size={17} /></a>}
        {incident.pr_url && !pr && <Notice tone="alarm">The server returned an invalid PR link. Open the incident again after the link is corrected.</Notice>}
        {prompt && <div className="incident-handoff"><Button onClick={handOff}>Hand off to coding agent<ArrowRight /></Button></div>}
        {!pr && !prompt && <p className="incident-muted">No pull request has been reported yet. A human reviews and merges the PR.</p>}
        {!!incident.verdict?.confirmed && run && <RecoveryPanel key={`recovery-${id}`} incidentId={id} run={run} />}
      </StorySection>
      <footer className="incident-actions">
        <div className="incident-action-main">{busy ? <><Button variant="primary" disabled>Waiting for results…</Button><span role="status">Updates arrive from the engine.</span><Button onClick={refresh}>Refresh</Button></> : primary && action && isIncidentAction(action) ? <Button variant="primary" onClick={() => { act.reset(); if (action === 'send_fix') handOff(); else setConfirm(action) }}>{primary.label}<ArrowRight /></Button> : action === 'open_pr' && pr ? <Button variant="primary" asChild><a href={pr} target="_blank" rel="noopener noreferrer">Open PR<ExternalLink /></a></Button> : action === 'open_pr' ? <span>Waiting for a valid PR link.</span> : <span><Check size={16} />{incident.automatic_clearance ? clearanceText ?? 'Automatic clearance recorded. Check the current run status.' : incident.status === 'false_positive' ? 'Review the replay, then unfreeze if appropriate.' : 'No further action requested.'}</span>}</div>
        {run?.status === 'frozen' && (isDemo || liveRunOwned(run, connection)) && <div className="incident-secondary">{!mediumPending && <Button variant="ghost" disabled={!canUnfreeze} title={!canUnfreeze ? 'Unfreeze is available only before confirmation or after a false positive.' : undefined} onClick={() => ask('unfreeze', run)}>Unfreeze</Button>}<Button variant="destructive" onClick={() => ask('kill', run)}>Kill</Button></div>}
        {run?.status === 'halted' && <div className="incident-secondary"><ResumeButton run={run} /></div>}
        {!isDemo && !incident.verdict?.confirmed && run && ['killed', 'halted', 'failed'].includes(run.status) && <div className="incident-secondary"><CleanRestartButton run={run} /></div>}
      </footer>
      {confirm && <HumanReasonDialog key={`${id}:${confirm}`} open title={`${INCIDENT_ACTIONS[confirm].label}?`} effect={INCIDENT_ACTIONS[confirm].effect} reasons={[INCIDENT_ACTIONS[confirm].reason]} verb={INCIDENT_ACTIONS[confirm].label} onClose={() => setConfirm(null)} onSubmit={submit} busy={act.isPending} error={act.error?.message} />}
      <HandoffDrawer open={drawer && !!prompt} onClose={() => setDrawer(false)} prompt={prompt} />
    </article>
  )
}

function BackLink() { return <Link className="incident-back" to="/fleet"><ArrowLeft size={15} />Back to Fleet</Link> }
function StorySection({ number, title, badge, children }: { number: string; title: string; badge?: string; children: ReactNode }) {
  return <section className="incident-section"><div className="incident-section-heading"><span className="incident-number" aria-hidden="true">{number}</span><h2>{title}</h2>{badge && <span className="incident-mirage">{badge}</span>}</div><div className="incident-section-body">{children}</div></section>
}
function Notice({ tone, children }: { tone?: 'alarm' | 'mirage'; children: ReactNode }) {
  return <div className="incident-notice" data-tone={tone} role={tone === 'alarm' ? 'alert' : 'status'}>{children}</div>
}

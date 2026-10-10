import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, ArrowUpRight, Calendar, Check, ChevronRight, Circle, Clock, Mail, Pause, Search, ShieldAlert, Wrench } from 'lucide-react'
import { useEvents, useRuns, type Run } from '@/api/client'
import { useNow } from '@/api/stream'
import { ResumeButton } from '@/components/actions'
import { AgentAvatar } from '@/components/avatar'
import { Button } from '@/components/ui/button'
import { avatarState, relTime, runLabel } from '@/lib/runs'
import { actionSummary, activityFacts, activityLabels, activityState, buildTraceCalls, buildWorkflow, stageState, type ActivityState, type TraceCallDetail } from '@/lib/workflow'
import './trace.css'

export type { TraceCallDetail } from '@/lib/workflow'

const STATUS: Record<Run['status'], string> = {
  queued: 'Waiting to start', running: 'Working', frozen: 'Paused for review',
  completed: 'Done', killed: 'Stopped', halted: 'Stopped',
}
const EMPTY: Record<Run['status'], string> = {
  queued: 'Activity will appear here when the assistant starts.',
  running: 'The assistant is working. Its first action will appear here.',
  frozen: 'This run is paused. No tool actions have been recorded yet.',
  completed: 'This run is done. No tool actions were recorded.',
  killed: 'This run was stopped. No tool actions were recorded.',
  halted: 'This run was stopped. No tool actions were recorded.',
}

function StateIcon({ state }: { state: ActivityState }) {
  const Icon = state === 'completed' ? Check : state === 'blocked' || state === 'error' ? ShieldAlert
    : state === 'paused' || state === 'stopped' ? Pause : state === 'allowed' ? Clock : Circle
  return <Icon size={16} aria-hidden="true" />
}

export function RunPage() {
  const { id } = useParams<{ id: string }>()
  return <RunWorkflow key={id} id={id} />
}

function RunWorkflow({ id }: { id: string | undefined }) {
  const { data: runs = [], isPending, isError, refetch } = useRuns()
  const { data: events = [] } = useEvents()
  const now = useNow()
  const run = runs.find((r) => r.id === id)
  const [selection, setSelection] = useState<{ stageId: string; callId: string } | null>(null)
  const traceCalls = useMemo(() => buildTraceCalls(events, id ?? ''), [events, id])
  const stages = useMemo(() => buildWorkflow(traceCalls, run?.agent ?? ''), [traceCalls, run?.agent])
  const selectedStage = stages.find((stage) => stage.id === selection?.stageId)
  const activeCall = selectedStage?.calls.find((call) => call.callId === selection?.callId)
  const latestCall = traceCalls.at(-1)
  const currentStage = stages.find((stage) => stage.calls.some((call) => call.callId === latestCall?.callId))
  const actionOrder = new Map(traceCalls.map((call, index) => [call.callId, index + 1]))
  const lastEvent = events.findLast((event) => event.run_id === id)

  if (!run) return <div className="trace-page"><div className="trace-container">
    <Link to="/fleet" className="trace-nav-back"><ArrowLeft size={16} /> Back to Fleet</Link>
    <section className="trace-empty" aria-live="polite">
      <h1>{isPending ? 'Loading this run…' : isError ? 'Unable to load this run' : 'Run not found'}</h1>
      <p>{isPending ? 'Getting the assistant’s latest activity.' : isError ? 'Try again to get the latest activity.'
        : 'This run is not in the current fleet. Return to Fleet to choose another.'}</p>
      {isError ? <Button onClick={() => void refetch()}>Try again</Button>
        : !isPending ? <Button asChild><Link to="/fleet">Return to Fleet</Link></Button> : null}
    </section>
  </div></div>

  const chooseStage = (stage: typeof stages[number]) => setSelection({ stageId: stage.id, callId: stage.calls.at(-1)!.callId })
  return <div className="trace-page" aria-label={`Activity for ${runLabel(run, runs)}`}><div className="trace-container">
    <Link to="/fleet" className="trace-nav-back"><ArrowLeft size={16} /> Back to Fleet</Link>
    <header className="trace-header">
      <div className="trace-header-left">
        <AgentAvatar agent={run.agent} state={avatarState(run)} size={40} />
        <div className="trace-header-title">
          <div className="trace-title-line"><h1>{runLabel(run, runs)}</h1>
            <span className={`trace-status ${run.status === 'frozen' ? 'trace-status--paused' : ''}`}>{STATUS[run.status]}</span>
          </div><p>{run.task}</p>
        </div>
      </div>
      <div className="trace-header-meta">
        {run.incident_id ? <Button asChild variant={run.status === 'frozen' ? 'primary' : 'secondary'}>
          <Link to={`/incidents/${run.incident_id}`}>Review incident <ArrowUpRight /></Link>
        </Button> : null}
        <ResumeButton run={run} variant="primary" />
        <span><Clock size={13} aria-hidden="true" /> Updated {relTime(lastEvent?.ts ?? run.ended_at ?? run.started_at, now)}</span>
      </div>
    </header>
    {isError ? <p className="trace-notice" role="status">Latest run status is unavailable. Showing the last received activity. <button onClick={() => void refetch()}>Try again</button></p> : null}
    {run.status === 'frozen' ? <div className="trace-pause-note"><Pause size={16} aria-hidden="true" />
      <p><strong>Paused for human review.</strong> Review its activity below{run.incident_id ? ' or open the incident to decide what happens next.' : '.'}</p>
    </div> : null}
    <section className="trace-workflow" aria-labelledby="workflow-title">
      <div className="trace-section-heading"><div><h2 id="workflow-title">The work so far</h2>
        <p>{stages.length ? 'Grouped by activity. The assistant can return to any stage.' : EMPTY[run.status]}</p>
      </div><span className="trace-following">{selection ? 'Reviewing selected activity' : run.status === 'running' ? 'Watching current activity' : 'Recorded activity'}</span></div>
      {stages.length ? <ul className="trace-stages">{stages.map((stage) => {
        const state = stageState(stage, run.status)
        const selected = selectedStage?.id === stage.id
        const current = !selection && stage.id === currentStage?.id
        const Icon = stage.title.startsWith('Send') || stage.title === 'Share review' ? Mail
          : stage.title.includes('calendar') || stage.title.includes('next steps') ? Calendar
          : stage.title === 'Other activity' ? Wrench : Search
        return <li key={stage.id}><button type="button"
          className={`trace-stage trace-state--${state} ${selected ? 'is-selected' : ''} ${current ? 'is-current' : ''}`}
          aria-pressed={selected} aria-controls={selectedStage ? 'workflow-detail' : undefined} onClick={() => chooseStage(stage)}>
          <span className="trace-stage-top"><span className="trace-stage-symbol"><Icon size={17} aria-hidden="true" /></span><StateIcon state={state} /></span>
          <strong>{stage.title}</strong>
          <span className="trace-stage-state">{activityLabels[state]}<ChevronRight size={13} aria-hidden="true" /></span>
          <span className="trace-stage-summary">{actionSummary(stage.calls.at(-1)!)}</span>
          <span className="trace-stage-count">{stage.calls.length} {stage.calls.length === 1 ? 'action' : 'actions'}</span>
        </button></li>
      })}</ul> : null}
      <div className="trace-current" aria-live="polite" aria-atomic="true">{latestCall ? <>
        <StateIcon state={activityState(latestCall, run.status)} /><span>
          {run.status === 'completed' ? 'Run finished.' : run.status === 'killed' || run.status === 'halted' ? 'Run stopped.' : 'Latest activity:'} {actionSummary(latestCall)} · {activityLabels[activityState(latestCall, run.status)]}
        </span></> : <span>{STATUS[run.status]}</span>}
      </div>
    </section>
    {selectedStage && activeCall ? <section id="workflow-detail" className="trace-detail" aria-labelledby="detail-title">
      <div className="trace-section-heading"><div><h2 id="detail-title">{selectedStage.title}</h2>
        <p>{selectedStage.calls.length === 1 ? 'One recorded action' : `${selectedStage.calls.length} actions, in recorded order`}</p></div>
        <Button variant="ghost" onClick={() => setSelection(null)}>{run.status === 'running' ? 'Return to current activity' : 'Return to overview'}</Button>
      </div>
      <div className={`trace-detail-layout ${selectedStage.calls.length === 1 ? 'trace-detail-layout--single' : ''}`}>
        {selectedStage.calls.length > 1 ? <ol className="trace-actions" aria-label="Actions in this stage">
          {selectedStage.calls.map((call) => {
            const state = activityState(call, run.status)
            return <li key={call.callId}><button type="button" className={`trace-action trace-state--${state}`}
              aria-pressed={activeCall.callId === call.callId} onClick={() => setSelection({ stageId: selectedStage.id, callId: call.callId })}>
              <StateIcon state={state} /><span><strong>{actionSummary(call)}</strong><small>Action {actionOrder.get(call.callId)} · {activityLabels[state]}</small></span>
            </button></li>
          })}
        </ol> : null}
        <ActionDetail key={activeCall.callId} call={activeCall} run={run} />
      </div>
    </section> : null}
    {traceCalls.length ? <details className="trace-history">
      <summary>View all {traceCalls.length} actions in order</summary>
      <ol className="trace-history-list">{traceCalls.map((call) => {
        const stage = stages.find((area) => area.calls.some((action) => action.callId === call.callId))!
        return <li key={call.callId}><button type="button" className="trace-action"
          aria-pressed={activeCall?.callId === call.callId} onClick={() => setSelection({ stageId: stage.id, callId: call.callId })}>
          <span className="trace-order">{actionOrder.get(call.callId)}</span><span><strong>{actionSummary(call)}</strong>
            <small>{stage.title} · {activityLabels[activityState(call, run.status)]} · <time dateTime={call.ts}>{relTime(call.ts, now)}</time></small>
          </span></button></li>
      })}</ol>
    </details> : null}
  </div></div>
}

function Facts({ value }: { value: unknown }) {
  const facts = activityFacts(value)
  return facts.length ? <dl className="trace-facts">{facts.map(([label, text]) =>
    <div key={label}><dt>{label}</dt><dd>{text}</dd></div>)}
  </dl> : null
}

function ActionDetail({ call, run }: { call: TraceCallDetail; run: Run }) {
  const state = activityState(call, run.status)
  const hasResult = call.resultRecorded || call.result !== undefined
  const resultItems = Array.isArray(call.result) ? call.result : null
  return <div className="trace-action-detail">
    <div className={`trace-action-heading trace-state--${state}`}><StateIcon state={state} /><h3>{actionSummary(call)}</h3></div>
    <p className={`trace-outcome trace-state--${state}`}>{state === 'allowed' ? 'Allowed by Mirage. Waiting for the action’s result.'
      : state === 'pending' ? 'Waiting for Mirage to check this action.' : state === 'blocked' ? 'Mirage held this action before execution.'
      : state === 'completed' && call.blocked ? 'A result was recorded after this action was held for review.'
      : state === 'completed' ? 'The action returned a result.' : activityLabels[state]}</p>
    {state === 'blocked' && call.decision?.explanation ? <p className="trace-held-reason">{call.decision.explanation}</p> : null}
    <Facts value={call.args} />
    {(call.tool === 'send_email' || call.tool === 'schedule_follow_up') && typeof call.args.body === 'string'
      ? <div className="trace-message"><h4>Message</h4><p>{call.args.body}</p></div> : null}
    {call.error !== null ? <p className="trace-held-reason">{call.error}</p> : null}
    {hasResult ? <div className="trace-result-summary"><h4>Result</h4>
      {resultItems ? <><p>{resultItems.length} {resultItems.length === 1 ? 'item' : 'items'} returned</p>
        {resultItems.slice(0, 3).map((item, index) => <div className="trace-returned-item" key={index}><Facts value={item} /></div>)}
        {resultItems.length > 3 ? <p>All {resultItems.length} items are available in technical details.</p> : null}
      </> : typeof call.result === 'string' ? <p className="trace-result-text">{call.result}</p>
        : call.result === null ? <p>An empty result was recorded.</p>
          : activityFacts(call.result).length ? <Facts value={call.result} /> : <p>A result was recorded. Open technical details to read the full response.</p>}
    </div> : null}
    <details className="trace-technical">
      <summary>Technical details</summary>
      <dl className="trace-facts"><div><dt>Tool</dt><dd>{call.tool}</dd></div><div><dt>Call ID</dt><dd>{call.callId}</dd></div>
        <div><dt>Requested at</dt><dd>{call.ts}</dd></div></dl>
      <h4>Gate decision</h4><pre>{call.decision ? JSON.stringify(call.decision, null, 2) : 'No gate decision recorded.'}</pre>
      <h4>Arguments</h4><pre>{JSON.stringify(call.args, null, 2)}</pre>
      <h4>Result</h4><pre>{hasResult ? JSON.stringify(call.result, null, 2) ?? 'An empty result was recorded.' : 'No result recorded.'}</pre>
      <h4>Error</h4><pre>{call.error ?? 'No error recorded.'}</pre>
    </details>
  </div>
}

import { useState } from 'react'
import { Link } from 'react-router'
import { ApiError, useApprovals, type Approval } from '@/api/client'
import { ACTOR, HumanReasonDialog } from './actions'
import { humanControlError, useEngineApproval } from './engine-controls'
import { Button } from './ui/button'
import { isDemo } from '@/lib/demo'

type Decision = 'approve' | 'reject'

export function EngineApprovals() {
  const queue = useApprovals()
  const [pending, setPending] = useState<{ approval: Approval; decision: Decision } | null>(null)
  const act = useEngineApproval()
  const choose = (approval: Approval, decision: Decision) => { act.reset(); setPending({ approval, decision }) }
  const error = act.error instanceof ApiError && act.error.status === 404
    ? 'This call is no longer waiting for approval. Refresh the queue before deciding again.'
    : act.error ? humanControlError(act.error) : undefined
  return <section className="engine-approvals" aria-label="Engine approvals">
    <div className="fleet-evidence-heading"><h3>Engine approvals{queue.data?.length ? ` (${queue.data.length})` : ''}</h3><span>Medium-risk tool calls</span></div>
    {queue.isPending ? <p role="status">Loading held calls…</p>
      : queue.isError ? <p role="alert">Approval queue could not refresh: {queue.error.message} <Button onClick={() => void queue.refetch()}>Refresh queue</Button></p>
      : !queue.data.length ? <p className="fleet-evidence-muted">No tool calls are waiting for approval.</p>
      : <><p className="fleet-evidence-muted">These calls are held before execution. Approve releases the call; reject ends the run.{isDemo && ' Recorded demo: decisions are unavailable; no live run is controlled.'}</p>
        <ul>{queue.data.map((approval) => <li key={approval.call_id}>
          <div className="engine-approval-copy"><Link to={`/runs/${encodeURIComponent(approval.run_id)}`}>{approval.agent || approval.run_id}</Link><code>{approval.tool}</code>
            <p>{approval.explanation}</p>
            <small>{approval.policy_id && `Policy ${approval.policy_id} · `}{approval.p != null && `Model score ${approval.p} · `}<time dateTime={approval.ts}>{new Date(approval.ts).toLocaleTimeString()}</time></small>
            <details><summary>Inspect held arguments</summary><pre>{JSON.stringify(approval.args, null, 2)}</pre></details>
          </div>
          <div className="engine-approval-actions"><Button disabled={isDemo || act.isPending} onClick={() => choose(approval, 'reject')}>Reject</Button><Button disabled={isDemo || act.isPending} onClick={() => choose(approval, 'approve')}>Approve</Button></div>
        </li>)}</ul></>}
    {pending && <HumanReasonDialog key={`${pending.approval.call_id}:${pending.decision}`} open
      title={`${pending.decision === 'approve' ? 'Approve' : 'Reject'} ${pending.approval.tool}?`}
      effect={pending.decision === 'approve' ? 'The held tool call will execute with the arguments shown in the queue.' : 'The held call will never run, and this run ends. A clean restart needs a separate human approval.'}
      reasons={pending.decision === 'approve' ? ['This call matches the task and its destination is expected.'] : ['The action does not fit the task.', 'The destination is not expected.']}
      verb={pending.decision === 'approve' ? 'Approve held call' : 'Reject held call'} destructive={pending.decision === 'reject'} busy={act.isPending} error={error}
      onClose={() => setPending(null)} onSubmit={(reason) => {
        if (act.isPending) return
        act.mutate({ callId: pending.approval.call_id, decision: pending.decision, body: { actor: ACTOR, reason } }, { onSuccess: () => setPending(null) })
      }} />}
  </section>
}

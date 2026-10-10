import type { Incident, MirageEvent, Run } from '../api/client'
import { actionSummary, activityState, buildTraceCalls, buildWorkflow } from '../lib/workflow.ts'

// Fleet labels describe availability; completed backend runs remain completed.
export function fleetStatus(run: Pick<Run, 'status'>) {
  switch (run.status) {
    case 'running': return 'Working'
    case 'completed': return 'Healthy'
    case 'frozen': return 'Frozen'
    case 'queued': return 'Queued'
    case 'killed': case 'halted': return 'Stopped'
  }
}

export function healthyAgents(runs: Run[]) {
  return runs.filter((run) => run.env === 'prod' && ['Working', 'Healthy'].includes(fleetStatus(run))).length
}

/** Only the baseline incident replay, never bisection or fix verification. */
export function sandboxStatus(incident: Incident | undefined, events: MirageEvent[]): string | undefined {
  if (!incident) return
  let status: string | undefined
  const excluded = new Set<unknown>()
  for (const event of events) {
    const p = event.payload as Record<string, unknown>
    if (event.incident_id !== incident.id && p.incident_id !== incident.id) continue
    if (p.removed_input_id || p.purpose === 'verify') {
      if (p.detonation_id || p.id) excluded.add(p.detonation_id ?? p.id)
      continue
    }
    if (excluded.has(p.detonation_id ?? p.id)) continue
    switch (event.type) {
      case 'run.status':
        if (event.run_id === incident.run_id && p.actor === 'system' && p.from === 'frozen' && p.to === 'frozen'
          && p.reason === 'Automatic sandbox detonation queued (3 replays)') status = 'Sandbox replay queued'
        break
      case 'detonation.started': status = 'Sandbox replay running'; break
      case 'detonation.completed': status = 'Sandbox replay complete'; break
      case 'detonation.failed': status = 'Sandbox replay failed'; break
      case 'verdict.ready': status = 'Sandbox replay complete'; break
    }
  }
  if (status) return status
  if (incident.status === 'detonating') return 'Sandbox replay starting'
  if (incident.verdict) return 'Sandbox replay complete'
}

/** Latest observed activity area, with evidence states rather than inferred task success. */
export function fleetActivity(run: Run, events: MirageEvent[], incident?: Incident) {
  const calls = buildTraceCalls(events, run.id)
  const latest = calls.at(-1)
  const stage = buildWorkflow(calls, run.agent).find((group) => group.calls.includes(latest!))
  const counts = new Map<string, number>()
  for (const call of stage?.calls ?? []) {
    const state = activityState(call, run.status)
    counts.set(state, (counts.get(state) ?? 0) + 1)
  }
  const countLabels: Record<string, string> = {
    completed: 'returned', blocked: 'held', error: 'failed', pending: 'awaiting check',
    allowed: 'awaiting result', paused: 'paused', stopped: 'stopped', unrecorded: 'result missing',
  }
  const results = [...counts].map(([state, count]) => `${count} ${countLabels[state]}`).join(' · ')
  const denied = calls.findLast((call) => call.blocked)
  const blocked = denied ? `${denied.released || denied.resultRecorded ? 'Previously blocked' : 'Blocked'}: ${actionSummary(denied)}`
    : run.status === 'frozen' && incident ? `Blocked: ${actionSummary(incident.trigger)}` : undefined
  return {
    title: stage ? `${stage.title} · ${stage.calls.length} ${stage.calls.length === 1 ? 'action' : 'actions'}` : 'No actions recorded',
    detail: latest && latest !== denied ? actionSummary(latest) : undefined,
    results,
    blocked,
  }
}

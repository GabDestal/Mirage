import type { Incident, MirageEvent, Run } from '../api/client'
import { actionSummary, activityState, buildTraceCalls, buildWorkflow } from '../lib/workflow.ts'
import { baselineEvidence } from './incident-data.ts'

// Fleet labels describe availability; completed backend runs remain completed.
export function fleetStatus(run: Pick<Run, 'status'>) {
  switch (run.status) {
    case 'running': return 'Working'
    case 'completed': return 'Healthy'
    case 'failed': return 'Failed'
    case 'frozen': return 'Frozen'
    case 'queued': return 'Queued'
    case 'killed': case 'halted': return 'Stopped'
  }
}

/** Distinct production agents; restarts add runs, not agents. */
export function agentCount(runs: Pick<Run, 'agent' | 'env'>[]) {
  return new Set(runs.filter((run) => run.env === 'prod').map((run) => run.agent)).size
}

/** Current production run per agent, independent of API ordering or historical success. */
export function latestProductionRuns(runs: Run[]): Run[] {
  return groupByAgent(runs.filter((run) => run.env === 'prod').sort((a, b) =>
    Date.parse(b.started_at) - Date.parse(a.started_at) || b.id.localeCompare(a.id, undefined, { numeric: true }))).map(({ runs }) => runs[0])
}

export function healthyAgents(runs: Run[]) {
  return latestProductionRuns(runs).filter((run) => ['Working', 'Healthy'].includes(fleetStatus(run))).length
}

/** Runs grouped by agent, keeping input order: newest-first runs give newest-first groups. */
export function groupByAgent<T extends Pick<Run, 'agent'>>(runs: T[]) {
  const groups = new Map<string, T[]>()
  for (const run of runs) groups.set(run.agent, [...(groups.get(run.agent) ?? []), run])
  return [...groups].map(([agent, runs]) => ({ agent, runs }))
}

/** Only the baseline incident replay, never bisection or fix verification. */
export function sandboxStatus(incident: Incident | undefined, events: MirageEvent[]): string | undefined {
  if (!incident) return
  switch (baselineEvidence(incident, events).status) {
    case 'queued': return 'Sandbox replay queued'
    case 'starting': return 'Sandbox replay starting'
    case 'running': return 'Sandbox replay running'
    case 'completed': return 'Sandbox replay complete'
    case 'failed': return 'Sandbox replay failed'
  }
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

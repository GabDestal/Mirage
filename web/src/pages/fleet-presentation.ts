import type { Incident, MirageEvent, Run } from '../api/client'

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
  for (const event of events) {
    const p = event.payload as Record<string, unknown>
    if (event.incident_id !== incident.id && p.incident_id !== incident.id) continue
    if (p.removed_input_id || p.purpose === 'verify') continue
    switch (event.type) {
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

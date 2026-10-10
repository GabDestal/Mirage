import type { Incident, MirageEvent } from '../api/client'

export type IncidentAction = 'detonate' | 'find_cause' | 'send_fix'
export const INCIDENT_ACTIONS = {
  detonate: { path: 'detonate', label: 'Detonate', effect: 'Replay this snapshot in Mirage. Tool writes are captured, never sent to real services.', reason: 'Investigate the blocked action in Mirage.' },
  find_cause: { path: 'bisect', label: 'Find the cause', effect: 'Remove one untrusted input at a time and replay the snapshot to test what caused the compromise.', reason: 'Find which input caused the confirmed compromise.' },
  send_fix: { path: 'handoff', label: 'Hand off to coding agent', effect: 'Open the fix prompt for your coding agent. Mirage does not write the fix.', reason: 'Hand off to coding agent' },
} as const

export function incidentEvents(events: MirageEvent[], id: string) {
  return events.filter((e) => e.incident_id === id || e.payload.incident_id === id)
}

export function isIncidentAction(action: Incident['next_action']): action is IncidentAction {
  return action === 'detonate' || action === 'find_cause' || action === 'send_fix'
}

export function safeLink(value: string | null | undefined) {
  if (!value) return undefined
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined
  } catch { return undefined }
}

export function latestFailure(events: MirageEvent[], stage: 'detonation' | 'bisection') {
  const types = stage === 'detonation'
    ? ['detonation.started', 'detonation.failed', 'verdict.ready', 'fix.verified']
    : ['bisection.step', 'bisection.completed']
  const event = events.findLast((e) => types.includes(e.type))
  return typeof event?.payload.error === 'string' ? event.payload.error : undefined
}

export function requestFinished(events: MirageEvent[], kind: IncidentAction, after: number) {
  const terminal = kind === 'detonate' ? ['verdict.ready', 'detonation.failed']
    : kind === 'find_cause' ? ['bisection.completed'] : ['handoff.created']
  return events.some((e) => e.seq > after && terminal.includes(e.type))
}

export function fixEvidence(events: MirageEvent[]) {
  const payload = events.findLast((e) => e.type === 'fix.verified')?.payload
  if (!payload || typeof payload.passed !== 'boolean' || typeof payload.attack_blocked !== 'string'
    || typeof payload.legit_task_completed !== 'string') return undefined
  return { passed: payload.passed, attack: payload.attack_blocked, legitimate: payload.legit_task_completed }
}

export function recordedHandoff(events: MirageEvent[]) {
  const prompt = events.findLast((e) => e.type === 'handoff.created')?.payload.prompt
  return typeof prompt === 'string' && prompt.trim() ? prompt : undefined
}

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
    ? ['detonation.started', 'detonation.completed', 'detonation.failed', 'verdict.ready']
    : ['bisection.step', 'bisection.completed']
  const event = (stage === 'detonation' ? detonationEvents(events, 'baseline') : events).findLast((e) => types.includes(e.type))
  return typeof event?.payload.error === 'string' ? event.payload.error : undefined
}

export function requestFinished(events: MirageEvent[], kind: IncidentAction, after: number) {
  const terminal = kind === 'detonate' ? ['verdict.ready', 'detonation.failed']
    : kind === 'find_cause' ? ['bisection.completed'] : ['handoff.created']
  return (kind === 'detonate' ? detonationEvents(events, 'baseline') : events).some((e) => e.seq > after && terminal.includes(e.type))
}

type ProofKind = 'baseline' | 'removal' | 'verify'
type ProofStatus = 'queued' | 'starting' | 'running' | 'completed' | 'failed'

function eventVerdict(p: MirageEvent['payload']): NonNullable<Incident['verdict']> | undefined {
  const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every((s) => typeof s === 'string')
  const blast = p.blast_radius
  if (typeof p.incident_id !== 'string' || typeof p.confirmed !== 'boolean' || typeof p.compromised_runs !== 'string'
    || !strings(p.policies_violated) || !blast || typeof blast !== 'object' || Array.isArray(blast)) return
  const b = blast as Record<string, unknown>
  if (typeof b.records !== 'number' || typeof b.summary !== 'string' || !strings(b.recipients) || !strings(b.secrets)) return
  return { incident_id: p.incident_id, confirmed: p.confirmed, compromised_runs: p.compromised_runs, policies_violated: p.policies_violated,
    blast_radius: { records: b.records, summary: b.summary, recipients: b.recipients, secrets: b.secrets } }
}

// Completion/effect/failure payloads omit purpose; bind them to their started job ID.
function detonationEvents(events: MirageEvent[], kind: ProofKind) {
  const kinds = new Map<unknown, ProofKind>()
  const purpose = (p: MirageEvent['payload']): ProofKind => p.removed_input_id ? 'removal' : p.purpose === 'verify' ? 'verify' : 'baseline'
  for (const event of events) {
    const p = event.payload
    const id = p.detonation_id ?? p.id
    if (id && (event.type === 'detonation.started' || p.removed_input_id || p.purpose)) kinds.set(id, purpose(p))
  }
  let active: ProofKind = 'baseline'
  return events.filter((event) => {
    const p = event.payload
    if (event.type === 'detonation.started') active = purpose(p)
    if (event.type === 'fix.verified') return kind === 'verify'
    if (event.type === 'verdict.ready') return kind === 'baseline'
    if (!event.type.startsWith('detonation.')) return kind === 'baseline'
    const id = p.detonation_id ?? p.id
    return (kinds.get(id) ?? (p.removed_input_id || p.purpose ? purpose(p) : id ? 'baseline' : active)) === kind
  })
}

function replayDiagnostics(events: MirageEvent[], jobId: unknown) {
  if (typeof jobId !== 'string' || !jobId) return []
  return events.flatMap((e) => e.type === 'agent.message' && e.env === 'mirage' && e.payload.role === 'system'
    && typeof e.payload.text === 'string' && e.payload.text.startsWith(`${jobId}: replay `) ? [e.payload.text] : [])
}

export function baselineEvidence(incident: Incident, events: MirageEvent[]) {
  const baseline = detonationEvents(incidentEvents(events, incident.id), 'baseline')
  let status: ProofStatus | undefined
  let requestedRuns: number | undefined
  let jobId: string | undefined
  let error: string | undefined
  let ratio: string | undefined
  let verdict: Incident['verdict']
  let resultIsPrevious = false
  let effects: MirageEvent['payload'][] = []
  for (const event of baseline) {
    const p = event.payload
    switch (event.type) {
      case 'run.status':
        if (event.run_id === incident.run_id && p.actor === 'system' && p.from === 'frozen' && p.to === 'frozen'
          && p.reason === 'Automatic sandbox detonation queued (3 replays)') { status = 'queued'; error = undefined; resultIsPrevious = true }
        break
      case 'detonation.started':
        status = 'running'; error = undefined; effects = []
        resultIsPrevious = true
        jobId = typeof p.detonation_id === 'string' ? p.detonation_id : undefined
        requestedRuns = typeof p.n_runs === 'number' ? p.n_runs : undefined
        break
      case 'detonation.effect': effects.push(p); break
      case 'detonation.completed':
        status = 'completed'; error = undefined
        jobId = typeof p.id === 'string' ? p.id : jobId
        if (typeof p.n_runs === 'number') requestedRuns = p.n_runs
        if (Array.isArray(p.effects)) effects = p.effects.filter((e): e is MirageEvent['payload'] => !!e && typeof e === 'object' && !Array.isArray(e))
        break
      case 'detonation.failed':
        status = 'failed'; error = typeof p.error === 'string' ? p.error : 'The sandbox did not return proof.'
        resultIsPrevious = true
        break
      case 'verdict.ready':
        status = 'completed'; error = undefined
        resultIsPrevious = false
        ratio = typeof p.compromised_runs === 'string' ? p.compromised_runs : undefined
        verdict = eventVerdict(p)
        break
    }
  }
  status ??= incident.verdict ? 'completed' : incident.status === 'detonating'
    && !incidentEvents(events, incident.id).some((e) => e.type === 'detonation.started') ? 'starting' : undefined
  ratio ??= incident.verdict?.compromised_runs
  verdict ??= incident.verdict ?? undefined
  // n_runs is requested work; use the reported verdict ratio, never infer clean runs from effects.
  return { status, jobId, requestedRuns, error, ratio, verdict, resultIsPrevious: !!ratio && resultIsPrevious, effects,
    diagnostics: replayDiagnostics(baseline, jobId) }
}

export function verificationEvidence(events: MirageEvent[]) {
  const verification = detonationEvents(events, 'verify')
  const latest = verification.findLast((e) => ['detonation.started', 'detonation.completed', 'detonation.failed', 'fix.verified'].includes(e.type))
  if (!latest) return undefined
  const status: ProofStatus = latest.type === 'detonation.started' ? 'running' : latest.type === 'detonation.failed' ? 'failed' : 'completed'
  const requestedRuns = verification.findLast((e) => e.type === 'detonation.started')?.payload.n_runs
  const jobId = verification.findLast((e) => e.type === 'detonation.started')?.payload.detonation_id
  return { status, requestedRuns: typeof requestedRuns === 'number' ? requestedRuns : undefined,
    error: latest.type === 'detonation.failed' && typeof latest.payload.error === 'string' ? latest.payload.error : undefined,
    result: fixEvidence(verification), resultIsPrevious: latest.type !== 'fix.verified', diagnostics: replayDiagnostics(events, jobId) }
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

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

export function requestFinished(events: MirageEvent[], kind: IncidentAction, after: number, job?: SandboxJob, previousJobId?: string) {
  const purpose = kind === 'detonate' ? 'detonate' : kind === 'find_cause' ? 'bisect' : undefined
  if (purpose && job?.purpose === purpose && job.id !== previousJobId && ['completed', 'failed'].includes(job.status)) return true
  const terminal = kind === 'detonate' ? ['verdict.ready', 'detonation.failed']
    : kind === 'find_cause' ? ['bisection.completed'] : ['handoff.created']
  return (kind === 'detonate' ? detonationEvents(events, 'baseline') : events).some((e) => e.seq > after && terminal.includes(e.type))
}

type ProofKind = 'baseline' | 'removal' | 'verify'
type ProofStatus = 'queued' | 'starting' | 'running' | 'completed' | 'failed'
type SandboxJob = NonNullable<Incident['sandbox_job']>
const statusOrder = { queued: 0, starting: 0, running: 1, completed: 2, failed: 3 }
const proofKind = (purpose: unknown): ProofKind => purpose === 'verify' ? 'verify' : purpose === 'bisect' ? 'removal' : 'baseline'

function typedJob(value: unknown): SandboxJob | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return
  const p = value as Record<string, unknown>
  if (typeof p.id !== 'string' || typeof p.purpose !== 'string' || !['detonate', 'bisect', 'verify'].includes(p.purpose)
    || typeof p.status !== 'string' || !['queued', 'running', 'completed', 'failed'].includes(p.status)
    || typeof p.n_runs !== 'number' || !Number.isInteger(p.n_runs) || p.n_runs < 1 || p.n_runs > 10
    || (p.error != null && typeof p.error !== 'string')) return
  return value as SandboxJob
}

// A detail refresh can lag the stream; a restart failure can also arrive before its event.
export function currentSandboxJob(incident: Incident | undefined, events: MirageEvent[]) {
  const metadata = (incident ? incidentEvents(events, incident.id) : events).flatMap((e) => { const job = typedJob(e.payload.sandbox_job); return job ? [job] : [] })
  const streamed = metadata.at(-1)
  const stored = incident?.sandbox_job ?? undefined
  if (!streamed || !stored) return streamed ?? stored
  if (streamed.id === stored.id) return statusOrder[stored.status] > statusOrder[streamed.status] ? stored : streamed
  return metadata.some((job) => job.id === stored.id) ? streamed : stored
}

export function sandboxJobError(job: SandboxJob | undefined) {
  if (!job || job.status !== 'failed') return undefined
  const errors: Record<string, string> = {
    interrupted: 'The engine restarted before this sandbox job finished',
    stopped: 'The sandbox job was stopped',
    scheduling_failed: 'The engine could not schedule the sandbox job',
    execution_failed: 'The sandbox runner failed',
  }
  return job.error ? errors[job.error] ?? job.error : 'The sandbox job failed before returning proof'
}

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
function detonationEvents(events: MirageEvent[], kind: ProofKind, job?: SandboxJob) {
  const kinds = new Map<unknown, ProofKind>()
  const purpose = (p: MirageEvent['payload']): ProofKind => p.removed_input_id ? 'removal' : proofKind(p.purpose)
  if (job) kinds.set(job.id, proofKind(job.purpose))
  for (const event of events) {
    const p = event.payload
    const metadata = typedJob(p.sandbox_job)
    if (metadata) kinds.set(metadata.id, proofKind(metadata.purpose))
    const id = p.detonation_id ?? p.id
    if (id && (event.type === 'detonation.started' || p.removed_input_id || p.purpose)) kinds.set(id, purpose(p))
  }
  let active: ProofKind = 'baseline'
  return events.filter((event) => {
    const p = event.payload
    const metadata = typedJob(p.sandbox_job)
    if (metadata) { active = proofKind(metadata.purpose); return active === kind }
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
  const scoped = incidentEvents(events, incident.id)
  const current = currentSandboxJob(incident, scoped)
  const baseline = detonationEvents(scoped, 'baseline', current)
  let status: ProofStatus | undefined
  let requestedRuns: number | undefined
  let jobId: string | undefined
  let error: string | undefined
  let ratio: string | undefined
  let verdict: Incident['verdict']
  let resultIsPrevious = false
  let effects: MirageEvent['payload'][] = []
  const applyJob = (job: SandboxJob) => {
    if (job.id !== jobId) { effects = []; resultIsPrevious = !!ratio }
    jobId = job.id; requestedRuns = job.n_runs; status = job.status; error = sandboxJobError(job)
    if (job.status === 'queued' || job.status === 'running' || job.status === 'failed') resultIsPrevious = true
  }
  for (const event of baseline) {
    const p = event.payload
    const metadata = typedJob(p.sandbox_job)
    if (metadata) { applyJob(metadata); continue }
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
        jobId = typeof p.detonation_id === 'string' ? p.detonation_id : jobId
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
  if (current?.purpose === 'detonate' && (current.id !== jobId || !status || statusOrder[current.status] >= statusOrder[status])) applyJob(current)
  if (current && current.purpose !== 'detonate' && (status === 'queued' || status === 'running')) status = incident.verdict ? 'completed' : undefined
  status ??= incident.verdict ? 'completed' : incident.status === 'detonating'
    && !current && !scoped.some((e) => e.type === 'detonation.started') ? 'starting' : undefined
  ratio ??= incident.verdict?.compromised_runs
  verdict ??= incident.verdict ?? undefined
  // n_runs is requested work; use the reported verdict ratio, never infer clean runs from effects.
  return { status, jobId, requestedRuns, error, ratio, verdict, resultIsPrevious: !!ratio && resultIsPrevious, effects,
    diagnostics: replayDiagnostics(baseline, jobId) }
}

export function verificationEvidence(events: MirageEvent[], incident?: Incident) {
  const current = currentSandboxJob(incident, events)
  const verification = detonationEvents(events, 'verify', current)
  let status: ProofStatus | undefined
  let requestedRuns: number | undefined
  let jobId: string | undefined
  let error: string | undefined
  let resultIsPrevious = true
  const applyJob = (job: SandboxJob) => {
    if (job.id !== jobId || job.status !== 'completed') resultIsPrevious = true
    jobId = job.id; status = job.status; requestedRuns = job.n_runs; error = sandboxJobError(job)
  }
  for (const event of verification) {
    const p = event.payload
    const metadata = typedJob(p.sandbox_job)
    if (metadata) { applyJob(metadata); continue }
    if (event.type === 'detonation.started') {
      status = 'running'; jobId = typeof p.detonation_id === 'string' ? p.detonation_id : undefined
      requestedRuns = typeof p.n_runs === 'number' ? p.n_runs : undefined; error = undefined; resultIsPrevious = true
    } else if (event.type === 'detonation.failed') { status = 'failed'; error = typeof p.error === 'string' ? p.error : undefined; resultIsPrevious = true }
    else if (event.type === 'detonation.completed') { status = 'completed'; error = undefined }
    else if (event.type === 'fix.verified') { status = 'completed'; error = undefined; resultIsPrevious = false }
  }
  if (current?.purpose === 'verify' && (current.id !== jobId || !status || statusOrder[current.status] >= statusOrder[status])) applyJob(current)
  if (!status) return undefined
  return { status, requestedRuns, error, result: fixEvidence(verification), resultIsPrevious, diagnostics: replayDiagnostics(events, jobId) }
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

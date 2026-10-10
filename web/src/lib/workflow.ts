import type { GateDecision, MirageEvent, Run } from '../api/client'

export type TraceCallDetail = {
  callId: string
  tool: string
  args: Record<string, unknown>
  result: unknown
  error: string | null
  decision?: GateDecision
  blocked: boolean
  ts: string
  resultRecorded?: boolean
  released?: boolean
}

type Call = TraceCallDetail
export type ActivityState = 'pending' | 'allowed' | 'completed' | 'blocked' | 'error' | 'paused' | 'stopped' | 'unrecorded'
export const activityLabels: Record<ActivityState, string> = {
  pending: 'Checking action', allowed: 'Awaiting result', completed: 'Completed',
  blocked: 'Held before execution', error: 'Needs attention', paused: 'Paused · no result',
  stopped: 'Stopped · no result', unrecorded: 'Result not recorded',
}

export function activityState(call: Call, status: Run['status']): ActivityState {
  if (call.error !== null) return 'error'
  if (call.resultRecorded || call.result !== undefined) return 'completed'
  if (call.blocked && !call.released) return 'blocked'
  if (status === 'killed' || status === 'halted') return 'stopped'
  if (status === 'frozen') return 'paused'
  if (status === 'completed') return 'unrecorded'
  return call.decision?.decision === 'allow' || call.released ? 'allowed' : 'pending'
}

export function readableTool(tool: string): string {
  const words = tool.replace(/[_.-]+/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : 'Unnamed action'
}

function stageTitle(tool: string, agent: string): string {
  switch (tool) {
    case 'search_contacts': case 'crm_query': case 'get_contact':
      return agent.includes('outreach') ? 'Review leads' : 'Read customer context'
    case 'list_activities': case 'read_inbox': case 'search_emails':
      return agent.includes('outreach') ? 'Read their history' : 'Read messages'
    case 'send_email':
      return agent.includes('outreach') ? 'Send follow-ups' : 'Send email'
    case 'schedule_follow_up': case 'log_activity': case 'update_contact': case 'create_contact':
      return agent.includes('outreach') ? 'Arrange next steps' : 'Update customer records'
    case 'read_calendar': return 'Review calendar'
    case 'crm_export': case 'export_contacts': return 'Export customer records'
    case 'read_ticket': case 'read_attachment': case 'get_ticket': return 'Review support request'
    case 'list_invoices': case 'get_invoice': return 'Review invoices'
    case 'create_invoice': case 'send_invoice': case 'record_payment': case 'mark_reminded': return 'Update invoices'
    case 'list_pull_requests': case 'read_pull_request': case 'read_file': return 'Review changes'
    case 'submit_review': case 'post_inline_comment': case 'set_labels': case 'update_description': return 'Share review'
    default: return 'Other activity'
  }
}

export type WorkflowStage<T extends Call = Call> = { id: string; title: string; calls: T[] }
/** Activity areas, not a planned sequence. Each area's actions retain recorded order. */
export function buildWorkflow<T extends Call>(calls: T[], agent: string): WorkflowStage<T>[] {
  const stages: WorkflowStage<T>[] = []
  const byTitle = new Map<string, WorkflowStage<T>>()
  for (const call of calls) {
    const title = stageTitle(call.tool, agent)
    const stage = byTitle.get(title)
    if (stage) stage.calls.push(call)
    else {
      const next = { id: title, title, calls: [call] }
      byTitle.set(title, next)
      stages.push(next)
    }
  }
  return stages
}

export function stageState(stage: WorkflowStage, status: Run['status']): ActivityState {
  const states = stage.calls.map((call) => activityState(call, status))
  return ['blocked', 'error', 'paused', 'stopped', 'unrecorded', 'pending', 'allowed', 'completed']
    .find((state) => states.includes(state as ActivityState)) as ActivityState
}

export function actionSummary(call: Pick<Call, 'tool' | 'args'>): string {
  const args = call.args
  if (call.tool === 'send_email' && typeof args.to === 'string') return `Send email to ${args.to}`
  if ((call.tool === 'search_contacts' || call.tool === 'search_emails' || call.tool === 'crm_query') && typeof args.query === 'string' && args.query)
    return `Search for “${args.query}”`
  if (call.tool === 'read_calendar' && typeof args.day === 'string') return `Review calendar for ${args.day}`
  if (call.tool === 'schedule_follow_up' && typeof args.send_on === 'string') return `Schedule follow-up for ${args.send_on}`
  const labels: Record<string, string> = {
    get_contact: 'Read contact profile', search_contacts: 'Find customer records', crm_query: 'Find customer records',
    list_activities: 'Review past interactions', log_activity: 'Record follow-up',
    read_inbox: 'Read incoming messages', search_emails: 'Find messages',
    update_contact: 'Update customer record', create_contact: 'Add contact',
    read_ticket: 'Read support request', get_ticket: 'Read support request', read_attachment: 'Read attachment',
  }
  if (Object.hasOwn(labels, call.tool)) return labels[call.tool]
  return readableTool(call.tool)
}

const FACT_FIELDS = ['name', 'email', 'company', 'to', 'subject', 'query', 'day', 'send_on', 'contact_id', 'invoice_id', 'title', 'start', 'due', 'summary', 'stage']
export function activityFacts(value: unknown): [string, string][] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  const record = value as Record<string, unknown>
  return FACT_FIELDS.flatMap((key) => typeof record[key] === 'string' || typeof record[key] === 'number'
    ? [[readableTool(key), String(record[key])] as [string, string]] : [])
}

export function buildTraceCalls(events: MirageEvent[], runId: string): TraceCallDetail[] {
  const map = new Map<string, TraceCallDetail>()
  const ownEvents = events.filter((event) => event.run_id === runId
    || (event.type === 'human.action' && event.payload.target === runId))
  // Replay fixtures can deliver a decision/result before its request; attach them in a second pass.
  for (const event of ownEvents) {
    if (event.type !== 'tool.requested') continue
    const p = event.payload
    const callId = String(p.call_id)
    if (!map.has(callId)) map.set(callId, {
      callId, tool: String(p.tool), args: (p.args as Record<string, unknown>) || {},
      result: undefined, error: null, blocked: false, ts: event.ts,
    })
  }
  for (const event of ownEvents) {
    const p = event.payload
    if ((event.type === 'human.action' && p.action === 'unfreeze')
      || (event.type === 'run.status' && p.from === 'frozen' && p.to === 'running')) {
      for (const call of map.values()) if (call.blocked) call.released = true
    }
    const existing = map.get(String(p.call_id))
    if (!existing) continue
    if (event.type === 'gate.decision') {
      existing.decision = p as GateDecision
      if (p.decision !== 'allow') { existing.blocked = true; existing.released = false }
      else if (existing.blocked) existing.released = true
    } else if (event.type === 'tool.result') {
      existing.result = p.result
      existing.error = typeof p.error === 'string' ? p.error : null
      existing.resultRecorded = true
    }
  }
  return Array.from(map.values()).sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts))
}

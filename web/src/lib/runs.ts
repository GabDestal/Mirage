// Plain-words status for runs (DESIGN.md §2, §8): the avatar state, the row sentence, the header sentence.
import type { GateDecision, Incident, MirageEvent, Run } from '@/api/client'
import type { AvatarState } from '@/components/avatar'

export function agentName(agent: string) {
  const words = agent.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** "Meeting assistant", or "Meeting assistant, run 2" when the same agent has several runs. */
export function runLabel(run: Run, runs: Run[]) {
  const name = agentName(run.agent)
  const siblings = runs.filter((r) => r.agent === run.agent)
  return siblings.length > 1 ? `${name}, run ${Number(run.id.replace(/\D/g, '')) || run.id}` : name
}

export function avatarState(run: Pick<Run, 'status' | 'env'>): AvatarState {
  if (run.env === 'mirage' && run.status === 'running') return 'mirage'
  switch (run.status) {
    case 'running':
      return 'working'
    case 'frozen':
      return 'frozen'
    case 'killed':
    case 'halted':
    case 'failed':
      return 'killed'
    default:
      return 'idle' // queued, completed
  }
}

const URGENCY: AvatarState[] = ['frozen', 'waiting', 'mirage', 'working', 'idle', 'killed']
/** One agent, many runs: the sidebar shows the most urgent state. */
export const mostUrgent = (states: AvatarState[]) =>
  URGENCY.find((s) => states.includes(s)) ?? 'idle'

export type Step = { callId: string; tool: string; blocked: boolean; ts: string }

/** Tool calls of one run, in order, with the gate's verdict folded in. */
export function steps(events: MirageEvent[], runId: string): Step[] {
  const out: Step[] = []
  for (const e of events) {
    if (e.run_id !== runId) continue
    const p = e.payload as Record<string, unknown>
    if (e.type === 'tool.requested') {
      out.push({ callId: String(p.call_id), tool: String(p.tool), blocked: false, ts: e.ts })
    } else if (e.type === 'gate.decision' && p.decision !== 'allow') {
      const step = out.find((s) => s.callId === p.call_id)
      if (step) step.blocked = true
    }
  }
  return out
}

export function blockedCall(events: MirageEvent[], runId: string) {
  let last: { decision: GateDecision; ts: string } | undefined
  for (const e of events) {
    const p = e.payload as GateDecision
    if (e.run_id === runId && e.type === 'gate.decision' && p.decision !== 'allow') last = { decision: p, ts: e.ts }
  }
  return last
}

/** "email attacker@evil.com" for a call with a `to`, else "run export_contacts". */
export function callPhrase(d: Pick<GateDecision, 'tool' | 'args'>) {
  const to = (d.args as Record<string, unknown>).to
  return typeof to === 'string' ? `email ${to}` : `run ${d.tool}`
}

export function relTime(iso: string | null | undefined, now: number) {
  if (!iso) return ''
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
  if (s < 60) return `${s} s ago`
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  return `${Math.round(s / 3600)} h ago`
}

/** The one-line state under the run name. `tone: 'alarm'` only for frozen. */
export function rowSentence(run: Run, events: MirageEvent[]): { text: string; tone?: 'alarm' } {
  const last = steps(events, run.id).at(-1)
  switch (run.status) {
    case 'queued':
      return { text: 'Queued' }
    case 'running':
      return { text: last ? `Working · ${last.tool}` : 'Starting' }
    case 'completed':
      return { text: 'Done' }
    case 'failed':
      return { text: run.status_reason || 'Run failed', tone: 'alarm' }
    case 'frozen': {
      const b = blockedCall(events, run.id)
      if (!b) return { text: 'Frozen', tone: 'alarm' }
      const frozenAt = events.findLast((e) => e.run_id === run.id && e.type === 'run.status')?.ts ?? b.ts
      const asked = events.find((e) => e.type === 'tool.requested' && (e.payload as { call_id?: string }).call_id === b.decision.call_id)
      const secs = asked ? ((Date.parse(frozenAt) - Date.parse(asked.ts)) / 1000).toFixed(1) : null
      return {
        text: `Frozen${secs ? ` in ${secs} s` : ''}. It tried to ${callPhrase(b.decision)}.`,
        tone: 'alarm',
      }
    }
    case 'killed':
    case 'halted': {
      const change = events.findLast((e) => e.run_id === run.id && e.type === 'run.status')
      const actor = (change?.payload as { actor?: string } | undefined)?.actor
      if (run.status === 'halted') return { text: 'Stopped by Stop all' }
      return { text: actor ? `Stopped by ${agentName(actor)}` : 'Stopped' }
    }
  }
}

/** The header status sentence: the status, in words (DESIGN.md §7). */
export function fleetSentence(runs: Run[]) {
  if (!runs.length) return 'No agents are running.'
  const frozen = runs.filter((r) => r.status === 'frozen')
  const working = runs.filter((r) => r.status === 'running' || r.status === 'queued')
  const others = working.length
  const keep = others === 0 ? 'Nothing else is running.' : `${others} ${others === 1 ? 'other keeps' : 'others keep'} working.`
  if (frozen.length === 1) return `${runLabel(frozen[0], runs)} is frozen. ${keep}`
  if (frozen.length > 1) return `${frozen.length} runs are frozen. ${keep}`
  if (runs.every((r) => r.status === 'halted')) return 'Everything is stopped.'
  const failed = runs.filter((r) => r.status === 'failed').length
  if (failed) {
    const ongoing = others ? `${others} ${others === 1 ? 'agent is' : 'agents are'} working.` : 'Nothing else is running.'
    return `${failed} ${failed === 1 ? 'run' : 'runs'} failed. ${ongoing}`
  }
  if (others && others === runs.length) return `All ${others} agents are working.`
  if (others) return `${others} ${others === 1 ? 'agent is' : 'agents are'} working. The rest are done.`
  return 'All runs are done.'
}

/** Stop all is on until a later `global.stop_lifted` (/demo/reset clears the log). */
export const stopOn = (events: MirageEvent[]) =>
  events.findLast((e) => ['global.stop', 'global.stop_lifted'].includes(e.type))?.type === 'global.stop'

// Detonation proved the run compromised: unfreeze and resume are refused from here on.
const CONFIRMED = ['confirmed', 'bisecting', 'root_caused', 'fix_pending', 'fix_verified', 'pr_open', 'merged']

/** A halted run that was not restarted yet can be resumed. Returns why the Resume button is disabled, or null. */
export function resumeBlock(run: Run, incidents: Incident[]) {
  const incident = incidents.find((i) => i.id === run.incident_id)
  if (incident?.status === 'detonating') return 'Detonation is running. Wait for the verdict.'
  if (incident && (CONFIRMED.includes(incident.status) || incident.verdict?.confirmed))
    return 'Detonation confirmed this run is compromised. Fix it, then approve a clean restart.'
  return null
}

/** Resume shows only on a halted run that has no restart yet. */
export const canResume = (run: Run, runs: Run[]) =>
  run.status === 'halted' && !runs.some((r) => r.restarted_from === run.id)

/** Resume all has work to do: Stop all is on, or a halted run can resume. */
export const resumeAllOn = (runs: Run[], incidents: Incident[], events: MirageEvent[]) =>
  stopOn(events) || runs.some((r) => canResume(r, runs) && !resumeBlock(r, incidents))

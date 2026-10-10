/// <reference types="node" />
// Run: node --experimental-strip-types src/pages/fleet-presentation.selfcheck.ts
import assert from 'node:assert/strict'
import { fleetActivity, fleetStatus, healthyAgents, sandboxStatus } from './fleet-presentation.ts'
import type { Incident, MirageEvent, Run } from '../api/client'
const run = (status: Run['status'], env: Run['env'] = 'prod') => ({ status, env } as Run)
assert.equal(fleetStatus(run('completed')), 'Healthy')
assert.equal(fleetStatus(run('running')), 'Working')
assert.equal(fleetStatus(run('killed')), 'Stopped')
assert.equal(fleetStatus(run('halted')), 'Stopped')
assert.equal(fleetStatus(run('queued')), 'Queued')
assert.equal(fleetStatus(run('frozen')), 'Frozen')
assert.equal(healthyAgents([run('completed'), run('running'), run('frozen'), run('queued'), run('halted'), run('completed', 'mirage')]), 2)
const incident: Incident = { id: 'inc_test', run_id: 'run_test', status: 'open', verdict: null,
  opened_at: '2026-10-10T12:00:00Z', snapshot_id: 'snap_test', inputs: [], bisection: [], next_action: 'detonate',
  trigger: { call_id: 'held', tool: 'send_email', args: { to: 'attacker@evil-corp-demo.com' }, decision: 'freeze', layer: 'hard_rule', explanation: 'Destination not allowed' } }
const event = (type: MirageEvent['type'], payload = {}, id = incident.id) => ({ type, payload, incident_id: id } as MirageEvent)
assert.equal(sandboxStatus(incident, []), undefined)
assert.equal(sandboxStatus({ ...incident, status: 'detonating' }, []), 'Sandbox replay starting')
assert.equal(sandboxStatus(incident, [event('detonation.started')]), 'Sandbox replay running')
assert.equal(sandboxStatus(incident, [event('detonation.started'), event('detonation.completed')]), 'Sandbox replay complete')
assert.equal(sandboxStatus(incident, [event('detonation.failed'), event('detonation.started')]), 'Sandbox replay running')
assert.equal(sandboxStatus(incident, [event('detonation.started'), event('detonation.failed')]), 'Sandbox replay failed')
assert.equal(sandboxStatus(incident, [event('detonation.started', {}, 'inc_other')]), undefined)
assert.equal(sandboxStatus(incident, [event('detonation.started', { removed_input_id: 'input_1' })]), undefined)
assert.equal(sandboxStatus(incident, [event('detonation.started', { purpose: 'verify' })]), undefined)
console.log('Fleet status and replay evidence checks passed')

assert.equal(sandboxStatus(incident, [event('detonation.failed'), event('detonation.started', { purpose: 'verify', detonation_id: 'fix' }), event('detonation.completed', { id: 'fix' })]), 'Sandbox replay failed')
const active = { ...run('running'), id: 'run_test', agent: 'outreach' } as Run
const own = (type: MirageEvent['type'], call_id: string, payload = {}) => ({ ...event(type, { call_id, ...payload }), run_id: active.id, ts: '2026-10-10T12:00:00Z' })
const activityEvents = [own('tool.requested', 'c1', { tool: 'search_contacts', args: {} }), own('tool.result', 'c1', { result: [], error: null }),
  own('tool.requested', 'c2', { tool: 'search_contacts', args: {} }), own('gate.decision', 'c2', { decision: 'allow' })]
let summary = fleetActivity(active, activityEvents)
assert.equal(summary.title, 'Review leads · 2 actions')
assert.equal(summary.results, '1 returned · 1 awaiting result')
assert.equal(summary.blocked, undefined)
assert.equal(fleetActivity({ ...active, status: 'completed' }, activityEvents).results, '1 returned · 1 result missing')
const blockedEvents = [...activityEvents, own('tool.requested', 'c3', { tool: 'send_email', args: { to: 'attacker@evil-corp-demo.com' } }), own('gate.decision', 'c3', { decision: 'block' }),
  own('tool.requested', 'c4', { tool: 'vendor_unknown_tool', args: {} })]
summary = fleetActivity({ ...active, status: 'frozen' }, blockedEvents)
assert.equal(summary.title, 'Other activity · 1 action')
assert.equal(summary.results, '1 paused')
assert.equal(summary.blocked, 'Blocked: Send email to attacker@evil-corp-demo.com')
assert.equal(summary.detail, 'Vendor unknown tool')
assert.equal(fleetActivity(active, [...blockedEvents, own('run.status', '', { from: 'frozen', to: 'running' })]).blocked, 'Previously blocked: Send email to attacker@evil-corp-demo.com')
assert.equal(fleetActivity(active, [own('tool.requested', 'c1', { tool: 'list_invoices' }), own('tool.result', 'c1', { result: null, error: 'Unavailable' })]).results, '1 failed')
assert.equal(fleetActivity(active, []).title, 'No actions recorded')
assert.equal(fleetActivity({ ...active, status: 'frozen' }, [], incident).blocked, 'Blocked: Send email to attacker@evil-corp-demo.com')
console.log('Fleet grouping, blocked action and missing-result checks passed')

const queued = { ...event('run.status', { actor: 'system', from: 'frozen', to: 'frozen', reason: 'Automatic sandbox detonation queued (3 replays)' }), run_id: incident.run_id }
assert.equal(sandboxStatus(incident, [queued]), 'Sandbox replay queued')
assert.equal(sandboxStatus(incident, [queued, event('detonation.started')]), 'Sandbox replay running')
assert.equal(sandboxStatus(incident, [queued, event('detonation.failed')]), 'Sandbox replay failed')
assert.equal(sandboxStatus(incident, [{ ...queued, run_id: 'other' }]), undefined)
assert.equal(sandboxStatus(incident, [{ ...queued, payload: { ...queued.payload, actor: 'Liam' } }]), undefined)
assert.equal(sandboxStatus(incident, [{ ...queued, payload: { ...queued.payload, reason: 'Manual freeze' } }]), undefined)
console.log('Target-bound automatic replay queue checks passed')

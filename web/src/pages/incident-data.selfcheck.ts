/// <reference types="node" />
// Run: node --experimental-strip-types src/pages/incident-data.selfcheck.ts
import assert from 'node:assert/strict'
import { fixEvidence, INCIDENT_ACTIONS, incidentEvents, isIncidentAction, latestFailure, recordedHandoff, requestFinished, safeLink } from './incident-data.ts'
import type { MirageEvent } from '../api/client'
const event = (seq: number, type: MirageEvent['type'], payload = {}, incident_id: string | null = 'inc_test'): MirageEvent => ({ seq, type, payload, incident_id, run_id: null, env: 'mirage', ts: '2026-10-10T12:00:00Z' })
assert.equal(INCIDENT_ACTIONS.find_cause.path, 'bisect')
assert.equal(INCIDENT_ACTIONS.send_fix.path, 'handoff')
assert.equal(isIncidentAction('open_pr'), false)
assert.equal(isIncidentAction('none'), false)
assert.equal(safeLink('javascript:alert(1)'), undefined)
assert.equal(safeLink('/relative'), undefined)
assert.equal(safeLink('https://github.com/team/repo/pull/1'), 'https://github.com/team/repo/pull/1')
const events = [event(1, 'detonation.failed', { error: 'Sandbox unavailable' }), event(2, 'detonation.started'), event(3, 'verdict.ready')]
assert.equal(latestFailure(events.slice(0, 1), 'detonation'), 'Sandbox unavailable')
assert.equal(latestFailure(events, 'detonation'), undefined)
assert.equal(requestFinished(events, 'detonate', 3), false) // An old result cannot finish a new request.
assert.equal(requestFinished(events, 'detonate', 2), true)
assert.equal(requestFinished(events, 'find_cause', 0), false) // A replay verdict cannot finish bisection.
assert.equal(requestFinished([event(4, 'bisection.completed', { error: 'Failed' })], 'find_cause', 3), true)
assert.equal(latestFailure([event(4, 'bisection.completed', { error: 'Failed' })], 'bisection'), 'Failed')
assert.deepEqual(incidentEvents([event(1, 'verdict.ready'), event(2, 'human.action', { incident_id: 'inc_test' }, null), event(3, 'verdict.ready', {}, 'inc_other')], 'inc_test').map((e) => e.seq), [1, 2])
assert.equal(fixEvidence([event(1, 'fix.verified', { passed: 'true' })]), undefined)
assert.deepEqual(fixEvidence([event(1, 'fix.verified', { passed: false, attack_blocked: '1/3', legit_task_completed: '3/3' })]), { passed: false, attack: '1/3', legitimate: '3/3' })
assert.equal(fixEvidence([event(1, 'verdict.ready', { confirmed: true })]), undefined) // Confirmation is not fix verification.
assert.equal(recordedHandoff([event(1, 'handoff.created', { prompt: 'Use the same snapshot.' })]), 'Use the same snapshot.')
assert.equal(recordedHandoff([event(1, 'handoff.created', { prompt: 123 })]), undefined)
console.log('Incident evidence self-check passed.')

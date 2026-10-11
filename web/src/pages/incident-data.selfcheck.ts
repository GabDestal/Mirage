/// <reference types="node" />
// Run: node --experimental-strip-types src/pages/incident-data.selfcheck.ts
import assert from 'node:assert/strict'
import { baselineEvidence, currentSandboxJob, fixEvidence, INCIDENT_ACTIONS, incidentEvents, isIncidentAction, latestFailure, recordedHandoff, requestFinished, safeLink, verificationEvidence } from './incident-data.ts'
import type { Incident, MirageEvent } from '../api/client'
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

const incident = { id: 'inc_test', run_id: 'run_test', status: 'open', verdict: null } as Incident
const baseline = [event(10, 'detonation.started', { detonation_id: 'base', n_runs: 3 }),
  event(11, 'detonation.effect', { detonation_id: 'base', run_index: 1, step: 1, tool: 'send_email' }),
  event(12, 'detonation.completed', { id: 'base', n_runs: 3, compromised_runs: 1, effects: [{ detonation_id: 'base', run_index: 1, step: 1, tool: 'send_email' }] }),
  event(13, 'verdict.ready', { compromised_runs: '1/2', confirmed: true })]
assert.equal(baselineEvidence(incident, baseline).status, 'completed') // Gate job completed before Chat opened.
assert.equal(baselineEvidence(incident, baseline).ratio, '1/2') // Preserve a historical engine ratio; never invent 3/3.
assert.equal(baselineEvidence(incident, baseline).requestedRuns, 3)
assert.equal(baselineEvidence(incident, baseline).effects.length, 1) // Completed ledger replaces streamed duplicates.
const later = [...baseline,
  event(14, 'detonation.started', { detonation_id: 'removed', removed_input_id: 'input_1', n_runs: 2 }),
  event(15, 'detonation.effect', { detonation_id: 'removed', tool: 'clean_action' }),
  event(16, 'detonation.completed', { id: 'removed', removed_input_id: 'input_1', n_runs: 2, compromised_runs: 0 }),
  event(17, 'detonation.started', { detonation_id: 'verify', purpose: 'verify', n_runs: 3 }),
  event(18, 'detonation.effect', { detonation_id: 'verify', tool: 'fixed_action' }),
  event(19, 'detonation.completed', { id: 'verify', n_runs: 3, compromised_runs: 0 }),
  event(20, 'fix.verified', { passed: false, attack_blocked: '2/2', legit_task_completed: '1/2' })]
assert.deepEqual(baselineEvidence(incident, later), baselineEvidence(incident, baseline))
assert.equal(verificationEvidence(later)?.result?.attack, '2/2')
assert.equal(verificationEvidence(later)?.result?.passed, false)
const failedVerify = [...baseline, event(21, 'detonation.started', { detonation_id: 'verify2', purpose: 'verify' }), event(22, 'detonation.failed', { detonation_id: 'verify2', error: 'Runner crashed' })]
assert.equal(latestFailure(failedVerify, 'detonation'), undefined)
assert.equal(verificationEvidence(failedVerify)?.error, 'Runner crashed')
assert.equal(requestFinished(failedVerify, 'detonate', 13), false)
const crashed = [event(1, 'detonation.started', { detonation_id: 'crash', n_runs: 3 }), event(2, 'detonation.failed', { detonation_id: 'crash', error: '3 of 3 replays crashed' })]
assert.equal(baselineEvidence(incident, crashed).status, 'failed')
assert.equal(baselineEvidence(incident, crashed).error, '3 of 3 replays crashed')
assert.equal(baselineEvidence(incident, crashed).ratio, undefined) // Failure is never a clean 0/3.
assert.equal(baselineEvidence(incident, [event(1, 'detonation.completed', { id: 'base', n_runs: 3, compromised_runs: 1 })]).ratio, undefined) // Completion has no finished denominator.
assert.equal(baselineEvidence(incident, [event(1, 'detonation.started', { n_runs: 3 }), event(2, 'detonation.effect', { run_index: 1 })]).ratio, undefined) // Effects are not completed-run progress.
assert.equal(baselineEvidence(incident, [event(1, 'detonation.failed', { error: 'Retained failure' }, 'inc_other')]).status, undefined)
assert.equal(baselineEvidence({ ...incident, status: 'detonating' }, [event(1, 'detonation.started', { purpose: 'verify' })]).status, undefined)
assert.equal(baselineEvidence(incident, [...baseline, event(21, 'detonation.started', { detonation_id: 'retry' }), event(22, 'detonation.completed', { id: 'retry' })]).resultIsPrevious, true)
assert.equal(baselineEvidence(incident, [...baseline, event(21, 'detonation.failed', { error: 'Reservation failed' })]).resultIsPrevious, true)
assert.equal(latestFailure([event(1, 'detonation.failed', { error: 'Old failure' }), event(2, 'detonation.completed')], 'detonation'), undefined)
const freshVerdict = { incident_id: incident.id, confirmed: false, compromised_runs: '0/2', policies_violated: [], blast_radius: { records: 0, recipients: [], secrets: [], summary: 'Fresh clean replay' } }
assert.deepEqual(baselineEvidence(incident, [event(1, 'verdict.ready', freshVerdict)]).verdict, freshVerdict) // SSE proof can precede the detail-query refresh.
assert.equal(baselineEvidence(incident, [event(1, 'verdict.ready', { ...freshVerdict, blast_radius: null })]).verdict, undefined)
const crashDiagnostic = event(23, 'agent.message', { role: 'system', text: 'verify2: replay 2/3 crashed: Synthetic runner failure' })
assert.deepEqual(verificationEvidence([...failedVerify, crashDiagnostic])?.diagnostics, ['verify2: replay 2/3 crashed: Synthetic runner failure'])
assert.deepEqual(baselineEvidence(incident, [...failedVerify, crashDiagnostic]).diagnostics, [])
assert.equal(verificationEvidence([...later, event(21, 'detonation.started', { detonation_id: 'verify_retry', purpose: 'verify' }), event(22, 'detonation.completed', { id: 'verify_retry' })])?.resultIsPrevious, true)
console.log('Persistent baseline, verification isolation and crash accounting checks passed.')

const job = (id: string, purpose: NonNullable<Incident['sandbox_job']>['purpose'], status: NonNullable<Incident['sandbox_job']>['status'], error: string | null = null) => ({ id, purpose, status, n_runs: 3, error })
assert.equal(baselineEvidence({ ...incident, sandbox_job: job('queued', 'detonate', 'queued') }, []).status, 'queued')
assert.equal(baselineEvidence({ ...incident, sandbox_job: job('lost', 'detonate', 'failed', 'interrupted') }, []).status, 'failed')
assert.match(baselineEvidence({ ...incident, sandbox_job: job('lost', 'detonate', 'failed', 'interrupted') }, []).error!, /restarted/)
assert.equal(baselineEvidence({ ...incident, status: 'detonating', sandbox_job: job('verify', 'verify', 'queued') }, []).status, undefined)
const reservedVerify = [event(1, 'agent.message', { sandbox_job: job('verify', 'verify', 'queued') }), event(2, 'detonation.failed', { detonation_id: 'verify', error: 'stopped' })]
assert.equal(baselineEvidence(incident, reservedVerify).status, undefined)
assert.equal(verificationEvidence(reservedVerify)?.status, 'failed')
assert.equal(verificationEvidence([], { ...incident, sandbox_job: job('verify', 'verify', 'queued') })?.status, 'queued')
const retryQueued = baselineEvidence({ ...incident, sandbox_job: job('retry', 'detonate', 'queued') }, baseline)
assert.equal(retryQueued.status, 'queued')
assert.equal(retryQueued.ratio, '1/2')
assert.equal(retryQueued.resultIsPrevious, true)
assert.equal(retryQueued.effects.length, 0) // Earlier effects cannot be called progress of a new job.
const typedCompleted = event(30, 'agent.message', { sandbox_job: job('base', 'detonate', 'completed') })
assert.equal(currentSandboxJob({ ...incident, sandbox_job: job('base', 'detonate', 'queued') }, [typedCompleted])?.status, 'completed')
assert.equal(currentSandboxJob({ ...incident, sandbox_job: job('base', 'detonate', 'failed', 'interrupted') }, [event(1, 'agent.message', { sandbox_job: job('base', 'detonate', 'running') })])?.status, 'failed')
assert.equal(currentSandboxJob({ ...incident, sandbox_job: job('old', 'detonate', 'completed') }, [event(1, 'agent.message', { sandbox_job: job('old', 'detonate', 'completed') }), event(2, 'agent.message', { sandbox_job: job('new', 'verify', 'queued') })])?.id, 'new')
assert.equal(requestFinished([], 'detonate', 20, job('new', 'detonate', 'failed'), 'old'), true)
assert.equal(requestFinished([], 'detonate', 20, job('old', 'detonate', 'failed'), 'old'), false)
assert.equal(requestFinished([], 'detonate', 20, job('new', 'verify', 'failed'), 'old'), false)
const typedVerdict = { ...incident, verdict: freshVerdict, sandbox_job: job('base', 'detonate', 'completed') }
assert.equal(baselineEvidence(typedVerdict, []).resultIsPrevious, false) // Detail-only proof of an external completed job is current.
const completedThenRetry = [...baseline, event(14, 'agent.message', { sandbox_job: job('retry', 'detonate', 'queued') }), event(15, 'agent.message', { sandbox_job: job('retry', 'detonate', 'failed', 'interrupted') })]
assert.equal(baselineEvidence(incident, completedThenRetry).ratio, '1/2')
assert.equal(baselineEvidence(incident, completedThenRetry).effects.length, 0)
assert.equal(baselineEvidence(incident, completedThenRetry).resultIsPrevious, true)
assert.equal(baselineEvidence(incident, completedThenRetry).status, 'failed')
assert.equal(baselineEvidence({ ...typedVerdict, sandbox_job: job('verify', 'verify', 'queued') }, [event(1, 'agent.message', { sandbox_job: job('base', 'detonate', 'queued') })]).status, 'completed')
assert.equal(baselineEvidence({ ...incident, sandbox_job: job('verify', 'verify', 'failed', 'execution_failed') }, []).status, undefined)
assert.equal(verificationEvidence([event(1, 'agent.message', { sandbox_job: job('verify', 'verify', 'failed', 'interrupted') })])?.status, 'failed')
assert.equal(verificationEvidence([...later, event(21, 'agent.message', { sandbox_job: job('verify_retry', 'verify', 'queued') })])?.resultIsPrevious, true)
assert.equal(verificationEvidence([...later, event(21, 'agent.message', { sandbox_job: job('verify', 'verify', 'completed') })])?.resultIsPrevious, false)
assert.equal(currentSandboxJob(typedVerdict, [event(1, 'agent.message', { sandbox_job: job('other', 'verify', 'queued') }, 'inc_other')])?.id, 'base')
console.log('Typed queued, restored failures, request identity and stale REST metadata checks passed.')

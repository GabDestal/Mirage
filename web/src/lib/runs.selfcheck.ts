/// <reference types="node" />
// Run: node --experimental-strip-types src/lib/runs.selfcheck.ts
import assert from 'node:assert/strict'
import { automaticClearanceText, canResume, resumeAllOn, resumeBlock, stopOn } from './runs.ts'
import type { Incident, MirageEvent, Run } from '../api/client'
const ev = (type: string) => ({ type } as MirageEvent)
const run = (id: string, status: Run['status'], extra: Partial<Run> = {}) => ({ id, status, incident_id: null, ...extra } as Run)
assert.equal(stopOn([]), false)
assert.equal(stopOn([ev('global.stop')]), true)
assert.equal(stopOn([ev('global.stop'), ev('run.status'), ev('global.stop_lifted')]), false)
assert.equal(stopOn([ev('global.stop'), ev('global.stop_lifted'), ev('global.stop')]), true)
const old = run('run_1', 'halted', { incident_id: 'inc_1' })
assert.equal(canResume(old, [old]), true)
assert.equal(canResume(old, [old, run('run_2', 'queued', { restarted_from: 'run_1' })]), false)
assert.equal(canResume(run('run_3', 'killed'), []), false)
assert.equal(resumeBlock(old, []), null)
assert.equal(resumeBlock(old, [{ id: 'inc_1', status: 'detonating' } as Incident]), 'Detonation is running. Wait for the verdict.')
assert.match(resumeBlock(old, [{ id: 'inc_1', status: 'confirmed' } as Incident])!, /compromised/)
assert.match(resumeBlock(old, [{ id: 'inc_1', status: 'open', verdict: { confirmed: true } } as Incident])!, /compromised/)
const bad = [{ id: 'inc_1', status: 'confirmed' } as Incident]
assert.equal(resumeAllOn([old], [], []), true)
assert.equal(resumeAllOn([old], bad, []), false)
assert.equal(resumeAllOn([old], bad, [ev('global.stop')]), true)
assert.equal(resumeAllOn([run('run_4', 'running')], [], []), false)
const medium = { id: 'inc_1', automatic_clearance: { status: 'checking', reason: 'initial_baseline' } } as Incident
assert.equal(automaticClearanceText(run('run_1', 'frozen', { incident_id: 'inc_1' }), medium), 'Checking in Mirage')
medium.automatic_clearance!.status = 'inconclusive'
assert.equal(automaticClearanceText(run('run_1', 'frozen', { incident_id: 'inc_1' }), medium), 'Still frozen')
assert.match(resumeBlock(old, [medium])!, /clean restart/)
medium.automatic_clearance!.status = 'cleared'
assert.equal(automaticClearanceText(run('run_1', 'frozen', { incident_id: 'inc_1' }), medium), null)
assert.equal(automaticClearanceText(run('run_1', 'running', { incident_id: 'inc_1' }), medium), 'Automatically resumed')
assert.equal(automaticClearanceText(run('run_1', 'halted', { incident_id: 'inc_1' }), medium), null)
assert.equal(automaticClearanceText(run('run_2', 'running'), medium), null)
console.log('runs selfcheck ok')

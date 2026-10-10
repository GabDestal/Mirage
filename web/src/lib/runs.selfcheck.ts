/// <reference types="node" />
// Run: node --experimental-strip-types src/lib/runs.selfcheck.ts
import assert from 'node:assert/strict'
import { canResume, resumeBlock, stopOn } from './runs.ts'
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
assert.equal(resumeBlock(old, [], false), null)
assert.match(resumeBlock(old, [], true)!, /Lift Stop all first/)
assert.match(resumeBlock(old, [{ id: 'inc_1', status: 'confirmed' } as Incident], false)!, /compromised/)
assert.match(resumeBlock(old, [{ id: 'inc_1', status: 'open', verdict: { confirmed: true } } as Incident], false)!, /compromised/)
console.log('runs selfcheck ok')

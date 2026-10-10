/// <reference types="node" />
// Run: node --experimental-strip-types src/pages/fleet-presentation.selfcheck.ts
import assert from 'node:assert/strict'
import { fleetStatus, healthyAgents, sandboxStatus } from './fleet-presentation.ts'
import type { Incident, MirageEvent, Run } from '../api/client'
const run = (status: Run['status'], env: Run['env'] = 'prod') => ({ status, env } as Run)
assert.equal(fleetStatus(run('completed')), 'Healthy')
assert.equal(fleetStatus(run('running')), 'Working')
assert.equal(fleetStatus(run('killed')), 'Stopped')
assert.equal(fleetStatus(run('halted')), 'Stopped')
assert.equal(fleetStatus(run('queued')), 'Queued')
assert.equal(fleetStatus(run('frozen')), 'Frozen')
assert.equal(healthyAgents([run('completed'), run('running'), run('frozen'), run('queued'), run('halted'), run('completed', 'mirage')]), 2)
const incident = { id: 'inc_test', status: 'open', verdict: null } as Incident
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

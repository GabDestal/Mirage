/// <reference types="node" />
// Run: node --experimental-strip-types src/components/repair-state.selfcheck.ts
import assert from 'node:assert/strict'
import { canSendRepair, prState, repairSettled } from './repair-state.ts'
import type { RepairJob } from '../api/repair'

const url = 'https://github.com/GabDestal/Mirage/pull/42'
const job = (patch: Partial<RepairJob>) => ({ id: 'repair_1', incident_id: 'inc_1', status: 'pr_open', pr_url: url,
  pull_request: { url, number: 42, headRefOid: 'b'.repeat(40), isDraft: true, state: 'OPEN' }, ...patch }) as RepairJob
const pr = (state: 'OPEN' | 'MERGED' | 'CLOSED') => job({ pull_request: { ...job({}).pull_request!, state } })

// The incident header renders "PR #42" plus exactly one state word.
assert.deepEqual(prState(pr('OPEN')), { state: 'OPEN', word: 'Open', url, number: 42 })
assert.equal(prState(pr('MERGED'))?.word, 'Merged')
assert.equal(prState(pr('CLOSED'))?.word, 'Closed')
assert.equal(prState(job({ status: 'verifying', pull_request: null })), null)
assert.equal(prState(job({ status: 'failed' })), null)
assert.equal(prState(job({ pull_request: { ...pr('OPEN').pull_request!, url: 'https://example.com/pull/42' } })), null)
// Polling continues while the PR is open; a closed PR (or failure) allows another repair.
assert.deepEqual([pr('OPEN'), pr('MERGED'), pr('CLOSED'), job({ status: 'running', pull_request: null }), job({ status: 'failed' })].map(repairSettled),
  [false, true, true, false, true])
assert.deepEqual([undefined, pr('OPEN'), pr('MERGED'), pr('CLOSED'), job({ status: 'failed' }), job({ status: 'running', pull_request: null })].map(canSendRepair),
  [true, false, false, true, true, false])
console.log('Repair PR state checks passed')

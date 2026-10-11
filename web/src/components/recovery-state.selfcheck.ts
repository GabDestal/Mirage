import assert from 'node:assert/strict'
import { recoveryMessage } from './recovery-state.ts'

assert.match(recoveryMessage({ status: 'queued', useful_task_completed: false }), /queued.*Waiting/)
assert.match(recoveryMessage({ status: 'running', useful_task_completed: false }), /is running/)
assert.match(recoveryMessage({ status: 'completed', useful_task_completed: false }), /has not been established/)
assert.match(recoveryMessage({ status: 'completed', useful_task_completed: true }), /exactly one expected prep brief/)
assert.match(recoveryMessage({ status: 'failed', useful_task_completed: false }), /failed or was contained/)
console.log('Recovery state truth checks passed')

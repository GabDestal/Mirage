// Run from web: node src/lib/workflow.selfcheck.mjs. No browser or new test framework.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { activityState, buildWorkflow, stageState } from './workflow.ts'

// Exercise the actual fold without loading the page's React/CSS dependencies in Node.
const source = readFileSync(new URL('../pages/trace.tsx', import.meta.url), 'utf8')
const fold = 'export ' + source.slice(source.indexOf('function buildTraceCalls'))
const compiled = ts.transpileModule(fold, { compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext } }).outputText
const { buildTraceCalls } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const event = (type, callId, payload = {}, offset = 0) => ({
  seq: offset + 1, ts: new Date(Date.UTC(2026, 9, 10, 12, 0, offset)).toISOString(),
  run_id: 'test', env: 'prod', type, payload: { call_id: callId, ...payload },
})
const request = (id, tool, offset) => event('tool.requested', id, { tool, args: {} }, offset)
const allowed = event('gate.decision', 'a', { decision: 'allow' })
const events = [request('a', 'search_contacts', 1), allowed]
let calls = buildTraceCalls(events, 'test')
assert.equal(activityState(calls[0], 'running'), 'allowed', 'Permission is not a result')
assert.equal(activityState(calls[0], 'completed'), 'unrecorded', 'Run completion does not invent a missing action result')
assert.equal(activityState(calls[0], 'frozen'), 'paused')
assert.equal(activityState(calls[0], 'killed'), 'stopped')
assert.equal(activityState(buildTraceCalls([events[0]], 'test')[0], 'running'), 'pending')
calls = buildTraceCalls([...events, event('tool.result', 'a', { result: null, error: null })], 'test')
assert.equal(activityState(calls[0], 'running'), 'completed', 'Null is a recorded result')
calls = buildTraceCalls([...events, event('tool.result', 'a', { result: null, error: 'Unavailable' })], 'test')
assert.equal(activityState(calls[0], 'completed'), 'error')
const mixed = [request('a', 'search_contacts', 1), request('b', 'get_contact', 2), request('c', 'send_email', 3),
  request('d', 'search_contacts', 4), request('e', 'vendor.unknown_tool', 5),
  event('gate.decision', 'c', { decision: 'freeze', explanation: 'Review destination' })]
calls = buildTraceCalls(mixed, 'test')
const stages = buildWorkflow(calls, 'outreach')
assert.deepEqual(stages.flatMap((stage) => stage.calls.map((call) => call.callId)).sort(), ['a', 'b', 'c', 'd', 'e'])
assert.deepEqual(stages.map((stage) => stage.title), ['Review leads', 'Send follow-ups', 'Other activity'])
assert.deepEqual(stages[0].calls.map((call) => call.callId), ['a', 'b', 'd'], 'Revisited group retains every action in order')
assert.equal(stageState(stages[1], 'frozen'), 'blocked')
assert.equal(activityState(buildTraceCalls([...mixed, event('human.action', null, { action: 'unfreeze' })], 'test')[2], 'running'), 'allowed')
assert.equal(activityState(buildTraceCalls([...mixed, event('tool.result', 'c', { result: 'sent' })], 'test')[2], 'running'), 'completed')
const reversed = [event('tool.result', 'a', { result: [] }), allowed, events[0]]
assert.equal(activityState(buildTraceCalls(reversed, 'test')[0], 'running'), 'completed', 'Replay result arriving before request is retained')
assert.equal(buildTraceCalls([...mixed, mixed[0]], 'test').length, 5, 'Duplicate request does not erase evidence')
assert.equal(buildTraceCalls(mixed, 'other').length, 0)
assert.equal(buildWorkflow(calls, 'meeting_assistant')[1].title, 'Send meeting brief')
assert.equal(buildWorkflow([buildTraceCalls([request('t', 'read_attachment', 0)], 'test')[0]], 'support')[0].title, 'Review support request')
const repeated = Array.from({ length: 26 }, (_, index) => request(`repeat-${index}`, ['get_contact', 'list_activities', 'send_email', 'schedule_follow_up'][index % 4], index))
const repeatedCalls = buildTraceCalls(repeated, 'test')
assert.equal(buildWorkflow(repeatedCalls, 'outreach').length, 4, 'Repeated outreach stays a compact overview')
assert.equal(buildWorkflow(repeatedCalls, 'outreach').flatMap((stage) => stage.calls).length, 26, 'Every repeated action remains inspectable')
assert.deepEqual(repeatedCalls.map((call) => call.callId), repeated.map((item) => item.payload.call_id), 'Full chronology preserves recorded action order')
console.log('Workflow selfcheck: 22 assertions passed')

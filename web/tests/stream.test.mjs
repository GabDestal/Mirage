import assert from 'node:assert/strict'
import { registerHooks } from 'node:module'
import { afterEach, beforeEach, test } from 'node:test'

// Node strips TS; Vite's extensionless local import needs the same resolution here.
registerHooks({ resolve(specifier, context, next) {
  if (specifier === './client' && context.parentURL?.endsWith('/api/stream.ts')) {
    return next('./client.ts', context)
  }
  return next(specifier, context)
} })
const { connect, disconnect, resetStream } = await import('../src/api/stream.ts')
const { queryClient } = await import('../src/api/client.ts')
const originalFetch = globalThis.fetch
const originalSource = globalThis.EventSource
const originalInvalidate = queryClient.invalidateQueries
let requests, sources, invalidations
let respond

class StubSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2
  readyState = 0
  listeners = new Map()
  constructor(url) { this.url = url; sources.push(this) }
  close() { this.readyState = 2; this.closed = true }
  addEventListener(type, listener) { this.listeners.set(type, listener) }
  open() { this.readyState = 1; this.onopen?.({}) }
  error(state = 0) { this.readyState = state; this.onerror?.({}) }
  message(event) { this.onmessage?.({ data: JSON.stringify(event) }) }
}
const event = (seq, type = 'run.status') => ({ seq, ts: '2026-10-11T08:00:00Z', type,
  run_id: 'synthetic-run', agent_id: 'synthetic-agent', env: 'prod', payload: {} })
const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve() }
const events = () => queryClient.getQueryData(['events']) ?? []
const health = () => queryClient.getQueryData(['connection'])
const eventReads = () => requests.filter((r) => r.url.startsWith('/api/events'))

beforeEach((t) => {
  disconnect()
  queryClient.clear()
  requests = []; sources = []; invalidations = []
  respond = () => Response.json([])
  globalThis.EventSource = StubSource
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init })
    return respond(String(url), init)
  }
  queryClient.invalidateQueries = async (options) => { invalidations.push(options) }
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'], now: 1_000_000 })
  resetStream()
  invalidations.length = 0
})
afterEach(() => {
  disconnect()
  queryClient.clear()
  globalThis.fetch = originalFetch
  globalThis.EventSource = originalSource
  queryClient.invalidateQueries = originalInvalidate
})

test('prolonged CONNECTING enters polling even if errors keep arriving', async (t) => {
  for (let i = 0; i < 8; i++) { sources[0].error(); t.mock.timers.tick(1000); await flush() }
  assert.ok(eventReads().length > 0, 'CONNECTING cannot hide current state forever')
  assert.equal(health().state, 'polling')
})

test('poll errors are visible and retain the last successful wall-clock sync', async (t) => {
  sources[0].error(2)
  t.mock.timers.tick(1000); await flush()
  const synced = health()?.lastSync
  assert.ok(synced)
  respond = () => { throw new Error('Engine unavailable') }
  t.mock.timers.tick(5000); await flush()
  assert.equal(health().state, 'disconnected')
  assert.match(health().error, /Engine unavailable/)
  assert.equal(health().lastSync, synced)
})

test('OPEN recovers from fallback, refreshes current state, and stops event polling', async (t) => {
  sources[0].error()
  t.mock.timers.tick(6000); await flush()
  sources[0].open(); await flush()
  const count = eventReads().length
  t.mock.timers.tick(5000); await flush()
  assert.equal(health().state, 'streaming')
  assert.equal(eventReads().length, count)
  assert.ok(invalidations.some((i) => i?.queryKey?.[0] === 'runs'))
  assert.ok(invalidations.some((i) => i?.queryKey?.[0] === 'incidents'))
})

test('disconnect closes SSE, cancels delayed refreshes, and ignores queued callbacks', async (t) => {
  sources[0].message(event(1))
  const late = sources[0].onmessage
  disconnect()
  late({ data: JSON.stringify(event(2)) })
  t.mock.timers.tick(20_000); await flush()
  assert.ok(sources[0].closed)
  assert.deepEqual(events().map((e) => e.seq), [1])
  assert.equal(invalidations.length, 0)
  assert.equal(eventReads().length, 0)
})

test('reset aborts inflight polling and fences a late old-generation result', async (t) => {
  let resolve
  respond = () => new Promise((r) => { resolve = r })
  sources[0].error(2)
  t.mock.timers.tick(1000); await flush()
  const request = eventReads()[0]
  assert.ok(request)
  resetStream()
  assert.equal(request.init?.signal?.aborted, true)
  resolve(Response.json([event(99)])); await flush()
  assert.deepEqual(events(), [])
})

test('SSE and catch-up duplicate events are applied once in sequence order', async (t) => {
  respond = () => Response.json([event(2), event(1), event(2)])
  sources[0].error(2)
  t.mock.timers.tick(1000); await flush()
  sources[0].message(event(2))
  assert.deepEqual(events().map((e) => e.seq), [1, 2])
})

test('disconnect aborts transport work and reconnect refreshes missed current state', async (t) => {
  let resolve
  respond = () => new Promise((r) => { resolve = r })
  sources[0].error(2)
  t.mock.timers.tick(1000); await flush()
  disconnect()
  assert.equal(eventReads()[0].init?.signal?.aborted, true)
  resolve(Response.json([event(50)])); await flush()
  assert.deepEqual(events(), [])
  respond = () => Response.json([])
  connect(); sources.at(-1).open(); await flush()
  assert.ok(invalidations.some((i) => i?.queryKey?.[0] === 'incidents'))
})

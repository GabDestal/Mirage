import assert from 'node:assert/strict'
import { registerHooks } from 'node:module'
import { afterEach, beforeEach, test } from 'node:test'
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import { QueryClientProvider } from '@tanstack/react-query'

// Node strips TS; Vite's extensionless local import needs the same resolution here.
registerHooks({ resolve(specifier, context, next) {
  if (['./client', './runtime'].includes(specifier) && /\/api\/(stream|runtime)\.ts$/.test(context.parentURL ?? '')) {
    return next(`${specifier}.ts`, context)
  }
  return next(specifier, context)
} })
const { connect, disconnect, resetStream } = await import('../src/api/stream.ts')
const { queryClient, useApprovals, useServiceView } = await import('../src/api/client.ts')
const originalFetch = globalThis.fetch
const originalSource = globalThis.EventSource
const originalInvalidate = queryClient.invalidateQueries
let requests, sources, invalidations
let respond
let runtime
const metadata = (epoch = 'epoch-1', last_seq = 0) => ({ engine_mode: 'live',
  instance_id: 'synthetic-instance', stream_epoch: epoch, last_seq, revision: null, owned_run_ids: ['synthetic-run'] })

class StubSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2
  readyState = 0
  listeners = new Map()
  constructor(url) { this.url = url; sources.push(this) }
  close() { this.readyState = 2; this.closed = true }
  addEventListener(type, listener) { this.listeners.set(type, listener) }
  open() { this.readyState = 1; this.onopen?.({}); this.runtime() }
  error(state = 0) { this.readyState = state; this.onerror?.({}) }
  message(event) { this.onmessage?.({ data: JSON.stringify(event) }) }
  runtime(info = runtime) { this.listeners.get('runtime')?.({ data: JSON.stringify(info) }) }
}
const event = (seq, type = 'run.status') => ({ seq, ts: '2026-10-11T08:00:00Z', type,
  run_id: 'synthetic-run', incident_id: null, env: 'prod', payload: {} })
const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve() }
const events = () => queryClient.getQueryData(['events']) ?? []
const health = () => queryClient.getQueryData(['connection'])
const eventReads = () => requests.filter((r) => r.url.startsWith('/api/events'))

beforeEach((t) => {
  disconnect()
  queryClient.clear()
  requests = []; sources = []; invalidations = []
  runtime = metadata()
  respond = () => Response.json([])
  globalThis.EventSource = StubSource
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init })
    if (String(url) === '/api/runtime') return Response.json(runtime)
    const response = await respond(String(url), init)
    if (!response.headers.has('X-Mirage-Stream-Epoch')) response.headers.set('X-Mirage-Stream-Epoch', runtime.stream_epoch)
    return response
  }
  queryClient.invalidateQueries = async (options) => { invalidations.push(options) }
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'], now: 1_000_000 })
  resetStream()
  sources[0].runtime()
  invalidations.length = 0
})
afterEach(() => {
  assert.ok(requests.every((r) => !r.init?.method || r.init.method === 'GET'), 'Recovery only performs reads')
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
  assert.equal(health().runtime, null, 'Unavailable sync cannot claim live ownership')
  respond = () => Response.json([])
  t.mock.timers.tick(1000); await flush()
  assert.equal(health().state, 'polling')
  assert.equal(health().error, null)
  assert.deepEqual(health().runtime.owned_run_ids, ['synthetic-run'])
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
  assert.equal(health().runtime, null, 'Disconnected consumers must lose ownership')
  assert.deepEqual(events().map((e) => e.seq), [1])
  assert.equal(invalidations.length, 0)
  assert.equal(eventReads().length, 0)
  assert.equal(requests.length, 0, 'Runtime probes and timeout work also stop')
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

test('CONNECTING falls back without requiring an error notification', async (t) => {
  t.mock.timers.tick(4000); await flush()
  assert.ok(eventReads().length > 0)
})

test('missing EventSource keeps the same read-only polling path', async (t) => {
  disconnect()
  globalThis.EventSource = undefined
  connect(); t.mock.timers.tick(1000); await flush()
  assert.equal(health().state, 'polling')
  assert.ok(eventReads().length > 0)
  assert.ok(requests.every((r) => !r.init?.method || r.init.method === 'GET'))
})

test('an unresolved poll does not overlap and times out visibly before retrying', async (t) => {
  respond = () => new Promise(() => {})
  sources[0].error(2)
  t.mock.timers.tick(2000); await flush()
  assert.equal(eventReads().length, 1)
  t.mock.timers.tick(4000); await flush()
  assert.equal(eventReads()[0].init.signal.aborted, true)
  assert.match(health().error, /timed out/)
  assert.equal(health().runtime, null)
  t.mock.timers.tick(1000); await flush()
  assert.ok(eventReads().length > 1)
})

test('reset cancels a stale TanStack run read even when fetch ignores abort', async () => {
  let resolve
  respond = () => new Promise((r) => { resolve = r })
  const old = queryClient.fetchQuery({ queryKey: ['runs'],
    queryFn: () => fetch('/api/runs').then((r) => r.json()) }).catch(() => {})
  await flush()
  resetStream()
  resolve(Response.json([{ id: 'old-runtime' }]))
  await old; await flush()
  assert.equal(queryClient.getQueryData(['runs']), undefined)
})

test('external reset replaces a high cursor with low-seq history in the new runtime', async (t) => {
  sources[0].message(event(80)); sources[0].open(); await flush()
  runtime = metadata('epoch-2', 2)
  respond = () => Response.json([event(1), event(2)])
  t.mock.timers.tick(5000); await flush()
  assert.ok(sources[0].closed)
  assert.ok(sources.at(-1).url.endsWith('after=0'))
  sources.at(-1).runtime(); sources.at(-1).open(); await flush()
  assert.deepEqual(events().map((e) => e.seq), [1, 2])
  assert.equal(health().runtime.stream_epoch, 'epoch-2')
})

test('new SSE epoch fences callbacks queued on the old source', () => {
  sources[0].message(event(50))
  const late = sources[0].onmessage
  runtime = metadata('epoch-2')
  sources[0].runtime()
  late({ data: JSON.stringify(event(51)) })
  sources.at(-1).runtime(); sources.at(-1).message(event(1))
  assert.deepEqual(events().map((e) => e.seq), [1])
})

test('business events wait for runtime metadata on each new SSE connection', () => {
  resetStream()
  sources.at(-1).message(event(1))
  assert.deepEqual(events(), [])
  sources.at(-1).runtime(); sources.at(-1).message(event(1))
  assert.deepEqual(events().map((e) => e.seq), [1])
})

test('a polling response with a different epoch never applies its business events', async (t) => {
  respond = () => Response.json([event(99)], { headers: { 'X-Mirage-Stream-Epoch': 'old-epoch' } })
  sources[0].error(2)
  t.mock.timers.tick(1000); await flush()
  assert.deepEqual(events(), [])
  assert.ok(health().error)
})

test('late catch-up rows are deduped by epoch/seq even after newer SSE events', async (t) => {
  let resolve
  respond = () => new Promise((r) => { resolve = r })
  sources[0].open(); await flush()
  sources[0].message(event(3))
  resolve(Response.json([event(1), event(2), event(3)])); await flush()
  assert.deepEqual(events().map((e) => e.seq), [1, 2, 3])
  t.mock.timers.tick(1000)
})

test('malformed SSE never corrupts the cursor or event cache', async () => {
  sources[0].message({ type: 'run.status' })
  assert.deepEqual(events(), [])
  assert.ok(health().error)
  sources[0].message(event(1))
  await flush()
  assert.deepEqual(events().map((e) => e.seq), [1])
})

test('a stale runtime probe cannot reset the new generation after local reset', async (t) => {
  let resolve
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init })
    return new Promise((r) => { resolve = r })
  }
  t.mock.timers.tick(5000); await flush()
  resetStream()
  sources.at(-1).runtime(metadata('new-epoch'))
  sources.at(-1).message(event(1))
  assert.equal(requests[0].init.signal.aborted, true)
  resolve(Response.json(metadata('old-epoch', 99))); await flush()
  assert.deepEqual(events().map((e) => e.seq), [1])
  assert.equal(health().runtime.stream_epoch, 'new-epoch')
})

test('reconnecting loses ownership until fresh metadata arrives', () => {
  sources[0].error()
  assert.equal(health().runtime, null)
  sources[0].readyState = StubSource.OPEN
  sources[0].onopen()
  assert.equal(health().runtime, null)
  sources[0].runtime()
  assert.deepEqual(health().runtime.owned_run_ids, ['synthetic-run'])
})

test('invalid named runtime metadata clears ownership and fences business events', () => {
  sources[0].open()
  sources[0].runtime({ ...runtime, owned_run_ids: null })
  assert.equal(health().state, 'disconnected')
  assert.equal(health().runtime, null)
  sources[0].message(event(99))
  assert.deepEqual(events(), [])
  sources[0].runtime()
  sources[0].message(event(1))
  assert.deepEqual(events().map((e) => e.seq), [1])
})

test('invalid runtime GET clears ownership and a later healthy read recovers', async (t) => {
  runtime = { ...runtime, engine_mode: 'unknown' }
  t.mock.timers.tick(5000); await flush()
  assert.equal(health().state, 'disconnected')
  assert.equal(health().runtime, null)
  assert.match(health().error, /runtime metadata/)
  runtime = metadata()
  t.mock.timers.tick(5000); await flush()
  assert.equal(health().error, null)
  assert.deepEqual(health().runtime.owned_run_ids, ['synthetic-run'])
})

for (const [key, hook] of [
  [['approvals'], useApprovals],
  [['services', 'outbox', 'prod'], () => useServiceView('outbox', 'prod')],
]) {
  test(`${key[0]} hook read aborts on disconnect and rejects a late result`, async () => {
    let resolve
    respond = () => new Promise((r) => { resolve = r })
    function View() { hook(); return null }
    renderToString(createElement(QueryClientProvider, { client: queryClient }, createElement(View)))
    const query = queryClient.getQueryCache().find({ queryKey: key, exact: true })
    const read = queryClient.fetchQuery(query.options).catch(() => {})
    await flush()
    const request = requests.at(-1)
    assert.ok(request.url.startsWith(`/api/${key[0]}`))
    disconnect()
    assert.equal(request.init?.signal?.aborted, true, 'The actual hook must forward cancellation')
    resolve(Response.json({ stale: true }))
    await read; await flush()
    assert.equal(queryClient.getQueryData(key), undefined)
  })
}

import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { batchDeltas, parseChatEvent, sanitize, streamTurn, submitApproval, type ChatTurn } from '../src/api/chat.ts'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

function fixture(chunks: Uint8Array[]) {
  return new Response(new ReadableStream({
    start(controller) { for (const chunk of chunks) controller.enqueue(chunk); controller.close() },
  }), { headers: { 'content-type': 'text/event-stream' } })
}

test('streams arbitrarily fragmented CRLF and UTF-8, skips SSE comments, and sends only server-owned session references', async () => {
  const wire = ': keepalive\r\n\r\ndata: {"type":"session","session_id":"server-id"}\r\n\r\ndata: {"type":"text_delta","text":"Hello 🌤"}\r\n\r\ndata: {"type":"done"}\r\n\r\n'
  const bytes = new TextEncoder().encode(wire)
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/chat/turn')
    assert.deepEqual(JSON.parse(String(init?.body)), { session_id: 'server-id', message: 'Hi', actor: 'liam' })
    assert.equal(init?.method, 'POST')
    return fixture(Array.from(bytes, (byte) => Uint8Array.of(byte)))
  }
  const events: unknown[] = []
  await streamTurn({ session_id: 'server-id', message: 'Hi', actor: 'liam' }, new AbortController().signal, (event) => events.push(event))
  assert.deepEqual(events, [{ type: 'session', session_id: 'server-id' }, { type: 'text_delta', text: 'Hello 🌤' }, { type: 'done' }])
})

test('requires a terminal done event and keeps partial text available to the caller', async () => {
  globalThis.fetch = async () => fixture([new TextEncoder().encode('data: {"type":"text_delta","text":"partial"}\n\n')])
  const events: unknown[] = []
  await assert.rejects(streamTurn({ message: 'Hi', actor: 'liam' }, new AbortController().signal, (event) => events.push(event)), /before the reply finished/)
  assert.deepEqual(events, [{ type: 'text_delta', text: 'partial' }])
})

test('surfaces model/service errors and rejects non-SSE responses', async () => {
  globalThis.fetch = async () => fixture([new TextEncoder().encode('data: {"type":"error","code":"offline","message":"Model unavailable"}\n\n')])
  await assert.rejects(streamTurn({ message: 'Hi', actor: 'liam' }, new AbortController().signal, () => {}), /Model unavailable/)
  globalThis.fetch = async () => new Response('<html>wrong service</html>')
  await assert.rejects(streamTurn({ message: 'Hi', actor: 'liam' }, new AbortController().signal, () => {}), /did not return a stream/)
})

test('validates event discriminants, approval schemas, and tool result shapes', () => {
  for (const value of [{ type: '__proto__' }, { type: 'text_delta', text: 10 }, { type: 'tool_result', call_id: 'a', tool: 'kill', result: {} }, { type: 'approval_required', approval_id: 'a', call_id: 'b', message: 'Approve?', schema: [] }]) {
    assert.throws(() => parseChatEvent(JSON.stringify(value)), /Invalid chat event/)
  }
  assert.deepEqual(parseChatEvent('{"type":"done"}'), { type: 'done' })
})

test('approval uses the exact server ID and requires acknowledgment', async () => {
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/chat/approvals/server%2Fid')
    assert.deepEqual(JSON.parse(String(init?.body)), { action: 'accept', content: { reason: 'Review complete', confirm: 'kill run-1' } })
    return Response.json({ accepted: true })
  }
  await submitApproval('server/id', 'accept', { reason: 'Review complete', confirm: 'kill run-1' })
  globalThis.fetch = async () => Response.json({ accepted: false })
  await assert.rejects(submitApproval('id', 'decline'), /did not confirm/)
})

test('abort signals are passed through to turn and approval requests', async () => {
  const controller = new AbortController()
  controller.abort()
  globalThis.fetch = async (_url, init) => {
    assert.equal(init?.signal, controller.signal)
    init?.signal?.throwIfAborted()
    throw new Error('unreachable')
  }
  await assert.rejects(streamTurn({ message: 'Hi', actor: 'liam' }, controller.signal, () => {}), { name: 'AbortError' })
  await assert.rejects(submitApproval('id', 'accept', {}, controller.signal), { name: 'AbortError' })
})

test('sanitizes nested credentials and bearer tokens while preserving visible incident facts', () => {
  assert.deepEqual(sanitize({ incident_id: 'inc-1', nested: [{ mirage_token: 'sensitive', explanation: 'Authorization: Bearer fake-capability and secret=hidden' }] }), {
    incident_id: 'inc-1', nested: [{ mirage_token: '[redacted]', explanation: 'Authorization: Bearer [redacted] and secret=[redacted]' }],
  })
})

test('reveals bursty text a few characters per frame and keeps later events behind it', async () => {
  const frames: FrameRequestCallback[] = []
  Object.assign(globalThis, { document: { hidden: false }, matchMedia: () => ({ matches: false }), requestAnimationFrame: (callback: FrameRequestCallback) => frames.push(callback), cancelAnimationFrame: () => {} })
  let turn: ChatTurn = { id: 't', question: 'q', parts: [], status: 'running' }
  const shown = () => turn.parts[0]?.kind === 'text' ? turn.parts[0].text.length : 0
  const batch = batchDeltas((change) => { turn = change(turn) })
  const burst = 'Mirage freezes the compromised run and detonates it in a twin. '.repeat(2)
  batch.apply({ type: 'text_delta', text: burst })
  let now = 0
  const step = () => { now += 16; frames.shift()?.(now) }
  step()
  assert.ok(shown() > 0 && shown() < 20, `first frame showed ${shown()} chars`)
  batch.apply({ type: 'done' })
  const drained = batch.drained()
  assert.equal(turn.status, 'running')
  while (frames.length) step()
  await drained
  assert.equal(shown(), burst.length)
  assert.equal(turn.status, 'done')
})

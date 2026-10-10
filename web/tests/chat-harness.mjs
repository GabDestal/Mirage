// Scripted, synthetic transport/UI fixture. No model, MCP client, or engine mutation.
import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'
import { setTimeout as delay } from 'node:timers/promises'

const approvals = new Map()
const sessions = new Set()
const seen = { turns: [], approvals: [], disconnects: 0, handoffReads: 0 }
const tools = ['list_runs', 'get_incident', 'get_audit', 'detonate', 'find_cause', 'unfreeze', 'kill', 'send_fix']
const server = createServer(async (request, response) => {
  const json = (value, status = 200) => { response.writeHead(status, { 'content-type': 'application/json' }); response.end(JSON.stringify(value)) }
  if (request.url === '/chat/debug') return json(seen)
  if (request.url === '/chat/handoffs/harness-id') {
    seen.handoffReads++
    response.writeHead(200, { 'content-type': 'text/plain', 'cache-control': 'no-store' })
    return response.end('Synthetic harness handoff only. Scoped fake token: FLAG{team26-harness}. Never a real engine action.')
  }
  const body = await new Promise((resolve) => { let data = ''; request.on('data', (chunk) => { data += chunk }); request.on('end', () => resolve(data)) })
  let input
  try { input = JSON.parse(body) } catch { return json({ message: 'Invalid JSON' }, 400) }
  if (request.url?.startsWith('/chat/approvals/')) {
    const id = decodeURIComponent(request.url.split('/').at(-1))
    const approval = approvals.get(id)
    if (!approval) return json({ message: 'Approval no longer available' }, 404)
    if (input.action === 'accept' && !approval.retried) { approval.retried = true; return json({ message: 'Synthetic transient failure' }, 503) }
    seen.approvals.push({ id, ...input })
    approval.resolve(input)
    if (approval.race) await delay(500)
    return json({ accepted: true })
  }
  if (request.url !== '/chat/turn') return json({ message: 'Not found' }, 404)
  if (input.session_id && !sessions.has(input.session_id)) return json({ message: 'Session not found. Start a new conversation.' }, 404)
  const session = input.session_id || randomUUID()
  sessions.add(session)
  seen.turns.push(input)
  response.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
  const emit = (value) => { if (!response.destroyed) response.write(`data: ${JSON.stringify(value)}\n\n`) }
  let pendingId
  let pendingResolve
  response.on('close', () => { if (!response.writableEnded) seen.disconnects++; if (pendingId) approvals.delete(pendingId); pendingResolve?.({ action: 'decline' }) })
  emit({ type: 'session', session_id: session })
  const message = input.message
  if (message.includes('error')) { await delay(150); emit({ type: 'error', code: 'harness_error', message: 'Synthetic fixture: model unavailable. Your draft is preserved.' }); return response.end() }
  if (message.includes('hold')) {
    emit({ type: 'tool_start', call_id: 'hold-call', tool: 'get_incident', args: { incident_id: 'synthetic-1' } })
    emit({ type: 'tool_progress', call_id: 'hold-call', message: 'Synthetic harness: holding this connection for Stop response testing.' })
    await delay(20_000)
    if (!response.destroyed) { emit({ type: 'done' }); response.end() }
    return
  }
  if (message.includes('approval')) {
    emit({ type: 'tool_start', call_id: 'approval-call', tool: 'kill', args: { run_id: 'synthetic-run' } })
    pendingId = randomUUID()
    const decision = new Promise((resolve) => { pendingResolve = resolve; approvals.set(pendingId, { resolve, retried: false, race: message.includes('race') }) })
    emit({ type: 'approval_required', approval_id: pendingId, call_id: 'approval-call', message: 'Synthetic fixture: end synthetic-run? No production action is performed.', schema: { type: 'object', properties: {} } })
    const answer = await decision
    approvals.delete(pendingId)
    if (response.destroyed) return
    emit({ type: 'tool_result', call_id: 'approval-call', tool: 'kill', result: { content: [{ type: 'text', text: JSON.stringify({ fixture: true, action: answer.action }) }] } })
    if (message.includes('race')) { emit({ type: 'done' }); return response.end() }
  }
  if (message.includes('tools') || message.includes('handoff')) for (const tool of tools) {
    emit({ type: 'tool_start', call_id: `call-${tool}`, tool, args: { fixture: true } })
    await delay(70)
    emit({ type: 'tool_result', call_id: `call-${tool}`, tool, result: { content: [{ type: 'text', text: 'Synthetic result only' }], structuredContent: tool === 'send_fix' ? { handoff_url: '/chat/handoffs/harness-id', mirage_token: 'fixture-secret-to-redact', fixture: true } : { fixture: true, tool } } })
  }
  const text = message.includes('long')
    ? 'Synthetic long-content fixture.\n\n' + Array.from({ length: 70 }, (_, index) => `${index + 1}. Evidence paragraph ${index + 1}: this is scripted UI test content, not a Mirage verdict. No actions have run.`).join('\n') + '\n\n```json\n' + JSON.stringify({ long_id: 'x'.repeat(350), html: '<script>window.bad = true</script>' }, null, 2) + '\n```'
    : 'Synthetic UI harness reply.\n\nThis text is streamed from a local fixture. It does not demonstrate Bedrock or engine acceptance.\n\n- Session continuity is server-owned.\n- Production actions use approval requests.'
  for (const chunk of text.match(/.{1,48}|\n/g) || []) {
    if (response.destroyed) return
    emit({ type: 'text_delta', text: chunk })
    await delay(message.includes('long') ? 8 : 25)
  }
  emit({ type: 'done' })
  response.end()
})
server.listen(Number(process.env.PORT || 8016), '127.0.0.1', () => console.log('Synthetic chat SSE harness: http://127.0.0.1:8016 (no model or engine mutations)'))

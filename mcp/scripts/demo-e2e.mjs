// Requires the managed launcher on 5174/8010/8011. Mutates only that disposable recording.
// Default: synthetic model seam + real HTTP/SSE/MCP. --live: launcher Bedrock chat, no fallback/retries.
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { ElicitRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { createServer } from '../dist/server.js';
import { createChatService } from '../dist/chat.js';

const live = process.argv.includes('--live');
assert(process.argv.slice(2).every((arg) => arg === '--live'), 'Only --live is supported');
const api = 'http://127.0.0.1:8010';
const web = 'http://127.0.0.1:5174';
const human = { actor: 'M1 acceptance', reason: 'Authorized disposable recorded rehearsal' };
const summary = { model: live ? 'real Bedrock via launcher' : 'synthetic provider seam', checks: [], turns: [] };
let synthetic, client, server, followController;

async function http(base, path, body, expected = 200) {
  const response = await fetch(base + path, { signal: AbortSignal.timeout(15_000),
    ...(body !== undefined && { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }) });
  assert.equal(response.status, expected, `${path}: expected HTTP ${expected}`);
  return response.status === 204 ? null : response.json();
}
const get = (path) => http(api, path);
const post = (path, body = human, status = 200) => http(api, path, body, status);
async function until(fn, label) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) { const value = await fn(); if (value) return value; await delay(250); }
  throw new Error(`Timed out: ${label}`);
}
const check = (label) => summary.checks.push(label);
const texts = (events) => events.filter((e) => e.type === 'text_delta').map((e) => e.text).join('');
const results = (events, name) => events.filter((e) => e.type === 'tool_result' && e.tool === name);

// Streaming parser handles CRLF, chunk splits, keepalives and multiple data fields.
async function sse(response, onEvent, stop = () => false) {
  assert.equal(response.status, 200, 'SSE HTTP status');
  assert.match(response.headers.get('content-type') ?? '', /text\/event-stream/, 'SSE content type');
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r/g, '');
      let split;
      while ((split = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, split); buffer = buffer.slice(split + 2);
        const data = frame.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n');
        if (!data) continue;
        const event = JSON.parse(data);
        await onEvent(event);
        if (stop(event)) return;
      }
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

// Reuse the existing ModelProvider seam. Only model output is scripted; handlers and engine are real.
function scriptedProvider() {
  return { async stream(messages) {
    const last = messages.at(-1);
    const text = last.content?.find((c) => c.text)?.text ?? '';
    let calls = [];
    if (last.role === 'user' && !last.content.some((c) => c.toolResult)) {
      if (text.includes('Read current')) calls = [['list_runs', {}], ['get_incident', { incident_id: 'inc_001' }]];
      if (text.includes('Find the cause')) calls = [['find_cause', { incident_id: 'inc_001' }]];
      if (text.includes('Prepare the handoff')) calls = [['send_fix', { incident_id: 'inc_001' }]];
    }
    const events = calls.length ? [
      ...calls.flatMap(([name, input], i) => [
        { contentBlockStart: { contentBlockIndex: i, start: { toolUse: { toolUseId: `call_${i}`, name } } } },
        { contentBlockDelta: { contentBlockIndex: i, delta: { toolUse: { input: JSON.stringify(input) } } } },
        { contentBlockStop: { contentBlockIndex: i } },
      ]), { messageStop: { stopReason: 'tool_use' } },
    ] : [{ contentBlockDelta: { contentBlockIndex: 0, delta: { text: 'Synthetic model summary of recorded engine evidence.' } } },
      { messageStop: { stopReason: 'end_turn' } }];
    summary.synthetic_model_calls = (summary.synthetic_model_calls ?? 0) + 1;
    return { $metadata: {}, stream: (async function* () { yield* events; })() };
  } };
}

async function main() {
  const policies = await get('/policies');
  assert(Object.values(policies.agents).every((a) => a.owner === 'recorded-demo' && !a.entrypoint), 'Require recorded agent specs');
  const proxied = await http(web, '/api/policies');
  assert.deepEqual(proxied, policies, 'Dashboard proxies the owned engine');
  await post('/demo/reset', null, 204);
  const streamed = [];
  await sse(await fetch(api + '/stream', { signal: AbortSignal.timeout(90_000) }),
    (event) => streamed.push(event), (event) => event.type === 'verdict.ready');
  const events = await get('/events');
  const freeze = events.find((e) => e.type === 'run.status' && e.payload.to === 'frozen');
  const start = events.find((e) => e.type === 'detonation.started');
  const completed = events.find((e) => e.type === 'detonation.completed');
  assert(freeze && start && completed && freeze.seq < start.seq && start.seq < completed.seq, 'Freeze precedes automatic proof');
  assert.equal(start.payload.n_runs, 3, 'Automatic baseline requests three recorded replays');
  assert(!events.some((e) => e.type === 'human.action'), 'No initial detonation control POST');
  const incident = await get('/incidents/inc_001');
  assert.equal(incident.status, 'confirmed');
  assert.equal(incident.verdict.compromised_runs, `${completed.payload.compromised_runs}/${completed.payload.n_runs}`, 'Use observed proof denominator');
  const effectRuns = new Set(events.filter((e) => e.type === 'detonation.effect').map((e) => e.payload.run_index));
  assert.equal(effectRuns.size, completed.payload.n_runs, 'Every completed recorded replay has effects');
  summary.baseline = { observed: incident.verdict.compromised_runs, effects: events.filter((e) => e.type === 'detonation.effect').length, stream_events: streamed.length };
  const runs = await get('/runs');
  assert.equal(runs.length, 4);
  assert.equal(runs.find((r) => r.agent === 'meeting_assistant').status, 'frozen');
  const healthy = events.filter((e) => e.seq > freeze.seq && e.run_id !== freeze.run_id && ['tool.called', 'run.status'].includes(e.type));
  assert(healthy.length > 0, 'Healthy recorded agents continue after freeze');
  assert(runs.filter((r) => r.agent !== 'meeting_assistant').every((r) => r.status === 'completed'));
  for (const path of ['/services/outbox', '/services/calendar', '/services/crm', '/services/outbox?env=mirage']) {
    assert((await get(path)).items.length, `${path}: service evidence`);
  }
  check('automatic baseline / real engine SSE / healthy continuation / service panels');
  const before = await get('/events');
  await post('/incidents/inc_001/handoff', human, 409);
  await post('/incidents/inc_001/verify', human, 409);
  await post('/incidents/inc_missing/bisect', human, 404);
  await post('/incidents/inc_001/bisect?runs=5', human, 409);
  await post('/runs/run_002/unfreeze', human, 409);
  assert.deepEqual(await get('/events'), before, 'Guard refusals have no effects');
  check('target / stage / run-count guards; confirmed unfreeze refused');

  server = createServer({ api, actor: human.actor });
  client = new Client({ name: 'M1 acceptance', version: '1' }, { capabilities: { elicitation: {} } });
  client.setRequestHandler(ElicitRequestSchema, ({ params }) => ({ action: 'accept', content: params._meta['mirage/confirm'] }));
  const [a, b] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(a), client.connect(b)]);
  assert((await client.listTools()).tools.some((t) => t.name === 'resume_all'));
  await post('/stop');
  const paused = await get('/events'); await delay(500);
  assert.deepEqual(await get('/events'), paused, 'STOP pauses recording');
  assert((await get('/runs')).some((r) => r.status === 'halted'));
  const resumed = await client.callTool({ name: 'resume_all', arguments: { reason: human.reason } });
  assert(!resumed.isError, 'Actual resume_all MCP handler lifts recorded STOP');
  assert.equal((await get('/runs/run_002')).status, 'frozen');
  check('STOP / actual MCP resume_all / preserved frozen incident');

  let chat = 'http://127.0.0.1:8011';
  if (!live) {
    synthetic = createChatService({ provider: scriptedProvider(), mcp: { api, pollMs: 100 } });
    await new Promise((ok) => synthetic.http.listen(0, '127.0.0.1', ok));
    chat = `http://127.0.0.1:${synthetic.http.address().port}`;
  }
  let session;
  async function turn(message, action, expectedTool) {
    const events = [];
    const response = await fetch(chat + '/chat/turn', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ actor: human.actor, message, ...(session && { session_id: session }) }), signal: AbortSignal.timeout(180_000) });
    await sse(response, async (event) => {
      events.push(event);
      if (event.type === 'session') session = event.session_id;
      if (event.type === 'error') throw new Error(`Chat failed: ${event.code}`);
      if (event.type === 'approval_required') {
        assert(action, 'Unexpected effect approval on read-only turn');
        assert.equal(events.find((e) => e.call_id === event.call_id && e.type === 'tool_start')?.tool, expectedTool, 'Approve only intended actual tool');
        assert.deepEqual(event.schema, { type: 'object', properties: {} });
        await http(chat, `/chat/approvals/${event.approval_id}`, { action });
        await http(chat, `/chat/approvals/${event.approval_id}`, { action }, 409);
      }
    });
    assert(events.some((e) => e.type === 'done'), 'Turn completes');
    if (action) assert.equal(events.filter((e) => e.type === 'approval_required').length, 1, 'One human decision');
    if (expectedTool) assert.equal(results(events, expectedTool).length, 1, 'Expected actual MCP result');
    summary.turns.push({ decision: action ?? 'read only', tools: events.filter((e) => e.type === 'tool_start').map((e) => e.tool), text: texts(events) });
    return events;
  }
  const read = await turn('Read current agent runs and Incident #1 proof using your tools. Briefly explain which background is recorded and which assistant is real. Do not take actions.');
  assert(results(read, 'list_runs').length && results(read, 'get_incident').length, 'Read uses current runs and proof tools');
  if (live) assert.match(texts(read), /recorded|simulat/i, 'Live model describes recorded evidence');
  check('current evidence read through actual MCP tools');

  const followEvents = [];
  followController = new AbortController();
  const followResponse = await fetch(chat + `/chat/sessions/${session}/events`, { signal: AbortSignal.any([followController.signal, AbortSignal.timeout(180_000)]) });
  const follow = sse(followResponse, (event) => {
    followEvents.push(event);
    if (event.type === 'error') throw new Error(`Follow-up failed: ${event.code}`);
  }, (event) => event.type === 'done');
  // Attach rejection immediately so a failed primary turn cannot leave an unhandled rejection.
  follow.catch(() => {});
  // Existing contract: cause finding is sandbox-only Level 0; handoff is Level 1.
  const accepted = await turn('Find the cause of Incident #1 using your cause-finding tool now. Report when the recorded cause tests finish.', undefined, 'find_cause');
  assert.equal(results(accepted, 'find_cause')[0].result.structuredContent.status, 'started');
  await follow;
  assert(followEvents.some((e) => e.type === 'follow_up'), 'Automatic bisection follow-up');
  const cause = results(followEvents, 'get_incident')[0]?.result.structuredContent.incident;
  assert.equal(cause?.cause_input_id, 'in_cal_03', 'Follow-up includes current cause evidence');
  summary.cause = { input: cause.cause_input_id, rows: cause.bisection.map((r) => ({ observed: r.compromised_runs, cause: r.is_cause })), follow_up: texts(followEvents) };
  check('human-requested actual find_cause / recorded bisection follow-up');
  const beforeDecline = await get('/events');
  const decline = await turn('Prepare the handoff for Incident #1 with your coding-agent handoff tool. Request human approval and wait.', 'decline', 'send_fix');
  assert(results(decline, 'send_fix')[0].result.isError, 'Declined tool reports refusal');
  assert.deepEqual(await get('/events'), beforeDecline, 'Human decline causes no engine effect');
  check('real chat approval / decline no effect / stale decision rejected');
  const handoff = await turn('Prepare the handoff for Incident #1 now. This is a new explicit request after my earlier decline. Use the same handoff tool and request fresh approval. Describe the recorded-only boundary without claiming a fix was made.', 'accept', 'send_fix');
  const safe = results(handoff, 'send_fix')[0].result;
  assert(!safe.isError);
  assert(!JSON.stringify(safe).includes('mirage_token'), 'No token in chat tool result');
  assert(safe.structuredContent.handoff_url, 'Human-only handoff download');
  const download = await fetch(chat + safe.structuredContent.handoff_url, { signal: AbortSignal.timeout(15_000) });
  assert.equal(download.status, 200);
  const prompt = await download.text();
  assert.match(prompt, /Recorded demo only/);
  assert.match(prompt, /no usable live snapshot/);
  assert.match(prompt, /No fix has been written/);
  assert(!/Bearer\s|mirage_token/.test(prompt), 'No live capability in recorded prompt');
  check('approved actual send_fix / recorded-only human prompt / no live capability');

  await post('/incidents/inc_001/verify');
  const verified = await until(async () => (await get('/events')).find((e) => e.type === 'fix.verified'), 'recorded fix verification');
  assert(verified.payload.passed);
  summary.recorded_verification = { attack_blocked: verified.payload.attack_blocked, legit_task_completed: verified.payload.legit_task_completed };
  const pr = 'https://example.invalid/recorded-demo/pr/42';
  await post('/incidents/inc_001/pr', { url: 'https://github.com/GabDestal/Mirage/pull/42' }, 409);
  await post('/incidents/inc_001/pr', { url: pr });
  await until(async () => (await get('/incidents/inc_001')).pr_url === pr, 'recorded PR progression');
  const final = await get('/events');
  assert.deepEqual(final.map((e) => e.seq), final.map((_, i) => i + 1), 'Contiguous evidence cursor');
  assert(final.filter((e) => e.type === 'human.action').every((e) => e.payload.actor.includes(human.actor)), 'Actual actor audit');
  check('approved HTTP recorded verify / inert PR evidence / audit / cursor');
  await post('/demo/reset', null, 204);
  const reset = await get('/events');
  assert(!reset.some((e) => ['human.action', 'bisection.completed', 'fix.verified', 'pr.opened'].includes(e.type)), 'Reset removes prior decisions/proof');
  assert.equal((await get('/incidents')).length, 0, 'Timed reset starts with empty incident dashboard');
  check('reset clears incident / cause / fix / PR / audit state');
}

try { await main(); console.log(JSON.stringify({ ok: true, ...summary }, null, 2)); }
catch (error) { console.error(JSON.stringify({ ok: false, code: 'DEMO_ACCEPTANCE_FAILED', message: error.message, ...summary }, null, 2)); process.exitCode = 1; }
finally {
  followController?.abort();
  await Promise.allSettled([client?.close(), server?.close(), synthetic?.close()]);
}

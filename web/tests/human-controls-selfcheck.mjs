// Synthetic REST and server-render checks; browser/provider acceptance is separate.
// Run from web/: node tests/human-controls-selfcheck.mjs [--demo]
import assert from 'node:assert/strict'
import { createElement as h } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { createServer } from 'vite'

const demo = process.argv.includes('--demo')
process.env.MIRAGE_UI_MODE = demo ? 'demo' : 'live'
const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
const originalFetch = globalThis.fetch
try {
  const client = await server.ssrLoadModule('/src/api/client.ts')
  const actions = await server.ssrLoadModule('/src/components/actions.tsx')
  const { Fleet } = await server.ssrLoadModule('/src/pages/fleet.tsx')
  const approvals = await server.ssrLoadModule('/src/components/engine-approvals.tsx')
  const services = await server.ssrLoadModule('/src/components/service-evidence.tsx')
  const controls = await server.ssrLoadModule('/src/components/engine-controls.ts')
  const run = { id: 'run/one', agent: 'meeting_assistant', env: 'prod', task: 'Synthetic test', status: 'running',
    started_at: '2026-10-11T00:00:00Z', tool_calls: 0 }
  const cache = client.queryClient
  const render = (component, props = {}) => renderToStaticMarkup(h(QueryClientProvider, { client: cache },
    h(MemoryRouter, {}, h(actions.ActionsProvider, {}, h(component, props)))))
  const capture = (hook, ...args) => {
    let value
    render(() => { value = hook(...args); return null })
    return value
  }
  cache.setQueryData(['runs'], [run])
  cache.setQueryData(['events'], [])
  cache.setQueryData(['incidents'], [])
  cache.setQueryData(['approvals'], [])
  for (const service of ['outbox', 'calendar', 'crm']) for (const env of ['prod', 'mirage'])
    cache.setQueryData(['services', service, env], { service, env, items: [] })
  const fleet = render(Fleet)
  assert.equal(fleet.includes('>Freeze<'), !demo, 'Only live production runs expose manual Freeze')
  assert.ok(fleet.includes('Service evidence'), 'Fleet must show current service evidence')
  assert.ok(fleet.includes('Engine approvals'), 'Fleet must show the engine approval queue')
  console.log('PASS fleet exposes services, engine approvals and appropriate manual freeze')

  if (demo) {
    assert.equal(render(actions.FreezeButton, { run }), '')
    assert.equal(render(actions.CleanRestartButton, { run: { ...run, status: 'killed' } }), '')
    cache.setQueryData(['runs'], [{ ...run, status: 'frozen' }])
    const frozenDemo = render(Fleet)
    assert.ok(!frozenDemo.includes('>Unfreeze<') && !frozenDemo.includes('>Kill<'))
    cache.setQueryData(['approvals'], [{ call_id: 'held', run_id: run.id, agent: run.agent, tool: 'send_email', args: {}, explanation: 'Synthetic review', ts: run.started_at }])
    const queue = render(approvals.EngineApprovals)
    assert.ok(queue.includes('Recorded demo: decisions are unavailable'))
    assert.equal((queue.match(/disabled=""/g) ?? []).length, 2)
    assert.ok(render(services.ServiceEvidence).includes('Recorded synthetic demo'))
    console.log('PASS demo hides unsupported freeze/restart, disables engine decisions and labels recorded evidence')
  } else {

  cache.setQueryData(['runs'], [{ ...run, status: 'frozen' }])
  const manual = render(Fleet)
  assert.ok(manual.includes('>Unfreeze<') && manual.includes('>Kill<'), 'Manual incident-less freeze must expose reason-controlled recovery')
  cache.setQueryData(['runs'], [{ ...run, status: 'frozen', incident_id: 'incident_test' }])
  const incidentFlow = render(Fleet)
  assert.ok(incidentFlow.includes('Review Incident') && !incidentFlow.includes('>Unfreeze<') && !incidentFlow.includes('>Kill<'))
  for (const variant of [{ ...run, status: 'frozen', env: 'mirage' }, { ...run, status: 'queued' }, { ...run, status: 'completed' }]) {
    cache.setQueryData(['runs'], [variant])
    const ineligible = render(Fleet)
    assert.ok(!ineligible.includes('>Unfreeze<') && !ineligible.includes('>Kill<'))
  }

  const killed = { ...run, status: 'killed' }
  cache.setQueryData(['runs'], [killed])
  assert.ok(render(actions.CleanRestartButton, { run: killed }).includes('Approve clean restart'))
  for (const status of ['queued', 'running', 'completed', 'frozen'])
    assert.equal(render(actions.CleanRestartButton, { run: { ...run, status } }), '')
  assert.equal(render(actions.FreezeButton, { run: { ...run, env: 'mirage' } }), '')
  const queued = { ...run, id: 'run/two', status: 'queued', restarted_from: run.id }
  cache.setQueryData(['runs'], [killed, queued])
  const pending = render(actions.CleanRestartButton, { run: killed })
  assert.ok(pending.includes('Clean restart pending · awaiting owner start'))
  assert.ok(pending.includes('<span class="clean-restart-status" role="status"><a href="/runs/run%2Ftwo"'), 'Pending status must preserve the trace link semantics')
  assert.ok(!pending.includes('Approve clean restart') && !pending.includes('running'))
  cache.setQueryData(['events'], [{ type: 'global.stop' }])
  cache.setQueryData(['runs'], [killed])
  assert.match(render(actions.CleanRestartButton, { run: killed }), /disabled=""/)
  cache.setQueryData(['events'], [])
  console.log('PASS restart status/duplicate/STOP guards and production-only freeze')

  const calls = []
  let respond = async () => new Response(JSON.stringify({ ...run, status: 'frozen' }), { status: 200 })
  globalThis.fetch = async (path, init) => {
    calls.push({ path, method: init?.method ?? 'GET', body: init?.body && JSON.parse(init.body) })
    return respond(path, init)
  }
  const body = { actor: actions.ACTOR, reason: 'Synthetic human decision' }
  const act = capture(actions.useHumanAction)
  for (const kind of ['unfreeze', 'kill']) {
    respond = async () => new Response(JSON.stringify({ ...run, status: kind === 'unfreeze' ? 'running' : 'killed' }))
    await act.mutateAsync({ kind, run: { ...run, status: 'frozen' }, body })
    assert.deepEqual(calls.pop(), { path: `/api/runs/run%2Fone/${kind}`, method: 'POST', body })
    respond = async () => new Response(JSON.stringify({ detail: 'Synthetic recovery refused' }), { status: 409 })
    await assert.rejects(act.mutateAsync({ kind, run: { ...run, status: 'frozen' }, body }), { status: 409 })
    assert.equal(calls.length, 1, 'Manual recovery POST must never retry')
    calls.length = 0
  }
  console.log('PASS incident-less recovery eligibility and actual unfreeze/kill actor/reason REST routes without retries')
  cache.setQueryData(['runs'], [run])
  respond = async () => new Response(JSON.stringify({ ...run, status: 'frozen' }))
  await act.mutateAsync({ kind: 'freeze', run, body })
  assert.deepEqual(calls.pop(), { path: '/api/runs/run%2Fone/freeze', method: 'POST', body })
  assert.equal(cache.getQueryData(['runs'])[0].status, 'frozen')
  cache.setQueryData(['runs'], [killed])
  let resolve
  respond = () => new Promise((done) => { resolve = done })
  const request = act.mutateAsync({ kind: 'restart', run: killed, body })
  await new Promise((done) => setImmediate(done))
  assert.deepEqual(cache.getQueryData(['runs']), [killed], 'Restart must not optimistically execute or replace the old run')
  resolve(new Response(JSON.stringify(queued)))
  await request
  assert.deepEqual(calls.pop(), { path: '/api/runs/run%2Fone/restart', method: 'POST', body })
  assert.deepEqual(cache.getQueryData(['runs']), [killed, queued])
  assert.ok(render(actions.CleanRestartButton, { run: killed }).includes('pending'))
  respond = async () => new Response(JSON.stringify({ detail: 'Run run/one is owned by another process (no live control)' }), { status: 409 })
  const before = cache.getQueryData(['runs'])
  await assert.rejects(act.mutateAsync({ kind: 'freeze', run, body }), (error) => {
    assert.equal(error.status, 409)
    assert.ok(controls.humanControlError(error).includes('restored the history, but has no live control'))
    return true
  })
  assert.equal(calls.length, 1, 'Control POST must never retry')
  assert.deepEqual(cache.getQueryData(['runs']), before, 'Refused action must preserve the evidence')
  calls.length = 0
  assert.equal(controls.humanControlError(new client.ApiError(409, 'Global STOP is on')), 'Global STOP is on')
  console.log('PASS actual freeze/restart REST bodies, queued cache update, ownership 409 and no POST retry')

  const held = { call_id: 'call/held', run_id: run.id, agent: run.agent, tool: 'send_email',
    args: { to: 'synthetic@example.test' }, explanation: 'New destination requires review.', policy_id: 'P5', p: 0.5, ts: run.started_at }
  cache.setQueryData(['approvals'], [held])
  assert.ok(render(approvals.EngineApprovals).includes('Inspect held arguments'))
  const decide = capture(controls.useEngineApproval)
  for (const decision of ['approve', 'reject']) {
    respond = async () => new Response(JSON.stringify({ ...run, status: decision === 'approve' ? 'running' : 'killed' }))
    await decide.mutateAsync({ callId: held.call_id, decision, body })
    assert.deepEqual(calls.pop(), { path: `/api/approvals/call%2Fheld/${decision}`, method: 'POST', body })
  }
  respond = async () => new Response(JSON.stringify({ detail: 'No call is waiting for approval' }), { status: 404 })
  await assert.rejects(decide.mutateAsync({ callId: held.call_id, decision: 'approve', body }), { status: 404 })
  assert.equal(calls.length, 1, 'Stale approvals must not retry')
  calls.length = 0
  console.log('PASS engine approvals use their own approve/reject routes and actor/reason, stale decisions fail once')

  const read = capture(client.useApprovals)
  respond = async () => new Response('[]')
  await read.refetch()
  assert.deepEqual(calls.pop(), { path: '/api/approvals', method: 'GET', body: undefined })
  for (const service of ['outbox', 'calendar', 'crm']) for (const env of ['prod', 'mirage']) {
    const view = { service, env, items: [{ id: `${env}-${service}`, title: `${env}-${service}-evidence`, subtitle: 'Synthetic only', ts: run.started_at, flag: 'normal' }] }
    respond = async () => new Response(JSON.stringify(view))
    await capture(client.useServiceView, service, env).refetch()
    assert.deepEqual(calls.pop(), { path: `/api/services/${service}?env=${env}`, method: 'GET', body: undefined })
    assert.deepEqual(cache.getQueryData(['services', service, env]), view)
  }
  const serviceHtml = render(services.ServiceEvidence)
  assert.ok(serviceHtml.includes('do not check provider health or confirm delivery'))
  for (const service of ['outbox', 'calendar', 'crm']) {
    const prod = serviceHtml.split(`aria-label="Production ${service === 'crm' ? 'CRM' : service[0].toUpperCase() + service.slice(1)}"`)[1].split('</section>')[0]
    assert.ok(prod.includes(`prod-${service}-evidence`) && !prod.includes(`mirage-${service}-evidence`))
  }
  assert.ok(serviceHtml.includes('Tool result recorded') && serviceHtml.includes('Captured effect · not sent'))
  assert.ok(serviceHtml.includes('Snapshot input') && serviceHtml.includes('Recorded read'))
  for (const [service, env, flag, label] of [
    ['outbox', 'prod', 'blocked', 'Blocked · never sent'],
    ['outbox', 'mirage', 'malicious', 'Harmful effect · not sent'],
    ['crm', 'prod', 'malicious', 'Proven cause'],
  ]) {
    const view = cache.getQueryData(['services', service, env])
    cache.setQueryData(['services', service, env], { ...view, items: [{ ...view.items[0], flag }] })
    assert.ok(render(services.ServiceEvidence).includes(label))
  }
  const failed = cache.getQueryCache().find({ queryKey: ['services', 'outbox', 'prod'] })
  failed.setState({ status: 'error', error: new Error('Synthetic read failure') })
  assert.ok(render(services.ServiceEvidence).includes('Could not refresh outbox: Synthetic read failure'))
  cache.getQueryCache().find({ queryKey: ['approvals'] }).setState({ status: 'error', error: new Error('Synthetic queue failure') })
  assert.ok(render(approvals.EngineApprovals).includes('Approval queue could not refresh: Synthetic queue failure'))
  console.log('PASS GET contracts, prod/Mirage cache and rendering isolation, evidence labels and read failures')
  }
  cache.clear()
} finally {
  globalThis.fetch = originalFetch
  await server.close()
}

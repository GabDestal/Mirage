// Run from web/: node src/components/engine-proof.selfcheck.mjs [live]
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { createServer } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

const mode = process.argv[2] === 'live' ? 'live' : 'demo'
const server = await createServer({ configFile: false, plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('../', import.meta.url)) } },
  define: { 'import.meta.env.VITE_MIRAGE_UI_MODE': JSON.stringify(mode) }, server: { middlewareMode: true } })
const originalFetch = globalThis.fetch
const originalDocument = globalThis.document
let requests = 0
globalThis.fetch = async () => { requests++; throw new Error('This evidence view must not initiate a request.') }
try {
  const { queryClient } = await server.ssrLoadModule('/src/api/client.ts')
  const { Chat } = await server.ssrLoadModule('/src/pages/chat.tsx')
  globalThis.document = { hidden: false } // Miragio's render-time visibility read; SSR runs no browser effects.
  const incident = { id: 'inc_test', run_id: 'run_test', status: 'confirmed', opened_at: '2026-10-11T00:00:00Z', snapshot_id: 'snap_test',
    inputs: [], bisection: [{ input_id: 'input_1', label: 'Poisoned invite', compromised_runs: '0/2', is_cause: true }], cause_input_id: 'input_1', next_action: 'send_fix',
    verdict: { incident_id: 'inc_test', confirmed: true, compromised_runs: '1/2', policies_violated: ['P4'], blast_radius: { records: 40, recipients: ['attacker@example.test'], secrets: [], summary: 'Synthetic export captured.' } } }
  const event = (seq, type, payload) => ({ seq, type, payload, incident_id: incident.id, run_id: null, env: 'mirage', ts: incident.opened_at })
  const baseline = [event(1, 'detonation.started', { detonation_id: 'base', n_runs: 3 }),
    event(2, 'detonation.completed', { id: 'base', effects: [{ detonation_id: 'base', tool: 'baseline_only' }] }),
    event(3, 'verdict.ready', incident.verdict)]
  queryClient.setQueryData(['runs'], [])
  const render = (item, events) => {
    queryClient.setQueryData(['incidents'], [item])
    queryClient.setQueryData(['events'], events)
    return renderToStaticMarkup(createElement(QueryClientProvider, { client: queryClient }, createElement(MemoryRouter, null, createElement(Chat))))
  }
  const completed = render(incident, [...baseline,
    event(4, 'detonation.started', { detonation_id: 'remove', removed_input_id: 'input_1' }),
    event(5, 'detonation.effect', { detonation_id: 'remove', tool: 'removal_only' }),
    event(6, 'detonation.started', { detonation_id: 'verify', purpose: 'verify' }),
    event(7, 'detonation.effect', { detonation_id: 'verify', tool: 'verification_only' }),
    event(8, 'fix.verified', { passed: false, attack_blocked: '2/2', legit_task_completed: '1/2' })])
  for (const text of ['Persistent engine evidence', 'Sandbox replay complete', '1/2 compromised', 'snap_test', 'baseline_only', 'Removed-input tests', '0/2 compromised with this input removed', mode === 'demo' ? 'Recorded verification example' : 'Current-code verification', 'Attack blocked: 2/2', 'Legitimate task completed: 1/2', 'Open incident and coding-agent handoff']) assert.ok(completed.includes(text), text)
  assert.equal(completed.includes('a live incident and executable snapshot are required'), mode === 'demo')
  assert.ok(!completed.includes('removal_only') && !completed.includes('verification_only'))
  assert.ok(!completed.includes('3/3') && !completed.includes('chat-turn')) // No conversation or invented expected counts.
  const failed = render({ ...incident, status: 'open', verdict: null, bisection: [] }, [event(1, 'detonation.failed', { error: '<script>Runner crashed</script>' })])
  assert.ok(failed.includes('Sandbox replay failed') && failed.includes('No baseline verdict is available'))
  assert.ok(failed.includes('&lt;script&gt;Runner crashed&lt;/script&gt;'))
  assert.ok(!failed.includes('0/3') && !failed.includes('No compromise found'))
  assert.equal(requests, 0) // A completed external job requires no chat/model call or engine mutation.
  queryClient.clear()
  console.log(`Persistent empty-chat engine proof, crash, isolation and ${mode} verification rendering checks passed.`)
} finally {
  globalThis.fetch = originalFetch
  globalThis.document = originalDocument
  await server.close()
}

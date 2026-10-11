// Synthetic REST/render regressions only; browser and live-engine acceptance are separate.
// Run from web/: node tests/run-lifecycle-truth-selfcheck.mjs [--demo]
// Phase 1 uses the agreed RuntimeInfo fixture in the transport's published connection cache.
// This baseline does not consume runtime metadata yet: ownership failures must stay RED.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement as h } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'
import { createServer } from 'vite'

const demo = process.argv.includes('--demo')
process.env.MIRAGE_UI_MODE = demo ? 'demo' : 'live'
const server = await createServer({
  server: { middlewareMode: true, ws: false }, appType: 'custom',
  plugins: [{
    name: 'lifecycle-dialog-test-seam',
    // Expose the existing private dialog without duplicating its copy or editing source.
    transform(code, id) {
      if (id.endsWith('/src/components/actions.tsx'))
        return `${code}\nexport { ReasonDialog as __LifecycleReasonDialog };`
    },
  }],
})
const originalFetch = globalThis.fetch
try {
  const client = await server.ssrLoadModule('/src/api/client.ts')
  const actions = await server.ssrLoadModule('/src/components/actions.tsx')
  const { Fleet } = await server.ssrLoadModule('/src/pages/fleet.tsx')
  const cache = client.queryClient
  const run = { id: 'run/one', agent: 'meeting_assistant', env: 'prod', task: 'Synthetic lifecycle check',
    status: 'running', started_at: '2026-10-11T00:00:00Z', tool_calls: 0 }
  const halted = { ...run, status: 'halted' }
  const queued = { ...run, id: 'run/two', status: 'queued', restarted_from: run.id }
  const body = { actor: actions.ACTOR, reason: 'Synthetic explicit human decision' }
  const runtime = (owned_run_ids = [], overrides = {}) => ({ engine_mode: 'live',
    instance_id: 'synthetic-engine-a', stream_epoch: 'synthetic-epoch-a', last_seq: 0,
    revision: null, owned_run_ids, ...overrides })
  const connection = (info, state = 'streaming') => cache.setQueryData(['connection'], {
    state, lastSync: state === 'disconnected' ? null : Date.now(),
    error: state === 'disconnected' ? 'Synthetic connection lost' : null, runtime: info,
  })
  const seed = (runs, info = runtime(runs.map((r) => r.id))) => {
    cache.clear()
    cache.setQueryData(['runs'], runs)
    cache.setQueryData(['events'], [])
    cache.setQueryData(['incidents'], [])
    cache.setQueryData(['approvals'], [])
    for (const service of ['outbox', 'calendar', 'crm']) for (const env of ['prod', 'mirage'])
      cache.setQueryData(['services', service, env], { service, env, items: [] })
    connection(info)
  }
  const render = (component, props = {}) => renderToStaticMarkup(h(QueryClientProvider, { client: cache },
    h(MemoryRouter, {}, h(actions.ActionsProvider, {}, h(component, props)))))
  const capture = (hook, ...args) => {
    let value
    render(() => { value = hook(...args); return null })
    return value
  }
  const dialog = (kind, subject = halted) => capture(() =>
    actions.__LifecycleReasonDialog({ pending: { kind, run: subject }, onClose() {} })).props
  const text = (html) => html.replace(/<[^>]*>/g, ' ')
  const enabled = (html, label) => [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)]
    .some(([, attributes, contents]) => !/(?:^|\s)disabled(?:=|\s|$)/.test(attributes) && text(contents).trim() === label)
  const stat = (html, label) => {
    const after = html.split(`>${label}</span>`)[1]
    assert.ok(after, `Fleet must retain the ${label} count`)
    return Number(after.match(/class="fleet-stat-value"[^>]*>(\d+)/)?.[1])
  }
  const request = async (kind, subject, response, status = 200) => {
    const calls = []
    globalThis.fetch = async (path, init) => {
      calls.push({ path, method: init?.method ?? 'GET', body: init?.body && JSON.parse(init.body) })
      return new Response(JSON.stringify(response), { status })
    }
    await capture(actions.useHumanAction).mutateAsync({ kind, run: subject, body })
    assert.deepEqual(calls, [{ path: kind === 'resumeAll' ? '/api/resume-all'
      : `/api/runs/${encodeURIComponent(subject.id)}/${kind}`, method: 'POST', body }])
    return String(toast.getHistory().at(-1).title)
  }

  if (demo) {
    await test('recorded controls remain labelled as playback and never imply a live launch', () => {
      seed([run], runtime([], { engine_mode: 'replay' }))
      assert.match(dialog('resumeAll').effect, /Recording continues/)
      assert.match(dialog('resumeAll').effect, /No agents or providers are launched/)
      assert.match(dialog('stop').effect, /Recording pauses/)
      assert.equal(render(actions.FreezeButton, { run }), '')
      assert.equal(render(actions.ResumeButton, { run: halted }), '')
      assert.equal(render(actions.CleanRestartButton, { run: { ...run, status: 'killed' } }), '')
      assert.match(render(Fleet), /Recorded agents/)
    })
    await test('recorded resume-all toast describes playback rather than queued or working agents', async () => {
      seed([halted], runtime([], { engine_mode: 'replay' }))
      assert.match(await request('resumeAll', undefined, { resumed: [], skipped: [] }), /Recording resumed/)
    })
  } else {
    await test('resume dialog explains queueing and waits for an observed owner start', () => {
      seed([halted])
      assert.match(dialog('resume').effect, /queued|queue/i)
      assert.match(dialog('resume').effect, /owner|observed|start is confirmed/i)
    })
    await test('resume-all dialog does not promise every halted agent has started', () => {
      seed([halted])
      assert.doesNotMatch(dialog('resumeAll').effect, /every halted agent starts/i)
      assert.match(dialog('resumeAll').effect, /queued|queue/i)
    })
    await test('STOP dialog does not promise Resume all restarts every agent', () => {
      seed([run])
      assert.doesNotMatch(dialog('stop').effect, /Resume all restarts them/i)
    })
    await test('queued resume REST result produces a pending toast and preserves the returned run', async () => {
      seed([halted])
      const message = await request('resume', halted, queued)
      assert.match(message, /queued|pending|waiting/i)
      assert.doesNotMatch(message, /is starting|working again/i)
      assert.deepEqual(cache.getQueryData(['runs']), [halted, queued])
    })
    await test('mixed resume-all response counts queued work without claiming execution', async () => {
      seed([halted])
      const skipped = [{ run_id: 'run/compromised', reason: 'Confirmed compromise' }]
      const message = await request('resumeAll', undefined, { resumed: [queued], skipped })
      assert.match(message, /1 .*queued|1 .*pending/i)
      assert.doesNotMatch(message, /starting again/i)
      assert.match(message, /1 .*skipped/i)
      assert.deepEqual(cache.getQueryData(['runs']), [halted, queued])
    })
    for (const status of ['running', 'failed']) {
      await test(`resume preserves an observed ${status} REST result without calling it queued`, async () => {
        seed([halted])
        const after = { ...queued, status }
        const message = await request('resume', halted, after)
        assert.ok(message.includes(status))
        assert.doesNotMatch(message, /queued|awaiting owner/i)
        assert.deepEqual(cache.getQueryData(['runs']), [halted, after])
      })
    }
    await test('pending resume approval cannot optimistically start a replacement run', async () => {
      seed([halted])
      let finish
      globalThis.fetch = () => new Promise((resolve) => { finish = resolve })
      const pending = capture(actions.useHumanAction).mutateAsync({ kind: 'resume', run: halted, body })
      await new Promise((resolve) => setImmediate(resolve))
      try {
        assert.deepEqual(cache.getQueryData(['runs']), [halted])
        assert.equal(stat(render(Fleet), 'Active Agents'), 0)
      } finally { finish(new Response(JSON.stringify(queued))); await pending }
      assert.deepEqual(cache.getQueryData(['runs']), [halted, queued])
    })
    await test('observed live owned running and frozen runs retain their explicit human controls', () => {
      seed([run])
      assert.ok(enabled(render(Fleet), 'Freeze'))
      const frozen = { ...run, status: 'frozen' }
      seed([frozen])
      assert.ok(enabled(render(Fleet), 'Unfreeze'))
      assert.ok(enabled(render(Fleet), 'Kill'))
    })
    for (const status of ['running', 'frozen']) {
      await test(`restored unowned ${status} history does not expose live controls`, () => {
        seed([{ ...run, status }], runtime([]))
        const html = render(Fleet)
        for (const label of ['Freeze', 'Unfreeze', 'Kill']) assert.ok(!enabled(html, label), `${label} needs current live authority`)
        assert.match(text(html), /restored|history|no live|not controlled|unowned/i)
        assert.equal(stat(html, 'Active Agents'), 0)
        assert.equal(stat(html, 'Healthy Agents'), 0)
      })
    }
    for (const [name, info, state] of [
      ['unknown runtime', null, 'connecting'],
      ['disconnected runtime with stale owned IDs', runtime([run.id]), 'disconnected'],
      ['replay engine despite live UI mode', runtime([run.id], { engine_mode: 'replay' }), 'streaming'],
    ]) {
      await test(`${name} cannot establish live control authority`, () => {
        for (const status of ['running', 'frozen']) {
          seed([{ ...run, status }], info)
          connection(info, state)
          const html = render(Fleet)
          for (const label of ['Freeze', 'Unfreeze', 'Kill']) assert.ok(!enabled(html, label), `${label} must fail closed`)
          assert.equal(stat(html, 'Active Agents'), 0)
        }
      })
    }
    await test('a changed engine instance removes stale ownership even when saved runs stay running', () => {
      seed([run])
      assert.ok(enabled(render(Fleet), 'Freeze'))
      connection(runtime([], { instance_id: 'synthetic-engine-b', stream_epoch: 'synthetic-epoch-b' }))
      assert.ok(!enabled(render(Fleet), 'Freeze'))
      assert.equal(stat(render(Fleet), 'Active Agents'), 0)
      assert.deepEqual(cache.getQueryData(['runs']), [run], 'Ownership changes must preserve historical evidence')
    })
    for (const status of [200, 409]) {
      await test(`late ${status} control response from a previous engine cannot replace current evidence`, async () => {
        seed([run])
        let finish
        globalThis.fetch = () => new Promise((resolve) => { finish = resolve })
        const pending = capture(actions.useHumanAction).mutateAsync({ kind: 'freeze', run, body })
        await new Promise((resolve) => setImmediate(resolve))
        const current = { ...run, id: 'run/current-engine', status: 'running' }
        connection(runtime([current.id], { instance_id: 'synthetic-engine-b', stream_epoch: 'synthetic-epoch-b' }))
        cache.setQueryData(['runs'], [current])
        finish(new Response(JSON.stringify(status === 200 ? { ...run, status: 'frozen' }
          : { detail: 'Synthetic old engine refused the action' }), { status }))
        if (status === 200) await pending
        else await assert.rejects(pending, { status: 409 })
        assert.deepEqual(cache.getQueryData(['runs']), [current], 'Stale completion/rollback must not restore the old engine cache')
      })
    }
    await test('queued recovery is pending until a running run has an observed live owner', () => {
      seed([halted, queued], runtime([]))
      const pending = render(Fleet)
      assert.match(text(pending), /pending|awaiting owner|waiting for .*start/i)
      assert.equal(stat(pending, 'Active Agents'), 0)
      assert.ok(!enabled(pending, 'Freeze'))
      cache.setQueryData(['runs'], [halted, { ...queued, status: 'running' }])
      assert.equal(stat(render(Fleet), 'Active Agents'), 0, 'Saved running alone is not current execution')
      connection(runtime([queued.id]))
      assert.equal(stat(render(Fleet), 'Active Agents'), 1)
      assert.ok(enabled(render(Fleet), 'Freeze'))
    })
    await test('failed run renders the failure and backend reason without becoming healthy or stopped', () => {
      const failed = { ...run, status: 'failed', status_reason: 'Synthetic owner exited before task completion', ended_at: '2026-10-11T00:01:00Z' }
      seed([failed], runtime([]))
      const html = render(Fleet)
      assert.match(html, />Failed</)
      assert.ok(text(html).includes(failed.status_reason))
      assert.equal(stat(html, 'Active Agents'), 0)
      assert.equal(stat(html, 'Healthy Agents'), 0)
      for (const label of ['Freeze', 'Unfreeze', 'Kill', 'Resume', 'Approve clean restart']) assert.ok(!enabled(html, label))
    })
    await test('an older completed run cannot make an agent with a newer failed run look healthy', () => {
      const completed = { ...run, status: 'completed', ended_at: '2026-10-11T00:01:00Z' }
      const failed = { ...run, id: 'run/newer-failure', status: 'failed',
        started_at: '2026-10-11T00:02:00Z', ended_at: '2026-10-11T00:03:00Z', status_reason: 'Synthetic task failed' }
      seed([completed, failed], runtime([]))
      assert.equal(stat(render(Fleet), 'Healthy Agents'), 0)
    })
    await test('restart eligibility matches the published endpoint: killed/halted only, not failed', () => {
      seed([run], runtime([]))
      for (const status of ['killed', 'halted'])
        assert.ok(enabled(render(actions.CleanRestartButton, { run: { ...run, status } }), 'Approve clean restart'))
      for (const status of ['queued', 'running', 'frozen', 'completed', 'failed'])
        assert.equal(render(actions.CleanRestartButton, { run: { ...run, status } }), '')
    })
    await test('restart approval preserves queued authority and the existing trace link', async () => {
      const killed = { ...run, status: 'killed' }
      seed([killed], runtime([]))
      assert.match(await request('restart', killed, queued), /queued.*Waiting for the owner/i)
      assert.deepEqual(cache.getQueryData(['runs']), [killed, queued])
      const pending = render(actions.CleanRestartButton, { run: killed })
      assert.match(pending, /pending · awaiting owner start/)
      assert.match(pending, /href="\/runs\/run%2Ftwo"/)
      assert.ok(!enabled(pending, 'Approve clean restart'))
    })
    await test('ownership refusal sends one actor/reason POST and rolls back without inventing execution', async () => {
      const frozen = { ...run, status: 'frozen' }
      seed([frozen])
      const before = cache.getQueryData(['runs'])
      let calls = 0
      globalThis.fetch = async (path, init) => {
        calls++
        assert.equal(path, '/api/runs/run%2Fone/unfreeze')
        assert.deepEqual(JSON.parse(init.body), body)
        return new Response(JSON.stringify({ detail: 'Run run/one is owned by another process (no live control)' }), { status: 409 })
      }
      await assert.rejects(capture(actions.useHumanAction).mutateAsync({ kind: 'unfreeze', run: frozen, body }), { status: 409 })
      assert.equal(calls, 1, 'Human POSTs must not retry')
      assert.deepEqual(cache.getQueryData(['runs']), before)
      assert.doesNotMatch(String(toast.getHistory().at(-1).title), /working again/i)
    })
  }
  cache.clear()
} finally {
  globalThis.fetch = originalFetch
  await server.close()
}

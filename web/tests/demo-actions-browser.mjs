// Synthetic API boundary test, not Bedrock or managed-backend acceptance.
// Run from web/: MIRAGE_PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node tests/demo-actions-browser.mjs
import assert from 'node:assert/strict'
import { createServer } from 'vite'
const { chromium } = await import(process.env.MIRAGE_PLAYWRIGHT_MODULE || 'playwright')
const browser = await chromium.launch({ headless: true })
try {
  for (const mode of ['default', 'live', 'demo']) {
    if (mode === 'default') delete process.env.VITE_MIRAGE_UI_MODE
    else process.env.VITE_MIRAGE_UI_MODE = mode
    const demo = mode === 'demo'
    const server = await createServer({ server: { host: '127.0.0.1', port: 0 } })
    const context = await browser.newContext()
    try {
      await server.listen()
      const page = await context.newPage()
      page.setDefaultTimeout(8000)
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      const run = { id: 'run_004', agent: 'meeting_assistant', task: 'Synthetic UI test', status: 'running',
        env: 'prod', started_at: new Date().toISOString(), ended_at: null, incident_id: null, tool_calls: 0 }
      let runs = [run]
      const events = []
      const posts = []
      let fail = false
      await page.route(/^http:\/\/127\.0\.0\.1:\d+\/api\//, async (route) => {
        const request = route.request()
        const path = new URL(request.url()).pathname.replace('/api', '')
        if (request.method() === 'POST') {
          posts.push({ path, body: request.postDataJSON() })
          if (fail) return route.fulfill({ status: 409, json: { detail: 'Synthetic action refused' } })
          const stop = path === '/stop'
          assert.ok(stop || path === '/resume-all', `Unexpected effect: ${path}`)
          events.push({ seq: events.length + 1, ts: new Date().toISOString(), type: stop ? 'global.stop' : 'global.stop_lifted',
            run_id: null, incident_id: null, env: 'prod', payload: {} })
          run.status = stop ? 'halted' : 'running'
          if (!stop && !demo) runs = [run, { ...run, id: 'run_005', status: 'queued', restarted_from: run.id }]
          return stop ? route.fulfill({ status: 204 }) : route.fulfill({ json: { resumed: demo ? [] : [runs[1]], skipped: [] } })
        }
        if (path === '/stream') return route.fulfill({ contentType: 'text/event-stream', body: 'retry: 50\n\n' + events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('') })
        if (path === '/incidents/inc_001') return route.fulfill({ json: {
          id: 'inc_001', run_id: run.id, status: 'fix_pending', snapshot_id: 'synthetic-snapshot',
          trigger: { call_id: 'synthetic-call', tool: 'send_email', args: {}, layer: 'hard_rule', explanation: 'Synthetic blocked call' },
          inputs: [], bisection: [], next_action: 'none',
        } })
        return route.fulfill({ json: path === '/runs' ? runs : path === '/events' ? events : [] })
      })
      await page.goto(server.resolvedUrls.local[0] + 'runs/run_004')
      await page.getByRole('button', { name: 'Sign in', exact: true }).click().catch(async (error) => {
        console.error(page.url(), errors, await page.locator('body').innerText())
        throw error
      })
      const stopLabel = demo ? 'Pause recording' : 'Stop all'
      const resumeLabel = demo ? 'Resume recording' : 'Resume all'
      const stopDialog = demo ? 'Pause recording?' : 'Stop all agents?'
      const resumeDialog = demo ? 'Resume recording?' : 'Resume all agents?'
      const open = async (label, title) => {
        await page.getByRole('button', { name: label, exact: true }).click()
        return page.getByRole('dialog', { name: title, exact: true })
      }
      let dialog = await open(stopLabel, stopDialog)
      assert.equal(await dialog.getByRole('button', { name: stopLabel, exact: true }).isDisabled(), true)
      await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
      assert.deepEqual(posts, [])
      fail = true
      dialog = await open(stopLabel, stopDialog)
      await dialog.getByRole('textbox', { name: 'Reason details' }).fill('Synthetic pause')
      await dialog.getByRole('button', { name: stopLabel, exact: true }).click()
      await page.getByText('Synthetic action refused', { exact: true }).waitFor()
      await page.getByRole('button', { name: stopLabel, exact: true }).waitFor()
      fail = false
      dialog = await open(stopLabel, stopDialog)
      const description = await dialog.getByRole('paragraph').first().textContent()
      assert.ok(demo ? !description.includes('tokens') : description.includes('tokens are revoked'))
      await dialog.getByRole('textbox', { name: 'Reason details' }).fill('Synthetic pause')
      await dialog.getByRole('button', { name: stopLabel, exact: true }).click()
      await page.getByText(demo ? 'Recording paused. Active recorded runs are halted.' : 'All agents stopped.', { exact: true }).waitFor()
      await page.getByRole('button', { name: resumeLabel, exact: true }).waitFor()
      assert.equal(await page.getByRole('button', { name: 'Resume', exact: true }).count(), demo ? 0 : 1)
      await page.getByRole('button', { name: /^Search/ }).click()
      await page.getByRole('dialog', { name: 'Command menu' }).waitFor()
      assert.equal(await page.getByText('Resume Meeting assistant', { exact: true }).count(), demo ? 0 : 1)
      await page.keyboard.press('Escape')
      dialog = await open(resumeLabel, resumeDialog)
      assert.ok((await dialog.textContent()).includes(demo ? 'No agents or providers are launched' : 'starts its task again from the beginning'))
      await dialog.getByRole('textbox', { name: 'Reason details' }).fill('Synthetic recovery')
      await dialog.getByRole('button', { name: resumeLabel, exact: true }).click()
      await page.getByText(demo ? 'Recording resumed from where it paused. Prior recorded run states restored.' : '1 agent starting again.', { exact: true }).waitFor()
      await page.getByRole('button', { name: stopLabel, exact: true }).waitFor()
      assert.deepEqual(posts, [
        { path: '/stop', body: { actor: 'liam', reason: 'Synthetic pause' } },
        { path: '/stop', body: { actor: 'liam', reason: 'Synthetic pause' } },
        { path: '/resume-all', body: { actor: 'liam', reason: 'Synthetic recovery' } },
      ])
      events.push({ seq: events.length + 1, ts: new Date().toISOString(), type: 'handoff.created',
        run_id: run.id, incident_id: 'inc_001', env: 'prod', payload: { prompt: 'Synthetic handoff example.' } })
      await page.goto(server.resolvedUrls.local[0] + 'incidents/inc_001')
      await page.getByRole('button', { name: 'Sign in', exact: true }).click()
      await page.getByRole('button', { name: 'Hand off to coding agent', exact: true }).click()
      const drawer = page.getByRole('dialog', { name: demo ? 'Demo handoff to coding agent' : 'Hand off to coding agent', exact: true })
      const liveAccess = 'This prompt includes access scoped to this incident. Share it only with your coding agent.'
      await drawer.getByText(demo ? 'This prompt is a recorded example. It does not grant live incident access.' : liveAccess, { exact: true }).waitFor()
      assert.equal(await drawer.getByText(liveAccess, { exact: true }).count(), demo ? 0 : 1)
      const prompt = await drawer.getByLabel('Handoff prompt').textContent()
      assert.ok(demo ? prompt.startsWith('Recorded demo handoff:') : prompt === 'Synthetic handoff example.')
      assert.deepEqual(errors, [])
      console.log(`PASS ${mode}: reason/cancel/failure guards, stop/recovery routes and toasts, per-run and command-menu availability, truthful handoff access copy`)
    } finally { await context.close(); await server.close() }
  }
} finally { await browser.close() }

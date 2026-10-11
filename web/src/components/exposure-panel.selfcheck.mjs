// Run from web/: node src/components/exposure-panel.selfcheck.mjs [engine-job.json]
import assert from 'node:assert/strict'
import { readFile, rm } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const output = resolve('node_modules/.tmp/exposure-selfcheck')
try {
  await build({ logLevel: 'warn', build: { ssr: 'src/components/exposure-panel.tsx', outDir: output, emptyOutDir: true } })
  const { ExposureResults, displayedExposureStatus } = await import(pathToFileURL(`${output}/exposure-panel.js`))
  const observation = (compromised_runs = '0/1') => ({ compromised_runs, legit_task_completed: '1/1', completed: true, error: null,
    effects: [{ detonation_id: 'det_sibling', run_index: 1, step: 1, tool: 'send_email', args: { body: '<script>external instruction</script>' }, violates: [], error: null }] })
  const identity = { snapshot_id: 'snapshot_sibling', snapshot_revision: 's'.repeat(64), code_revision: 'c'.repeat(40), policy_revision: 'p'.repeat(64), replay_kind: 'model_backed' }
  const results = [
    { ...identity, agent_name: 'meeting_assistant_sibling', status: 'vulnerable', reason: 'A prohibited effect was observed.', attack: observation('1/1'), clean: observation() },
    { ...identity, agent_name: 'restricted_assistant', status: 'blocked', reason: 'The task completed without prohibited effects.', attack: observation(), clean: observation() },
    { agent_name: 'invoicing', status: 'not_applicable', reason: 'No calendar input path.' },
    { agent_name: 'unsupported', status: 'could_not_evaluate', reason: 'Missing independent recording.' },
  ]
  const job = { id: 'exposure_1', incident_id: 'inc_original', agent_names: results.map((r) => r.agent_name), status: 'completed', results }
  const render = (data) => renderToStaticMarkup(createElement(ExposureResults, { job: data }))
  const html = render(job)
  for (const status of ['vulnerable', 'blocked', 'not_applicable', 'could_not_evaluate']) assert.ok(html.includes(`data-status="${status}"`))
  for (const value of ['1/1 compromised', '0/1 compromised', '1/1 legitimate task completed', ...Object.values(identity).slice(0, 4)]) assert.ok(html.includes(value))
  assert.ok(html.includes('Fresh model-backed replay'))
  assert.ok(html.includes('&lt;script&gt;'))
  assert.ok(!html.includes('<script>'))
  assert.equal(displayedExposureStatus({ ...results[1], clean: null }), 'could_not_evaluate')
  assert.equal(displayedExposureStatus({ ...results[1], attack: { ...observation(), error: 'read_unavailable' } }), 'could_not_evaluate')
  assert.equal(displayedExposureStatus({ ...results[1], clean: { ...observation(), legit_task_completed: '0/1' } }), 'could_not_evaluate')
  assert.equal(displayedExposureStatus({ ...results[0], attack: { ...observation('1/1'), completed: false, error: 'execution_failed' } }), 'vulnerable') // Earlier harm survives a later error.
  assert.equal(displayedExposureStatus({ ...results[0], attack: null }), 'could_not_evaluate')
  assert.ok(render({ ...job, results: [{ ...results[0], replay_kind: 'scripted' }] }).includes('Scripted replay'))
  assert.ok(!render({ ...job, status: 'queued', results: [] }).includes('data-status="blocked"'))
  if (process.argv[2]) {
    const actual = JSON.parse(await readFile(process.argv[2], 'utf8'))
    const actualHtml = render(actual)
    for (const result of actual.results) {
      assert.ok(actualHtml.includes(`data-status="${displayedExposureStatus(result)}"`))
      if (result.snapshot_revision) assert.ok(actualHtml.includes(result.snapshot_revision))
    }
    console.log(`Rendered actual engine job ${actual.id}: ${actual.results.length} results`)
  }
  console.log('Exposure presentation checks passed: four statuses, exact identities, 1/1 counts, errors and escaped effects')
} finally {
  await rm(output, { recursive: true, force: true })
}

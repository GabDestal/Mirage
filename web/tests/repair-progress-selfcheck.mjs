// Synthetic render checks. Real coding-worker and provider acceptance belongs to the operator rehearsal.
import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClientProvider } from '@tanstack/react-query'
import { createServer } from 'vite'

process.env.MIRAGE_UI_MODE = 'live'
const cacheDir = await mkdtemp(join(tmpdir(), 'mirage-repair-render-'))
const server = await createServer({ configLoader: 'runner', cacheDir, server: { middlewareMode: true, ws: false }, appType: 'custom' })
try {
  const { RepairProgress } = await server.ssrLoadModule('/src/components/repair-progress.tsx')
  const { queryClient } = await server.ssrLoadModule('/src/api/client.ts')
  const base = { id: 'repair_synthetic', incident_id: 'inc_synthetic', repository: 'GabDestal/Mirage', base_branch: 'special-improvements',
    base_sha: 'a'.repeat(40), snapshot_digest: 'b'.repeat(64), baseline_digest: 'c'.repeat(64), created_at: 'now', updated_at: 'now' }
  const render = (job, canStart = false) => {
    queryClient.clear()
    queryClient.setQueryData(['repair-jobs', base.id], { ...base, ...job })
    return renderToStaticMarkup(createElement(QueryClientProvider, { client: queryClient }, createElement(RepairProgress, { incidentId: base.incident_id, jobId: base.id, canStart })))
  }
  const queued = render({ status: 'queued' })
  assert.ok(queued.includes('Repair queued') && queued.includes('role="status"'))
  assert.ok(!queued.includes('Review draft PR') && !queued.includes('Attack blocked'))
  const running = render({ status: 'running' })
  assert.ok(running.includes('local repair runtime') && !running.includes('draft PR is ready'))
  const verifying = render({ status: 'verifying' })
  assert.ok(verifying.includes('committed candidate') && !verifying.includes('Attack blocked'))
  const failed = render({ status: 'failed', error: 'verification_failed' })
  assert.ok(failed.includes('run stays contained') && failed.includes('role="alert"') && failed.includes('did not pass'))
  assert.ok(render({ status: 'failed', error: 'verification_failed' }, true).includes('Retry repair'))
  assert.ok(!render({ status: 'running' }, true).includes('Retry repair'))
  const ready = render({ status: 'pr_open', candidate_sha: 'd'.repeat(40), pr_url: 'https://github.com/GabDestal/Mirage/pull/201',
    verification: { attack_blocked: '3/3', legit_task_completed: '3/3', clean_task_completed: '1/1' } })
  assert.ok(ready.includes('Review draft PR') && ready.includes('Clean task</dt><dd>1/1') && ready.includes('dddddddddddd'))
  assert.ok(ready.includes('noopener noreferrer') && ready.includes('separately approves a clean restart'))
  assert.ok(!render({ status: 'pr_open', pr_url: 'javascript:alert(1)' }).includes('href='))
  assert.ok(!ready.includes('prompt') && !ready.includes('token') && !ready.includes('terminal transcript'))
  console.log('RepairProgress: synthetic progress, retry and privacy checks passed.')
} finally { await server.close(); await rm(cacheDir, { recursive: true, force: true }) }

// Synthetic markup and handler checks only; browser/provider acceptance is separate.
// Run from web/: node tests/handoff-ui-selfcheck.mjs [--demo]
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { Children, cloneElement, isValidElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { toast } from 'sonner'
import { createServer } from 'vite'

const demo = process.argv.includes('--demo')
process.env.MIRAGE_UI_MODE = demo ? 'demo' : 'live'
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' })
const originals = Object.fromEntries(['navigator', 'window', 'fetch'].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
const mock = (key, value) => Object.defineProperty(globalThis, key, { configurable: true, value })
const prompt = 'Incident inc_synthetic\nSnapshot snap_synthetic\nMIRAGE_SNAPSHOTS=/synthetic/snapshots\nMIRAGE_DB=/synthetic/events.db\nuv run python -m engine.cli detonate --incident inc_synthetic\nUntrusted data: <send_email>\n'
const manualCopy = 'Clipboard unavailable. Select and copy the prompt in the drawer.'
const settle = () => new Promise((done) => setImmediate(done))

try {
  const { HandoffDrawer } = await server.ssrLoadModule('/src/components/handoff-drawer.tsx')
  const { Button } = await server.ssrLoadModule('/src/components/ui/button.tsx')
  const { api, queryClient } = await server.ssrLoadModule('/src/api/client.ts')
  const nodes = (node) => isValidElement(node)
    ? [node, ...Children.toArray(node.props.children).flatMap(nodes)] : []
  const drawer = (props = {}) => HandoffDrawer({ open: true, onClose() {}, prompt, ...props })
  // SSR does not mount portals. Keep the real Radix root/content, placing its portal children inline.
  const markup = (tree) => {
    const window = Object.getOwnPropertyDescriptor(globalThis, 'window')
    delete globalThis.window
    try { return renderToStaticMarkup(cloneElement(tree, {}, tree.props.children.props.children)) }
    finally { if (window) Object.defineProperty(globalThis, 'window', window) }
  }
  const buttons = (tree) => nodes(tree).filter((node) => node.type === Button && node.props.onClick)
  const displayedPrompt = (tree) => nodes(tree).find((node) => node.props['aria-label'] === 'Handoff prompt')
  const click = async (button) => {
    assert.equal(button.props.disabled, false)
    button.props.onClick()
    await settle()
  }
  const expectedPrompt = displayedPrompt(drawer()).props.children

  await test('access wording matches live local paths or a labelled recorded example', () => {
    const html = markup(drawer())
    assert.ok(!html.includes('This prompt includes access scoped to this incident'))
    if (demo) {
      assert.ok(html.includes('Demo handoff to coding agent'))
      assert.ok(html.includes('does not grant live incident access'))
      assert.ok(html.includes('does not provide a live executable snapshot'))
      assert.ok(expectedPrompt.startsWith('Recorded demo handoff:'))
      assert.ok(expectedPrompt.endsWith(prompt))
    } else {
      assert.ok(html.includes('incident context') && html.includes('local verification paths'))
      assert.ok(html.includes('checkout and snapshot') && html.includes('reachable Mirage deployment'))
      assert.ok(html.includes('transfer files') && html.includes('connect Mirage'))
      assert.equal(expectedPrompt, prompt, 'Live backend prompt must remain byte-for-byte intact')
    }
    assert.ok(html.includes('human') && html.includes('merges the PR') && html.includes('approves a clean restart'))
    assert.ok(html.includes('tabindex="0" aria-label="Handoff prompt"'))
    assert.ok(html.includes('&lt;send_email&gt;') && !html.includes('<send_email>'))
  })

  await test('loading disables every prompt action and displays its status', () => {
    const tree = drawer({ prompt: undefined })
    assert.equal(buttons(tree).length, 3)
    assert.ok(buttons(tree).every((button) => button.props.disabled))
    assert.ok(markup(tree).includes('Loading prompt…'))
    assert.equal((markup(tree).match(/disabled=""/g) ?? []).length, 3)
  })

  await test('empty or whitespace-only text cannot enable a handoff', () => {
    for (const value of ['', ' \n\t'])
      assert.ok(buttons(drawer({ prompt: value })).every((button) => button.props.disabled))
  })

  await test('a backend error disables stale prompt actions and remains visible', () => {
    const tree = drawer({ error: 'Synthetic snapshot unavailable. Close and try again.' })
    assert.ok(buttons(tree).every((button) => button.props.disabled))
    assert.ok(markup(tree).includes('role="alert"'))
    assert.ok(markup(tree).includes('Synthetic snapshot unavailable. Close and try again.'))
    assert.equal(displayedPrompt(tree), undefined)
  })

  await test('copy preserves the exact prompt and never opens an agent', async () => {
    const copied = []
    mock('navigator', { clipboard: { writeText: async (value) => copied.push(value) } })
    mock('window', { open() { assert.fail('Copy prompt must not open a tab') } })
    await click(buttons(drawer())[2])
    assert.deepEqual(copied, [expectedPrompt])
    assert.equal(toast.getHistory().at(-1).title, 'Prompt copied.')
  })

  await test('agent buttons open the existing no-prefill URLs before copying', async () => {
    for (const [index, name, url] of [[0, 'Claude Code', 'https://claude.ai/code'], [1, 'Codex', 'https://chatgpt.com/codex/cloud']]) {
      const calls = []
      mock('window', { open: (...args) => { calls.push(['open', ...args]); return null } })
      mock('navigator', { clipboard: { writeText: async (value) => calls.push(['copy', value]) } })
      await click(buttons(drawer())[index])
      assert.deepEqual(calls, [['open', url, '_blank', 'noopener,noreferrer'], ['copy', expectedPrompt]])
      assert.equal(toast.getHistory().at(-1).title, `Prompt copied. Paste it into ${name}.`)
    }
  })

  await test('absent or rejected clipboard keeps the exact manual-copy fallback', async () => {
    for (const navigator of [{}, { clipboard: { writeText: async () => { throw new Error('Synthetic permission denied') } } }]) {
      mock('navigator', navigator)
      await click(buttons(drawer())[2])
      assert.equal(toast.getHistory().at(-1).title, manualCopy)
      assert.equal(displayedPrompt(drawer()).props.children, expectedPrompt)
    }
    const opened = []
    mock('navigator', {})
    mock('window', { open: (...args) => opened.push(args) })
    await click(buttons(drawer())[0])
    assert.equal(opened.length, 1)
    assert.equal(toast.getHistory().at(-1).title, manualCopy)
  })

  await test('mocked handoff REST response keeps its separate token out of the drawer and actions', async () => {
    const calls = []
    const token = 'synthetic-separate-capability'
    const body = { actor: 'synthetic via web', reason: 'Hand off a synthetic incident' }
    mock('fetch', async (path, init) => {
      calls.push({ path, method: init.method, body: JSON.parse(init.body) })
      return new Response(JSON.stringify({ prompt, mirage_token: token }))
    })
    const result = await api(`/incidents/${encodeURIComponent('inc/synthetic')}/handoff`, body)
    assert.deepEqual(calls, [{ path: '/api/incidents/inc%2Fsynthetic/handoff', method: 'POST', body }])
    const tree = drawer({ prompt: result.prompt })
    assert.ok(!markup(tree).includes(token))
    mock('navigator', { clipboard: { writeText: async (value) => { assert.equal(value, expectedPrompt); assert.ok(!value.includes(token)) } } })
    mock('window', { open: (url) => { assert.ok(!url.includes(token)); assert.equal(new URL(url).search, '') } })
    for (const button of buttons(tree)) await click(button)
    queryClient.clear()
  })

  await test('mocked failed handoff surfaces the backend message without retrying or enabling old text', async () => {
    let calls = 0
    mock('fetch', async () => { calls++; return new Response(JSON.stringify({ detail: 'Synthetic incident has no snapshot' }), { status: 409 }) })
    let error
    await assert.rejects(api('/incidents/inc_synthetic/handoff', { actor: 'synthetic', reason: 'Synthetic check' }), (cause) => {
      assert.equal(cause.status, 409)
      error = cause.message
      return true
    })
    assert.equal(calls, 1)
    const tree = drawer({ error })
    assert.ok(markup(tree).includes(error))
    assert.ok(buttons(tree).every((button) => button.props.disabled))
  })

  await test('closing delegates to the owner and reopening preserves the prompt', () => {
    let closed = 0
    const tree = drawer({ onClose() { closed++ } })
    tree.props.onOpenChange(true)
    assert.equal(closed, 0)
    tree.props.onOpenChange(false)
    assert.equal(closed, 1)
    assert.equal(displayedPrompt(drawer()).props.children, expectedPrompt)
  })
} finally {
  for (const [key, descriptor] of Object.entries(originals)) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor)
    else delete globalThis[key]
  }
  await server.close()
}

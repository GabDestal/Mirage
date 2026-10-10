// Run against chat-harness.mjs only. Playwright stays an external QA dependency.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
const { chromium } = await import(process.env.MIRAGE_PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.MIRAGE_UI_URL || 'http://127.0.0.1:5176'
const out = process.env.MIRAGE_QA_DIR || '.impeccable/review'
await mkdir(out, { recursive: true })
const browser = await chromium.launch({ headless: true })
const evidence = []
for (const [device, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
  const context = await browser.newContext({ viewport, colorScheme: 'dark', permissions: ['clipboard-read', 'clipboard-write'] })
  const page = await context.newPage()
  await page.route('**/api/runs', (route) => route.fulfill({ json: [{
    id: 'synthetic-run', agent: 'assistant', env: 'prod', task: 'Synthetic UI fixture',
    status: 'frozen', started_at: '2026-10-10T14:02:11Z', ended_at: null,
    incident_id: 'synthetic-incident', restarted_from: null, tool_calls: 4,
  }] }))
  page.setDefaultTimeout(8000)
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  const record = async (name, run) => {
    try { await run(); evidence.push({ device, name, passed: true }); console.log(`PASS ${device}: ${name}`) }
    catch (error) { evidence.push({ device, name, passed: false, error: error.message }); console.log(`FAIL ${device}: ${name}: ${error.message}`); await page.screenshot({ path: `${out}/${device}-failure-${name.replaceAll(' ', '-')}.png` }) }
  }
  await page.goto(base)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('heading', { name: 'What needs your attention today?' }).waitFor()
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(300)
  const input = page.getByRole('textbox', { name: 'Message Miragio', exact: true })
  const stop = page.getByRole('button', { name: 'Stop response' })
  const send = async (message) => { await input.fill(message); await input.press('Enter') }
  const newChat = async () => { await page.getByRole('button', { name: 'New chat', exact: true }).click() }
  const done = async () => { await page.getByRole('button', { name: 'Send message', exact: true }).waitFor(); await page.getByRole('button', { name: 'Copy response', exact: true }).last().waitFor() }
  await record('welcome and light shell', async () => {
    assert.equal(await page.locator('.shell--chat').evaluate((el) => getComputedStyle(el).getPropertyValue('--paper').trim()), '#fff')
    assert.equal(await page.locator('.chat-page').evaluate((el) => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)')
    await page.getByRole('button', { name: 'Stop all', exact: true }).waitFor()
    assert.ok(await input.isVisible())
    await page.screenshot({ path: `${out}/${device}.png` })
  })
  await record('suggestions and incident summary auto-send', async () => {
    const prompts = [
      ['Which agents need my attention?', 'Which agents need my attention?'],
      ['Show me the proof for the latest incident', 'Show me the proof for the latest incident'],
      ['What is happening across my agents?', 'What is happening across my agents?'],
      ['Summarize incidents', 'Which agents need my attention?'],
    ]
    for (const [button, message] of prompts) {
      await input.fill('Existing draft should not be sent')
      const before = await (await fetch(base + '/chat/debug')).json()
      await page.getByRole('button', { name: button, exact: true }).click()
      await done()
      assert.equal(await page.locator('.chat-question').textContent(), `You: ${message}`)
      assert.equal(await input.inputValue(), '')
      const after = await (await fetch(base + '/chat/debug')).json()
      assert.equal(after.turns.length, before.turns.length + 1)
      assert.equal(after.turns.at(-1).message, message)
      await newChat()
    }
  })
  await record('keyboard and IME', async () => {
    await input.fill('harness stream')
    await input.press('Shift+Enter')
    assert.match(await input.inputValue(), /\n/)
    await input.evaluate((el) => el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, isComposing: true })))
    assert.equal(await page.locator('.chat-turn').count(), 0)
    await input.press('Enter')
    await stop.waitFor()
    await page.getByText('Synthetic UI harness reply.', { exact: false }).first().waitFor()
    await done()
    assert.equal(await page.locator('.chat-turn').count(), 1)
    assert.equal(await input.inputValue(), '')
    await send('harness stream followup')
    await done()
    const debug = await (await fetch(base + '/chat/debug')).json()
    assert.ok(debug.turns.at(-1).session_id)
    assert.equal(Object.hasOwn(debug.turns.at(-1), 'history'), false)
  })
  await record('tool evidence and handoff', async () => {
    await newChat()
    await send('harness tools handoff')
    await done()
    assert.equal(await page.locator('.mirage-tool-card').count(), 8)
    const sendFix = page.locator('.mirage-tool-card').filter({ has: page.getByText('Handing off to your coding agent', { exact: true }) })
    await sendFix.locator('summary').click()
    await page.waitForTimeout(250)
    assert.equal(await page.getByText('fixture-secret-to-redact', { exact: false }).count(), 0)
    const before = await (await fetch(base + '/chat/debug')).json()
    assert.equal(await page.locator('.chat-page').getByText('FLAG{team26-harness}', { exact: false }).count(), 0)
    await page.getByRole('button', { name: 'Hand off to coding agent', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: 'Hand off to coding agent' })
    await drawer.getByText('FLAG{team26-harness}', { exact: false }).waitFor()
    await drawer.getByRole('button', { name: 'Copy prompt', exact: true }).click()
    await page.getByText('Prompt copied.', { exact: true }).waitFor()
    const after = await (await fetch(base + '/chat/debug')).json()
    assert.equal(after.handoffReads, before.handoffReads + 1)
    await page.keyboard.press('Escape')
    await drawer.waitFor({ state: 'hidden' })
    await sendFix.locator('summary').scrollIntoViewIfNeeded()
    await page.waitForTimeout(250)
    await page.screenshot({ path: `${out}/${device}-tools.png` })
  })
  await record('approval retry and decision', async () => {
    await newChat()
    await send('harness approval')
    const form = page.getByRole('form', { name: 'Mirage approval' })
    await form.waitFor()
    await page.waitForTimeout(300)
    await page.screenshot({ path: `${out}/${device}-approval.png` })
    assert.equal(await form.locator('input, select, textarea').count(), 0)
    await page.getByText('Waiting for you', { exact: true }).waitFor()
    await form.getByRole('button', { name: 'Approve', exact: true }).click()
    await page.getByText(/Couldn't submit your decision/).waitFor()
    await form.getByRole('button', { name: 'Approve', exact: true }).click()
    await page.getByText('You approved this action', { exact: true }).waitFor()
    await done()
    await newChat()
    await send('harness approval race')
    await page.getByRole('form', { name: 'Mirage approval' }).waitFor()
    await page.getByRole('button', { name: 'Decline', exact: true }).click()
    await page.getByText('You declined this action', { exact: true }).waitFor()
  })
  await record('error preserved draft and recovery', async () => {
    await newChat()
    await send('harness error')
    await page.getByText('Synthetic fixture: model unavailable. Your draft is preserved.', { exact: true }).waitFor()
    assert.equal(await input.inputValue(), 'harness error')
    await page.screenshot({ path: `${out}/${device}-error.png` })
    await send('harness stream recovery')
    await done()
  })
  await record('stop and new chat fence', async () => {
    await newChat()
    await send('harness hold')
    await stop.waitFor()
    await stop.click()
    await page.getByText(/Reply stopped\./).waitFor()
    assert.equal(await input.inputValue(), '')
    await send('harness approval cancel')
    await page.getByRole('form', { name: 'Mirage approval' }).waitFor()
    await newChat()
    await page.getByRole('heading', { name: 'What needs your attention today?' }).waitFor()
    await page.waitForTimeout(80)
    assert.equal(await input.inputValue(), '')
    assert.equal(await page.locator('.chat-turn').count(), 0)
  })
  await record('long content scroll and safe rendering', async () => {
    await send('harness long')
    await page.getByText(/Evidence paragraph 12/).waitFor()
    await page.locator('.chat-thread').evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event('scroll')) })
    await page.getByRole('button', { name: 'Jump to latest' }).waitFor()
    const before = await page.locator('.chat-thread').evaluate((el) => el.scrollTop)
    await done()
    assert.equal(before, 0)
    assert.equal(await page.locator('.chat-thread').evaluate((el) => el.scrollTop), 0)
    assert.equal(await page.evaluate(() => window.bad), undefined)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await page.screenshot({ path: `${out}/${device}-long.png` })
    await page.getByRole('button', { name: 'Jump to latest' }).click()
    await page.waitForTimeout(400)
    assert.ok(await page.locator('.chat-thread').evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight < 80))
  })
  await record('offline draft and reduced motion', async () => {
    await input.fill('Draft retained offline')
    await context.setOffline(true)
    await page.getByText(/You’re offline\./).waitFor()
    assert.equal(await input.inputValue(), 'Draft retained offline')
    assert.ok(await input.isDisabled())
    await context.setOffline(false)
    await page.waitForFunction(() => !document.querySelector('textarea').disabled)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    assert.equal(await page.locator('.chat-suggestions').count(), 0)
    assert.equal(await page.locator('.chat-copy').first().evaluate((el) => getComputedStyle(el).transitionDuration), '1e-05s')
  })
  evidence.push({ device, name: 'runtime errors', passed: errors.length === 0, errors })
  await context.close()
}
await browser.close()
await writeFile(`${out}/chat-browser-results.json`, JSON.stringify(evidence, null, 2))
console.log(JSON.stringify(evidence, null, 2))
if (evidence.some((item) => !item.passed)) process.exitCode = 1

// Synthetic chat harness only; reuses the external Playwright install used by chat-browser.mjs.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
const { chromium } = await import(process.env.MIRAGE_PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.MIRAGE_UI_URL || 'http://127.0.0.1:5186'
const out = process.env.MIRAGE_QA_DIR || '../docs/miragio-qa'
await mkdir(out, { recursive: true })
const browser = await chromium.launch({ headless: true, executablePath: process.env.MIRAGE_CHROMIUM_EXECUTABLE })
function instrument({ random, hidden = false }) {
  const timers = new Set()
  const pointers = new Set()
  const listeners = new Set()
  window.miragioSchedule = []
  window.miragioRandom = random
  const rng = Math.random.bind(Math)
  Math.random = () => new Error().stack.includes('/src/components/miragio.tsx') ? window.miragioRandom : rng()
  const set = window.setTimeout.bind(window)
  const clear = window.clearTimeout.bind(window)
  const add = window.addEventListener.bind(window)
  const remove = window.removeEventListener.bind(window)
  window.setTimeout = (callback, delay, ...args) => {
    const owned = new Error().stack.includes('/src/components/miragio.tsx')
    const timer = set(() => { timers.delete(timer); callback(...args) }, delay)
    if (owned) { timers.add(timer); window.miragioSchedule.push({ delay, at: performance.now() }) }
    return timer
  }
  window.clearTimeout = (timer) => { timers.delete(timer); clear(timer) }
  window.addEventListener = (name, handler, options) => { if (name === 'pointermove' && new Error().stack.includes('/src/components/miragio.tsx')) pointers.add(handler); add(name, handler, options) }
  window.removeEventListener = (name, handler, options) => { if (name === 'pointermove') pointers.delete(handler); remove(name, handler, options) }
  const eventAdd = EventTarget.prototype.addEventListener
  const eventRemove = EventTarget.prototype.removeEventListener
  EventTarget.prototype.addEventListener = function (name, handler, options) {
    if (new Error().stack.includes('/src/components/miragio.tsx')) listeners.add(handler)
    return eventAdd.call(this, name, handler, options)
  }
  EventTarget.prototype.removeEventListener = function (name, handler, options) {
    listeners.delete(handler)
    return eventRemove.call(this, name, handler, options)
  }
  window.miragioResources = () => ({ timers: timers.size, pointers: pointers.size })
  window.miragioListeners = () => listeners.size
  if (hidden) Object.defineProperty(document, 'hidden', { configurable: true, value: true })
}
function watchBlinks(svg) {
  window.miragioClosed = []
  window.miragioHeadAtBlink = []
  window.miragioWatchStarted = performance.now()
  let closed = false
  window.miragioBlinkObserver = new MutationObserver(() => {
    const scale = /scaleY\(([^)]+)\)/.exec(svg.querySelector('[data-miragio="blink"]').style.transform)
    const next = scale && Number(scale[1]) < 0.7
    if (next && !closed) {
      window.miragioClosed.push(performance.now())
      window.miragioHeadAtBlink.push(svg.querySelector('[data-miragio="head"]').style.transform)
    }
    closed = next
  })
  window.miragioBlinkObserver.observe(svg, { attributes: true, subtree: true, attributeFilter: ['style'] })
}
async function setHidden(page, hidden) {
  await page.evaluate((value) => {
    Object.defineProperty(document, 'hidden', { configurable: true, value })
    document.dispatchEvent(new Event('visibilitychange'))
  }, hidden)
}
async function assertStill(page, welcome) {
  await page.waitForTimeout(100)
  assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 0, pointers: 0 })
  assert.equal(await welcome.locator('[data-miragio="blink"]').evaluate((el) => el.style.transform), 'none')
  const still = await welcome.locator('[data-miragio]').evaluateAll((els) => els.map((el) => el.getAttribute('style')))
  await page.waitForTimeout(400)
  assert.deepEqual(await welcome.locator('[data-miragio]').evaluateAll((els) => els.map((el) => el.getAttribute('style'))), still, 'Interrupted portrait stays static')
}
const results = []
try {
  for (const [device, viewport] of [['desktop', { width: 1440, height: 1000 }], ['phone', { width: 390, height: 844 }]]) {
    for (const theme of ['light', 'dark']) {
      const context = await browser.newContext({ viewport, colorScheme: theme })
      const page = await context.newPage()
      // Keep unrelated engine-status reflow out of the synthetic mascot lifecycle checks.
      await page.route(/\/api\/(runs|incidents)(\?.*)?$/, (route) => route.fulfill({ json: [] }))
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.clock.install()
      await page.addInitScript(instrument, { random: 0.5 })
      await page.goto(base)
      await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 100)))
      await page.getByRole('button', { name: 'Sign in', exact: true }).evaluate((button) => button.click())
      const welcome = page.locator('.chat-miragio')
      await welcome.waitFor()
      const head = welcome.locator('[data-miragio="head"]')
      assert.equal(await welcome.locator('[data-miragio="entry"]').count(), 0, 'No entrance wrapper')
      assert.equal(await head.evaluate((el) => getComputedStyle(el).transform), 'none', 'First frame is at rest')
      const initialTile = await welcome.evaluate((svg) => {
        const head = svg.querySelector('[data-miragio="head"]')
        const box = head.getBBox()
        return {
          fixed: [...head.parentElement.children].filter((el) => el !== head).map((el) => ({
            name: el.dataset.miragio || (el.tagName === 'rect' ? 'paper' : 'chest'),
            transform: getComputedStyle(el).transform, box: el.getBoundingClientRect().toJSON(),
          })),
          visible: box.x >= 0 && box.y >= 0 && box.x + box.width <= 1000 && box.y + box.height <= 1000,
          opacity: getComputedStyle(head).opacity,
          rect: { x: svg.getBoundingClientRect().x, y: svg.getBoundingClientRect().y, width: svg.getBoundingClientRect().width, height: svg.getBoundingClientRect().height },
        }
      })
      assert.deepEqual(initialTile.fixed.map(({ name }) => name), ['paper', 'chest', 'ribbon', 'ribbon'])
      assert.ok(initialTile.visible, 'Entire head is visible from the first frame')
      assert.equal(initialTile.opacity, '1', 'No appearance fade')
      await welcome.evaluate(watchBlinks)
      await page.screenshot({ clip: initialTile.rect, path: `${out}/${device}-${theme}-first.png` })
      await page.clock.runFor(80)
      assert.equal(await page.evaluate(() => window.miragioClosed.length), 1)
      assert.equal(await head.evaluate((el) => getComputedStyle(el).transform), 'none', 'Blink does not move the head')
      await page.screenshot({ clip: initialTile.rect, path: `${out}/${device}-${theme}-closed.png` })
      await page.clock.runFor(340)
      assert.equal(await page.evaluate(() => window.miragioClosed.length), 2, 'Startup forces two blinks even with random=.5')
      assert.equal(await welcome.locator('[data-miragio="blink"]').evaluate((el) => el.style.transform), 'none')
      assert.equal(await head.evaluate((el) => getComputedStyle(el).transform), 'none', 'No startup head transform')
      assert.deepEqual(await welcome.evaluate((svg) => {
        const head = svg.querySelector('[data-miragio="head"]')
        return [...head.parentElement.children].filter((el) => el !== head).map((el) => ({
          name: el.dataset.miragio || (el.tagName === 'rect' ? 'paper' : 'chest'),
          transform: getComputedStyle(el).transform, box: el.getBoundingClientRect().toJSON(),
        }))
      }), initialTile.fixed, 'Paper, chest and sea stay fixed')
      assert.ok(initialTile.fixed.every(({ transform }) => transform === 'none'))
      assert.deepEqual(await welcome.evaluate((svg) => {
        const { x, y, width, height } = svg.getBoundingClientRect()
        return { x, y, width, height }
      }), initialTile.rect, 'Tile and layout stay fixed')
      await page.screenshot({ clip: initialTile.rect, path: `${out}/${device}-${theme}-rest.png` })
      const startup = await page.evaluate(() => ({
        closes: window.miragioClosed.slice(), head: window.miragioHeadAtBlink.slice(),
      }))
      assert.ok(startup.head.every((transform) => transform === 'none'))
      assert.ok(startup.closes[1] - startup.closes[0] >= 160 && startup.closes[1] - startup.closes[0] <= 210, 'Second blink follows sequential 180ms close/open')
      assert.ok(await page.evaluate(() => window.miragioSchedule.some(({ delay }) => delay === 3250)), 'Recurring gap remains 2–4.5 seconds')
      await page.evaluate((random) => { window.miragioRandom = random }, device === 'phone' ? 0.1 : 0.5)
      await page.clock.resume()
      await page.waitForFunction(() => window.miragioClosed.length > 2)
      await page.waitForTimeout(450)
      assert.equal(await page.evaluate(() => window.miragioClosed.length), device === 'phone' ? 4 : 3, 'Recurring 20% double probability is preserved')
      const timing = await page.evaluate(() => ({
        blinkClosesMs: window.miragioClosed.map((time) => Math.round(time - window.miragioWatchStarted)),
        ownedDelaysMs: window.miragioSchedule.map(({ delay }) => delay),
      }))
      assert.ok(timing.ownedDelaysMs.includes(device === 'phone' ? 2250 : 3250))
      await page.evaluate(() => window.miragioBlinkObserver.disconnect())
      await page.evaluate(() => document.fonts.ready)
      const input = page.getByRole('textbox', { name: 'Message Miragio', exact: true })
      await input.blur()
      await page.waitForTimeout(500)
      assert.equal(await welcome.evaluate((el) => el.getBoundingClientRect().width), device === 'desktop' ? 80 : 64)
      assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 2, pointers: 1 })
      const initialHead = await welcome.locator('[data-miragio="head"]').getAttribute('style')
      await page.mouse.move(viewport.width - 20, 100)
      await page.waitForTimeout(600)
      assert.notEqual(await welcome.locator('[data-miragio="head"]').getAttribute('style'), initialHead)
      assert.notEqual(await welcome.locator('[data-miragio="gaze"]').getAttribute('style'), null)
      const beforeReading = await welcome.locator('[data-miragio="gaze"]').getAttribute('style')
      const startupTimers = await page.evaluate(() => window.miragioSchedule.filter(({ delay }) => delay === 0).length)
      await input.fill('Which agents need my attention?')
      await page.waitForTimeout(600)
      assert.equal(await page.evaluate(() => window.miragioSchedule.filter(({ delay }) => delay === 0).length), startupTimers, 'Typing never schedules another startup')
      assert.notEqual(await welcome.locator('[data-miragio="gaze"]').getAttribute('style'), beforeReading)
      await input.fill('')
      await input.blur()
      await page.screenshot({ path: `${out}/${device}-${theme}.png` })
      if (device === 'desktop' && theme === 'light') {
        const sea = await welcome.locator('[data-miragio="ribbon"]').evaluateAll((els) => els.map((el) => ({ transform: getComputedStyle(el).transform, box: el.getBoundingClientRect().toJSON() })))
        await page.waitForTimeout(400)
        assert.ok(sea.every(({ transform }) => transform === 'none'), 'Sea has no idle transform')
        assert.deepEqual(await welcome.locator('[data-miragio="ribbon"]').evaluateAll((els) => els.map((el) => ({ transform: getComputedStyle(el).transform, box: el.getBoundingClientRect().toJSON() }))), sea, 'Both sea ribbons stay still during idle')
        await page.evaluate(() => {
          Object.defineProperty(document, 'hidden', { configurable: true, value: true })
          document.dispatchEvent(new Event('visibilitychange'))
        })
        await page.waitForTimeout(100)
        assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 0, pointers: 0 })
        await assertStill(page, welcome)
        await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: false }); document.dispatchEvent(new Event('visibilitychange')) })
        await page.waitForTimeout(100)
        assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 2, pointers: 1 })
        const count = await page.evaluate(() => window.miragioClosed.length)
        await page.waitForTimeout(500)
        assert.equal(await page.evaluate(() => window.miragioClosed.length), count, 'Resume waits for recurring gap')
      }
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await page.waitForTimeout(100)
      assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 0, pointers: 0 })
      const still = await welcome.locator('[data-miragio]').evaluateAll((els) => els.map((el) => el.getAttribute('style')))
      await input.fill('A draft must not animate reduced motion')
      await page.mouse.move(20, 20)
      await page.waitForTimeout(700)
      assert.deepEqual(await welcome.locator('[data-miragio]').evaluateAll((els) => els.map((el) => el.getAttribute('style'))), still, 'Reduced motion stays static while typing and pointing')
      await input.fill('')
      await input.blur()
      await page.screenshot({ path: `${out}/${device}-${theme}-reduced.png` })
      await page.emulateMedia({ reducedMotion: 'no-preference' })
      await input.fill('harness stream')
      await input.press('Enter')
      await page.getByRole('button', { name: 'Copy response', exact: true }).waitFor()
      assert.equal(await welcome.count(), 0)
      assert.equal(await page.evaluate(() => window.miragioListeners()), 0)
      assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 0, pointers: 0 })
      await input.fill('harness stream followup')
      await input.press('Enter')
      await page.waitForFunction(() => document.querySelectorAll('.chat-copy').length === 2)
      assert.equal(await page.locator('.chat-answer-miragio').count(), 2)
      assert.equal(await page.locator('.chat-answer-miragio').first().evaluate((el) => el.getBoundingClientRect().width), device === 'desktop' ? 32 : 28)
      const ids = await page.locator('.chat-answer-miragio [id]').evaluateAll((els) => els.map((el) => el.id))
      assert.equal(ids.length, new Set(ids).size)
      assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 0, pointers: 0 })
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
      assert.deepEqual(errors, [])
      await page.screenshot({ path: `${out}/${device}-${theme}-replies.png` })
      results.push({ device, theme, passed: true, timing, checks: ['visible at rest from first frame', 'forced sequential double blink at random=.5', 'no startup head transform', 'fixed sea/chest and layout', 'recurring single/double and gaps', 'native dimensions', 'gaze/reading', 'reduced motion', 'static replies/unmount resources', 'unique ids', 'synthetic SSE followup', 'overflow/runtime errors'] })
      await context.close()
    }
  }
  for (const scenario of ['initial-reduced', 'initial-hidden', 'first-blink-reduced', 'interblink-hidden', 'second-blink-hidden', 'first-blink-unmount']) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: scenario === 'initial-reduced' ? 'reduce' : 'no-preference' })
    const page = await context.newPage()
    await page.route(/\/api\/(runs|incidents)(\?.*)?$/, (route) => route.fulfill({ json: [] }))
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.clock.install()
    await page.addInitScript(instrument, { random: 0.5, hidden: scenario === 'initial-hidden' })
    await page.goto(base)
    await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 100)))
    await page.getByRole('button', { name: 'Sign in', exact: true }).evaluate((button) => button.click())
    const welcome = page.locator('.chat-miragio')
    await welcome.waitFor()
    await welcome.evaluate(watchBlinks)
    if (scenario === 'interblink-hidden') {
      // Hide synchronously when the first blink reopens, before the awaited second blink.
      await welcome.evaluate((svg) => {
        const eyes = svg.querySelector('[data-miragio="blink"]')
        const observer = new MutationObserver(() => {
          const scale = /scaleY\(([^)]+)\)/.exec(eyes.style.transform)
          if (window.miragioClosed.length === 1 && (!scale || Number(scale[1]) >= 0.999)) {
            observer.disconnect()
            Object.defineProperty(document, 'hidden', { configurable: true, value: true })
            document.dispatchEvent(new Event('visibilitychange'))
          }
        })
        observer.observe(eyes, { attributes: true })
      })
      await page.clock.runFor(220)
      assert.equal(await page.evaluate(() => document.hidden), true)
    } else if (scenario.includes('blink')) {
      await page.clock.runFor(scenario.startsWith('second') ? 260 : 80)
      assert.equal(await page.evaluate(() => window.miragioClosed.length), scenario.startsWith('second') ? 2 : 1)
    }
    const input = page.getByRole('textbox', { name: 'Message Miragio', exact: true })
    if (scenario.endsWith('unmount')) {
      await input.fill('harness stream')
      await input.press('Enter')
    } else {
      if (scenario.endsWith('reduced')) await page.emulateMedia({ reducedMotion: 'reduce' })
      else await setHidden(page, true)
    }
    await page.clock.resume()
    if (scenario.endsWith('unmount')) {
      await page.getByRole('button', { name: 'Copy response', exact: true }).waitFor()
      await page.waitForTimeout(400)
      assert.equal(await welcome.count(), 0)
      assert.equal(await page.evaluate(() => window.miragioClosed.length), 1, 'Unmount cancels the second startup blink')
    } else {
      await assertStill(page, welcome)
      const count = await page.evaluate(() => window.miragioClosed.length)
      assert.equal(count, scenario.startsWith('second') ? 2 : scenario.startsWith('initial') ? 0 : 1, 'No late second blink after cancellation')
      await page.screenshot({ path: `${out}/${scenario}.png` })
      await page.emulateMedia({ reducedMotion: 'no-preference' })
      await setHidden(page, false)
      await page.waitForTimeout(600)
      assert.equal(await page.evaluate(() => window.miragioClosed.length), count, 'Resume waits for recurring gap, never replays startup')
      assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 2, pointers: 1 })
      await page.evaluate(() => window.miragioBlinkObserver.disconnect())
      await input.fill('harness stream')
      await input.press('Enter')
      await page.getByRole('button', { name: 'Copy response', exact: true }).waitFor()
    }
    assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 0, pointers: 0 })
    assert.equal(await page.evaluate(() => window.miragioListeners()), 0)
    assert.deepEqual(errors, [])
    results.push({ scenario, passed: true, checks: ['static cancellation/unmount', 'no late second blink/timer', 'resume without startup', 'initial preference', 'listener/timer cleanup'] })
    await context.close()
  }
} finally {
  await browser.close()
  await writeFile(`${out}/results.json`, JSON.stringify(results, null, 2) + '\n')
}
console.log(JSON.stringify(results, null, 2))

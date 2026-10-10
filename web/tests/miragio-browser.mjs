// Synthetic chat harness only; reuses the external Playwright install used by chat-browser.mjs.
import assert from 'node:assert/strict'
import { mkdir, writeFile, rename } from 'node:fs/promises'
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
  const rng = Math.random.bind(Math)
  Math.random = () => new Error().stack.includes('/src/components/miragio.tsx') ? random : rng()
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
  window.miragioEntryAtBlink = []
  window.miragioWatchStarted = performance.now()
  let closed = false
  window.miragioBlinkObserver = new MutationObserver(() => {
    const scale = /scaleY\(([^)]+)\)/.exec(svg.querySelector('[data-miragio="blink"]').style.transform)
    const next = scale && Number(scale[1]) < 0.7
    if (next && !closed) {
      window.miragioClosed.push(performance.now())
      window.miragioEntryAtBlink.push(svg.querySelector('[data-miragio="entry"]').style.transform)
    }
    closed = next
  })
  window.miragioBlinkObserver.observe(svg.querySelector('[data-miragio="blink"]'), { attributes: true })
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
  assert.equal(await welcome.locator('[data-miragio="entry"]').evaluate((el) => el.style.transform), 'none')
  assert.equal(await welcome.locator('[data-miragio="blink"]').evaluate((el) => el.style.transform), 'none')
  const still = await welcome.screenshot()
  await page.waitForTimeout(400)
  assert.ok(still.equals(await welcome.screenshot()), 'Interrupted portrait stays visibly static')
}
const results = []
try {
  for (const [device, viewport] of [['desktop', { width: 1440, height: 1000 }], ['phone', { width: 390, height: 844 }]]) {
    for (const theme of ['light', 'dark']) {
      const context = await browser.newContext({ viewport, colorScheme: theme,
        ...(theme === 'light' ? { recordVideo: { dir: out, size: viewport } } : {}) })
      const page = await context.newPage()
      // Keep unrelated engine-status reflow out of the synthetic mascot lifecycle checks.
      await page.route(/\/api\/(runs|incidents)(\?.*)?$/, (route) => route.fulfill({ json: [] }))
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.clock.install()
      await page.addInitScript(instrument, { random: device === 'phone' ? 0.1 : 0.5 })
      await page.goto(base)
      await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 100)))
      await page.getByRole('button', { name: 'Sign in', exact: true }).evaluate((button) => button.click())
      const welcome = page.locator('.chat-miragio')
      await welcome.waitFor()
      const entry = welcome.locator('[data-miragio="entry"]')
      assert.equal(await entry.evaluate((el) => getComputedStyle(el).transform), 'none', 'First frame is already at rest')
      const initialTile = await welcome.evaluate((svg) => {
        const group = svg.querySelector('[data-miragio="entry"]')
        const paper = group.parentElement.firstElementChild
        const box = group.getBBox()
        return {
          children: [...group.children].map((el) => el.dataset.miragio),
          fixed: [...group.parentElement.children].filter((el) => el !== group).map((el) => el.dataset.miragio || (el.tagName === 'rect' ? 'paper' : 'chest')),
          paperFixed: paper.tagName === 'rect' && paper.parentElement === group.parentElement && group.parentElement.hasAttribute('clip-path'),
          visible: box.x >= 0 && box.y >= 0 && box.x + box.width <= 1000 && box.y + box.height <= 1000,
          opacity: getComputedStyle(group).opacity,
          origin: group.style.transformOrigin,
          transformBox: getComputedStyle(group).transformBox,
          rect: { x: svg.getBoundingClientRect().x, y: svg.getBoundingClientRect().y, width: svg.getBoundingClientRect().width, height: svg.getBoundingClientRect().height },
        }
      })
      assert.deepEqual(initialTile.children, ['head'], 'Only head, gaze and blink share the greeting transform')
      assert.deepEqual(initialTile.fixed, ['paper', 'chest', 'ribbon', 'ribbon'], 'Paper, chest and sea stay outside the greeting group')
      assert.ok(initialTile.paperFixed && initialTile.visible, 'Entire head is inside the fixed tile on the first frame')
      assert.equal(initialTile.opacity, '1', 'No appearance fade')
      assert.equal(initialTile.transformBox, 'fill-box')
      assert.match(initialTile.origin, /^50% 75%( 0px)?$/, 'Greeting pivots near the lower head')
      await entry.evaluate((group) => {
        window.miragioEntrySamples = []
        const sample = () => {
          const matrix = new DOMMatrix(getComputedStyle(group).transform)
          const fixed = [...group.parentElement.children].filter((el) => el !== group).map((el) => getComputedStyle(el).transform)
          window.miragioEntrySamples.push({ at: performance.now(), a: matrix.a, b: matrix.b, c: matrix.c, d: matrix.d, x: matrix.e, y: matrix.f, fixed })
        }
        sample()
        window.miragioEntryObserver = new MutationObserver(sample)
        window.miragioEntryObserver.observe(group, { attributes: true, attributeFilter: ['style'] })
      })
      await welcome.evaluate(watchBlinks)
      const initialPose = await welcome.locator('[data-miragio="head"], [data-miragio="gaze"]').evaluateAll((els) => els.map((el) => el.style.transform))
      await page.screenshot({ clip: initialTile.rect, path: `${out}/${device}-${theme}-first.png` })
      await page.clock.resume()
      await page.waitForFunction(() => new DOMMatrix(getComputedStyle(document.querySelector('.chat-miragio [data-miragio="entry"]')).transform).f < -9.8, null, { polling: 'raf' })
      await page.screenshot({ clip: initialTile.rect, path: `${out}/${device}-${theme}-peak.png` })
      await page.waitForFunction(() => window.miragioClosed.length >= 1)
      await page.waitForTimeout(450)
      assert.equal(await page.evaluate(() => window.miragioClosed.length), device === 'phone' ? 2 : 1, 'Deterministic single/double blink after greeting')
      assert.equal(await entry.evaluate((el) => el.style.transform), 'none', 'Greeting settles at rest')
      await page.evaluate(() => window.miragioEntryObserver.disconnect())
      const entrySamples = await page.evaluate(() => window.miragioEntrySamples)
      const moving = entrySamples.filter(({ y }) => y < -0.01)
      assert.ok(moving.length > 2 && moving.some(({ y }) => y < -9.8), 'Observed tiny greeting peak')
      assert.ok(entrySamples.every(({ a, b, c, d, x, y }) => Math.abs(x) < 0.001 && y >= -10.001 && y <= 0 && Math.abs(a * d - b * c - 1) < 0.00001 && Math.atan2(b, a) * 180 / Math.PI >= -1.501 && b <= 0), 'Greeting only lifts and tilts, with no x, scale or overshoot')
      const motionMs = Math.round(moving.at(-1).at - moving[0].at)
      assert.ok(motionMs >= 1650 && motionMs <= 1900, 'Greeting lasts a slow 1.8 seconds')
      assert.ok(entrySamples.every(({ fixed }) => fixed.length === 4 && fixed.every((transform) => transform === 'none')), 'Paper, chest and both ribbons stay fixed throughout greeting')
      assert.deepEqual(await welcome.evaluate((svg) => {
        const { x, y, width, height } = svg.getBoundingClientRect()
        return { x, y, width, height }
      }), initialTile.rect, 'Paper tile and layout stay fixed throughout greeting')
      // Compare the same gaze/position, without screenshot actionability skipping animated frames.
      await page.clock.pauseAt(new Date(await page.evaluate(() => Date.now() + 100)))
      const rest = await welcome.evaluate((svg, pose) => {
        const parts = [...svg.querySelectorAll('[data-miragio="head"], [data-miragio="gaze"]')]
        const saved = parts.map((el) => el.style.transform)
        parts.forEach((el, index) => { el.style.transform = pose[index] })
        return saved
      }, initialPose)
      await page.screenshot({ clip: initialTile.rect, path: `${out}/${device}-${theme}-rest.png` })
      await welcome.evaluate((svg, pose) => [...svg.querySelectorAll('[data-miragio="head"], [data-miragio="gaze"]')].forEach((el, index) => { el.style.transform = pose[index] }), rest)
      await page.clock.resume()
      assert.ok(await page.evaluate(() => window.miragioSchedule.some(({ delay }) => delay === 3250 || delay === 2250)), 'Recurring gap is 2–4.5 seconds')
      await page.waitForFunction((count) => window.miragioClosed.length > count, device === 'phone' ? 2 : 1)
      await page.waitForTimeout(450)
      assert.equal(await page.evaluate(() => window.miragioClosed.length), device === 'phone' ? 4 : 2)
      const timing = { greetingMotionMs: motionMs, ...await page.evaluate(() => ({
        blinkClosesMs: window.miragioClosed.map((time) => Math.round(time - window.miragioWatchStarted)),
        entryAtBlink: window.miragioEntryAtBlink,
        ownedDelaysMs: window.miragioSchedule.map(({ delay }) => delay),
      })) }
      assert.ok(timing.entryAtBlink.every((transform) => transform === 'none'), 'Blink starts only after greeting completes')
      if (device === 'phone') {
        const doubleGap = timing.blinkClosesMs[1] - timing.blinkClosesMs[0]
        assert.ok(doubleGap >= 140 && doubleGap <= 260, 'Double blink follows sequential 180ms close/open')
      }
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
      await input.fill('Which agents need my attention?')
      await page.waitForTimeout(600)
      assert.equal(await entry.evaluate((el) => el.style.transform), 'none', 'Typing does not replay greeting')
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
        const hidden = await welcome.screenshot()
        await page.waitForTimeout(400)
        assert.ok(hidden.equals(await welcome.screenshot()), 'Hidden portrait must stop even in the middle of an animation')
        await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: false }); document.dispatchEvent(new Event('visibilitychange')) })
        await page.waitForTimeout(100)
        assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 2, pointers: 1 })
        assert.equal(await entry.evaluate((el) => el.style.transform), 'none', 'Visibility resume does not replay greeting')
      }
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await page.waitForTimeout(100)
      assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 0, pointers: 0 })
      // Pin the portrait for pixel comparison: textarea resizing can shift the centred mobile column by half a pixel.
      await welcome.evaluate((el) => { el.style.position = 'fixed'; el.style.left = '0'; el.style.top = '0' })
      const still = await welcome.screenshot()
      await input.fill('A draft must not animate reduced motion')
      await page.mouse.move(20, 20)
      await page.waitForTimeout(700)
      const afterTyping = await welcome.screenshot()
      if (!still.equals(afterTyping)) {
        await writeFile(`${out}/${device}-${theme}-still-before.png`, still)
        await writeFile(`${out}/${device}-${theme}-still-after.png`, afterTyping)
        console.log(await welcome.locator('[data-miragio]').evaluateAll((els) => els.map((el) => ({ name: el.dataset.miragio, style: el.getAttribute('style') }))))
      }
      assert.ok(still.equals(afterTyping), `${device}/${theme}: Reduced-motion portrait must stay pixel-identical during typing/pointer movement`)
      await welcome.evaluate((el) => { el.style.removeProperty('position'); el.style.removeProperty('left'); el.style.removeProperty('top') })
      await input.fill('')
      await input.blur()
      await page.screenshot({ path: `${out}/${device}-${theme}-reduced.png` })
      if (device === 'desktop' && theme === 'light') {
        await welcome.evaluate((el) => { el.style.width = '320px'; el.style.height = '320px' })
        await welcome.screenshot({ path: `${out}/portrait.png` })
        await welcome.evaluate((el) => {
          const comparison = document.createElement('div')
          comparison.id = 'miragio-comparison'
          comparison.style.cssText = 'position:fixed;inset:0;background:#fafafa;z-index:99999;padding:32px;display:flex;gap:32px;align-items:flex-start;font:14px sans-serif'
          const source = document.createElement('div')
          source.innerHTML = '<p style="margin-bottom:16px">Approved portrait — tile crop</p><div style="width:320px;height:320px;overflow:hidden;position:relative"><img src="/brand/miragio-approved-master.png" style="position:absolute;width:414.72px;max-width:none;height:388.16px;left:-47.36px;top:-30.08px"></div>'
          const traced = document.createElement('div')
          traced.innerHTML = '<p style="margin-bottom:16px">Miragio SVG — reduced motion</p>'
          traced.append(el.cloneNode(true))
          comparison.append(source, traced)
          document.body.append(comparison)
        })
        await page.locator('#miragio-comparison img').evaluate((img) => img.decode())
        await page.screenshot({ path: `${out}/source-comparison.png` })
        await page.locator('#miragio-comparison').evaluate((el) => el.remove())
        await welcome.evaluate((el) => { el.style.removeProperty('width'); el.style.removeProperty('height') })
      }
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
      results.push({ device, theme, passed: true, timing, checks: ['visible first frame matches rest', 'head-only greeting', 'tiny no-x 1.8s greeting', 'fixed sea/chest throughout greeting and idle', 'fixed tile/layout', 'one-time greeting', 'single/double blink', '2–4.5s gap', 'dimensions', 'gaze', 'reading', 'reduced pixel equality', 'static/unmount resources', 'unique ids', 'read-only synthetic SSE followup', 'overflow', 'runtime errors'] })
      const video = page.video()
      await context.close()
      if (video) await rename(await video.path(), `${out}/${device}-animation.webm`)
    }
  }
  for (const scenario of ['initial-reduced', 'initial-hidden', 'greeting-reduced', 'greeting-hidden', 'first-blink-reduced', 'second-blink-hidden']) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: scenario === 'initial-reduced' ? 'reduce' : 'no-preference' })
    const page = await context.newPage()
    await page.route(/\/api\/(runs|incidents)(\?.*)?$/, (route) => route.fulfill({ json: [] }))
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.addInitScript(instrument, { random: 0.1, hidden: scenario === 'initial-hidden' })
    await page.goto(base)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    const welcome = page.locator('.chat-miragio')
    await welcome.waitFor()
    await welcome.evaluate(watchBlinks)
    if (scenario.startsWith('greeting-')) {
      await page.waitForTimeout(350)
      assert.notEqual(await welcome.locator('[data-miragio="entry"]').evaluate((el) => el.style.transform), 'none')
    } else if (scenario.includes('blink')) {
      await page.waitForFunction((count) => window.miragioClosed.length === count, scenario.startsWith('first') ? 1 : 2, { polling: 'raf' })
    }
    if (scenario.endsWith('reduced')) await page.emulateMedia({ reducedMotion: 'reduce' })
    else await setHidden(page, true)
    await assertStill(page, welcome)
    const count = await page.evaluate(() => window.miragioClosed.length)
    assert.equal(count, scenario.startsWith('first') ? 1 : scenario.startsWith('second') ? 2 : 0, 'No late blink after cancellation')
    await page.screenshot({ path: `${out}/${scenario}.png` })
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await setHidden(page, false)
    await page.waitForTimeout(600)
    assert.equal(await welcome.locator('[data-miragio="entry"]').evaluate((el) => el.style.transform), 'none', 'Resume never repeats the greeting')
    assert.equal(await page.evaluate(() => window.miragioClosed.length), count, 'Resume waits for the recurring gap')
    assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 2, pointers: 1 })
    await page.evaluate(() => window.miragioBlinkObserver.disconnect())
    const input = page.getByRole('textbox', { name: 'Message Miragio', exact: true })
    await input.fill('harness stream')
    await input.press('Enter')
    await page.getByRole('button', { name: 'Copy response', exact: true }).waitFor()
    assert.deepEqual(await page.evaluate(() => window.miragioResources()), { timers: 0, pointers: 0 })
    assert.equal(await page.evaluate(() => window.miragioListeners()), 0)
    assert.deepEqual(errors, [])
    results.push({ scenario, passed: true, checks: ['immediate static resolution', 'no late second blink/timer', 'resume without greeting', 'initial preference', 'listener/timer cleanup'] })
    await context.close()
  }
} finally {
  await browser.close()
  await writeFile(`${out}/results.json`, JSON.stringify(results, null, 2) + '\n')
}
console.log(JSON.stringify(results, null, 2))

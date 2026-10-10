// Synthetic chat harness only; reuses the external Playwright install used by chat-browser.mjs.
import assert from 'node:assert/strict'
import { mkdir, writeFile, rename } from 'node:fs/promises'
const { chromium } = await import(process.env.MIRAGE_PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.MIRAGE_UI_URL || 'http://127.0.0.1:5186'
const out = process.env.MIRAGE_QA_DIR || '../docs/miragio-qa'
await mkdir(out, { recursive: true })
const browser = await chromium.launch({ headless: true, executablePath: process.env.MIRAGE_CHROMIUM_EXECUTABLE })
const results = []
try {
  for (const [device, viewport] of [['desktop', { width: 1440, height: 1000 }], ['phone', { width: 390, height: 844 }]]) {
    for (const theme of ['light', 'dark']) {
      const context = await browser.newContext({ viewport, colorScheme: theme,
        ...(device === 'desktop' && theme === 'light' ? { recordVideo: { dir: out, size: { width: 720, height: 500 } } } : {}) })
      const page = await context.newPage()
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.addInitScript(() => {
        const timers = new Set()
        const pointers = new Set()
        const set = window.setTimeout.bind(window)
        const clear = window.clearTimeout.bind(window)
        const add = window.addEventListener.bind(window)
        const remove = window.removeEventListener.bind(window)
        window.setTimeout = (callback, delay, ...args) => {
          const owned = new Error().stack.includes('/src/components/miragio.tsx')
          const timer = set(() => { timers.delete(timer); callback(...args) }, delay)
          if (owned) timers.add(timer)
          return timer
        }
        window.clearTimeout = (timer) => { timers.delete(timer); clear(timer) }
        window.addEventListener = (name, handler, options) => { if (name === 'pointermove' && new Error().stack.includes('/src/components/miragio.tsx')) pointers.add(handler); add(name, handler, options) }
        window.removeEventListener = (name, handler, options) => { if (name === 'pointermove') pointers.delete(handler); remove(name, handler, options) }
        window.miragioResources = () => ({ timers: timers.size, pointers: pointers.size })
      })
      await page.goto(base)
      await page.getByRole('button', { name: 'Sign in', exact: true }).click()
      const welcome = page.locator('.chat-miragio')
      await welcome.waitFor()
      await page.evaluate(() => document.fonts.ready)
      const input = page.getByRole('textbox', { name: 'Message Mirage' })
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
      assert.notEqual(await welcome.locator('[data-miragio="gaze"]').getAttribute('style'), beforeReading)
      await input.fill('')
      await input.blur()
      await page.screenshot({ path: `${out}/${device}-${theme}.png` })
      if (device === 'desktop' && theme === 'light') {
        await welcome.evaluate((svg) => {
          window.miragioBlinks = 0
          window.miragioBlinkObserver = new MutationObserver(() => {
            const scale = /scaleY\(([^)]+)\)/.exec(svg.querySelector('[data-miragio="blink"]').style.transform)
            if (scale && Number(scale[1]) < 0.7) window.miragioBlinks++
          })
          window.miragioBlinkObserver.observe(svg.querySelector('[data-miragio="blink"]'), { attributes: true })
        })
        await page.waitForFunction(() => window.miragioBlinks > 0, { timeout: 7500 })
        await page.evaluate(() => window.miragioBlinkObserver.disconnect())
        const ripple = await welcome.locator('[data-miragio="ribbon"]').first().getAttribute('style')
        await page.waitForTimeout(400)
        assert.notEqual(await welcome.locator('[data-miragio="ribbon"]').first().getAttribute('style'), ripple)
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
      results.push({ device, theme, passed: true, checks: ['dimensions', 'gaze', 'reading', 'reduced pixel equality', 'static/unmount resources', 'unique ids', 'read-only synthetic SSE followup', 'overflow', 'runtime errors'] })
      const video = page.video()
      await context.close()
      if (video) await rename(await video.path(), `${out}/animation.webm`)
    }
  }
} finally {
  await browser.close()
  await writeFile(`${out}/results.json`, JSON.stringify(results, null, 2) + '\n')
}
console.log(JSON.stringify(results, null, 2))

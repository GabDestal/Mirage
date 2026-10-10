import { spawn } from 'node:child_process'
import { access, mkdtemp, rm } from 'node:fs/promises'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const loopback = (port) => `http://127.0.0.1:${port}`

function number(value, name, max) {
  const n = Number(value)
  if (!Number.isInteger(n) || n < 1 || n > max) throw new Error(`Invalid ${name}`)
  return n
}

export function resolveLaunch(argv, env = process.env, root = ROOT) {
  const args = [...argv]
  let mode
  for (let i = 0; i < args.length; i++) {
    if (args[i] !== '--mode' && !args[i].startsWith('--mode=')) continue
    if (mode !== undefined) throw new Error('Specify --mode only once')
    const inline = args[i].startsWith('--mode=')
    mode = inline ? args[i].slice(7) : args[i + 1]
    if (!mode || mode.startsWith('-')) throw new Error('--mode requires live or demo')
    args.splice(i, inline ? 1 : 2)
    i--
  }
  mode ??= env.MIRAGE_UI_MODE ?? 'live'
  if (!['live', 'demo'].includes(mode)) throw new Error('UI mode must be live (attach) or demo')
  if (mode === 'live') return { mode, root, args, env: { ...env, MIRAGE_UI_MODE: 'live' } }

  const ports = { web: env.MIRAGE_DEMO_WEB_PORT ?? '5174', engine: env.MIRAGE_DEMO_ENGINE_PORT ?? '8010', chat: env.MIRAGE_DEMO_CHAT_PORT ?? '8011' }
  const names = { '--port': 'web', '--engine-port': 'engine', '--chat-port': 'chat' }
  const viteArgs = []
  const seen = new Set()
  for (let i = 0; i < args.length; i++) {
    const [flag, ...values] = args[i].split('=')
    const inline = values.length ? values.join('=') : undefined
    if (flag === '--open' && inline === undefined) { viteArgs.push(flag); continue }
    const name = names[flag]
    if (!name || seen.has(name)) throw new Error(`Unsupported or repeated demo option: ${flag}`)
    seen.add(name)
    ports[name] = inline ?? args[++i]
  }
  for (const name of Object.keys(ports)) ports[name] = number(ports[name], `${name} port`, 65535)
  if (new Set(Object.values(ports)).size !== 3 || Object.values(ports).some((p) => [5173, 8000, 8001].includes(p)))
    throw new Error('Demo ports must be distinct and must not use attach ports 5173/8000/8001')
  const fixture = join(root, 'contracts/fixtures/fleet_demo_4agents.jsonl')
  const origins = ['127.0.0.1', 'localhost'].flatMap((host) => [ports.web, ports.chat].map((port) => `http://${host}:${port}`)).join(',')
  const fixed = { MIRAGE_MODE: 'replay', MIRAGE_REPLAY_MANAGED: '1', MIRAGE_API: loopback(ports.engine), MIRAGE_CHAT_API: loopback(ports.chat),
    MIRAGE_CHAT_PORT: String(ports.chat), MIRAGE_CHAT_ORIGINS: origins, MIRAGE_FIXTURE: fixture, VITE_MIRAGE_UI_MODE: 'demo' }
  for (const [key, value] of Object.entries(fixed)) {
    if (env[key] !== undefined && env[key] !== value) throw new Error(`Demo configuration conflicts with ${key}; unset it or use the matching demo value`)
  }
  for (const key of ['MIRAGE_DB', 'MIRAGE_SNAPSHOTS', 'MIRAGE_TOKENS', 'MIRAGE_PUBLIC', 'MIRAGE_DEMO_CONTROLS']) {
    if (env[key] !== undefined) throw new Error(`Unset ${key}; demo owns disposable state and recorded controls`)
  }
  const speed = Number(env.MIRAGE_REPLAY_SPEED ?? '2')
  if (!Number.isFinite(speed) || speed <= 0 || speed > 10) throw new Error('MIRAGE_REPLAY_SPEED must be finite, greater than 0 and at most 10')
  const envFile = env.MIRAGE_CHAT_ENV_FILE ?? join(root, '.env')
  if (!isAbsolute(envFile)) throw new Error('MIRAGE_CHAT_ENV_FILE must be an absolute path')
  const timeout = number(env.MIRAGE_DEMO_READY_TIMEOUT_MS ?? '30000', 'readiness timeout', 120000)
  return { mode, root, env, ports, fixed, fixture, envFile, speed, timeout, args: viteArgs }
}

export function demoPlan(config, stateDir) {
  if (!isAbsolute(stateDir)) throw new Error('Demo state directory must be absolute')
  // Only chat inherits provider credentials. UV must not load an environment file for Replay.
  const base = Object.fromEntries(['PATH', 'HOME', 'TMPDIR', 'TMP', 'TEMP', 'LANG', 'LC_ALL', 'SYSTEMROOT'].filter((key) => config.env[key] !== undefined).map((key) => [key, config.env[key]]))
  const isolated = { MIRAGE_DB: join(stateDir, 'events.db'), MIRAGE_SNAPSHOTS: join(stateDir, 'snapshots'), MIRAGE_TOKENS: join(stateDir, 'handoff_tokens.json') }
  const common = { ...config.fixed, ...isolated, MIRAGE_UI_MODE: 'demo', MIRAGE_REPLAY_SPEED: String(config.speed) }
  return [
    { name: 'engine', command: 'uv', args: ['run', '--no-env-file', '--no-sync', 'uvicorn', 'engine.api.server:app', '--host', '127.0.0.1', '--port', String(config.ports.engine)], cwd: config.root,
      env: { ...base, ...common }, url: `${config.fixed.MIRAGE_API}/runs`, status: 200 },
    { name: 'chat', command: process.execPath, args: [join(config.root, 'mcp/dist/chat-main.js')], cwd: join(config.root, 'mcp'),
      env: { ...config.env, ...common, MIRAGE_CHAT_ENV_FILE: config.envFile }, url: `${config.fixed.MIRAGE_CHAT_API}/chat/turn`, status: 404 },
    { name: 'web', command: process.execPath, args: [join(config.root, 'web/node_modules/vite/bin/vite.js'), '--mode', 'demo', '--host', '127.0.0.1', '--port', String(config.ports.web), '--strictPort', ...config.args], cwd: join(config.root, 'web'),
      env: { ...base, ...common }, url: loopback(config.ports.web), status: 200 },
  ]
}

export function assertPortFree(port) {
  return new Promise((ok, fail) => {
    const server = createServer()
    server.once('error', () => fail(new Error(`Demo port ${port} is unavailable; no existing service was attached or stopped`)))
    server.listen(port, '127.0.0.1', () => server.close(ok))
  })
}

async function prerequisites(config) {
  for (const [path, message] of [
    [config.fixture, 'Missing recorded fleet fixture'],
    [config.envFile, 'Missing chat env file; configure root .env or an absolute MIRAGE_CHAT_ENV_FILE'],
    [join(config.root, 'mcp/dist/chat-main.js'), 'Build real chat first: cd mcp && npm ci && npm run build'],
    [join(config.root, 'web/node_modules/vite/bin/vite.js'), 'Install web dependencies first: cd web && npm ci'],
  ]) {
    try { await access(path) } catch { throw new Error(message) }
  }
}

async function stopChildren(children) {
  const signal = (child, sig) => {
    if (!child.pid) return
    try { process.kill(-child.pid, sig) } catch (error) { if (error.code !== 'ESRCH') throw error }
  }
  for (const child of children) signal(child, 'SIGTERM')
  const settled = Promise.all(children.map((child) => !child.pid || child.exitCode !== null || child.signalCode !== null ? undefined : new Promise((ok) => child.once('exit', ok))))
  await Promise.race([settled, delay(2000)])
  for (const child of children) signal(child, 'SIGKILL')
  await settled
}

export async function runDemo(config, { signal, spawnChild = spawn, checkPrerequisites = prerequisites, log = console.log } = {}) {
  await checkPrerequisites(config)
  for (const port of Object.values(config.ports)) await assertPortFree(port)
  const stateDir = await mkdtemp(join(tmpdir(), 'mirage-demo-'))
  const children = []
  let failure
  const aborted = () => signal?.aborted
  let wake
  const stopped = new Promise((ok) => { wake = ok })
  const onAbort = () => wake()
  signal?.addEventListener('abort', onAbort, { once: true })
  try {
    for (const spec of demoPlan(config, stateDir)) {
      if (aborted()) break
      const child = spawnChild(spec.command, spec.args, { cwd: spec.cwd, env: spec.env, stdio: 'inherit', detached: true })
      children.push(child)
      child.once('error', () => { failure ??= new Error(`${spec.name} could not start; check its prerequisites`); wake() })
      child.once('exit', (code, sig) => { failure ??= new Error(`${spec.name} exited (${code ?? sig})`); wake() })
      const deadline = Date.now() + config.timeout
      let ready = false
      while (!ready && !failure && !aborted() && Date.now() < deadline) {
        try {
          const response = await fetch(spec.url, { signal: AbortSignal.timeout(Math.min(1000, config.timeout)), redirect: 'error' })
          if (response.status === spec.status) {
            if (spec.name === 'engine') ready = Array.isArray(await response.json())
            else if (spec.name === 'chat') ready = (await response.json()).code === 'NOT_FOUND'
            else ready = (response.headers.get('content-type') ?? '').includes('text/html')
          }
          await response.body?.cancel().catch(() => {})
        } catch { /* Child exit and deadline below distinguish failure from startup. */ }
        if (!ready) await Promise.race([delay(100), stopped])
      }
      if (failure) throw failure
      if (aborted()) break
      if (!ready) throw new Error(`${spec.name} readiness timed out; no demo control writes were sent`)
      // Let a strict-bind failure settle before considering the child ready.
      await Promise.race([delay(100), stopped])
      if (failure) throw failure
    }
    if (!aborted()) {
      log(`Recorded engine demo · real Miragio: ${loopback(config.ports.web)} (Ctrl+C stops this launch)`)
      await stopped
      if (!aborted() && failure) throw failure
    }
  } finally {
    signal?.removeEventListener('abort', onAbort)
    await stopChildren(children)
    await rm(stateDir, { recursive: true, force: true })
  }
}

async function main() {
  const config = resolveLaunch(process.argv.slice(2))
  const controller = new AbortController()
  for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => controller.abort())
  if (config.mode === 'demo') return runDemo(config, { signal: controller.signal })
  // Attach is still just Vite with the same flags, proxy defaults and caller environment.
  const child = spawn(process.execPath, [join(config.root, 'web/node_modules/vite/bin/vite.js'), ...config.args], { cwd: join(config.root, 'web'), env: config.env, stdio: 'inherit' })
  controller.signal.addEventListener('abort', () => child.kill('SIGTERM'), { once: true })
  await new Promise((ok, fail) => { child.once('error', fail); child.once('exit', (code) => { process.exitCode = controller.signal.aborted ? 0 : code ?? 1; ok() }) })
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(`Mirage startup: ${error.message}`); process.exitCode = 1 })
}

import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { isAbsolute, join } from 'node:path'
import { assertPortFree, demoPlan, resolveLaunch, runDemo } from './dev.mjs'

const root = await mkdtemp(join(tmpdir(), 'mirage-launcher-test-'))
const env = { PATH: process.env.PATH, HOME: process.env.HOME }
const occupied = createServer()
const port = async () => {
  const server = createServer()
  await new Promise((ok) => server.listen(0, '127.0.0.1', ok))
  const value = server.address().port
  await new Promise((ok) => server.close(ok))
  return value
}

try {
  await mkdir(join(root, 'mcp'))
  await mkdir(join(root, 'web'))
  const attach = resolveLaunch(['--port', '5199', '--strictPort', '--host'], { ...env, MIRAGE_API: 'http://localhost:8000' }, root)
  assert.equal(attach.mode, 'live')
  assert.deepEqual(attach.args, ['--port', '5199', '--strictPort', '--host'])
  assert.equal(attach.env.MIRAGE_API, 'http://localhost:8000')
  assert.equal(attach.env.MIRAGE_CHAT_API, undefined)
  assert.equal(resolveLaunch(['--mode=live'], { ...env, MIRAGE_UI_MODE: 'demo' }, root).mode, 'live')
  assert.equal(resolveLaunch([], { ...env, MIRAGE_UI_MODE: 'demo' }, root).mode, 'demo')
  assert.equal(resolveLaunch(['--mode', 'demo'], { ...env, MIRAGE_UI_MODE: 'invalid' }, root).mode, 'demo')
  for (const args of [['--mode'], ['--mode', 'offline'], ['--mode=demo', '--mode=live'], ['--mode=demo', '--host', '0.0.0.0'], ['--mode=demo', '--config', 'other.ts'], ['--mode=demo', '--port', '5173'], ['--mode=demo', '--port', '8010'], ['--mode=demo', '--chat-port', 'NaN'], ['--mode=demo', '--chat-port=8011=unexpected']])
    assert.throws(() => resolveLaunch(args, env, root))
  for (const override of [{ MIRAGE_MODE: 'live' }, { MIRAGE_DB: '/existing.db' }, { MIRAGE_SNAPSHOTS: '/existing' }, { MIRAGE_TOKENS: '/existing.json' }, { MIRAGE_API: 'http://127.0.0.1:8000' }, { MIRAGE_CHAT_API: 'http://127.0.0.1:8001' }, { MIRAGE_CHAT_PORT: '8001' }, { MIRAGE_FIXTURE: 'other.jsonl' }, { MIRAGE_REPLAY_MANAGED: '0' }, { MIRAGE_PUBLIC: '1' }, { MIRAGE_CHAT_ENV_FILE: './.env' }, { MIRAGE_REPLAY_SPEED: 'inf' }, { MIRAGE_REPLAY_SPEED: '0' }, { MIRAGE_REPLAY_SPEED: '11' }, { VITE_MIRAGE_UI_MODE: 'live' }, { MIRAGE_CHAT_ORIGINS: 'http://localhost:5173' }])
    assert.throws(() => resolveLaunch(['--mode=demo'], { ...env, ...override }, root))
  const config = resolveLaunch(['--mode=demo', '--port', '55174', '--engine-port=58010', '--chat-port', '58011', '--open'], { ...env, MIRAGE_DEMO_WEB_PORT: '55175', AWS_BEARER_TOKEN_BEDROCK: 'synthetic-test-token', MIRAGE_CHAT_ENV_FILE: join(root, '.env') }, root)
  const specs = demoPlan(config, join(root, 'state'))
  assert.equal(config.ports.web, 55174)
  assert.equal(config.speed, 2)
  assert.equal(specs[0].env.MIRAGE_MODE, 'replay')
  assert.equal(specs[0].env.MIRAGE_REPLAY_MANAGED, '1')
  assert.equal(specs[0].env.AWS_BEARER_TOKEN_BEDROCK, undefined)
  assert.equal(specs[2].env.AWS_BEARER_TOKEN_BEDROCK, undefined)
  assert.equal(specs[1].env.AWS_BEARER_TOKEN_BEDROCK, 'synthetic-test-token')
  assert.equal(specs[1].env.MIRAGE_CHAT_ENV_FILE, join(root, '.env'))
  assert(specs[0].args.includes('--no-env-file'))
  assert(specs[2].args.includes('--strictPort'))
  for (const spec of specs) {
    assert.equal(spec.env.MIRAGE_API, 'http://127.0.0.1:58010')
    assert.equal(spec.env.MIRAGE_CHAT_API, 'http://127.0.0.1:58011')
    assert.equal(spec.env.MIRAGE_UI_MODE, 'demo')
    for (const key of ['MIRAGE_DB', 'MIRAGE_SNAPSHOTS', 'MIRAGE_TOKENS', 'MIRAGE_FIXTURE']) assert(isAbsolute(spec.env[key]))
    for (const key of ['MIRAGE_DB', 'MIRAGE_SNAPSHOTS', 'MIRAGE_TOKENS']) assert(spec.env[key].startsWith(join(root, 'state/')))
    assert(spec.env.MIRAGE_CHAT_ORIGINS.includes('http://127.0.0.1:55174'))
    assert(spec.env.MIRAGE_CHAT_ORIGINS.includes('http://localhost:55174'))
  }
  assert.equal(specs[0].env.MIRAGE_FIXTURE, join(root, 'contracts/fixtures/fleet_demo_4agents.jsonl'))

  await new Promise((ok) => occupied.listen(0, '127.0.0.1', ok))
  await assert.rejects(assertPortFree(occupied.address().port), /unavailable/)
  const conflict = { ...config, ports: { web: await port(), engine: occupied.address().port, chat: await port() } }
  let spawns = 0
  await assert.rejects(runDemo(conflict, { checkPrerequisites: async () => {}, spawnChild: () => { spawns++; throw new Error('should not spawn') } }), /unavailable/)
  assert.equal(spawns, 0)
  assert(occupied.listening)
  await assert.rejects(runDemo(config), /Missing recorded fleet fixture/)

  const script = join(root, 'stub.mjs')
  await writeFile(script, `
    import { createServer } from 'node:http';
    import { appendFileSync } from 'node:fs';
    import { spawn } from 'node:child_process';
    const [name, port, requests, behavior] = process.argv.slice(2);
    if (name === 'engine') {
      const descendant = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], {stdio:'ignore'});
      appendFileSync(requests + '.descendant', String(descendant.pid));
    }
    if (behavior === 'exit') process.exit(7);
    if (behavior === 'hang') setInterval(() => {}, 1000);
    else createServer((req, res) => {
      appendFileSync(requests, JSON.stringify({name, method:req.method, path:req.url}) + '\\n');
      if (name === 'engine') { res.setHeader('content-type','application/json'); res.end('[]'); }
      else if (name === 'chat') { res.writeHead(404, {'content-type':'application/json'}); res.end(JSON.stringify({code:'NOT_FOUND'})); }
      else { res.setHeader('content-type','text/html'); res.end('<html>stub</html>'); }
    }).listen(Number(port), '127.0.0.1');
  `)
  for (const behavior of ['ready', 'sigint', 'exit', 'hang', 'spawn-error']) {
    const ports = { web: await port(), engine: await port(), chat: await port() }
    const c = resolveLaunch(['--mode=demo', '--port', String(ports.web), '--engine-port', String(ports.engine), '--chat-port', String(ports.chat)], { ...env, MIRAGE_DEMO_READY_TIMEOUT_MS: behavior === 'hang' ? '350' : '3000' }, root)
    const requests = join(root, `${behavior}.jsonl`)
    await writeFile(requests, '')
    const controller = new AbortController()
    const onInterrupt = () => controller.abort()
    if (behavior === 'sigint') process.once('SIGINT', onInterrupt)
    const children = []
    let stateDir
    const spawnChild = (command, args, options) => {
      const name = options.env.MIRAGE_CHAT_ENV_FILE ? 'chat' : command === 'uv' ? 'engine' : 'web'
      stateDir = options.env.MIRAGE_DB.slice(0, -'/events.db'.length)
      const child = spawn(behavior === 'spawn-error' && name === 'chat' ? '/nonexistent-mirage-test-executable' : process.execPath,
        [script, name, String(ports[name]), requests, name === 'chat' ? behavior : 'ready'], { ...options, stdio: 'ignore' })
      children.push(child)
      return child
    }
    const run = runDemo(c, { signal: controller.signal, spawnChild, checkPrerequisites: async () => {}, log: () => behavior === 'sigint' ? process.kill(process.pid, 'SIGINT') : controller.abort() })
    if (['ready', 'sigint'].includes(behavior)) await run
    else await assert.rejects(run, behavior === 'exit' ? /chat exited/ : behavior === 'hang' ? /readiness timed out/ : /chat could not start/)
    await assert.rejects(access(stateDir))
    for (const child of children) if (child.pid) assert.throws(() => process.kill(child.pid, 0), { code: 'ESRCH' })
    const descendant = Number(await readFile(requests + '.descendant', 'utf8'))
    assert.throws(() => process.kill(descendant, 0), { code: 'ESRCH' })
    for (const value of Object.values(ports)) await assertPortFree(value)
    const calls = (await readFile(requests, 'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse)
    assert(calls.length > 0)
    assert(calls.every((call) => call.method === 'GET' && ['/', '/runs', '/chat/turn'].includes(call.path)))
    if (['ready', 'sigint'].includes(behavior)) assert.deepEqual([...new Set(calls.map((call) => call.name))], ['engine', 'chat', 'web'])
    else assert(!calls.some((call) => call.name === 'web'))
    process.removeListener('SIGINT', onInterrupt)
    assert(occupied.listening)
  }
  await new Promise((ok) => occupied.close(ok))
  console.log('Demo launcher selfcheck passed: configuration, isolation, strict ports, read-only readiness, child failure and owned shutdown; attach preserved.')
} finally {
  if (occupied.listening) await new Promise((ok) => occupied.close(ok))
  await rm(root, { recursive: true, force: true })
}

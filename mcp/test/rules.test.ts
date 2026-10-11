import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js'
import { expect, test } from 'vitest'
import { registerRules, type RuleTransport } from '../src/rules.js'

const version = 'a'.repeat(64)
const draft = { version, agent: 'meeting_assistant', status: 'draft', created_at: '2026-10-11T00:00:00Z', activated_at: null,
  allow: { tools: ['read_calendar', 'send_email'], email_to: ['demo-user@mirage-demo.com'], url_hosts: [] } }
const preview = { version, summary: 'Meeting assistant may send only to the named demo user.', effective_allow: draft.allow, authoritative: true, decision: null }

async function connect(approved: string | null, overrides: Record<string, unknown> = {}) {
  const calls: { method: string; path: string; body?: unknown }[] = []
  const confirmations: string[] = []
  const responses = { 'GET /rules/agents': [{ name: draft.agent, tools: draft.allow.tools, allow: draft.allow }],
    'GET /rules?offset=0&limit=100': [draft], [`GET /rules/${version}`]: draft,
    'POST /rules': draft, [`POST /rules/${version}/preview`]: preview,
    [`POST /rules/${version}/activate`]: { ...draft, status: 'active' }, ...overrides }
  const server = new McpServer({ name: 'rules selfcheck', version: '1' })
  const call: RuleTransport['call'] = async <T>(method: 'GET' | 'POST', path: string, body?: unknown) => {
    calls.push({ method, path, body })
    const key = `${method} ${path}`
    const value = responses[key as keyof typeof responses]
    if (value instanceof Error) throw value
    if (!(key in responses)) throw new Error(`Unexpected request ${key}`)
    return value as T
  }
  registerRules(server, { call, actor: () => 'test operator via MCP', confirm: async (message, phrase) => {
    confirmations.push(`${message}\n${phrase}`)
    return approved
  } })
  const client = new Client({ name: 'rules selfcheck', version: '1' })
  const [a, b] = InMemoryTransport.createLinkedPair()
  await Promise.all([server.connect(a), client.connect(b)])
  return { client, calls, confirmations, close: async () => { await client.close(); await server.close() } }
}

test('proposal saves the typed engine draft without activation and rejects wildcard fields', async () => {
  const c = await connect(null)
  try {
    const result = await c.client.callTool({ name: 'propose_rule', arguments: { agent: draft.agent, tools: draft.allow.tools, email_to: draft.allow.email_to } })
    expect(result.isError).toBeFalsy()
    expect(c.calls).toEqual([{ method: 'POST', path: '/rules', body: { agent: draft.agent, allow: draft.allow } }])
    expect(c.confirmations).toEqual([])
    for (const invalid of [{ tools: ['*'], email_to: [] }, { tools: [], email_to: ['*@mirage-demo.com'] }, { tools: [], email_to: ['mirage-demo.com'] }]) {
      const refused = await c.client.callTool({ name: 'propose_rule', arguments: { agent: draft.agent, ...invalid } })
      expect(refused.isError).toBe(true)
    }
    expect(c.calls).toHaveLength(1)
  } finally { await c.close() }
})

test('activation previews before confirmation and uses the confirmed human reason', async () => {
  const c = await connect('Human reviewed exact recipients')
  try {
    const result = await c.client.callTool({ name: 'activate_rule', arguments: { version, reason: 'Proposed reason' } })
    expect(result.isError).toBeFalsy()
    expect(c.calls.map((call) => call.path)).toEqual([`/rules/${version}`, `/rules/${version}/preview`, `/rules/${version}/activate`])
    expect(c.calls.at(-1)?.body).toEqual({ actor: 'test operator via MCP', reason: 'Human reviewed exact recipients' })
    expect(c.confirmations[0]).toContain(version)
    expect(c.confirmations[0]).toContain('demo-user@mirage-demo.com')
    expect(c.confirmations[0]).toContain('existing runs')
  } finally { await c.close() }
})

test('decline, preview failure, wrong digest and non-authoritative preview cannot activate', async () => {
  for (const overrides of [{}, { [`POST /rules/${version}/preview`]: new Error('409 preview unavailable') },
    { [`POST /rules/${version}/preview`]: { ...preview, version: 'b'.repeat(64) } },
    { [`POST /rules/${version}/preview`]: { ...preview, authoritative: false } }]) {
    const c = await connect(null, overrides)
    try {
      const result = await c.client.callTool({ name: 'activate_rule', arguments: { version, reason: 'Review' } })
      expect(result.isError).toBe(true)
      expect(c.calls.some((call) => call.path.endsWith('/activate'))).toBe(false)
    } finally { await c.close() }
  }
})

test('engine refusals and a non-active activation response remain failures', async () => {
  for (const response of [new Error('403 trusted local operator required'), draft]) {
    const c = await connect('Reviewed', { [`POST /rules/${version}/activate`]: response })
    try {
      const result = await c.client.callTool({ name: 'activate_rule', arguments: { version, reason: 'Review' } })
      expect(result.isError).toBe(true)
    } finally { await c.close() }
  }
})

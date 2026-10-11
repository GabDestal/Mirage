// M3 is an HTTP consumer. Engine validation and the existing human elicitation remain authoritative.
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import type { CallToolResult } from '@modelcontextprotocol/sdk/types.js'
import { z } from 'zod'

type Allowlist = { tools: string[]; email_to: string[]; url_hosts: string[] }
type RuleRevision = { version: string; agent: string; allow: Allowlist; status: 'draft' | 'active' | 'superseded'; created_at: string; activated_at: string | null }
type RulePreview = { version: string; summary: string; effective_allow: Allowlist; authoritative: boolean; decision: unknown }
type RuleAgent = { name: string; tools: string[]; allow: Allowlist }
export type RuleTransport = {
  call: <T>(method: 'GET' | 'POST', path: string, body?: unknown) => Promise<T>
  confirm: (message: string, phrase: string, reason: string) => Promise<string | null>
  actor: () => string
}

const versionArg = z.string().regex(/^[a-f0-9]{64}$/).describe('Immutable SHA256 revision returned by the engine.')
const toolArg = z.string().regex(/^[\w.-]+$/).describe('Exact registered tool name; no wildcards.')
const recipientArg = z.string().regex(/^[^\s@<>,;*]+@[^\s@<>,;*]+\.[^\s@<>,;*]+$/).describe('Exact full email address; no domains, wildcards or display names.')
const read = { readOnlyHint: true, openWorldHint: false }
const result = (message: string, data: Record<string, unknown>): CallToolResult => ({ content: [{ type: 'text', text: message }], structuredContent: data })
const refusal = (message: string): CallToolResult => ({ content: [{ type: 'text', text: `Not done: ${message}` }], isError: true })
const path = (version: string) => `/rules/${encodeURIComponent(version)}`

export function registerRules(server: McpServer, transport: RuleTransport) {
  const safe = <A>(fn: (args: A) => Promise<CallToolResult>) => async (args: A) => {
    try { return await fn(args) } catch (error) { return refusal(error instanceof Error ? error.message : 'Engine request failed; check current rules before retrying.') }
  }

  server.registerTool('list_rule_agents', {
    title: 'List registered rule agents', description: 'Named registered agents and exact tool identities for drafting a restrictive rule. These are role registrations, not the effective policy; use preview_rule for that.',
    inputSchema: {}, annotations: read,
  }, safe(async () => {
    const agents = await transport.call<RuleAgent[]>('GET', '/rules/agents')
    return result(agents.length ? agents.map((agent) => `${agent.name}: ${agent.tools.join(', ') || 'no tools'}`).join('\n') : 'No registered agents yet.', { agents })
  }))

  server.registerTool('list_rules', {
    title: 'List rules', description: 'Durable drafts, active and superseded restrictive revisions from the same engine used by the dashboard. Returns up to 100 revisions; use offset for the next page.',
    inputSchema: { agent: z.string().trim().min(1).optional(), offset: z.number().int().min(0).default(0) }, annotations: read,
  }, safe(async ({ agent, offset }) => {
    const query = new URLSearchParams({ offset: String(offset), limit: '100', ...(agent && { agent }) })
    const rules = await transport.call<RuleRevision[]>('GET', `/rules?${query}`)
    return result(rules.length ? rules.map((rule) => `${rule.agent}: ${rule.status}, revision ${rule.version}`).join('\n') : 'No saved rules yet.', { rules, offset, limit: 100 })
  }))

  server.registerTool('get_rule', {
    title: 'Read rule revision', description: 'Read one immutable rule revision and its current activation status from the engine.',
    inputSchema: { version: versionArg }, annotations: read,
  }, safe(async ({ version }) => {
    const rule = await transport.call<RuleRevision>('GET', path(version))
    return result(`${rule.agent}: ${rule.status}, revision ${rule.version}. Activation affects new runs; existing runs retain their pinned policy.`, { rule })
  }))

  server.registerTool('propose_rule', {
    title: 'Propose a restrictive rule', description: 'Save a durable typed draft for one registered agent. Only narrows tools and exact email recipients; no URL editing, no P1–P6 edits. Empty tools or recipients allow none. Saving never activates it. Next preview_rule, then explicit human activation.',
    inputSchema: { agent: z.string().trim().min(1), tools: z.array(toolArg), email_to: z.array(recipientArg) },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  }, safe(async ({ agent, tools, email_to }) => {
    const rule = await transport.call<RuleRevision>('POST', '/rules', { agent, allow: { tools, email_to, url_hosts: [] } })
    return result(`Draft saved for ${rule.agent}, revision ${rule.version}, current status ${rule.status}. No activation was requested. Preview it and ask the human before activation.`, { rule })
  }))

  server.registerTool('preview_rule', {
    title: 'Preview rule', description: 'Ask the engine for effective permissions and optional hard-rule decision for a sample call. Runs no real tool and no model. Never activates anything.',
    inputSchema: { version: versionArg, tool: toolArg.optional(), args: z.record(z.string(), z.unknown()).default({}) }, annotations: read,
  }, safe(async ({ version, tool, args }) => {
    const preview = await transport.call<RulePreview>('POST', `${path(version)}/preview`, { ...(tool && { tool }), args })
    if (preview.authoritative !== true || preview.version !== version) return refusal('Engine preview was not authoritative for this revision. Do not activate it.')
    return result(`${preview.summary}\nRevision ${preview.version}. New runs only; existing runs retain their pinned policy.`, { preview })
  }))

  server.registerTool('activate_rule', {
    title: 'Activate rule for new runs', description: 'Preview this exact revision, show digest and permissions to the human, and activate only after human confirmation through MCP elicitation. A false-positive verdict never activates a rule automatically. Existing runs and already approved restarts retain their pinned policy.',
    inputSchema: { version: versionArg, reason: z.string().trim().min(1) },
    annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: false },
  }, safe(async ({ version, reason }) => {
    const rule = await transport.call<RuleRevision>('GET', path(version))
    if (rule.status === 'active') return result(`Revision ${rule.version} is already active. No activation was sent.`, { rule })
    const preview = await transport.call<RulePreview>('POST', `${path(version)}/preview`, { args: {} })
    if (preview.authoritative !== true || preview.version !== version) return refusal('Engine preview was not authoritative for this revision. No activation was sent.')
    const confirmedReason = await transport.confirm(`Activate rule for ${rule.agent}, exact revision ${version}. ${preview.summary} Effective tools: ${preview.effective_allow.tools.join(', ') || 'none'}. Exact recipients: ${preview.effective_allow.email_to.join(', ') || 'none'}. New runs use it; existing runs and already approved restarts retain their policy. Reason: ${reason}`, `activate rule ${version}`, reason)
    if (!confirmedReason?.trim()) return refusal('Human confirmation was declined, unavailable or invalid. No activation was sent.')
    const activated = await transport.call<RuleRevision>('POST', `${path(version)}/activate`, { actor: transport.actor(), reason: confirmedReason.trim() })
    if (activated.version !== version || activated.status !== 'active') return refusal('Engine did not confirm activation. Read the rule before retrying.')
    return result(`Engine confirmed ${activated.agent} revision ${version} is active for new runs. Existing runs and already approved restarts retain their pinned policy.`, { rule: activated })
  }))
}

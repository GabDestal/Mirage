// Additive consumer types for the agreed M3 contract; Python models remain authoritative.
import { useQuery } from '@tanstack/react-query'
import { api } from './client.ts'

export type RuleAllowlist = { tools: string[]; email_to: string[]; url_hosts: string[] }
export type RuleAgent = { name: string; tools: string[]; allow: RuleAllowlist }
export type RuleDraftRequest = { agent: string; allow: RuleAllowlist }
export type RuleRevision = RuleDraftRequest & {
  version: string
  status: 'draft' | 'active' | 'superseded'
  created_at: string
  activated_at: string | null
}
export type RulePreview = {
  version: string
  summary: string
  effective_allow: RuleAllowlist
  decision: { decision: 'allow' | 'freeze' | 'block'; explanation: string } | null
  authoritative: boolean
}

export const rulesPath = (version: string) => `/rules/${encodeURIComponent(version)}`
export const useRuleAgents = () => useQuery({ queryKey: ['rule-agents'], queryFn: ({ signal }) => api<RuleAgent[]>('/rules/agents', undefined, signal), refetchInterval: 5_000 })
export const useRules = () => useQuery({ queryKey: ['rules'], queryFn: ({ signal }) => api<RuleRevision[]>('/rules', undefined, signal), refetchInterval: 2_000 })
export const readRule = (version: string) => api<RuleRevision>(rulesPath(version))
export const createRule = (draft: RuleDraftRequest) => api<RuleRevision>('/rules', draft)
export const previewRule = (version: string) => api<RulePreview>(`${rulesPath(version)}/preview`, { args: {} })
export const activateRule = (version: string, actor: string, reason: string) => api<RuleRevision>(`${rulesPath(version)}/activate`, { actor: actor.trim(), reason: reason.trim() })

export function ruleSentence(agent: string, allow: Pick<RuleAllowlist, 'tools' | 'email_to'>) {
  return `${agent || 'This agent'} may use ${allow.tools.length ? allow.tools.join(', ') : 'no tools'} and send email to ${allow.email_to.length ? allow.email_to.join(', ') : 'no recipients'}. Other permissions remain restricted by the engine.`
}

/** Form syntax only; permission checks always belong to the engine. */
export function draftFromFields(agent: string, toolsText: string, recipientsText: string): RuleDraftRequest {
  const split = (value: string) => [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))]
  const tools = split(toolsText), email_to = split(recipientsText)
  if (!agent.trim()) throw new Error('Choose a registered agent.')
  if (tools.some((tool) => !/^[\w.-]+$/.test(tool))) throw new Error('Use exact tool names, separated by commas or new lines. Wildcards are not supported.')
  if (email_to.some((address) => !/^[^\s@<>,;*]+@[^\s@<>,;*]+\.[^\s@<>,;*]+$/.test(address)))
    throw new Error('Use full email addresses, separated by commas or new lines. Domains, wildcards and display names are not supported.')
  return { agent: agent.trim(), allow: { tools, email_to, url_hosts: [] } }
}

/** Extract agent, tools, and email recipients from natural language text. */
export function extractRuleFromNaturalLanguage(prompt: string, agents: RuleAgent[]) {
  const text = prompt.toLowerCase()
  let matchedAgent = agents.find(
    (a) => text.includes(a.name.toLowerCase()) || text.includes(a.name.replace(/[_-]+/g, ' ').toLowerCase())
  )
  if (!matchedAgent) {
    if (text.includes('meeting') || text.includes('calendar')) {
      matchedAgent = agents.find((a) => a.name.includes('meeting') || a.name.includes('assistant'))
    } else if (text.includes('outreach') || text.includes('crm')) {
      matchedAgent = agents.find((a) => a.name.includes('outreach'))
    }
  }
  const targetAgent = matchedAgent ?? agents[0]
  if (!targetAgent) throw new Error('No registered agents found to apply this rule to.')

  const availableTools = targetAgent.tools.length ? targetAgent.tools : ['read_calendar', 'send_email', 'fetch_url', 'crm_query', 'crm_export']
  const detectedTools = new Set<string>()

  for (const tool of availableTools) {
    const readable = tool.replace(/_/g, ' ')
    if (text.includes(tool.toLowerCase()) || text.includes(readable)) {
      detectedTools.add(tool)
    }
  }
  if (text.includes('read calendar') || text.includes('check calendar') || text.includes('calendar')) detectedTools.add('read_calendar')
  if (text.includes('send email') || text.includes('send mail') || text.includes('email') || text.includes('mail')) detectedTools.add('send_email')
  if (text.includes('crm query') || text.includes('search contacts')) detectedTools.add('crm_query')
  if (text.includes('crm export')) detectedTools.add('crm_export')

  const tools = detectedTools.size > 0 ? Array.from(detectedTools) : availableTools.slice(0, 2)
  const emailRegex = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g
  const matchedEmails = prompt.match(emailRegex) ?? []
  const email_to = Array.from(new Set(matchedEmails.map((e) => e.toLowerCase().trim())))

  return {
    agent: targetAgent.name,
    tools,
    email_to,
  }
}


import assert from 'node:assert/strict'
import { activateRule, createRule, draftFromFields, previewRule, readRule, ruleSentence } from './rules.ts'

const draft = draftFromFields('meeting_assistant', 'read_calendar, send_email\nread_calendar', 'demo-user@mirage-demo.com')
assert.deepEqual(draft, { agent: 'meeting_assistant', allow: { tools: ['read_calendar', 'send_email'], email_to: ['demo-user@mirage-demo.com'], url_hosts: [] } })
for (const [agent, tools, recipients] of [['', '', ''], ['assistant', '*', ''], ['assistant', 'read calendar', ''], ['assistant', '', '*@mirage-demo.com'], ['assistant', '', 'mirage-demo.com'], ['assistant', '', 'Operator <demo-user@mirage-demo.com>']]) {
  assert.throws(() => draftFromFields(agent, tools, recipients))
}
assert.deepEqual(draftFromFields('assistant', '', '').allow, { tools: [], email_to: [], url_hosts: [] })
assert.match(ruleSentence('Meeting assistant', draft.allow), /send_email.*demo-user@mirage-demo.com/)

const calls: { url: string; method: string; body: unknown }[] = []
const originalFetch = globalThis.fetch
globalThis.fetch = (async (url, init) => {
  calls.push({ url: String(url), method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined })
  return Response.json({ version: 'a'.repeat(64), status: 'draft' })
}) as typeof fetch
try {
  const version = 'a'.repeat(64)
  await createRule(draft); await readRule(version); await previewRule(version); await activateRule(version, 'operator via web', ' Reviewed ')
  assert.deepEqual(calls.map(({ url, method }) => [url, method]), [['/api/rules', 'POST'], [`/api/rules/${version}`, 'GET'], [`/api/rules/${version}/preview`, 'POST'], [`/api/rules/${version}/activate`, 'POST']])
  assert.deepEqual(calls[2].body, { args: {} })
  assert.deepEqual(calls[3].body, { actor: 'operator via web', reason: 'Reviewed' })
  globalThis.fetch = (async () => Response.json({ detail: 'Rule broadens registered tool permissions' }, { status: 422 })) as typeof fetch
  await assert.rejects(() => createRule(draft), /Rule broadens registered tool permissions/)
} finally { globalThis.fetch = originalFetch }
console.log('Rules form and typed HTTP client selfcheck passed (scripted transport).')

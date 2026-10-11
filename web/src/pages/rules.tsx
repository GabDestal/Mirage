import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { queryClient } from '@/api/client'
import { activateRule, createRule, draftFromFields, previewRule, readRule, ruleSentence, useRuleAgents, useRules, type RulePreview, type RuleRevision } from '@/api/rules'
import { Button } from '@/components/ui/button'
import { agentName } from '@/lib/runs'
import './rules.css'

export function Rules() {
  const agents = useRuleAgents(), rules = useRules()
  const [agent, setAgent] = useState('')
  const [tools, setTools] = useState('')
  const [recipients, setRecipients] = useState('')
  const [selected, setSelected] = useState<RuleRevision | null>(null)
  const [preview, setPreview] = useState<RulePreview | null>(null)
  const [actor, setActor] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const currentAgent = agents.data?.find((item) => item.name === agent)
  const current = rules.data?.find((item) => item.version === selected?.version) ?? selected
  const canActivate = current?.status !== 'active' && preview?.authoritative === true && preview.version === current?.version

  async function perform(action: string, fn: () => Promise<void>) {
    if (busy) return
    setBusy(action); setError(''); setNotice('')
    try { await fn() } catch (err) { setError(err instanceof Error ? err.message : 'The engine request failed. Retry after checking its status.') }
    finally { setBusy('') }
  }

  function save(event: FormEvent) {
    event.preventDefault()
    void perform('create', async () => {
      const draft = draftFromFields(agent, tools, recipients)
      const revision = await createRule(draft)
      setSelected(revision); setPreview(null); setReason('')
      await queryClient.invalidateQueries({ queryKey: ['rules'] })
      setNotice('Draft saved in the engine. Preview it before deciding whether to activate.')
    })
  }

  function inspect(version: string) {
    setPreview(null)
    void perform('preview', async () => {
      const revision = await readRule(version)
      setSelected(revision); setReason('')
      const result = await previewRule(version)
      if (result.version !== version || !result.authoritative) throw new Error('The engine did not return an authoritative preview for this revision. Activation is unavailable.')
      setPreview(result)
    })
  }

  function activate(event: FormEvent) {
    event.preventDefault()
    if (!current || !canActivate || !actor.trim() || !reason.trim()) return
    const version = current.version
    void perform('activate', async () => {
      const result = await activateRule(version, `${actor.trim()} via web`, reason)
      if (result.version !== version || result.status !== 'active') throw new Error('The engine did not confirm activation. Refresh the rule list to check its status.')
      setSelected(result)
      await queryClient.invalidateQueries({ queryKey: ['rules'] })
      setNotice('Engine confirmed activation. New runs use this revision; existing runs keep their pinned policy.')
      toast.success('Rule activated for new runs.')
    })
  }

  return <div className="rules-page">
    <header className="rules-header"><h1>Rules</h1>
      <p>Narrow the tools and email recipients a named agent may use. The engine keeps the role permissions and P1–P6 checks in force.</p>
      <p>Activation affects new runs. Existing runs and already approved restarts keep their pinned policy.</p>
    </header>
    {error ? <p className="rules-error" role="alert">{error}</p> : null}
    {notice ? <p className="rules-feedback" role="status">{notice}</p> : null}
    <section aria-labelledby="rules-create-heading"><h2 id="rules-create-heading">Create a draft</h2>
      {agents.isPending ? <p role="status">Loading registered agents…</p> : agents.isError ? <div role="alert"><p>Could not load registered agents: {agents.error.message}</p><Button onClick={() => agents.refetch()}>Retry agents</Button></div> : !agents.data?.length ? <p>Register a protected agent with the engine to create its first rule.</p> :
        <form className="rules-form" onSubmit={save}>
          <div className="rules-wide"><label htmlFor="rule-agent">Agent</label><select id="rule-agent" value={agent} required disabled={!!busy} onChange={(event) => { setAgent(event.target.value); setTools(''); setRecipients('') }}>
            <option value="">Choose a registered agent</option>{agents.data.map((item) => <option key={item.name} value={item.name}>{agentName(item.name)} ({item.name})</option>)}
          </select></div>
          <div><label htmlFor="rule-tools">Allowed tools</label><textarea id="rule-tools" value={tools} disabled={!!busy || !agent} onChange={(event) => setTools(event.target.value)} placeholder="read_calendar, send_email" aria-describedby="rule-tools-help" />
            <small id="rule-tools-help">Exact names, separated by commas or new lines. Leave empty to allow no tools.{currentAgent ? ` Registered tools: ${currentAgent.tools.join(', ') || 'none'}.` : ''}</small></div>
          <div><label htmlFor="rule-recipients">Exact email recipients</label><textarea id="rule-recipients" value={recipients} disabled={!!busy || !agent} onChange={(event) => setRecipients(event.target.value)} placeholder="demo-user@mirage-demo.com" aria-describedby="rule-recipient-help" />
            <small id="rule-recipient-help">Full addresses only. Separate with commas or new lines. Leave empty to allow no recipients. URL permissions are not edited here.</small></div>
          <p className="rules-sentence rules-wide">{ruleSentence(agentName(agent), { tools: tools.split(/[\n,]/).map((item) => item.trim()).filter(Boolean), email_to: recipients.split(/[\n,]/).map((item) => item.trim()).filter(Boolean) })}</p>
          <div className="rules-actions rules-wide"><Button type="submit" variant="primary" disabled={!!busy || !agent}>{busy === 'create' ? 'Saving draft…' : 'Save draft'}</Button><span>Saving does not activate a rule.</span></div>
        </form>}
    </section>
    <section className="rules-section" aria-labelledby="rules-list-heading"><div className="rules-actions"><h2 id="rules-list-heading">Saved revisions</h2><Button disabled={!!busy} onClick={() => rules.refetch()}>Refresh rules</Button></div>
      {rules.isPending ? <p role="status">Loading rules…</p> : rules.isError ? <p role="alert" className="rules-error">Could not load rules: {rules.error.message}. Use Refresh rules to retry.</p> : !rules.data?.length ? <p className="rules-empty">No saved rules yet. Create a draft, review the engine preview, then activate it explicitly.</p> : rules.data.map((revision) =>
        <article className="rules-row" key={revision.version}><div><h3>{agentName(revision.agent)}<span className={`rules-status rules-status-${revision.status}`}>{revision.status}</span></h3>
          <p>{ruleSentence(agentName(revision.agent), revision.allow)}</p>
          <p className="rules-digest">Immutable revision <code>{revision.version}</code></p>
          <p>Created <time dateTime={revision.created_at}>{new Date(revision.created_at).toLocaleString()}</time>{revision.activated_at ? <> · Activated <time dateTime={revision.activated_at}>{new Date(revision.activated_at).toLocaleString()}</time></> : null}</p>
        </div><Button disabled={!!busy} onClick={() => inspect(revision.version)} aria-label={`Preview ${revision.agent} revision ${revision.version}`}>Preview</Button></article>)}
    </section>
    {current ? <section className="rules-section rules-preview" aria-labelledby="rule-preview-heading"><h2 id="rule-preview-heading">Review {agentName(current.agent)}</h2>
      <p className="rules-digest">Immutable revision <code>{current.version}</code> · {current.status}</p>
      {!preview ? <div className="rules-actions"><p>{busy === 'preview' ? 'Loading engine preview…' : 'Engine preview is required before activation.'}</p><Button disabled={!!busy} onClick={() => inspect(current.version)}>Preview draft</Button></div> : <>
        <p className="rules-sentence">{preview.summary}</p><dl><dt>Effective tools</dt><dd>{preview.effective_allow.tools.join(', ') || 'None'}</dd><dt>Effective recipients</dt><dd>{preview.effective_allow.email_to.join(', ') || 'None'}</dd><dt>URL hosts</dt><dd>{preview.effective_allow.url_hosts.join(', ') || 'None'}</dd></dl>
        <p>The engine computed these permissions. A saved rule can only narrow the registered role. This preview runs no real tool.</p>
        {current.status === 'active' ? <p role="status">This revision is active for new runs.</p> : <form className="rules-form" onSubmit={activate}>
          <div><label htmlFor="rule-actor">Operator</label><input id="rule-actor" value={actor} onChange={(event) => setActor(event.target.value)} required maxLength={200} disabled={!!busy} autoComplete="off" /></div>
          <div><label htmlFor="rule-reason">Reason for activation</label><input id="rule-reason" value={reason} onChange={(event) => setReason(event.target.value)} required maxLength={1000} disabled={!!busy} autoComplete="off" /></div>
          <p className="rules-wide">Activate this exact revision for new runs. Existing runs and already approved restarts retain their policy. Your operator name and reason are logged.</p>
          <div className="rules-actions rules-wide"><Button type="submit" variant="primary" disabled={!!busy || !canActivate || !actor.trim() || !reason.trim()}>{busy === 'activate' ? 'Activating…' : 'Activate for new runs'}</Button></div>
        </form>}
      </>}
    </section> : null}
  </div>
}

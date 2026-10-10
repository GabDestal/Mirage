import { CalendarDays, Copy, Database, KeyRound, Mail, MessageSquare, Plus, Terminal, Trash2 } from 'lucide-react'
import { AlertDialog, Dialog, Tabs } from 'radix-ui'
import { useEffect, useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { API_KEYS_STORAGE, createApiKey, listApiKeys, revokeApiKey, type ApiKey, type KeyEnvironment } from '@/api/api-keys'
import { Button } from '@/components/ui/button'
import './integrations.css'

const SHELL_SNIPPET = 'export MIRAGE_API_KEY="mirage_live_..."'
const PYTHON_SNIPPET = `import mirage

# Planned API key authentication
# Reads MIRAGE_API_KEY or accepts an explicit key
agent = mirage.protect(agent, name="assistant", api_key="mirage_live_...")`
const CURRENT_SNIPPET = `import mirage

agent = mirage.protect(agent, name="assistant")`
const SERVICES = [
  { name: 'Gmail', icon: Mail, description: 'Read messages and send meeting summaries.', status: 'Demo agent tool' },
  { name: 'Google Calendar', icon: CalendarDays, description: 'Read events and prepare for upcoming meetings.', status: 'Demo agent tool' },
  { name: 'HubSpot CRM', icon: Database, description: 'Look up synthetic customer contacts and records.', status: 'Demo agent tool' },
  { name: 'Slack', icon: MessageSquare, description: 'Bring agent protection to team conversations.', status: 'Planned' },
]

function readKeys() {
  try { return { keys: listApiKeys(), error: '' } }
  catch { return { keys: [] as ApiKey[], error: 'API key storage could not be read. Enable site storage, or restore or clear invalid saved API key metadata, then retry.' } }
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value)
    toast.success('Copied to clipboard.')
  } catch {
    toast.error('Could not copy. Select the text and copy it manually.')
  }
}

const dateLabel = (value: string) => new Date(value).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })

export function Integrations() {
  const [stored, setStored] = useState(readKeys)
  const [createOpen, setCreateOpen] = useState(false)
  const [created, setCreated] = useState<ReturnType<typeof createApiKey> | null>(null)
  const [name, setName] = useState('')
  const [environment, setEnvironment] = useState<KeyEnvironment>('Production')
  const [revoking, setRevoking] = useState<ApiKey | null>(null)
  const refresh = () => setStored(readKeys())

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === API_KEYS_STORAGE || event.key === null) setStored(readKeys())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  function closeCreate() {
    setCreateOpen(false)
    setCreated(null)
    setName('')
    setEnvironment('Production')
  }

  function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setCreated(createApiKey(name, environment))
      refresh()
      toast.success('Demo API key created.')
    } catch {
      toast.error('Could not save the key. Check site storage and your key name, then try again.')
      refresh()
    }
  }

  function revoke() {
    if (!revoking) return
    try {
      revokeApiKey(revoking.id)
      refresh()
      setRevoking(null)
      toast.success('Demo API key revoked in this browser.')
    } catch {
      toast.error('Could not revoke the key. Check site storage and retry.')
      refresh()
    }
  }

  return (
    <div className="integrations-page">
      <div className="integrations-container">
        <header className="integrations-header">
          <h1>Integrations &amp; API Keys</h1>
          <p>Manage credentials for agent protection and explore the services your agents use.</p>
        </header>
        <Tabs.Root defaultValue="keys">
          <Tabs.List className="integrations-tabs" aria-label="Integrations">
            <Tabs.Trigger value="keys"><KeyRound size={16} aria-hidden />API Keys</Tabs.Trigger>
            <Tabs.Trigger value="services"><Database size={16} aria-hidden />Connected Services</Tabs.Trigger>
          </Tabs.List>
          <Tabs.Content value="keys" className="integrations-panel">
            <div className="integrations-section-heading">
              <div><h2>Mirage API keys</h2><p>Create a named key for each agent or environment.</p></div>
              <Dialog.Root open={createOpen} onOpenChange={(open) => open ? setCreateOpen(true) : closeCreate()}>
                <Dialog.Trigger asChild><Button variant="primary" disabled={!!stored.error}><Plus aria-hidden />Create API Key</Button></Dialog.Trigger>
                <Dialog.Portal>
                  <Dialog.Overlay className="integrations-overlay" />
                  <Dialog.Content className="integrations-dialog">
                    <Dialog.Title>{created ? 'Copy your API key' : 'Create API key'}</Dialog.Title>
                    <Dialog.Description>
                      {created ? 'Save this key now. Once you close this dialog, it cannot be shown again.' : 'Give this demo key a name so you can recognize it later.'}
                    </Dialog.Description>
                    {created ? <div className="integrations-form">
                      <label htmlFor="created-api-key">{created.key.name} · {created.key.environment}</label>
                      <textarea id="created-api-key" readOnly value={created.secret} rows={3} spellCheck={false} onFocus={(event) => event.target.select()} />
                      <p className="integrations-help">Demo key only. SDK authentication is not enabled yet.</p>
                      <div className="integrations-dialog-actions">
                        <Button onClick={closeCreate}>Done</Button>
                        <Button variant="primary" onClick={() => copyText(created.secret)}><Copy aria-hidden />Copy Key</Button>
                      </div>
                    </div> : <form onSubmit={generate} className="integrations-form">
                      <label htmlFor="api-key-name">Name</label>
                      <input id="api-key-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Meeting assistant" maxLength={100} required autoComplete="off" />
                      <label htmlFor="api-key-environment">Environment</label>
                      <select id="api-key-environment" value={environment} onChange={(event) => setEnvironment(event.target.value as KeyEnvironment)}>
                        <option>Production</option><option>Development</option>
                      </select>
                      <p className="integrations-help">Environment is a label in this demo; both use the mirage_live_ prefix.</p>
                      <div className="integrations-dialog-actions">
                        <Button type="button" variant="ghost" onClick={closeCreate}>Cancel</Button>
                        <Button type="submit" variant="primary" disabled={!name.trim()}>Generate Key</Button>
                      </div>
                    </form>}
                  </Dialog.Content>
                </Dialog.Portal>
              </Dialog.Root>
            </div>
            <p className="integrations-notice">Browser demo · Only masked key metadata is saved on this device. These keys do not authenticate SDK requests yet.</p>
            {stored.error ? <div className="integrations-storage-error" role="alert"><p>{stored.error}</p><Button onClick={refresh}>Retry storage</Button></div> :
              <div className="integrations-table-wrap" tabIndex={0} role="region" aria-label="API keys; scroll horizontally for details and revocation">
                <table className="integrations-table">
                  <caption className="sr-only">API keys saved in this browser</caption>
                  <thead><tr><th scope="col">Name</th><th scope="col">API key</th><th scope="col">Environment</th><th scope="col">Created</th><th scope="col">Last used</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                  <tbody>{stored.keys.map((key) => <tr key={key.id}>
                    <th scope="row">{key.name}</th><td><code>{key.maskedKey}</code></td>
                    <td><span className="integrations-environment">{key.environment}</span></td>
                    <td><time dateTime={key.createdAt}>{dateLabel(key.createdAt)}</time></td>
                    <td>{key.lastUsedAt ? <time dateTime={key.lastUsedAt}>{dateLabel(key.lastUsedAt)}</time> : 'Never'}</td>
                    <td><Button variant="destructive" aria-label={`Revoke ${key.name}`} onClick={() => setRevoking(key)}><Trash2 aria-hidden /><span>Revoke</span></Button></td>
                  </tr>)}</tbody>
                </table>
                {stored.keys.length === 0 ? <div className="integrations-empty"><KeyRound size={24} aria-hidden /><h3>No API keys yet</h3><p>Create your first key to preview how agents will connect to Mirage.</p></div> : null}
              </div>}
            <section className="integrations-quickstart" aria-labelledby="quickstart-title">
              <div className="integrations-section-heading"><div><h2 id="quickstart-title"><Terminal size={18} aria-hidden />SDK quickstart</h2><p>Keep credentials in your environment, outside your source code.</p></div></div>
              <Snippet label="Environment variable" code={SHELL_SNIPPET} />
              <Snippet label="Python · planned API key support" code={PYTHON_SNIPPET} />
              <p className="integrations-help">The current SDK does not read MIRAGE_API_KEY or accept api_key. Until authentication is added, use the existing wrapper:</p>
              <Snippet label="Python · current SDK" code={CURRENT_SNIPPET} />
            </section>
          </Tabs.Content>
          <Tabs.Content value="services" className="integrations-panel">
            <div className="integrations-section-heading"><div><h2>Services your agents use</h2><p>Mirage checks tool calls while your agents keep their own service credentials.</p></div></div>
            <p className="integrations-notice">Service overview · Connection status is not available in this demo. Configure service access in your agent.</p>
            <ul className="integrations-services">{SERVICES.map(({ name: serviceName, icon: Icon, description, status }) => <li key={serviceName}>
              <Icon size={20} aria-hidden /><div><h3>{serviceName}</h3><p>{description}</p></div><span className="integrations-environment">{status}</span>
            </li>)}</ul>
          </Tabs.Content>
        </Tabs.Root>
      </div>
      <AlertDialog.Root open={!!revoking} onOpenChange={(open) => !open && setRevoking(null)}>
        <AlertDialog.Portal><AlertDialog.Overlay className="integrations-overlay" /><AlertDialog.Content className="integrations-dialog">
          <AlertDialog.Title>Revoke {revoking?.name}?</AlertDialog.Title>
          <AlertDialog.Description>This removes the key from this browser. This demo action does not stop agents or revoke engine tokens.</AlertDialog.Description>
          <div className="integrations-dialog-actions">
            <AlertDialog.Cancel asChild><Button>Cancel</Button></AlertDialog.Cancel>
            <Button variant="destructive" onClick={revoke}>Revoke key</Button>
          </div>
        </AlertDialog.Content></AlertDialog.Portal>
      </AlertDialog.Root>
    </div>
  )
}

function Snippet({ label, code }: { label: string; code: string }) {
  return <div className="integrations-snippet"><div><span>{label}</span><Button variant="ghost" aria-label={`Copy ${label}`} onClick={() => copyText(code)}><Copy aria-hidden />Copy</Button></div><pre><code>{code}</code></pre></div>
}

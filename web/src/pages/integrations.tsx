import { Copy, Trash2 } from 'lucide-react'
import { AlertDialog } from 'radix-ui'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { API_KEYS_STORAGE, createApiKey, listApiKeys, revokeApiKey, type ApiKey } from '@/api/api-keys'
import { Button } from '@/components/ui/button'
import './integrations.css'

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
  const [created, setCreated] = useState<ReturnType<typeof createApiKey> | null>(null)
  const [name, setName] = useState('')
  const [revoking, setRevoking] = useState<ApiKey | null>(null)
  const nameInput = useRef<HTMLInputElement>(null)
  const secretInput = useRef<HTMLTextAreaElement>(null)
  const refresh = () => setStored(readKeys())

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === API_KEYS_STORAGE || event.key === null) {
        const next = readKeys()
        setStored(next)
        setCreated((current) => current && next.keys.some((key) => key.id === current.key.id) ? current : null)
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  useEffect(() => {
    if (created) secretInput.current?.focus()
  }, [created])

  function finishCreate() {
    setCreated(null)
    setName('')
    requestAnimationFrame(() => nameInput.current?.focus())
  }

  function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (created) return
    try {
      setCreated(createApiKey(name))
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
      if (created?.key.id === revoking.id) finishCreate()
      refresh()
      setRevoking(null)
      toast.success('Demo API key revoked in this browser.')
    } catch {
      toast.error('Could not revoke the key. Check site storage and retry.')
      refresh()
    }
  }

  return (
    <AlertDialog.Root open={!!revoking} onOpenChange={(open) => !open && setRevoking(null)}>
      <div className="integrations-page">
        <div className="integrations-container">
          <header className="integrations-header">
            <h1>API keys</h1>
            <p>Demo keys — authentication is not enabled yet.</p>
          </header>
          {created ? <section className="integrations-reveal" aria-label="New API key">
            <label htmlFor="created-api-key">{created.key.name}</label>
            <p id="save-key-help">Save this key now. It won’t be shown again.</p>
            <textarea ref={secretInput} id="created-api-key" aria-describedby="save-key-help" readOnly value={created.secret} rows={3} spellCheck={false} onFocus={(event) => event.target.select()} />
            <div className="integrations-reveal-actions">
              <Button variant="primary" onClick={() => copyText(created.secret)}><Copy aria-hidden />Copy key</Button>
              <Button onClick={finishCreate}>Done</Button>
            </div>
          </section> : <form onSubmit={generate} className="integrations-form">
            <div className="integrations-name-field">
              <label htmlFor="api-key-name">Name</label>
              <input ref={nameInput} id="api-key-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Meeting assistant" maxLength={100} required autoComplete="off" disabled={!!stored.error} />
            </div>
            <Button type="submit" variant="primary" disabled={!!stored.error || !name.trim()}>Create key</Button>
          </form>}
          {stored.error ? <div className="integrations-storage-error" role="alert"><p>{stored.error}</p><Button onClick={refresh}>Retry storage</Button></div> :
            stored.keys.length === 0 ? <div className="integrations-empty"><p>No API keys yet.</p></div> :
              <div className="integrations-table-wrap" tabIndex={0} role="region" aria-label="API keys">
                <table className="integrations-table">
                  <caption className="sr-only">API keys saved in this browser</caption>
                  <thead><tr><th scope="col">Name</th><th scope="col">API key</th><th scope="col">Created</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                  <tbody>{stored.keys.map((key) => <tr key={key.id}>
                    <th scope="row">{key.name}</th><td><code>{key.maskedKey}</code></td>
                    <td><time dateTime={key.createdAt}>{dateLabel(key.createdAt)}</time></td>
                    <td><AlertDialog.Trigger asChild><Button variant="destructive" aria-label={`Revoke ${key.name}`} onClick={() => setRevoking(key)}><Trash2 aria-hidden /><span>Revoke</span></Button></AlertDialog.Trigger></td>
                  </tr>)}</tbody>
                </table>
              </div>}
        </div>
      </div>
      <AlertDialog.Portal><AlertDialog.Overlay className="integrations-overlay" /><AlertDialog.Content className="integrations-dialog">
        <AlertDialog.Title>Revoke {revoking?.name}?</AlertDialog.Title>
        <AlertDialog.Description>This removes the key from this browser. This demo action does not stop agents or revoke engine tokens.</AlertDialog.Description>
        <div className="integrations-dialog-actions">
          <AlertDialog.Cancel asChild><Button>Cancel</Button></AlertDialog.Cancel>
          <Button variant="destructive" onClick={revoke}>Revoke key</Button>
        </div>
      </AlertDialog.Content></AlertDialog.Portal>
    </AlertDialog.Root>
  )
}

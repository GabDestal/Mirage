import { createRoot } from 'react-dom/client'
import { useState } from 'react'
import { ChatActivity, ChatApprovalCard, ChatComposer, ChatToolCard, type ChatActivityState } from '../chat-primitives'
import '../../pages/login.css'
import './preview.css'

export function Preview() {
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [disabled, setDisabled] = useState(false)
  const [state, setState] = useState<ChatActivityState>('thinking')
  const [count, setCount] = useState(0)
  const [decision, setDecision] = useState('No decision sent')
  const [pending, setPending] = useState(false)
  return <main className="mirage-preview">
    <p className="preview-note">Component validation · synthetic examples · no engine calls</p>
    <img src="/favicon.svg" width="64" height="64" alt="" />
    <h1>What needs your attention today?</h1>
    <ChatComposer value={draft} onChange={setDraft} onSubmit={() => { setCount(count + 1); setBusy(true); setDraft('') }} busy={busy} disabled={disabled} onStop={() => setBusy(false)} placeholder="Ask which agents are frozen, and what happened…" />
    <div className="preview-controls"><button onClick={() => setBusy(!busy)}>Toggle busy</button><button onClick={() => setDisabled(!disabled)}>Toggle disabled</button><output>Submissions: {count}</output></div>
    <ChatActivity state={state} label={{ thinking: 'Miragio is thinking…', tool: 'Checking the incident evidence…', approval: 'Waiting for your decision', error: 'Could not reach Mirage', done: 'Evidence is ready' }[state]} />
    <div className="preview-controls">{(['thinking', 'tool', 'approval', 'error', 'done'] as const).map(next => <button key={next} onClick={() => setState(next)}>{next}</button>)}</div>
    <ChatToolCard tool="mirage_get_incident" status={state === 'done' ? 'complete' : state === 'error' ? 'error' : 'running'} summary="Calendar invite · Q4 partner sync"><pre>{JSON.stringify({ incident_id: 'inc_007', status: 'frozen', source: 'calendar_invite', result: 'Synthetic evidence for component validation. ' + 'long-result-'.repeat(22) }, null, 2)}</pre></ChatToolCard>
    <ChatApprovalCard message="Unfreeze run_002 (support_agent) and resume it in production. The action it was stopped on goes through the gate again." pending={pending} onRespond={(action) => setDecision(JSON.stringify({ action }))} />
    <div className="preview-controls"><button onClick={() => setPending(!pending)}>Toggle pending</button></div>
    <output className="preview-decision">{decision}</output>
  </main>
}

createRoot(document.getElementById('root')!).render(<Preview />)

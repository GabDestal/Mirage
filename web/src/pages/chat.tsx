import { ArrowUp, ChartNoAxesColumn, Info, ListFilter, MessageSquarePlus, ShieldCheck } from 'lucide-react'
import { useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { api, queryClient, useIncidents, useRuns, type Incident, type Run } from '@/api/client'
import { fleetSentence, runLabel } from '@/lib/runs'
import './chat.css'

const suggestions = [
  { icon: ListFilter, text: 'Which agents need my attention?' },
  { icon: ShieldCheck, text: 'Show me the proof for the latest incident' },
  { icon: ChartNoAxesColumn, text: 'What is happening across my agents?' },
]

type Exchange = { question: string; runs: Run[]; incidents: Incident[]; at: string }

export function Chat() {
  const runs = useRuns()
  const incidents = useIncidents()
  const [draft, setDraft] = useState('')
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const input = useRef<HTMLTextAreaElement>(null)
  const thread = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  const submitting = useRef(false)
  const frozen = runs.data?.filter((run) => run.status === 'frozen').length ?? 0
  const conversation = exchanges.length > 0
  const loading = runs.isPending || incidents.isPending
  const unavailable = runs.isError || incidents.isError

  useLayoutEffect(() => {
    if (thread.current && follow.current) thread.current.scrollTop = thread.current.scrollHeight
  }, [exchanges, sending])

  async function send(text = draft) {
    const question = text.trim()
    if (!question || submitting.current) return
    submitting.current = true
    setSending(true)
    setError('')
    try {
      const [currentRuns, currentIncidents] = await Promise.all([
        queryClient.fetchQuery({ queryKey: ['runs'], queryFn: () => api<Run[]>('/runs'), staleTime: 0 }),
        queryClient.fetchQuery({ queryKey: ['incidents'], queryFn: () => api<Incident[]>('/incidents'), staleTime: 0 }),
      ])
      setExchanges((previous) => [...previous, { question, runs: currentRuns, incidents: currentIncidents, at: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }])
      setDraft('')
    } catch (cause) {
      setError(`Couldn't load the latest context. ${cause instanceof Error ? cause.message : 'Try sending again.'}`)
    } finally {
      submitting.current = false
      setSending(false)
      input.current?.focus()
    }
  }

  function prefill(text: string) {
    setDraft(text)
    setError('')
    input.current?.focus()
  }

  return (
    <section className={`chat-page${conversation ? ' chat-page--conversation' : ''}`} aria-label="Ask Mirage">
      {conversation ? (
        <>
          <div className="chat-thread-toolbar">
            <button type="button" onClick={() => { follow.current = true; setExchanges([]); setError(''); input.current?.focus() }} disabled={sending}>
              <MessageSquarePlus size={16} aria-hidden="true" /> New chat
            </button>
            <Link to="/fleet">View fleet</Link>
          </div>
          <div className="chat-thread" ref={thread} role="log" aria-label="Conversation" aria-live="polite" onScroll={(event) => {
            const el = event.currentTarget
            follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
          }}>
            <div className="chat-column">
              {exchanges.map((exchange, index) => (
                <div className="chat-exchange" key={index}>
                  <p className="chat-question">{exchange.question}</p>
                  <div className="chat-answer">
                    <img className="chat-answer-mark" src="/brand/mirage-mark.svg" width="36" height="24" alt="Mirage" />
                    <div><ContextAnswer exchange={exchange} /><p className="chat-answer-time">Fleet snapshot at {exchange.at}</p></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}

      <div className="chat-column chat-start">
        {!conversation ? (
          <div className="chat-welcome">
            <img className="chat-mark" src="/brand/mirage-mark.svg" width="96" height="58" alt="Mirage" />
            <h2>What needs your attention today?</h2>
          </div>
        ) : null}

        <div className={`chat-composer-group${!conversation ? ' chat-composer-group--context' : ''}`}>
          <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); void send() }} onMouseDown={(event) => {
            if ((event.target as HTMLElement).closest('button, textarea')) return
            event.preventDefault()
            input.current?.focus()
          }}>
            <textarea ref={input} rows={2} value={draft} readOnly={sending} aria-label="Message Mirage" aria-describedby={error ? 'chat-error' : 'chat-scope'}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229) return
                event.preventDefault()
                void send()
              }}
              placeholder={conversation ? 'Ask a follow-up…' : 'Ask which agents are frozen, and what happened…'} />
            <div className="chat-composer-actions">
              <button className="chat-send" type="submit" disabled={!draft.trim() || sending} aria-label={sending ? 'Loading fleet context' : 'Send message'}>
                <ArrowUp size={18} strokeWidth={2} aria-hidden="true" />
              </button>
            </div>
          </form>
          {!conversation ? (
            <div className="chat-context" aria-live="polite">
              <Info size={14} aria-hidden="true" />
              {loading ? <span>Checking your agents…</span> : unavailable ? (
                <span>Can't reach the Mirage engine. <button type="button" onClick={() => { void runs.refetch(); void incidents.refetch() }}>Try again</button></span>
              ) : frozen ? (
                <span>{frozen} {frozen === 1 ? 'agent needs' : 'agents need'} your attention. <button type="button" disabled={sending} onClick={() => void send(suggestions[0].text)}>Summarize incidents</button></span>
              ) : <span>{fleetSentence(runs.data ?? [])} <Link to="/fleet">View fleet</Link></span>}
            </div>
          ) : null}
        </div>
        {sending ? <p className="chat-feedback" role="status">Reading the latest fleet context…</p> : null}
        {error ? <p className="chat-error" id="chat-error" role="alert">{error} Your draft is saved.</p> : null}

        {!conversation ? (
          <div className="chat-suggestions">
            <p>Based on your agents</p>
            {suggestions.map(({ icon: Icon, text }) => (
              <button key={text} type="button" disabled={sending} onClick={() => prefill(text)}><Icon size={16} strokeWidth={1.5} aria-hidden="true" /><span>{text}</span></button>
            ))}
          </div>
        ) : null}
        <p className="chat-scope" id="chat-scope">Live fleet summaries. Open an incident to investigate or take action.</p>
      </div>
    </section>
  )
}

function ContextAnswer({ exchange }: { exchange: Exchange }) {
  const { question, runs, incidents } = exchange
  const attention = question === suggestions[0].text
  const proof = question === suggestions[1].text
  const shownRuns = attention ? runs.filter((run) => run.status === 'frozen') : runs
  const shownIncidents = proof ? [...incidents].sort((a, b) => b.opened_at.localeCompare(a.opened_at)).slice(0, 1) : incidents.filter((incident) => incident.status !== 'closed' && incident.status !== 'merged')

  // shortcut: read-only summaries of current API data; add natural-language answers when a chat endpoint is agreed.
  return (
    <>
      <p>{proof ? 'Here is the latest recorded incident and its evidence.' : attention ? 'Here are the runs that need attention.' : 'Here is the current fleet context. This chat currently provides run and incident summaries.'}</p>
      {!proof ? <>
        <p>{fleetSentence(runs)}</p>
        <ul className="chat-run-list">{shownRuns.map((run) => <li key={run.id}><Link to={`/runs/${run.id}`}>{runLabel(run, runs)}</Link><span>{run.status}</span><p>{run.task}</p></li>)}</ul>
        <Link to="/fleet">Open fleet overview</Link>
      </> : null}
      {proof && !shownIncidents.length ? <p>No incidents have been recorded yet.</p> : null}
      {shownIncidents.map((incident) => (
        <div className="chat-incident" key={incident.id}>
          <Link to={`/incidents/${incident.id}`}>{incident.id} · {incident.status.replaceAll('_', ' ')}</Link>
          <p>{incident.trigger.explanation}</p>
          <p>{incident.verdict ? `${incident.verdict.confirmed ? 'Compromise confirmed' : 'No compromise confirmed'} in replay. ${incident.verdict.compromised_runs} runs compromised.` : 'Replay evidence is not available yet. Open the incident to investigate.'}</p>
          {incident.verdict ? <p>{incident.verdict.blast_radius.summary}</p> : null}
        </div>
      ))}
    </>
  )
}

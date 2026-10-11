import { ArrowDown, ArrowRight, Check, Copy, Info, ListFilter, MessageSquarePlus, ShieldCheck, ChartNoAxesColumn, Unplug } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Fragment, memo, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { useEvents, useIncidents, useRuns } from '@/api/client'
import { sanitize, useChat, type ChatPart, type ChatTurn, type ToolResult } from '@/api/chat'
import { ChatActivity, ChatApprovalCard, ChatComposer, ChatToolCard } from '@/components/chat-primitives'
import { HandoffDrawer } from '@/components/handoff-drawer'
import { RepairProgress } from '@/components/repair-progress'
import { EngineProof } from '@/components/engine-proof'
import { Miragio } from '@/components/miragio'
import { Button } from '@/components/ui/button'
import { agentCount } from './fleet-presentation'
import './chat.css'

const suggestions = [
  { icon: ListFilter, text: 'Which agents need my attention?' },
  { icon: ShieldCheck, text: 'Show me the proof for the latest incident' },
  { icon: ChartNoAxesColumn, text: 'What is happening across my agents?' },
]
const ease = [0.23, 1, 0.32, 1] as const

export function Chat() {
  const chat = useChat()
  const stopChat = chat.stop
  const runs = useRuns()
  const incidentQuery = useIncidents()
  const incidents = incidentQuery.data ?? []
  const events = useEvents().data ?? []
  const activity = incidents.some((i) => i.status === 'detonating') ? 'Detonating in Mirage…' : incidents.some((i) => i.status === 'bisecting') ? 'Identifying root cause…' : null
  const [draft, setDraft] = useState('')
  const [composerFocused, setComposerFocused] = useState(false)
  const [online, setOnline] = useState(navigator.onLine)
  const [behind, setBehind] = useState(false)
  const thread = useRef<HTMLDivElement>(null)
  const composer = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  const submission = useRef(0)
  const reduce = useReducedMotion()
  const conversation = chat.turns.length > 0
  const frozen = runs.data?.filter((run) => run.status === 'frozen').length ?? 0
  const agents = agentCount(runs.data ?? [])
  const latest = chat.turns.at(-1)
  const lastError = latest?.status === 'error' ? latest.error : undefined

  useEffect(() => {
    const sync = () => { setOnline(navigator.onLine); if (!navigator.onLine) stopChat() }
    window.addEventListener('online', sync)
    window.addEventListener('offline', sync)
    return () => { window.removeEventListener('online', sync); window.removeEventListener('offline', sync) }
  }, [stopChat])

  function jump() {
    follow.current = true
    setBehind(false)
    if (thread.current) thread.current.scrollTop = thread.current.scrollHeight
  }
  useLayoutEffect(() => {
    if (!thread.current) return
    if (follow.current) thread.current.scrollTop = thread.current.scrollHeight
    else setBehind(thread.current.scrollHeight - thread.current.scrollTop - thread.current.clientHeight > 80)
  }, [chat.turns, chat.busy])
  useEffect(() => {
    const el = thread.current
    if (!el) return
    const observer = new ResizeObserver(() => {
      if (follow.current) el.scrollTop = el.scrollHeight
    })
    observer.observe(el)
    if (el.firstElementChild) observer.observe(el.firstElementChild)
    return () => observer.disconnect()
  }, [conversation])

  function focusComposer() { composer.current?.querySelector('textarea')?.focus() }
  function prefill(text: string) { setDraft(text); focusComposer(); void send(text) }
  async function send(text = draft) {
    if (!text.trim() || chat.busy || !online) return
    const message = text.trim()
    const attempt = ++submission.current
    setDraft('')
    follow.current = true
    setBehind(false)
    const success = await chat.send(message)
    if (submission.current !== attempt) return
    if (!success) setDraft((current) => current || message)
    focusComposer()
  }
  function newChat() {
    submission.current++
    chat.reset()
    follow.current = true
    setBehind(false)
    focusComposer()
  }
  function stopReply() { submission.current++; chat.stop(); focusComposer() }

  return (
    <section className={`chat-page${conversation ? ' chat-page--conversation' : ''}`} aria-label="Ask Miragio">
      {conversation ? <div className="chat-thread-toolbar">
        <button type="button" onClick={newChat}><MessageSquarePlus size={16} aria-hidden="true" />New chat</button>
        <Link to="/fleet">View fleet</Link>
      </div> : null}
      {incidents.length > 0 || incidentQuery.isError ? <section className="chat-column mb-4 max-h-[35vh] shrink-0 overflow-auto" aria-label="Persistent engine evidence">
        <h2 className="text-body font-medium">Engine evidence</h2>
        {incidentQuery.isError ? <p className="text-ink-2" role="status">Engine evidence could not refresh. <button type="button" className="underline" onClick={() => void incidentQuery.refetch()}>Retry</button></p> : null}
        {incidents.map((incident) => <EngineProof key={incident.id} incident={incident} events={events} />)}
      </section> : null}
      {conversation ? <div className="chat-thread" ref={thread} aria-label="Conversation" tabIndex={0} onScroll={(event) => {
        const el = event.currentTarget
        follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
        setBehind(!follow.current)
      }}>
        <div className="chat-column chat-transcript">
          {chat.turns.map((turn) => <TranscriptTurn key={turn.id} turn={turn} onRespond={chat.respond} />)}
          {chat.busy && latest ? <Activity turn={latest} /> : null}
          <div className="chat-scroll-anchor" />
        </div>
      </div> : null}

      <div className="chat-column chat-start" ref={composer}>
          {!conversation ? <div className="chat-welcome">
            <Miragio className="chat-miragio" animate readingProgress={composerFocused ? Math.min(draft.length / 200, 1) : null} />
            <h2>What needs your attention today?</h2>
          </div> : null}
        <AnimatePresence>
          {behind ? <motion.button className="chat-jump" type="button" onClick={jump} initial={{ opacity: 0, y: reduce ? 0 : 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reduce ? 0 : 0.16, ease }}>
            <ArrowDown size={14} aria-hidden="true" /> Jump to latest
          </motion.button> : null}
        </AnimatePresence>
        {activity ? <p className="chat-activity-status" role="status">{activity}</p> : null}
        <div className={`chat-composer-group${!conversation ? ' chat-composer-group--context' : ''}`}
          onFocusCapture={(event) => { if (event.target instanceof HTMLTextAreaElement) setComposerFocused(true) }}
          onBlurCapture={(event) => { if (event.target instanceof HTMLTextAreaElement) setComposerFocused(false) }}>
          <ChatComposer value={draft} onChange={setDraft} onSubmit={() => void send()} busy={chat.busy} disabled={!online}
            onStop={stopReply} placeholder={conversation ? 'Ask a follow-up…' : 'Ask which agents are frozen, and what happened…'} error={lastError ? 'Your draft is saved. Review any actions before sending again.' : undefined} />
          {!conversation ? <div className="chat-context">
            <Info size={14} aria-hidden="true" />
            {runs.isPending ? <span>Checking your agents…</span> : runs.isError ? <span>Can’t reach the Mirage engine. <button type="button" onClick={() => void runs.refetch()}>Try again</button></span> : frozen ? <span>{frozen} {frozen === 1 ? 'agent needs' : 'agents need'} your attention. <button type="button" onClick={() => prefill(suggestions[0].text)}>Summarize incidents</button></span> : <span>{agents ? `${agents} ${agents === 1 ? 'agent' : 'agents'} in your fleet.` : 'No agents connected yet.'} <Link to="/fleet">View fleet</Link></span>}
          </div> : null}
        </div>
        {!online ? <p className="chat-offline" role="alert"><Unplug size={15} aria-hidden="true" />You’re offline. Your conversation and draft stay here; reconnect to continue.</p> : null}
        {!conversation ? <div className="chat-suggestions">
          <p>Based on your agents</p>
          {suggestions.map(({ icon: Icon, text }) => <button key={text} type="button" onClick={() => prefill(text)}><Icon size={16} strokeWidth={1.5} aria-hidden="true" /><span>{text}</span></button>)}
        </div> : null}
        <p className="chat-scope">{chat.busy ? 'Stop reply ends this reply only. Actions already started may continue.' : 'Investigate with evidence. Production actions need your approval.'}</p>
      </div>
    </section>
  )
}

// Users see what Miragio is doing, never the raw MCP tool name.
const toolLabels: Record<string, string> = {
  list_runs: 'Checking your agents', get_incident: 'Reading the incident', get_audit: 'Reading the audit log', detonate: 'Detonating in Mirage',
  find_cause: 'Finding the cause', unfreeze: 'Unfreezing the agent', kill: 'Stopping the agent', resume: 'Resuming the agent', resume_all: 'Resuming all agents', send_fix: 'Handing off to your coding agent', start_repair: 'Repairing and proving the fix', get_repair: 'Checking repair progress',
}
const toolLabel = (tool: string) => toolLabels[tool] ?? tool.replaceAll('_', ' ').replace(/^./, (first) => first.toUpperCase())

function Activity({ turn }: { turn: ChatTurn }) {
  const approval = turn.parts.some((part) => part.kind === 'approval' && ['waiting', 'sending'].includes(part.status))
  const tool = turn.parts.findLast((part) => part.kind === 'tool' && part.status === 'running')
  return <ChatActivity state={approval ? 'approval' : tool ? 'tool' : 'thinking'} label={approval ? 'Waiting for your decision' : tool?.kind === 'tool' ? toolLabel(tool.tool) : turn.parts.at(-1)?.kind === 'text' ? 'Responding' : 'Waiting for Miragio’s reply'} />
}

// One shared element: React skips the static SVG portrait when a streamed delta re-renders its turn.
const answerMiragio = <Miragio className="chat-answer-miragio" />

const TranscriptTurn = memo(function TranscriptTurn({ turn, onRespond }: { turn: ChatTurn; onRespond: (id: string, action: 'accept' | 'decline', content?: Record<string, unknown>) => Promise<void> }) {
  const response = turn.parts.filter((part) => part.kind === 'text').map((part) => part.text).join('\n\n')
  return <article className="chat-turn" aria-label="Conversation turn">
    {turn.auto ? <h3 className="sr-only">{turn.question}</h3> : <div className="chat-question"><span className="sr-only">You: </span>{turn.question}</div>}
    <div className="chat-answer">
      {answerMiragio}
      <div className="chat-answer-content">
        {turn.parts.map((part, index) => {
          if (part.kind === 'text') return <FormattedText key={index} text={String(sanitize(part.text))} />
          if (part.kind === 'tool') return <Tool key={part.id} part={part} waiting={turn.parts.some((other) => other.kind === 'approval' && other.callId === part.id && ['waiting', 'sending'].includes(other.status))} />
          return <div key={part.id} className="chat-approval">
            {['waiting', 'sending'].includes(part.status) ? <>
              <ChatApprovalCard message={part.message} pending={part.status === 'sending'} onRespond={(action) => void onRespond(part.id, action)} />
              {part.error ? <p className="chat-error" role="alert">{part.error}</p> : null}
            </> : <ChatActivity state={part.status === 'cancelled' ? 'error' : 'done'} label={part.status === 'accepted' ? 'You approved this action' : part.status === 'declined' ? 'You declined this action' : part.error ? 'Decision not confirmed; check the incident before trying again' : 'Approval cancelled when the connection ended'} />}
          </div>
        })}
        {turn.status === 'error' ? <p className="chat-error" role="alert">{turn.error}</p> : null}
        {turn.status === 'stopped' ? <p className="chat-stopped" role="status">Reply stopped. Actions already started may still be running; check the incident before trying again.</p> : null}
        {turn.status === 'done' && !turn.parts.length ? <p className="chat-stopped">Miragio finished without a reply. Ask a follow-up or start a new conversation.</p> : null}
        {response && turn.status !== 'running' ? <CopyButton text={String(sanitize(response))} label="Copy response" /> : null}
      </div>
    </div>
  </article>
})

function resultText(result: ToolResult) {
  const safe = sanitize(result) as ToolResult
  const texts = safe.content.filter((item) => item.type === 'text' && typeof item.text === 'string').map((item) => item.text as string)
  return safe.structuredContent ? JSON.stringify(safe.structuredContent, null, 2) : texts.length ? texts.join('\n\n') : JSON.stringify(safe.content, null, 2)
}

function Tool({ part, waiting }: { part: Extract<ChatPart, { kind: 'tool' }>; waiting: boolean }) {
  const evidence = part.result ? resultText(part.result) : ''
  const handoffUrl = part.tool === 'send_fix' ? part.result?.structuredContent?.handoff_url : undefined
  const safeHandoff = typeof handoffUrl === 'string' && /^\/chat\/handoffs\/[A-Za-z0-9_-]+$/.test(handoffUrl) ? handoffUrl : undefined
  const repair = part.result?.structuredContent?.repair_job as { id?: unknown; incident_id?: unknown } | undefined
  return <><ChatToolCard tool={toolLabel(part.tool)} status={waiting ? 'waiting' : part.status} summary={waiting ? 'Approve or decline below' : part.progress || (part.status === 'running' ? 'Request sent to Mirage' : part.status === 'error' ? 'Check the result before trying again' : 'Result received')}>
    <div className="chat-tool-evidence">
      <h4>Request</h4><pre>{JSON.stringify(sanitize(part.args), null, 2)}</pre>
      {evidence ? <><h4>Result</h4><pre>{evidence}</pre><CopyButton text={evidence} label="Copy visible result" /></> : null}
    </div>
  </ChatToolCard>
  {repair && typeof repair.id === 'string' && typeof repair.incident_id === 'string' ? <RepairProgress incidentId={repair.incident_id} jobId={repair.id} /> : null}
  {safeHandoff ? <HandoffActions url={safeHandoff} /> : null}</>
}

function HandoffActions({ url }: { url: string }) {
  const [open, setOpen] = useState(false)
  const [prompt, setPrompt] = useState<string>()
  const [error, setError] = useState<string>()
  async function show() {
    setOpen(true)
    if (prompt) return
    setError(undefined)
    try {
      const response = await fetch(url, { headers: { Accept: 'text/plain' }, cache: 'no-store', redirect: 'error' })
      if (!response.ok) throw new Error(`Prompt unavailable (${response.status}). Close and try again.`)
      if (!response.headers.get('content-type')?.includes('text/plain')) throw new Error('The chat service did not return a handoff prompt.')
      setPrompt(await response.text())
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Couldn’t load the prompt. Close and try again.') }
  }
  return <div className="chat-handoff">
    <Button onClick={() => void show()}>Hand off to coding agent<ArrowRight /></Button>
    <HandoffDrawer open={open} onClose={() => setOpen(false)} prompt={prompt} error={error} />
  </div>
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'error'>('idle')
  useEffect(() => {
    if (state === 'idle') return
    const timer = window.setTimeout(() => setState('idle'), 2200)
    return () => window.clearTimeout(timer)
  }, [state])
  return <button type="button" className="chat-copy" aria-label={label} onClick={() => {
    if (!navigator.clipboard) { setState('error'); return }
    void navigator.clipboard.writeText(text).then(() => setState('copied'), () => setState('error'))
  }}>{state === 'copied' ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}<span role="status">{state === 'copied' ? 'Copied' : state === 'error' ? 'Copy failed. Try again.' : label}</span></button>
}

// shortcut: safe paragraphs, lists, tables and fenced code; use a Markdown library if richer formatting becomes a requirement.
function FormattedText({ text }: { text: string }) {
  const reduce = useReducedMotion()
  const blocks: ReactNode[] = []
  const lines = text.split('\n')
  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) { index++; continue }
    if (line.startsWith('```')) {
      const start = index++
      const code: string[] = []
      while (index < lines.length && !lines[index].startsWith('```')) code.push(lines[index++])
      if (index < lines.length) index++
      blocks.push(<pre key={start}><code>{code.join('\n')}</code></pre>)
      continue
    }
    if (isTableStart(lines, index)) {
      const start = index
      const head = cells(lines[index])
      const align = cells(lines[index + 1]).map((cell): 'left' | 'center' | 'right' => cell.endsWith(':') ? (cell.startsWith(':') ? 'center' : 'right') : 'left')
      index += 2
      const rows: string[][] = []
      while (index < lines.length && lines[index].trim().startsWith('|')) rows.push(cells(lines[index++]))
      blocks.push(<div key={start} className="chat-table-wrapper"><table className="chat-table">
        <thead><tr>{head.map((cell, col) => <th key={col} scope="col" style={{ textAlign: align[col] }}>{inline(cell)}</th>)}</tr></thead>
        <tbody>{rows.map((row, r) => <tr key={r}>{head.map((_, col) => <td key={col} style={{ textAlign: align[col] }}>{inline(row[col] ?? '')}</td>)}</tr>)}</tbody>
      </table></div>)
      continue
    }
    const list = /^(?:[-*]|\d+\.)\s+/.exec(line)
    if (list) {
      const start = index
      const ordered = /^\d/.test(line)
      const items: ReactNode[] = []
      while (index < lines.length && (ordered ? /^\d+\.\s+/ : /^[-*]\s+/).test(lines[index])) {
        items.push(<li key={index}>{inline(lines[index++].replace(/^(?:[-*]|\d+\.)\s+/, ''))}</li>)
      }
      blocks.push(ordered ? <ol key={start}>{items}</ol> : <ul key={start}>{items}</ul>)
      continue
    }
    const start = index++
    const paragraph = [line.replace(/^#{1,6}\s+/, '')]
    while (index < lines.length && lines[index].trim() && !/^(?:```|[-*]\s|\d+\.\s|#{1,6}\s)/.test(lines[index]) && !isTableStart(lines, index)) paragraph.push(lines[index++])
    blocks.push(<p key={start}>{inline(paragraph.join('\n'))}</p>)
  }
  return <motion.div className="chat-prose" initial={reduce ? false : { opacity: 0.7, filter: 'blur(1px)' }} animate={{ opacity: 1, filter: 'blur(0px)' }} transition={{ duration: reduce ? 0 : 0.18, ease }}>{blocks}</motion.div>
}
function isTableStart(lines: string[], index: number) {
  return lines[index].trim().startsWith('|') && /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(lines[index + 1] ?? '')
}
// shortcut: escaped pipes (\|) split cells; handle them if the engine ever emits them.
function cells(line: string) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
}
function inline(text: string) {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((chunk, index) => chunk.startsWith('`') ? <code key={index}>{chunk.slice(1, -1)}</code> : chunk.startsWith('**') ? <strong key={index}>{chunk.slice(2, -2)}</strong> : <Fragment key={index}>{chunk}</Fragment>)
}

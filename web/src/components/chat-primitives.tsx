import { ThinkingOrb } from 'thinking-orbs'
import { AnimatePresence, motion, useReducedMotion, useAnimationControls } from 'motion/react'
import { ArrowUp, Check, ChevronDown, Circle, CircleAlert, ShieldCheck, Square, Wrench } from 'lucide-react'
import { useEffect, useId, useImperativeHandle, useLayoutEffect, useRef, useState, type ReactNode, type Ref } from 'react'
import './chat-primitives.css'

export type ChatComposerProps = {
  value: string
  onChange(value: string): void
  onSubmit(): void
  disabled?: boolean
  busy?: boolean
  onStop?(): void
  placeholder?: string
  error?: string
  inputRef?: Ref<HTMLTextAreaElement>
}
export type ChatActivityState = 'thinking' | 'tool' | 'approval' | 'error' | 'done'
export type ChatActivityProps = { label: string; state: ChatActivityState }
export type ChatToolCardProps = { tool: string; status: 'running' | 'waiting' | 'complete' | 'error'; summary?: string; children?: ReactNode }
export type ChatApprovalCardProps = { message: string; pending?: boolean; onRespond(action: 'accept' | 'decline'): void }

// One-shot motion follows Transitions.dev's text swap, panel reveal and icon swap.
const quick = { duration: 0.15, ease: [0.22, 1, 0.36, 1] as const }
const panel = { duration: 0.22, ease: quick.ease }
const reveal = { opacity: 0, y: 4, filter: 'blur(2px)' }
const settled = { opacity: 1, y: 0, filter: 'blur(0px)' }

function useMotionGate() {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const [visible, setVisible] = useState(false)
  const [pageVisible, setPageVisible] = useState(false)
  useEffect(() => {
    const update = () => setPageVisible(document.visibilityState === 'visible')
    update()
    document.addEventListener('visibilitychange', update)
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting))
    if (ref.current) observer.observe(ref.current)
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', update) }
  }, [])
  return [ref, reduced === false && visible && pageVisible] as const
}

export function ChatComposer({ value, onChange, onSubmit, disabled = false, busy = false, onStop, placeholder = 'Ask Miragio…', error, inputRef }: ChatComposerProps) {
  const input = useRef<HTMLTextAreaElement>(null)
  const composing = useRef(false)
  const [visibilityRef, animate] = useMotionGate()
  const id = useId()
  const canSend = !disabled && !busy && !!value.trim()
  useImperativeHandle(inputRef, () => input.current!, [])
  useLayoutEffect(() => {
    const element = input.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`
  }, [value])
  return <div className="mirage-composer-group" ref={visibilityRef}>
    <form className="mirage-composer" aria-label="Message Mirage" aria-busy={busy} onSubmit={event => { event.preventDefault(); if (canSend && !composing.current) onSubmit() }}
      onMouseDown={event => { if (!(event.target as HTMLElement).closest('button, textarea')) { event.preventDefault(); input.current?.focus() } }}>
      <textarea ref={input}
        value={value} onChange={event => onChange(event.target.value)} rows={2} disabled={disabled} readOnly={busy}
        aria-label="Message Miragio" aria-invalid={!!error} aria-describedby={error ? `${id}-error` : undefined} placeholder={placeholder}
        onCompositionStart={() => { composing.current = true }} onCompositionEnd={() => { composing.current = false }}
        onKeyDown={event => { if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229 || composing.current) return; event.preventDefault(); if (canSend) onSubmit() }} />
      <div className="mirage-composer-actions">
        <div className="mirage-send-slot">
          <button className="mirage-send" type={busy ? 'button' : 'submit'} disabled={busy ? disabled || !onStop : !canSend} aria-label={busy ? onStop ? 'Stop response' : 'Waiting for Miragio' : 'Send message'} onClick={busy && onStop ? onStop : undefined}>
            <span className="mirage-icon-slot" aria-hidden="true"><AnimatePresence initial={false} mode="popLayout"><motion.span key={busy ? 'stop' : 'send'} initial={animate ? { opacity: 0, scale: 0.8, filter: 'blur(2px)' } : false} animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }} exit={{ opacity: 0, scale: 0.8 }} transition={animate ? quick : { duration: 0 }}>{busy ? <Square size={14} fill="currentColor" /> : <ArrowUp size={18} />}</motion.span></AnimatePresence></span>
          </button>
        </div>
      </div>
    </form>
    {error ? <p className="mirage-chat-error" id={`${id}-error`} role="alert">{error}</p> : null}
  </div>
}

export function ChatActivity({ label, state }: ChatActivityProps) {
  const [visibilityRef, animate] = useMotionGate()
  const Icon = state === 'done' ? Check : state === 'error' ? CircleAlert : state === 'approval' ? ShieldCheck : state === 'tool' ? Wrench : Circle
  return <div className="mirage-activity" data-state={state} ref={visibilityRef} role="status" aria-live="polite" aria-atomic="true">
    <span className="mirage-activity-icon" aria-hidden="true">{animate && (state === 'thinking' || state === 'tool') ? <ThinkingOrb size={20} state="breathing" theme="light" speed={0.7} /> : <Icon size={17} />}</span>
    <AnimatePresence initial={false} mode="popLayout"><motion.span key={`${state}:${label}`} initial={animate ? reveal : false} animate={settled} exit={animate ? { opacity: 0, y: -4, filter: 'blur(2px)' } : { opacity: 0 }} transition={animate ? quick : { duration: 0 }}>{label}</motion.span></AnimatePresence>
  </div>
}

export function ChatToolCard({ tool, status, summary, children }: ChatToolCardProps) {
  const [visibilityRef, animate] = useMotionGate()
  const [open, setOpen] = useState(false)
  const Icon = status === 'complete' ? Check : status === 'error' ? CircleAlert : Wrench
  const header = <><span className="mirage-tool-icon" aria-hidden="true"><AnimatePresence initial={false} mode="popLayout"><motion.span key={status} initial={animate ? { opacity: 0, scale: 0.8 } : false} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }} transition={animate ? quick : { duration: 0 }}><Icon size={16} /></motion.span></AnimatePresence></span><span className="mirage-tool-name">{tool}</span><span className="mirage-tool-status">{status === 'running' ? 'Running' : status === 'waiting' ? 'Waiting for you' : status === 'complete' ? 'Complete' : 'Error'}</span></>
  return <div className="mirage-tool-card" ref={visibilityRef} data-status={status}>
    {children !== undefined ? <details onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="mirage-tool-header">{header}<ChevronDown className="mirage-tool-chevron" size={15} aria-hidden="true" /></summary>
      {summary ? <p className="mirage-tool-summary">{summary}</p> : null}
      <motion.div className="mirage-tool-content" initial={false} animate={open && animate ? settled : { opacity: 1, y: 0, filter: 'blur(0px)' }} key={open ? 'open' : 'closed'} transition={animate ? panel : { duration: 0 }}>{open ? <motion.div initial={animate ? reveal : false} animate={settled} transition={animate ? panel : { duration: 0 }}>{children}</motion.div> : null}</motion.div>
    </details> : <><div className="mirage-tool-header">{header}</div>{summary ? <p className="mirage-tool-summary">{summary}</p> : null}</>}
  </div>
}

export function ChatApprovalCard({ message, pending = false, onRespond }: ChatApprovalCardProps) {
  // The click is the confirmation; the chat service answers the MCP form with the tool's own phrase and reason.
  const [visibilityRef, animate] = useMotionGate()
  const entrance = useAnimationControls()
  const revealed = useRef(false)
  useEffect(() => {
    if (!animate) { entrance.stop(); entrance.set(settled); return }
    if (!revealed.current) { revealed.current = true; entrance.set(reveal); void entrance.start(settled, panel) }
  }, [animate, entrance])
  return <div ref={visibilityRef} className="mirage-approval-card">
    <motion.form initial={false} animate={entrance} transition={animate ? panel : { duration: 0 }} aria-label="Mirage approval" aria-busy={pending} onSubmit={event => { event.preventDefault(); if (!pending) onRespond('accept') }}>
      <div className="mirage-approval-heading"><ShieldCheck size={17} aria-hidden="true" /><h3>Your approval is needed</h3></div>
      <p className="mirage-approval-message">{message}</p>
      <div className="mirage-approval-actions"><button type="button" disabled={pending} onClick={() => { if (!pending) onRespond('decline') }}>Decline</button><button className="mirage-approve" type="submit" disabled={pending}>{pending ? 'Sending decision…' : 'Approve'}</button></div>
    </motion.form>
  </div>
}

import { ThinkingOrb } from 'thinking-orbs'
import { AnimatePresence, motion, useReducedMotion, useAnimationControls } from 'motion/react'
import { ArrowUp, Check, ChevronDown, Circle, CircleAlert, ShieldCheck, Square, Wrench } from 'lucide-react'
import { useEffect, useId, useImperativeHandle, useLayoutEffect, useRef, useState, type ReactNode, type Ref } from 'react'
import { approvalDefaults, readApprovalSchema, validateApproval, type ApprovalScalar } from './chat/approval-schema'
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
export type ChatToolCardProps = { tool: string; status: 'running' | 'complete' | 'error'; summary?: string; children?: ReactNode }
export type ChatApprovalCardProps = { message: string; schema: Record<string, unknown>; pending?: boolean; onRespond(action: 'accept' | 'decline', content?: Record<string, unknown>): void }

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
  const header = <><span className="mirage-tool-icon" aria-hidden="true"><AnimatePresence initial={false} mode="popLayout"><motion.span key={status} initial={animate ? { opacity: 0, scale: 0.8 } : false} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }} transition={animate ? quick : { duration: 0 }}><Icon size={16} /></motion.span></AnimatePresence></span><span className="mirage-tool-name">{tool}</span><span className="mirage-tool-status">{status === 'running' ? 'Running' : status === 'complete' ? 'Complete' : 'Error'}</span></>
  return <div className="mirage-tool-card" ref={visibilityRef} data-status={status}>
    {children !== undefined ? <details onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="mirage-tool-header">{header}<ChevronDown className="mirage-tool-chevron" size={15} aria-hidden="true" /></summary>
      {summary ? <p className="mirage-tool-summary">{summary}</p> : null}
      <motion.div className="mirage-tool-content" initial={false} animate={open && animate ? settled : { opacity: 1, y: 0, filter: 'blur(0px)' }} key={open ? 'open' : 'closed'} transition={animate ? panel : { duration: 0 }}>{open ? <motion.div initial={animate ? reveal : false} animate={settled} transition={animate ? panel : { duration: 0 }}>{children}</motion.div> : null}</motion.div>
    </details> : <><div className="mirage-tool-header">{header}</div>{summary ? <p className="mirage-tool-summary">{summary}</p> : null}</>}
  </div>
}

export function ChatApprovalCard(props: ChatApprovalCardProps) {
  // A new request remounts only its form; composer focus and selection are unaffected.
  return <ApprovalForm key={JSON.stringify([props.message, props.schema])} {...props} />
}

function ApprovalForm({ message, schema, pending = false, onRespond }: ChatApprovalCardProps) {
  const { fields, error: unsupported } = readApprovalSchema(schema)
  const [values, setValues] = useState<Record<string, ApprovalScalar>>(() => approvalDefaults(fields))
  const [error, setError] = useState<string>()
  const [visibilityRef, animate] = useMotionGate()
  const id = useId()
  const entrance = useAnimationControls()
  const revealed = useRef(false)
  useEffect(() => {
    if (!animate) { entrance.stop(); entrance.set(settled); return }
    if (!revealed.current) { revealed.current = true; entrance.set(reveal); void entrance.start(settled, panel) }
  }, [animate, entrance])
  const update = (name: string, value: ApprovalScalar | undefined) => { setError(undefined); setValues(previous => { const next = { ...previous }; if (value === undefined) delete next[name]; else return { ...next, [name]: value }; return next }) }
  return <div ref={visibilityRef} className="mirage-approval-card">
    <motion.form initial={false} animate={entrance} transition={animate ? panel : { duration: 0 }} aria-label="Mirage approval" aria-busy={pending} onSubmit={event => {
      event.preventDefault()
      if (pending || unsupported || !event.currentTarget.reportValidity()) return
      const invalid = validateApproval(fields, values)
      if (invalid) { setError(invalid); return }
      onRespond('accept', values)
    }}>
      <div className="mirage-approval-heading"><ShieldCheck size={17} aria-hidden="true" /><h3>Your approval is needed</h3></div>
      <p className="mirage-approval-message">{message}</p>
      {unsupported ? <p className="mirage-chat-error" role="alert">{unsupported}</p> : <fieldset disabled={pending} className="mirage-approval-fields">{fields.map(field => <div className="mirage-approval-field" key={field.name}>
        <label htmlFor={`${id}-${field.name}`}>{field.title}{field.required ? <span className="mirage-required"> (required)</span> : null}</label>
        {field.description ? <p id={`${id}-${field.name}-help`}>{field.description}</p> : null}
        {field.enum ? <select id={`${id}-${field.name}`} value={values[field.name] === undefined ? '' : String(field.enum.indexOf(values[field.name]))} required={field.required} onChange={event => update(field.name, event.target.value === '' ? undefined : field.enum![Number(event.target.value)])} aria-describedby={field.description ? `${id}-${field.name}-help` : undefined}><option value="">Choose a value</option>{field.enum.map((value, index) => <option key={index} value={index}>{String(value)}</option>)}</select>
          : field.type === 'boolean' ? <select id={`${id}-${field.name}`} required={field.required} value={values[field.name] === undefined ? '' : String(values[field.name])} onChange={event => update(field.name, event.target.value === '' ? undefined : event.target.value === 'true')}><option value="">Choose a value</option><option value="true">Yes</option><option value="false">No</option></select>
          : <input id={`${id}-${field.name}`} type={field.type === 'string' ? field.format === 'email' ? 'email' : field.format === 'uri' ? 'url' : 'text' : 'number'}
            value={String(values[field.name] ?? '')} required={field.required} minLength={field.minLength} maxLength={field.maxLength} min={field.minimum} max={field.maximum} step={field.type === 'integer' ? 1 : 'any'}
            autoComplete="off" spellCheck={!field.phrase} aria-describedby={field.description ? `${id}-${field.name}-help` : undefined}
            onChange={event => update(field.name, field.type === 'string' ? event.target.value : event.target.value === '' ? undefined : event.target.valueAsNumber)} />}
      </div>)}</fieldset>}
      {error ? <p className="mirage-chat-error" role="alert">{error}</p> : null}
      <div className="mirage-approval-actions"><button type="button" disabled={pending} onClick={() => { if (!pending) onRespond('decline') }}>Decline</button><button className="mirage-approve" type="submit" disabled={pending || !!unsupported}>{pending ? 'Sending decision…' : 'Approve'}</button></div>
    </motion.form>
  </div>
}

import { useCallback, useEffect, useRef, useState } from 'react'

export type ToolResult = { content: Record<string, unknown>[]; structuredContent?: Record<string, unknown>; isError?: boolean }
export type ChatEvent =
  | { type: 'session'; session_id: string }
  | { type: 'text_delta'; text: string }
  | { type: 'tool_start'; call_id: string; tool: string; args: Record<string, unknown> }
  | { type: 'tool_progress'; call_id: string; message: string }
  | { type: 'tool_result'; call_id: string; tool: string; result: ToolResult }
  | { type: 'approval_required'; approval_id: string; call_id: string; message: string; schema: Record<string, unknown> }
  | { type: 'follow_up'; title: string }
  | { type: 'done' }
  | { type: 'error'; code: string; message: string }

const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
export function parseChatEvent(data: string): ChatEvent {
  const value: unknown = JSON.parse(data)
  if (!object(value)) throw new Error('Invalid chat event. Start a new conversation and try again.')
  const fields: Record<string, string[]> = {
    session: ['session_id'], text_delta: ['text'], tool_start: ['call_id', 'tool'],
    tool_progress: ['call_id', 'message'], tool_result: ['call_id', 'tool'],
    approval_required: ['approval_id', 'call_id', 'message'], follow_up: ['title'], done: [], error: ['code', 'message'],
  }
  const type = value.type
  if (typeof type !== 'string' || !Object.hasOwn(fields, type) || fields[type].some((key) => typeof value[key] !== 'string')
    || (type === 'tool_start' && !object(value.args))
    || (type === 'approval_required' && !object(value.schema))
    || (type === 'tool_result' && (!object(value.result) || !Array.isArray(value.result.content) || !value.result.content.every(object)
      || (value.result.structuredContent !== undefined && !object(value.result.structuredContent))
      || (value.result.isError !== undefined && typeof value.result.isError !== 'boolean')))) {
    throw new Error('Invalid chat event. Start a new conversation and try again.')
  }
  return value as ChatEvent
}

// Fetch is required: EventSource cannot POST the turn or abort its model continuation.
export async function streamTurn(body: { session_id?: string; message: string; actor: string }, signal: AbortSignal, onEvent: (event: ChatEvent) => void) {
  const response = await fetch('/chat/turn', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' }, body: JSON.stringify(body), signal,
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(object(detail) && typeof detail.message === 'string' ? detail.message : `Chat unavailable (${response.status}). Check the operator chat service and try again.`)
  }
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('The chat service did not return a stream. Check the operator chat service.')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false
  const dispatch = (frame: string) => {
    const data = frame.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).replace(/^ /, '')).join('\n')
    if (!data) return
    const event = parseChatEvent(data)
    onEvent(event)
    if (event.type === 'error') throw new Error(event.message)
    if (event.type === 'done') finished = true
  }
  try {
    while (!finished) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      // Normalize after buffering so CRLF split across network chunks stays intact.
      buffer = buffer.replace(/\r\n/g, '\n')
      let end: number
      while ((end = buffer.indexOf('\n\n')) >= 0 && !finished) {
        const frame = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        dispatch(frame)
      }
      if (buffer.length > 1_000_000) throw new Error('Chat event is too large. Start a new conversation.')
      if (done) {
        if (buffer.trim() && !finished) dispatch(buffer)
        if (!finished) throw new Error('The connection ended before the reply finished. Your partial reply is saved; check actions before sending again.')
        break
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}

export async function submitApproval(id: string, action: 'accept' | 'decline', content?: Record<string, unknown>, signal?: AbortSignal) {
  const response = await fetch(`/chat/approvals/${encodeURIComponent(id)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, ...(content ? { content } : {}) }), signal,
  })
  if (!response.ok) throw new Error(`Couldn't submit your decision (${response.status}). Check the connection and try again.`)
  const result: unknown = await response.json()
  if (!object(result) || result.accepted !== true) throw new Error('The chat service did not confirm your decision. Check the connection and try again.')
}

export type ChatPart =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; id: string; tool: string; args: Record<string, unknown>; status: 'running' | 'complete' | 'error'; progress?: string; result?: ToolResult }
  | { kind: 'approval'; id: string; callId: string; message: string; schema: Record<string, unknown>; status: 'waiting' | 'sending' | 'accepted' | 'declined' | 'cancelled'; error?: string }
// auto: Miragio's unprompted follow-up (e.g. a finished detonation); question holds its title.
export type ChatTurn = { id: string; question: string; auto?: boolean; parts: ChatPart[]; status: 'running' | 'done' | 'error' | 'stopped'; error?: string }

function applyEvent(turn: ChatTurn, event: ChatEvent): ChatTurn {
  const parts = [...turn.parts]
  switch (event.type) {
    case 'text_delta': {
      const last = parts.at(-1)
      if (last?.kind === 'text') parts[parts.length - 1] = { ...last, text: last.text + event.text }
      else parts.push({ kind: 'text', text: event.text })
      break
    }
    case 'tool_start': parts.push({ kind: 'tool', id: event.call_id, tool: event.tool, args: event.args, status: 'running' }); break
    case 'tool_progress': return { ...turn, parts: parts.map((part) => part.kind === 'tool' && part.id === event.call_id ? { ...part, progress: event.message } : part) }
    case 'tool_result': return { ...turn, parts: parts.map((part) => part.kind === 'tool' && part.id === event.call_id ? { ...part, status: event.result.isError ? 'error' : 'complete', result: event.result, progress: undefined } : part) }
    case 'approval_required': parts.push({ kind: 'approval', id: event.approval_id, callId: event.call_id, message: event.message, schema: event.schema, status: 'waiting' }); break
    case 'done': return { ...turn, status: 'done' }
    case 'error': return { ...turn, status: 'error', error: event.message }
  }
  return { ...turn, parts }
}

// Bedrock sends ~120-char bursts every ~430ms, so text is revealed a few characters per frame: the backlog
// drains over ~LAG ms (faster when it grows). Other events wait behind the text and speed up the drain to keep order.
const LAG = 300
const FINISH_LAG = 80
export function batchDeltas(update: (change: (turn: ChatTurn) => ChatTurn) => void) {
  let text = ''
  let queue: ChatEvent[] = []
  let frame = 0
  let last = 0
  let waiting: (() => void)[] = []
  const reveal = (chunk: string) => { if (chunk) update((turn) => applyEvent(turn, { type: 'text_delta', text: chunk })) }
  const settle = () => {
    cancelAnimationFrame(frame)
    frame = 0
    last = 0
    for (const event of queue) update((turn) => applyEvent(turn, event))
    queue = []
    for (const resolve of waiting) resolve()
    waiting = []
  }
  const flush = () => { reveal(text); text = ''; settle() }
  const tick = (now: number) => {
    const elapsed = last ? Math.min(now - last, 100) : 16
    last = now
    let count = Math.max(1, Math.ceil(text.length * elapsed / (queue.length ? FINISH_LAG : LAG)))
    if (/[\uD800-\uDBFF]/.test(text[count - 1] ?? '')) count++
    reveal(text.slice(0, count))
    text = text.slice(count)
    if (text) frame = requestAnimationFrame(tick)
    else settle()
  }
  const apply = (event: ChatEvent) => {
    if (event.type === 'text_delta' && !queue.length) text += event.text
    else if (text) queue.push(event)
    else { update((turn) => applyEvent(turn, event)); return }
    if (document.hidden || matchMedia('(prefers-reduced-motion: reduce)').matches) flush()
    else frame ||= requestAnimationFrame(tick)
  }
  // Resolves once every buffered event is on screen.
  const drained = () => text || queue.length ? new Promise<void>((resolve) => waiting.push(resolve)) : Promise.resolve()
  return { apply, flush, drained }
}

export function useChat() {
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [busy, setBusy] = useState(false)
  const session = useRef<string | undefined>(undefined)
  const [sessionId, setSessionId] = useState<string>()
  const active = useRef<AbortController | null>(null)
  const pending = useRef(new Set<string>())
  const decisions = useRef(new Set<string>())
  const approvalRequests = useRef(new Set<AbortController>())

  const stop = useCallback(() => {
    active.current?.abort()
    for (const controller of approvalRequests.current) controller.abort()
    approvalRequests.current.clear()
    active.current = null
    pending.current.clear()
    decisions.current.clear()
    setBusy(false)
    setTurns((previous) => previous.map((turn) => turn.status !== 'running' ? turn : {
      ...turn, status: 'stopped', parts: turn.parts.map((part) => part.kind === 'approval' && ['waiting', 'sending'].includes(part.status)
        ? { ...part, status: 'cancelled' } : part.kind === 'tool' && part.status === 'running' ? { ...part, status: 'error', progress: 'Connection stopped; check the incident for the action outcome.' } : part),
    }))
  }, [])
  useEffect(() => () => { active.current?.abort(); for (const controller of approvalRequests.current) controller.abort() }, [])

  const send = useCallback(async (question: string) => {
    if (active.current || !question.trim()) return false
    const controller = new AbortController()
    active.current = controller
    const id = crypto.randomUUID()
    setBusy(true)
    setTurns((previous) => [...previous, { id, question, parts: [], status: 'running' }])
    const update = (change: (turn: ChatTurn) => ChatTurn) => {
      if (active.current !== controller) return
      setTurns((previous) => previous.map((turn) => turn.id === id ? change(turn) : turn))
    }
    const batch = batchDeltas(update)
    try {
      await streamTurn({ session_id: session.current, message: question, actor: 'liam' }, controller.signal, (event) => {
        if (active.current !== controller) return
        if (event.type === 'session') { session.current = event.session_id; setSessionId(event.session_id); return }
        if (event.type === 'approval_required') pending.current.add(event.approval_id)
        batch.apply(event)
      })
      return true
    } catch (cause) {
      if (!controller.signal.aborted) update((turn) => ({ ...turn, status: 'error', error: cause instanceof Error ? cause.message : 'Connection lost. Try again.' }))
      controller.abort()
      return false
    } finally {
      if (controller.signal.aborted) batch.flush()
      else await batch.drained()
      if (active.current === controller) {
        active.current = null
        pending.current.clear()
        setBusy(false)
        setTurns((previous) => previous.map((turn) => turn.id !== id ? turn : {
          ...turn, parts: turn.parts.map((part) => part.kind === 'approval' && ['waiting', 'sending'].includes(part.status) && (!decisions.current.has(part.id) || controller.signal.aborted) ? { ...part, status: 'cancelled' }
            : part.kind === 'tool' && part.status === 'running' ? { ...part, status: 'error', progress: 'No outcome received; check the incident.' } : part),
        }))
      }
    }
  }, [])

  const respond = useCallback(async (id: string, action: 'accept' | 'decline', content?: Record<string, unknown>) => {
    const controller = active.current
    if (!controller || !pending.current.has(id) || decisions.current.has(id)) return
    decisions.current.add(id)
    approvalRequests.current.add(controller)
    const update = (status: 'sending' | 'waiting' | 'accepted' | 'declined' | 'cancelled', error?: string) => {
      if (controller.signal.aborted) return
      setTurns((previous) => previous.map((turn) => ({ ...turn, parts: turn.parts.map((part) => part.kind === 'approval' && part.id === id ? { ...part, status, error } : part) })))
    }
    update('sending')
    try {
      await submitApproval(id, action, content, controller.signal)
      pending.current.delete(id)
      update(action === 'accept' ? 'accepted' : 'declined')
    } catch (cause) {
      if (!controller.signal.aborted) update(active.current === controller ? 'waiting' : 'cancelled', cause instanceof Error ? cause.message : 'Your decision could not be submitted. Try again.')
    } finally { decisions.current.delete(id); if (!decisions.current.size) approvalRequests.current.clear() }
  }, [])

  // Unprompted follow-ups (finished detonation / bisection) arrive on the session stream as their own turn.
  useEffect(() => {
    if (!sessionId) return
    const source = new EventSource(`/chat/sessions/${encodeURIComponent(sessionId)}/events`)
    let batch: ReturnType<typeof batchDeltas> | null = null
    source.onmessage = (message) => {
      let event: ChatEvent
      try { event = parseChatEvent(message.data) } catch { return }
      if (event.type === 'follow_up') {
        batch?.flush()
        const id = crypto.randomUUID()
        batch = batchDeltas((change) => setTurns((previous) => previous.map((turn) => turn.id === id && turn.status === 'running' ? change(turn) : turn)))
        setBusy(true)
        setTurns((previous) => [...previous, { id, question: event.title, auto: true, parts: [], status: 'running' }])
        return
      }
      if (!batch) return
      batch.apply(event)
      if (event.type === 'done' || event.type === 'error') { batch = null; setBusy(false) }
    }
    return () => { batch?.flush(); source.close() }
  }, [sessionId])

  const reset = useCallback(() => { stop(); session.current = undefined; setSessionId(undefined); setTurns([]) }, [stop])
  return { turns, busy, send, stop, reset, respond }
}

// Defense in depth for expandable evidence and clipboard text; never render raw HTML.
export function sanitize(value: unknown, depth = 0): unknown {
  if (depth > 12) return '[nested content omitted]'
  if (typeof value === 'string') {
    return value.replace(/(Bearer\s+)[\w.-]+/gi, '$1[redacted]').replace(/\b(?:sk-[\w-]{12,}|AKIA[A-Z0-9]{16})\b/g, '[redacted]')
      .replace(/((?:api[_ -]?key|access[_ -]?token|mirage[_ -]?token|password|secret)\s*[=:]\s*)[^\s,;]+/gi, '$1[redacted]')
  }
  if (Array.isArray(value)) return value.slice(0, 200).map((item) => sanitize(item, depth + 1))
  if (object(value)) return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, /token|secret|password|credential|api.?key|authorization/i.test(key) ? '[redacted]' : sanitize(item, depth + 1)]))
  return value
}

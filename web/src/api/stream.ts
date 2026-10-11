// Native SSE with bounded CONNECTING recovery and a read-only polling fallback.
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, queryClient, type MirageEvent } from './client'

const REFRESH_RUNS = /^(run\.|agent\.registered|tool\.requested|global\.|human\.action)/
const REFRESH_INCIDENTS = /^(incident\.|detonation\.|verdict\.|bisection\.|handoff\.|fix\.|pr\.)/
const engineQueries = { predicate: (q: { queryKey: readonly unknown[] }) =>
  ['events', 'runs', 'incidents'].includes(String(q.queryKey[0])) }

type Connection = {
  state: 'connecting' | 'streaming' | 'polling' | 'disconnected'
  lastSync: number | null
  error: string | null
}
const initialConnection: Connection = { state: 'connecting', lastSync: null, error: null }
let lastSeq = 0
let generation = 0
let active = false
let source: EventSource | null = null
let poll: ReturnType<typeof setInterval> | null = null
let fallback: ReturnType<typeof setTimeout> | null = null
let refresh: ReturnType<typeof setTimeout> | null = null
let inflight: AbortController | null = null
const pending = new Set<string>()
let clockOffset = 0 // event clock minus wall clock: fixtures carry their own timestamps

function status(update: Partial<Connection>) {
  queryClient.setQueryData<Connection>(['connection'], (old = initialConnection) => ({ ...old, ...update }))
}

function refreshState() {
  for (const key of ['runs', 'incidents']) void queryClient.invalidateQueries({ queryKey: [key] })
}

function receive(events: MirageEvent[]) {
  const fresh: MirageEvent[] = []
  for (const e of [...events].sort((a, b) => a.seq - b.seq)) {
    if (e.seq <= lastSeq) continue
    lastSeq = e.seq
    fresh.push(e)
  }
  if (!fresh.length) return
  const timestamp = Date.parse(fresh.at(-1)!.ts)
  if (Number.isFinite(timestamp)) clockOffset = timestamp - Date.now()
  queryClient.setQueryData<MirageEvent[]>(['events'], (old = []) => [...old, ...fresh])
  for (const e of fresh) {
    if (REFRESH_RUNS.test(e.type)) pending.add('runs')
    if (REFRESH_INCIDENTS.test(e.type) || e.incident_id) pending.add('incidents')
  }
  const current = generation
  refresh ??= setTimeout(() => {
    if (!active || current !== generation) return
    for (const key of pending) void queryClient.invalidateQueries({ queryKey: [key] })
    pending.clear()
    refresh = null
  }, 120)
}

async function catchUp() {
  if (!active || inflight) return
  const current = generation
  const controller = new AbortController()
  inflight = controller
  try {
    const events = await api<MirageEvent[]>(`/events?after=${lastSeq}`, undefined, controller.signal)
    if (!active || current !== generation || controller.signal.aborted) return
    receive(events)
    status({ state: poll ? 'polling' : 'streaming', lastSync: Date.now(), error: null })
    refreshState()
  } catch (error) {
    if (active && current === generation && !controller.signal.aborted) {
      status({ state: 'disconnected', error: error instanceof Error ? error.message : 'Engine sync failed' })
    }
  } finally {
    if (inflight === controller) inflight = null
  }
}

function startPolling() {
  if (poll) return
  status({ state: 'polling' })
  poll = setInterval(() => {
    if (!source) openSource()
    void catchUp()
  }, 1000)
  void catchUp()
}

function openSource() {
  if (typeof EventSource === 'undefined') return startPolling()
  const current = generation
  const stream = new EventSource(`/api/stream?after=${lastSeq}`)
  source = stream
  const valid = () => active && current === generation && source === stream
  const waitForOpen = () => {
    fallback ??= setTimeout(() => {
      fallback = null
      if (valid() && stream.readyState !== EventSource.OPEN) startPolling()
    }, 3000)
  }
  waitForOpen()
  stream.onopen = () => {
    if (!valid()) return
    if (fallback) clearTimeout(fallback)
    fallback = null
    if (poll) clearInterval(poll)
    poll = null
    status({ state: 'streaming', error: null })
    refreshState()
    void catchUp()
  }
  stream.onmessage = (message) => {
    if (!valid()) return
    try {
      receive([JSON.parse(message.data)])
      status({ lastSync: Date.now(), error: null })
    } catch {
      status({ error: 'Unreadable engine event; refreshing current state' })
      startPolling()
    }
  }
  stream.onerror = () => {
    if (!valid()) return
    if (stream.readyState === EventSource.CLOSED) {
      stream.close()
      source = null
      if (fallback) clearTimeout(fallback)
      fallback = null
      startPolling()
    } else {
      if (!poll) status({ state: 'connecting' })
      waitForOpen()
    }
  }
}

export function connect() {
  if (active) return
  active = true
  generation++
  status({ state: 'connecting', error: null })
  refreshState()
  openSource()
}

export function disconnect() {
  active = false
  generation++
  source?.close()
  source = null
  if (poll) clearInterval(poll)
  if (fallback) clearTimeout(fallback)
  if (refresh) clearTimeout(refresh)
  poll = fallback = refresh = null
  pending.clear()
  inflight?.abort()
  inflight = null
  clockOffset = 0
  void queryClient.cancelQueries(engineQueries)
  status({ state: 'disconnected' })
}

/** A successful reset replaces event history; old work cannot update the new cache. */
export function resetStream() {
  disconnect()
  lastSeq = 0
  queryClient.setQueryData<MirageEvent[]>(['events'], [])
  status({ lastSync: null, error: null })
  void queryClient.resetQueries({ ...engineQueries, predicate: (q) =>
    engineQueries.predicate(q) && q.queryKey[0] !== 'events' })
  connect()
}

export function useEventStream() {
  useEffect(() => {
    connect()
    return disconnect
  }, [])
  return useQuery<Connection>({ queryKey: ['connection'], queryFn: () => initialConnection,
    initialData: initialConnection, enabled: false }).data
}

/** Now, on the event clock, ticking every second (for "12 s ago"). */
export function useNow() {
  const [now, setNow] = useState(() => Date.now() + clockOffset)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() + clockOffset), 1000)
    return () => clearInterval(timer)
  }, [])
  return now
}

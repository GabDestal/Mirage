// Native SSE with bounded CONNECTING recovery and a read-only polling fallback.
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { queryClient, type MirageEvent } from './client'
import { parseEvents, parseRuntime, readEvents, readRuntime, type RuntimeInfo } from './runtime'

const REFRESH_RUNS = /^(run\.|agent\.registered|tool\.requested|global\.|human\.action)/
const REFRESH_INCIDENTS = /^(incident\.|detonation\.|verdict\.|bisection\.|handoff\.|fix\.|pr\.)/
const engineQueries = { predicate: (q: { queryKey: readonly unknown[] }) =>
  ['events', 'runs', 'incidents', 'approvals', 'services'].includes(String(q.queryKey[0])) }

type Connection = {
  state: 'connecting' | 'streaming' | 'polling' | 'disconnected'
  lastSync: number | null
  error: string | null
  runtime: RuntimeInfo | null
}
const initialConnection: Connection = { state: 'connecting', lastSync: null, error: null, runtime: null }
let runtime: RuntimeInfo | null = null
let lastSeq = 0
let generation = 0
let active = false
const seen = new Set<number>()
let source: EventSource | null = null
let poll: ReturnType<typeof setInterval> | null = null
let fallback: ReturnType<typeof setTimeout> | null = null
let refresh: ReturnType<typeof setTimeout> | null = null
let inflight: AbortController | null = null
let syncTimeout: ReturnType<typeof setTimeout> | null = null
let runtimeWatch: ReturnType<typeof setInterval> | null = null
const pending = new Set<string>()
let clockOffset = 0 // event clock minus wall clock: fixtures carry their own timestamps

function status(update: Partial<Connection>) {
  queryClient.setQueryData<Connection>(['connection'], (old = initialConnection) => ({ ...old, ...update }))
}

function refreshState() {
  for (const key of ['runs', 'incidents', 'approvals', 'services']) void queryClient.invalidateQueries({ queryKey: [key] })
}

function adoptRuntime(info: RuntimeInfo) {
  if (runtime && (runtime.stream_epoch !== info.stream_epoch || runtime.instance_id !== info.instance_id)) {
    resetStream()
    runtime = info
    void catchUp()
    return false
  }
  runtime = info
  return true
}

function receive(events: MirageEvent[]) {
  const fresh: MirageEvent[] = []
  for (const e of [...events].sort((a, b) => a.seq - b.seq)) {
    if (seen.has(e.seq)) continue
    seen.add(e.seq)
    lastSeq = Math.max(lastSeq, e.seq)
    fresh.push(e)
  }
  if (!fresh.length) return
  const timestamp = Date.parse(fresh.at(-1)!.ts)
  if (fresh.at(-1)!.seq === lastSeq && Number.isFinite(timestamp)) clockOffset = timestamp - Date.now()
  queryClient.setQueryData<MirageEvent[]>(['events'], (old = []) => [...old, ...fresh].sort((a, b) => a.seq - b.seq))
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

async function catchUp(includeEvents = true) {
  if (!active || inflight) return
  const current = generation
  const controller = new AbortController()
  inflight = controller
  const valid = () => active && current === generation && !controller.signal.aborted
  const timer = setTimeout(() => {
    if (!valid()) return
    controller.abort()
    inflight = null
    syncTimeout = null
    status({ state: 'disconnected', error: 'Engine sync timed out; retrying', runtime: null })
  }, 5000)
  syncTimeout = timer
  try {
    const info = await readRuntime(controller.signal)
    if (!valid() || !adoptRuntime(info)) return
    if (includeEvents || info.last_seq > lastSeq) {
      const batch = await readEvents(lastSeq, controller.signal)
      if (!valid()) return
      if (batch.epoch !== info.stream_epoch) {
        const latest = await readRuntime(controller.signal)
        if (!valid() || !adoptRuntime(latest)) return
        throw new Error('Engine changed during sync; retrying')
      }
      receive(batch.events)
      refreshState()
    }
    status({ state: poll ? 'polling' : source?.readyState === EventSource.OPEN ? 'streaming' : 'connecting',
      lastSync: Date.now(), error: null, runtime })
  } catch (error) {
    if (valid()) {
      status({ state: 'disconnected', error: error instanceof Error ? error.message : 'Engine sync failed', runtime: null })
    }
  } finally {
    clearTimeout(timer)
    if (inflight === controller) {
      inflight = null
      syncTimeout = null
    }
  }
}

function startPolling() {
  if (poll) return
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
  let streamEpoch: string | null = null
  source = stream
  const valid = () => active && current === generation && source === stream
  const waitForOpen = () => {
    fallback ??= setTimeout(() => {
      fallback = null
      if (valid() && (stream.readyState !== EventSource.OPEN || !streamEpoch)) startPolling()
    }, 3000)
  }
  waitForOpen()
  const recovered = () => {
    if (fallback) clearTimeout(fallback)
    fallback = null
    if (poll) clearInterval(poll)
    poll = null
    status({ state: 'streaming', error: null })
  }
  stream.onopen = () => {
    if (!valid()) return
    if (streamEpoch) recovered()
    refreshState()
    void catchUp()
  }
  stream.onmessage = (message) => {
    if (!valid() || !streamEpoch || streamEpoch !== runtime?.stream_epoch) return
    try {
      receive(parseEvents([JSON.parse(message.data)]))
      status({ lastSync: Date.now(), error: null })
    } catch {
      status({ state: 'disconnected', error: 'Unreadable engine event; refreshing current state', runtime: null })
      startPolling()
    }
  }
  stream.addEventListener('runtime', (message) => {
    if (!valid()) return
    try {
      const info = parseRuntime(JSON.parse((message as MessageEvent).data))
      if (!adoptRuntime(info)) return
      streamEpoch = info.stream_epoch
      status({ runtime: info })
      if (stream.readyState === EventSource.OPEN) recovered()
    } catch (error) {
      streamEpoch = null
      status({ state: 'disconnected', error: error instanceof Error ? error.message : 'Invalid engine runtime', runtime: null })
      startPolling()
    }
  })
  stream.onerror = () => {
    if (!valid()) return
    streamEpoch = null
    status({ runtime: null })
    if (stream.readyState === EventSource.CLOSED) {
      stream.close()
      source = null
      if (fallback) clearTimeout(fallback)
      fallback = null
      status({ state: 'connecting' })
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
  runtimeWatch = setInterval(() => { void catchUp(false) }, 5000)
}

export function disconnect() {
  active = false
  generation++
  source?.close()
  source = null
  if (poll) clearInterval(poll)
  if (fallback) clearTimeout(fallback)
  if (refresh) clearTimeout(refresh)
  if (syncTimeout) clearTimeout(syncTimeout)
  if (runtimeWatch) clearInterval(runtimeWatch)
  syncTimeout = runtimeWatch = null
  poll = fallback = refresh = null
  pending.clear()
  inflight?.abort()
  inflight = null
  clockOffset = 0
  void queryClient.cancelQueries(engineQueries)
  status({ state: 'disconnected', runtime: null })
}

/** A successful reset replaces event history; old work cannot update the new cache. */
export function resetStream() {
  disconnect()
  lastSeq = 0
  seen.clear()
  runtime = null
  queryClient.setQueryData<MirageEvent[]>(['events'], [])
  status({ lastSync: null, error: null, runtime: null })
  void queryClient.resetQueries({ ...engineQueries, predicate: (q) =>
    engineQueries.predicate(q) && q.queryKey[0] !== 'events' })
  connect()
}

export function useEventStream() {
  useEffect(() => {
    connect()
    return disconnect
  }, [])
  return useConnection()
}

/** Shared health/runtime reads do not own the transport's mount/unmount lifecycle. */
export function useConnection() {
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

// Live events: native EventSource on /stream, polling /events?after=seq if the stream dies.
// Every event lands in the ['events'] cache; run and incident events refresh /runs and /incidents.
import { useEffect, useState } from 'react'
import { api, queryClient, type MirageEvent } from './client'

const REFRESH_RUNS = /^(run\.|tool\.requested|global\.stop|human\.action)/
const REFRESH_INCIDENTS = /^(incident\.|detonation\.|verdict\.|bisection\.|handoff\.|fix\.|pr\.)/

let lastSeq = 0
let source: EventSource | null = null
let poll: ReturnType<typeof setInterval> | null = null
let refresh: ReturnType<typeof setTimeout> | null = null
let pending = new Set<string>()
let clockOffset = 0 // event clock minus wall clock: replay fixtures carry their own timestamps

function receive(events: MirageEvent[]) {
  const fresh = events.filter((e) => e.seq > lastSeq)
  if (!fresh.length) return
  lastSeq = fresh[fresh.length - 1].seq
  clockOffset = Date.parse(fresh[fresh.length - 1].ts) - Date.now()
  queryClient.setQueryData<MirageEvent[]>(['events'], (old = []) => [...old, ...fresh])
  for (const e of fresh) {
    if (REFRESH_RUNS.test(e.type)) pending.add('runs')
    if (REFRESH_INCIDENTS.test(e.type) || e.incident_id) pending.add('incidents')
  }
  // Batch refetches: a replay can deliver dozens of events in one tick.
  refresh ??= setTimeout(() => {
    for (const key of pending) queryClient.invalidateQueries({ queryKey: [key] })
    pending = new Set()
    refresh = null
  }, 120)
}

function startPolling() {
  poll ??= setInterval(() => {
    api<MirageEvent[]>(`/events?after=${lastSeq}`).then(receive, () => {})
  }, 1000)
}

export function connect() {
  if (source || poll) return
  if (typeof EventSource === 'undefined') return startPolling()
  source = new EventSource(`/api/stream?after=${lastSeq}`)
  source.onmessage = (m) => receive([JSON.parse(m.data)])
  source.onerror = () => {
    // CONNECTING: the browser retries on its own (with Last-Event-ID). CLOSED: it gave up.
    if (source?.readyState === EventSource.CLOSED) {
      source = null
      startPolling()
    }
  }
}

export function disconnect() {
  source?.close()
  source = null
  if (poll) clearInterval(poll)
  poll = null
}

/** After /demo/start or /demo/reset the engine restarts at seq 1: drop what we had and reconnect. */
export function resetStream() {
  disconnect()
  lastSeq = 0
  queryClient.setQueryData<MirageEvent[]>(['events'], [])
  queryClient.invalidateQueries()
  connect()
}

export function useEventStream() {
  useEffect(() => {
    connect()
    return disconnect
  }, [])
}

/** Now, on the event clock, ticking every second (for "12 s ago"). */
export function useNow() {
  const [now, setNow] = useState(() => Date.now() + clockOffset)
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() + clockOffset), 1000)
    return () => clearInterval(t)
  }, [])
  return now
}

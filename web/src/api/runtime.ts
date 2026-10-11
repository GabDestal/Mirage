import { api, ApiError, type MirageEvent } from './client'

// Approved engine contract; generated schema remains owned by the shared engine PR.
export type RuntimeInfo = {
  engine_mode: 'live' | 'replay'
  instance_id: string
  stream_epoch: string
  last_seq: number
  revision: string | null
  owned_run_ids: string[]
}

export function parseRuntime(value: unknown): RuntimeInfo {
  const info = value as Partial<RuntimeInfo> | null
  if (!info || !['live', 'replay'].includes(String(info.engine_mode)) ||
    typeof info.instance_id !== 'string' || !info.instance_id ||
    typeof info.stream_epoch !== 'string' || !info.stream_epoch ||
    !Number.isSafeInteger(info.last_seq) || info.last_seq! < 0 ||
    (info.revision !== null && typeof info.revision !== 'string') ||
    !Array.isArray(info.owned_run_ids) || !info.owned_run_ids.every((id) => typeof id === 'string')) {
    throw new Error('Engine runtime metadata is unavailable or invalid')
  }
  return info as RuntimeInfo
}

export async function readRuntime(signal: AbortSignal) {
  return parseRuntime(await api<unknown>('/runtime', undefined, signal))
}

export function parseEvents(value: unknown): MirageEvent[] {
  if (!Array.isArray(value) || value.some((event) => !event ||
    !Number.isSafeInteger(event.seq) || event.seq < 1 || typeof event.type !== 'string' ||
    typeof event.ts !== 'string' || !Number.isFinite(Date.parse(event.ts)) ||
    !['prod', 'mirage'].includes(event.env) || !event.payload ||
    typeof event.payload !== 'object' || Array.isArray(event.payload))) {
    throw new Error('Engine event history is unavailable or invalid')
  }
  return value as MirageEvent[]
}

export async function readEvents(after: number, signal: AbortSignal) {
  // Read the atomic epoch header without changing the existing API body's Event[] shape.
  const response = await fetch(`/api/events?after=${after}`, { signal })
  if (!response.ok) throw new ApiError(response.status, `Engine event sync failed (${response.status})`)
  const epoch = response.headers.get('X-Mirage-Stream-Epoch')
  const events = parseEvents(await response.json())
  if (!epoch) throw new Error('Engine event history is missing its runtime epoch')
  return { epoch, events }
}

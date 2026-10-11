// Tiny client for the engine API (CONTRACTS.md §5). Types come from /openapi.json: `npm run api:types`.
import { QueryClient, useQuery } from '@tanstack/react-query'
import type { components } from './schema'

type S = components['schemas']
export type Run = S['Run']
export type Incident = S['Incident']
export type MirageEvent = S['Event']
export type GateDecision = S['GateDecision']
export type HumanRequest = S['HumanRequest']
export type ResumeAll = S['ResumeAll']
export type Approval = S['Approval']
export type ServiceView = S['ServiceView']
export type ServiceItem = S['ServiceItem']

const BASE = '/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(BASE + path, body === undefined ? { signal } : {
    signal,
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail, () => null)
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `${res.status} ${res.statusText}`)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 2_000, retry: 1, refetchOnWindowFocus: false } },
})

export const useRuns = () => useQuery({ queryKey: ['runs'], queryFn: ({ signal }) => api<Run[]>('/runs', undefined, signal) })
export const useIncidents = () =>
  useQuery({ queryKey: ['incidents'], queryFn: ({ signal }) => api<Incident[]>('/incidents', undefined, signal) })

// These views are folded from events. Read-only polling also catches decisions made in MCP.
export const useApprovals = () => useQuery({
  queryKey: ['approvals'], queryFn: () => api<Approval[]>('/approvals'), refetchInterval: 2_000,
})
export const useServiceView = (service: ServiceView['service'], env: ServiceView['env']) => useQuery({
  queryKey: ['services', service, env],
  queryFn: () => api<ServiceView>(`/services/${service}?env=${env}`), refetchInterval: 2_000,
})

// Events live in the query cache under ['events'], filled by the stream (stream.ts), never fetched.
export const useEvents = () =>
  useQuery<MirageEvent[]>({ queryKey: ['events'], queryFn: () => [], initialData: [], enabled: false })

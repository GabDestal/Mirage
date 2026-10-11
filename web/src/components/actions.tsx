// Human actions (Unfreeze, Kill, Resume, Stop all, Resume all): a reason dialog, then the control-plane POST with
// HumanRequest {actor, reason}, an optimistic update and a toast (DESIGN.md §2.6, §11).
import { useMutation } from '@tanstack/react-query'
import { Dialog, RadioGroup } from 'radix-ui'
import { createContext, useContext, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { api, queryClient, useEvents, useIncidents, useRuns, type HumanRequest, type MirageEvent, type ResumeAll, type Run } from '@/api/client'
import { useConnection } from '@/api/stream'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { blockedCall, canResume, resumeBlock, runLabel, stopOn } from '@/lib/runs'
import { isDemo } from '@/lib/demo'
import { humanControlError } from './engine-controls'

// shortcut: one operator for the demo, upgrade to a sign-in when Mirage has users.
export const ACTOR = 'liam'

export type ActionKind = 'freeze' | 'restart' | 'unfreeze' | 'kill' | 'resume' | 'stop' | 'resumeAll'
type Ask = (kind: ActionKind, run?: Run) => void

const REASONS: Record<ActionKind, string[]> = {
  freeze: ['Pause this run while I investigate.', 'Unexpected tool activity.'],
  restart: ['The fix has been reviewed and merged.', 'The task is safe to start again.'],
  unfreeze: ['False positive: the destination is expected.', 'The customer asked for this in the ticket.', 'Mirage showed no harm.'],
  kill: ['Confirmed compromise.', 'The run is stuck or looping.', 'The task is no longer needed.'],
  resume: ['The investigation is over.', 'This agent was not involved.', 'Demo or test reset.'],
  stop: ['Suspected compromise across agents.', 'Stopping everything while we investigate.', 'Demo or test reset.'],
  resumeAll: ['The investigation is over.', 'Stop all was a precaution.', 'Demo or test reset.'],
}

const VERB = { freeze: 'Freeze', restart: 'Approve clean restart', unfreeze: 'Unfreeze', kill: 'Kill', resume: 'Resume', stop: 'Stop all', resumeAll: 'Resume all' }

function copy(kind: ActionKind, run: Run | undefined, runs: Run[]) {
  if (isDemo && kind === 'stop') return {
    title: 'Pause recording?', effect: 'Recording pauses and active recorded runs show as halted. Resume recording restores their prior state and continues from here.',
  }
  if (isDemo && kind === 'resumeAll') return {
    title: 'Resume recording?', effect: 'Stop all is lifted. Recording continues from its paused position and prior recorded run states are restored. No agents or providers are launched.',
  }
  if (kind === 'stop') return { title: 'Stop all agents?', effect: 'Active runs halt and their tokens are revoked. Resume all can queue eligible halted tasks for a new start.' }
  if (kind === 'resumeAll') return {
    title: 'Resume all agents?',
    effect: 'Stop all is lifted and eligible halted tasks are queued to start from the beginning. A queued run waits for its owner to start it. Compromised or detonating runs stay stopped. New actions go through the gate.',
  }
  const label = run ? runLabel(run, runs) : 'this run'
  if (kind === 'freeze') return { title: `Freeze ${label}?`, effect: 'This run pauses before its next tool call. Other runs keep working. A manual freeze does not create incident proof.' }
  if (kind === 'restart') return { title: `Approve a clean restart of ${label}?`, effect: 'A new run is queued with the same task. It waits for the owner to start the agent; this approval does not launch it or merge a PR.' }
  if (kind === 'resume') return { title: `Resume ${label}?`, effect: 'A new run is queued to start the task from the beginning. It waits for its owner to start it; queued does not mean running. New actions go through the gate.' }
  if (kind === 'kill') return { title: `Kill ${label}?`, effect: 'The call it was holding never runs, and the run ends for good.' }
  const events = queryClient.getQueryData<MirageEvent[]>(['events']) ?? []
  const held = run && blockedCall(events, run.id)?.decision
  const to = (held?.args as { to?: unknown } | undefined)?.to
  return {
    title: `Unfreeze ${label}?`,
    effect: held
      ? typeof to === 'string' ? `It will send the held email to ${to}.` : `It will run the ${held.tool} call it was holding.`
      : 'It continues where it stopped.',
  }
}

const AskContext = createContext<Ask>(() => {})
export const useAsk = () => useContext(AskContext)

type Connection = ReturnType<typeof useConnection>
const connectionNow = () => queryClient.getQueryData<Connection>(['connection'])
const liveEngineAvailable = (connection: Connection | undefined) =>
  connection?.runtime?.engine_mode === 'live' && ['streaming', 'polling'].includes(connection.state) && !connection.error

export const liveRunOwned = (run: Run, connection: Connection | undefined) =>
  !isDemo && run.env === 'prod' && liveEngineAvailable(connection) && !!connection?.runtime?.owned_run_ids.includes(run.id)

export function runControlNote(run: Run, connection: Connection | undefined) {
  if (isDemo || run.env !== 'prod' || !['running', 'frozen'].includes(run.status) || liveRunOwned(run, connection)) return null
  return liveEngineAvailable(connection) ? `Restored history · no live owner. Last recorded state: ${run.status}.`
    : `Live ownership unavailable. Showing recorded ${run.status} state.`
}

const needsOwner = (kind: ActionKind) => ['freeze', 'unfreeze', 'kill'].includes(kind)
const requireOwner = (kind: ActionKind, run?: Run) => {
  const recorded = isDemo && connectionNow()?.runtime?.engine_mode === 'replay'
  if (needsOwner(kind) && !recorded && (!run || !liveRunOwned(run, connectionNow())))
    throw new Error('This engine has no observed live control of this run. Its recorded history is still available.')
  if (!isDemo && ['resume', 'resumeAll', 'restart'].includes(kind) && !liveEngineAvailable(connectionNow()))
    throw new Error('Live engine ownership is unavailable. Wait for a successful sync before approving recovery.')
}

const sameRuntime = (before: Connection['runtime'] | undefined) => {
  const current = connectionNow()?.runtime
  return before?.instance_id === current?.instance_id && before?.stream_epoch === current?.stream_epoch
}

export function ActionsProvider({ children }: { children: ReactNode }) {
  const connection = useConnection()
  const [pending, setPending] = useState<Omit<Vars, 'body'> | null>(null)
  const ask: Ask = (kind, run) => {
    try {
      requireOwner(kind, run)
      if (!sameRuntime(connection.runtime)) throw new Error('The engine changed. Review the current run before acting again.')
      setPending({ kind, run, runtime: connection.runtime })
    }
    catch (error) { toast.error(humanControlError(error instanceof Error ? error : new Error(String(error)))) }
  }
  return (
    <AskContext.Provider value={ask}>
      {children}
      <ReasonDialog pending={pending} onClose={() => setPending(null)} />
    </AskContext.Provider>
  )
}

/** Resume on a halted run that has no restart yet; disabled with the reason while it cannot run. */
export function ResumeButton({ run, variant = 'secondary' }: { run: Run; variant?: 'primary' | 'secondary' }) {
  const ask = useAsk()
  const { data: runs = [] } = useRuns()
  const { data: incidents = [] } = useIncidents()
  const connection = useConnection()
  if (isDemo || !canResume(run, runs)) return null
  const blocked = !liveEngineAvailable(connection) ? 'Live engine ownership is unavailable. Wait for a successful sync.' : resumeBlock(run, incidents)
  return <Button variant={variant} disabled={!!blocked} title={blocked ?? undefined}
    onClick={(e) => { e.stopPropagation(); ask('resume', run) }}>Resume</Button>
}

export function FreezeButton({ run }: { run: Run }) {
  const ask = useAsk()
  const connection = useConnection()
  if (run.status !== 'running' || !liveRunOwned(run, connection)) return null
  return <Button onClick={(e) => { e.stopPropagation(); ask('freeze', run) }}>Freeze</Button>
}

/** A restart approval queues work; only an observed running state establishes execution. */
export function CleanRestartButton({ run }: { run: Run }) {
  const ask = useAsk()
  const { data: runs = [] } = useRuns()
  const { data: events = [] } = useEvents()
  const connection = useConnection()
  if (isDemo || run.env !== 'prod' || !['killed', 'halted'].includes(run.status)) return null
  const restart = runs.find((r) => r.restarted_from === run.id)
  if (restart) return <span className="clean-restart-status" role="status"><Link to={`/runs/${encodeURIComponent(restart.id)}`} onClick={(e) => e.stopPropagation()}>
    {restart.status === 'queued' ? 'Clean restart pending · awaiting owner start'
      : runControlNote(restart, connection) ? `Recorded restart: ${restart.status} · live ownership unavailable` : `Clean restart: ${restart.status}`}
  </Link></span>
  const stopped = stopOn(events)
  const available = liveEngineAvailable(connection)
  return <Button disabled={stopped || !available} title={!available ? 'Live engine ownership is unavailable. Wait for a successful sync.' : stopped ? 'Global STOP is on. Lift STOP before approving a clean restart.' : 'Queues a new run; the owner must start it.'}
    onClick={(e) => { e.stopPropagation(); ask('restart', run) }}>Approve clean restart</Button>
}

function ReasonDialog({ pending, onClose }: { pending: Omit<Vars, 'body'> | null; onClose: () => void }) {
  const act = useHumanAction()
  const kind = pending?.kind ?? 'unfreeze'
  const runs = queryClient.getQueryData<Run[]>(['runs']) ?? []
  const { title, effect } = copy(kind, pending?.run, runs)
  const retained = kind === 'freeze' || kind === 'restart'
  return <HumanReasonDialog key={pending ? `${kind}:${pending.run?.id}:${pending.runtime?.instance_id}:${pending.runtime?.stream_epoch}` : 'closed'} open={!!pending} title={title} effect={effect}
    reasons={REASONS[kind]} verb={isDemo && kind === 'stop' ? 'Pause recording' : isDemo && kind === 'resumeAll' ? 'Resume recording' : VERB[kind]} destructive={kind === 'kill' || kind === 'stop'} onClose={() => { act.reset(); onClose() }}
    busy={act.isPending} error={retained && act.error ? humanControlError(act.error) : undefined}
    onSubmit={(reason) => {
      if (!pending || act.isPending) return
      act.mutate({ kind, run: pending.run, runtime: pending.runtime, body: { actor: ACTOR, reason } }, retained ? { onSuccess: onClose } : undefined)
      if (!retained) onClose()
    }} />
}

export function HumanReasonDialog({ open, title, effect, reasons, verb, destructive = false,
  onClose, onSubmit, busy = false, error }: {
  open: boolean; title: string; effect: string; reasons: string[]; verb: string;
  destructive?: boolean; onClose: () => void; onSubmit: (reason: string) => void;
  busy?: boolean; error?: string;
}) {
  const [choice, setChoice] = useState('')
  const [note, setNote] = useState('')
  const reason = [choice, note.trim()].filter(Boolean).join(' ')
  const close = () => {
    if (busy) return
    onClose()
    setChoice('')
    setNote('')
  }
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!reason || busy) return
    onSubmit(reason)
  }

  return (
    <Dialog.Root open={open} onOpenChange={(open) => !open && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/20 animate-[fade_160ms_var(--ease-out)]" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[min(440px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-node bg-paper p-6 shadow-float animate-[pop_160ms_var(--ease-out)]">
          <form onSubmit={submit} className="flex flex-col gap-5">
            <div className="flex flex-col gap-1.5">
              <Dialog.Title className="text-title font-semibold text-balance">{title}</Dialog.Title>
              <Dialog.Description className="text-ink-2">{effect}</Dialog.Description>
              <p className="text-control text-ink-2">Recorded as {ACTOR} (demo operator).</p>
            </div>
            <fieldset disabled={busy} className="flex flex-col gap-3">
              <legend className="mb-2 text-control font-medium">Why?</legend>
              <RadioGroup.Root value={choice} onValueChange={setChoice} className="flex flex-col gap-0.5">
                {reasons.map((r) => (
                  <label key={r} className="flex cursor-pointer items-center gap-3 rounded-control px-2 py-1.5 hover:bg-paper-2">
                    <RadioGroup.Item value={r} className="grid size-4 shrink-0 place-items-center rounded-full border border-ink-3 data-[state=checked]:border-ink">
                      <RadioGroup.Indicator className="size-2 rounded-full bg-ink" />
                    </RadioGroup.Item>
                    {r}
                  </label>
                ))}
              </RadioGroup.Root>
              <textarea
                aria-label="Reason details"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Add details (optional if you picked a reason)"
                rows={2}
                className="resize-none rounded-control border border-line bg-paper px-3 py-2 outline-none focus-visible:border-ink focus-visible:outline-none"
              />
            </fieldset>
            {error && <p role="alert" className="text-alarm">{error}</p>}
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <Button type="button" variant="ghost" disabled={busy}>Cancel</Button>
              </Dialog.Close>
              <Button type="submit" variant={destructive ? 'destructive' : 'primary'} disabled={!reason || busy}>
                {busy ? 'Working…' : verb}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

const runCount = (n: number) => `${n} ${n === 1 ? 'run' : 'runs'}`
const resumeAllToast = ({ resumed, skipped }: ResumeAll) =>
  (resumed.length ? [...new Set(resumed.map((run) => run.status))].map((status) =>
    `${runCount(resumed.filter((run) => run.status === status).length)} ${status}${status === 'queued' ? ' · awaiting owner start' : ''}.`,
  ).join(' ') : 'No new recovery runs.') + (skipped.length ? ` ${runCount(skipped.length)} skipped.` : '')

type Vars = { kind: ActionKind; run?: Run; body: HumanRequest; runtime?: Connection['runtime'] }

export function useHumanAction() {
  return useMutation({
    retry: false,
    mutationFn: ({ kind, run, body, runtime }: Vars) => {
      requireOwner(kind, run)
      if (runtime !== undefined && !sameRuntime(runtime)) throw new Error('The engine changed. Review the current run before acting again.')
      return api<Run | ResumeAll>(kind === 'stop' ? '/stop' : kind === 'resumeAll' ? '/resume-all' : `/runs/${encodeURIComponent(run!.id)}/${kind}`, body)
    },
    onMutate: async ({ kind, run, runtime: expected }: Vars) => {
      const runtime = expected === undefined ? connectionNow()?.runtime : expected
      await queryClient.cancelQueries({ queryKey: ['runs'] })
      const before = queryClient.getQueryData<Run[]>(['runs'])
      requireOwner(kind, run)
      if (!sameRuntime(runtime)) throw new Error('The engine changed. Review the current run before acting again.')
      queryClient.setQueryData<Run[]>(['runs'], (old = []) =>
        old.map((r) =>
          kind === 'stop'
            ? (isDemo || liveRunOwned(r, connectionNow())) && ['running', 'frozen', 'queued'].includes(r.status) ? { ...r, status: 'halted' } : r
            : r.id === run?.id && kind === 'kill' ? { ...r, status: 'killed' } : r,
        ),
      )
      return { before, runtime }
    },
    onSuccess: (data, { kind, run }, ctx) => {
      if (!sameRuntime(ctx?.runtime)) {
        toast('The engine changed while this decision was pending. Review its current state before acting again.')
        return
      }
      const recovered = kind === 'resumeAll' && !isDemo ? (data as ResumeAll).resumed
        : ['freeze', 'restart', 'resume', 'unfreeze', 'kill'].includes(kind) && data && 'id' in data ? [data] : []
      if (recovered.length) {
        queryClient.setQueryData<Run[]>(['runs'], (old = []) => [
          ...old.filter((r) => !recovered.some((next) => next.id === r.id)), ...recovered,
        ])
      }
      const runs = queryClient.getQueryData<Run[]>(['runs']) ?? []
      const label = run ? runLabel(run, runs) : ''
      if (kind === 'resumeAll') return toast(isDemo ? 'Recording resumed from where it paused. Prior recorded run states restored.' : resumeAllToast(data as ResumeAll))
      if (kind === 'restart') return toast((data as Run).status === 'queued'
        ? 'Clean restart approved and queued. Waiting for the owner to start the agent.'
        : `Clean restart approved. Last observed state: ${(data as Run).status}.`)
      if (kind === 'resume') return toast((data as Run).status === 'queued'
        ? `${label} restart queued. Waiting for the owner to start it.` : `${label} restart: ${(data as Run).status}.`)
      if (kind === 'freeze') return toast(`${label} is frozen.`)
      if (isDemo && (kind === 'kill' || kind === 'unfreeze')) return toast(`Recorded ${label}: ${(data as Run).status}.`)
      toast(kind === 'stop' ? isDemo ? 'Recording paused. Active recorded runs are halted.' : 'Global STOP is on. Live tool calls are blocked.'
        : kind === 'kill' ? `${label} was killed.` : `${label} released. Last observed state: ${(data as Run).status}.`)
    },
    onError: (err, _, ctx) => {
      if (ctx && !sameRuntime(ctx.runtime)) {
        toast.error('The engine changed while this decision was pending. Review its current state before acting again.')
        return
      }
      if (ctx && sameRuntime(ctx.runtime)) queryClient.setQueryData(['runs'], ctx.before)
      toast.error(humanControlError(err))
    },
    onSettled: (_, __, ___, ctx) => {
      if (ctx && sameRuntime(ctx.runtime)) return queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}

// Human actions (Unfreeze, Kill, Resume, Stop all, Lift stop): a reason dialog, then the control-plane POST with
// HumanRequest {actor, reason}, an optimistic update and a toast (DESIGN.md §2.6, §11).
import { useMutation } from '@tanstack/react-query'
import { Dialog, RadioGroup } from 'radix-ui'
import { createContext, useContext, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { api, queryClient, useEvents, useIncidents, useRuns, type HumanRequest, type MirageEvent, type Run } from '@/api/client'
import { Button } from '@/components/ui/button'
import { blockedCall, canResume, resumeBlock, runLabel, stopOn } from '@/lib/runs'

// shortcut: one operator for the demo, upgrade to a sign-in when Mirage has users.
export const ACTOR = 'liam'

export type ActionKind = 'unfreeze' | 'kill' | 'resume' | 'stop' | 'lift'
type Ask = (kind: ActionKind, run?: Run) => void

const REASONS: Record<ActionKind, string[]> = {
  unfreeze: ['False positive: the destination is expected.', 'The customer asked for this in the ticket.', 'Mirage showed no harm.'],
  kill: ['Confirmed compromise.', 'The run is stuck or looping.', 'The task is no longer needed.'],
  resume: ['The investigation is over.', 'This agent was not involved.', 'Demo or test reset.'],
  stop: ['Suspected compromise across agents.', 'Stopping everything while we investigate.', 'Demo or test reset.'],
  lift: ['The investigation is over.', 'Stop all was a precaution.', 'Demo or test reset.'],
}

const VERB = { unfreeze: 'Unfreeze', kill: 'Kill', resume: 'Resume', stop: 'Stop all', lift: 'Lift stop' }

function copy(kind: ActionKind, run: Run | undefined, runs: Run[]) {
  if (kind === 'stop') return { title: 'Stop all agents?', effect: 'Every run halts and all tokens are revoked. You can restart runs one by one later.' }
  if (kind === 'lift') return { title: 'Lift Stop all?', effect: 'Nothing restarts on its own. You then resume halted agents one at a time.' }
  const label = run ? runLabel(run, runs) : 'this run'
  if (kind === 'resume') return { title: `Resume ${label}?`, effect: 'It starts its task again from the beginning. Every action goes through the gate.' }
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

export function ActionsProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<{ kind: ActionKind; run?: Run } | null>(null)
  const ask: Ask = (kind, run) => setPending({ kind, run })
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
  const { data: events = [] } = useEvents()
  if (!canResume(run, runs)) return null
  const blocked = resumeBlock(run, incidents, stopOn(events))
  return <Button variant={variant} disabled={!!blocked} title={blocked ?? undefined}
    onClick={(e) => { e.stopPropagation(); ask('resume', run) }}>Resume</Button>
}

function ReasonDialog({ pending, onClose }: { pending: { kind: ActionKind; run?: Run } | null; onClose: () => void }) {
  const act = useHumanAction()
  const kind = pending?.kind ?? 'unfreeze'
  const runs = queryClient.getQueryData<Run[]>(['runs']) ?? []
  const { title, effect } = copy(kind, pending?.run, runs)
  return <HumanReasonDialog key={pending ? `${kind}:${pending.run?.id}` : 'closed'} open={!!pending} title={title} effect={effect}
    reasons={REASONS[kind]} verb={VERB[kind]} destructive={kind === 'kill' || kind === 'stop'} onClose={onClose}
    onSubmit={(reason) => {
      if (!pending) return
      act.mutate({ kind, run: pending.run, body: { actor: ACTOR, reason } })
      onClose()
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

type Vars = { kind: ActionKind; run?: Run; body: HumanRequest }

export function useHumanAction() {
  return useMutation({
    mutationFn: ({ kind, run, body }: Vars) =>
      api(kind === 'stop' ? '/stop' : kind === 'lift' ? '/stop/lift' : `/runs/${run!.id}/${kind}`, body),
    onMutate: async ({ kind, run }: Vars) => {
      await queryClient.cancelQueries({ queryKey: ['runs'] })
      const before = queryClient.getQueryData<Run[]>(['runs'])
      queryClient.setQueryData<Run[]>(['runs'], (old = []) =>
        old.map((r) =>
          kind === 'stop'
            ? ['running', 'frozen', 'queued'].includes(r.status) ? { ...r, status: 'halted' } : r
            : r.id === run?.id && (kind === 'unfreeze' || kind === 'kill') ? { ...r, status: kind === 'kill' ? 'killed' : 'running' } : r,
        ),
      )
      return { before }
    },
    onSuccess: (_, { kind, run }) => {
      const runs = queryClient.getQueryData<Run[]>(['runs']) ?? []
      const label = run ? runLabel(run, runs) : ''
      toast(kind === 'stop' ? 'All agents stopped.' : kind === 'lift' ? 'Stop all lifted. Resume agents one at a time.'
        : kind === 'resume' ? `${label} is starting its task again.` : kind === 'kill' ? `${label} was killed.` : `${label} is working again.`)
    },
    onError: (err, _, ctx) => {
      queryClient.setQueryData(['runs'], ctx?.before)
      toast.error(err.message)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['runs'] }),
  })
}

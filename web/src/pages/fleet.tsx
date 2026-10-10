// Fleet (DESIGN.md §11 agent row, §10 compact trace). Healthy is quiet; only the frozen row changes.
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { api, useEvents, useRuns, type MirageEvent, type Run } from '@/api/client'
import { resetStream, useNow } from '@/api/stream'
import { useAsk } from '@/components/actions'
import { AgentAvatar } from '@/components/avatar'
import { Button } from '@/components/ui/button'
import { avatarState, relTime, rowSentence, runLabel, steps } from '@/lib/runs'
import { cn } from '@/lib/utils'

const EASE_OUT = [0.23, 1, 0.32, 1] as const

export function Fleet() {
  const { data: runs, isPending, isError, error } = useRuns()
  const { data: events } = useEvents()
  const now = useNow()
  const navigate = useNavigate()
  const ask = useAsk()
  const [selected, setSelected] = useState(-1)

  // J/K move, Enter opens, U unfreezes the selected run (DESIGN.md §13).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!runs?.length || e.metaKey || e.ctrlKey || e.altKey || document.querySelector('[role=dialog]')) return
      if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return
      const run = runs[selected]
      if (e.key === 'j') setSelected((i) => Math.min(i + 1, runs.length - 1))
      else if (e.key === 'k') setSelected((i) => Math.max(i - 1, 0))
      else if (e.key === 'Enter' && run) navigate(`/runs/${run.id}`)
      else if (e.key === 'u' && run?.status === 'frozen') ask('unfreeze', run)
      else if (e.key === 'Escape') setSelected(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [runs, selected, navigate, ask])

  if (isPending) return <Skeleton />
  if (isError)
    return (
      <Empty text={`Can't reach the Mirage engine. ${error.message}`} action="Try again" onAction={() => location.reload()} />
    )
  if (!runs.length)
    return (
      <Empty
        text="No agents are running. Runs show up here the moment an agent starts."
        action="Play the demo"
        onAction={() => api('/demo/start', {}).then(resetStream, (e) => toast.error(e.message))}
      />
    )

  return (
    <ul className="flex max-w-[1080px] flex-col py-2" aria-label="Runs">
      {runs.map((run, i) => (
        <AgentRow key={run.id} run={run} runs={runs} events={events} now={now} selected={i === selected} />
      ))}
    </ul>
  )
}

function AgentRow({ run, runs, events, now, selected }: { run: Run; runs: Run[]; events: MirageEvent[]; now: number; selected: boolean }) {
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const sentence = rowSentence(run, events)
  const label = runLabel(run, runs)
  const when = run.ended_at ?? run.started_at

  return (
    <li
      onClick={() => navigate(`/runs/${run.id}`)}
      className={cn(
        'group grid h-[52px] cursor-pointer grid-cols-[20px_minmax(0,300px)_minmax(0,1fr)_auto_72px] items-center gap-4 px-6 transition-colors duration-[120ms] hover:bg-paper-2',
        selected && 'bg-paper-3 hover:bg-paper-3',
      )}
    >
      <AgentAvatar agent={run.agent} state={avatarState(run)} />
      <div className="flex min-w-0 flex-col">
        <Link to={`/runs/${run.id}`} onClick={(e) => e.stopPropagation()} className="truncate font-medium outline-offset-0 hover:underline">
          {label}
        </Link>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={sentence.text}
            initial={{ opacity: 0, filter: reduce ? 'none' : 'blur(2px)' }}
            animate={{ opacity: 1, filter: 'blur(0px)' }}
            exit={{ opacity: 0, transition: { duration: 0.12 } }}
            transition={{ duration: 0.22, ease: EASE_OUT }}
            className={cn('truncate text-meta', sentence.tone === 'alarm' ? 'text-alarm' : 'text-ink-2')}
          >
            {sentence.text}
          </motion.span>
        </AnimatePresence>
      </div>
      <CompactTrace run={run} events={events} />
      <div className="flex justify-end">
        <AnimatePresence initial={false}>
          {run.status === 'frozen' && run.incident_id && (
            <motion.div
              initial={{ opacity: 0, transform: 'scale(0.96)' }}
              animate={{ opacity: 1, transform: 'scale(1)' }}
              exit={{ opacity: 0, transition: { duration: 0.12 } }}
              transition={{ duration: 0.22, ease: EASE_OUT }}
            >
              <Button asChild variant="secondary" onClick={(e) => e.stopPropagation()}>
                <Link to={`/incidents/${run.incident_id}`}>Open incident</Link>
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <time dateTime={when} title={new Date(when).toLocaleString()} className="text-right text-meta text-ink-3 tabular">
        {relTime(when, now)}
      </time>
    </li>
  )
}

const MAX_STEPS = 5

/** Tool names in mono, `→` between, newest last; older fade to ink-3, the blocked one in alarm. */
function CompactTrace({ run, events }: { run: Run; events: MirageEvent[] }) {
  const all = steps(events, run.id)
  const shown = all.slice(-MAX_STEPS)
  const hidden = all.length - shown.length
  return (
    <ol className="flex min-w-0 items-center gap-1.5 overflow-hidden font-mono text-code whitespace-nowrap" aria-label="Tool calls">
      {hidden > 0 && <li className="font-sans text-meta text-ink-3 tabular">+{hidden}</li>}
      <AnimatePresence initial={false}>
        {shown.map((s, i) => (
          <motion.li
            key={s.callId}
            layout="position"
            initial={{ opacity: 0, transform: 'translateX(-8px)' }}
            animate={{ opacity: 1, transform: 'translateX(0px)' }}
            transition={{ duration: 0.22, ease: EASE_OUT }}
            className="flex items-center gap-1.5"
          >
            {(i > 0 || hidden > 0) && <span className="text-ink-3" aria-hidden>→</span>}
            <span
              className={cn(
                'transition-colors duration-[220ms]',
                s.blocked ? 'text-alarm' : i === shown.length - 1 && run.status === 'running' ? 'text-ink' : 'text-ink-3',
              )}
            >
              {s.tool}
              {s.blocked && <span className="sr-only"> (blocked)</span>}
            </span>
          </motion.li>
        ))}
      </AnimatePresence>
    </ol>
  )
}

function Skeleton() {
  return (
    <ul className="flex max-w-[1080px] flex-col py-2" aria-busy="true" aria-label="Loading runs">
      {[0, 1, 2].map((i) => (
        <li key={i} className="grid h-[52px] grid-cols-[20px_minmax(0,300px)_minmax(0,1fr)] items-center gap-4 px-6">
          <span className="size-5 rounded-full bg-paper-3" />
          <span className="flex flex-col gap-1.5">
            <span className="h-3 w-40 rounded bg-paper-3" />
            <span className="h-2.5 w-24 rounded bg-paper-2" />
          </span>
          <span className="h-3 w-64 rounded bg-paper-2" />
        </li>
      ))}
    </ul>
  )
}

const DEMO_AGENTS = ['meeting_assistant', 'support', 'invoicing']

function Empty({ text, action, onAction }: { text: string; action: string; onAction: () => void }) {
  return (
    <div className="mx-auto flex max-w-[420px] flex-col items-center gap-5 px-6 py-24 text-center">
      <div className="flex gap-3">
        {DEMO_AGENTS.map((a) => (
          <AgentAvatar key={a} agent={a} state="idle" size={32} />
        ))}
      </div>
      <p className="text-ink-2 text-balance">{text}</p>
      <Button variant="primary" onClick={onAction}>{action}</Button>
    </div>
  )
}

// App shell (DESIGN.md §7): sidebar, 52 px header with the status sentence, content.
import { AlertTriangle, LayoutList, Octagon, Search } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useMatches, useNavigate } from 'react-router'
import { useRuns } from '@/api/client'
import { useEventStream } from '@/api/stream'
import { useAsk } from '@/components/actions'
import { AgentAvatar } from '@/components/avatar'
import { CommandMenu } from '@/components/command-menu'
import { Kbd, Tooltip } from '@/components/ui/tooltip'
import { agentName, avatarState, fleetSentence, mostUrgent } from '@/lib/runs'
import { cn } from '@/lib/utils'

const typing = (e: KeyboardEvent) =>
  e.target instanceof HTMLElement && (e.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName))

export function Shell() {
  useEventStream()
  const [menu, setMenu] = useState(false)
  const navigate = useNavigate()
  const ask = useAsk()
  const title = (useMatches().at(-1)?.handle as { title?: string } | undefined)?.title ?? ''

  useEffect(() => {
    let g = 0
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setMenu((m) => !m)
      } else if (e.metaKey && e.shiftKey && (e.key === '.' || e.key === '>')) {
        e.preventDefault()
        ask('stop')
      } else if (typing(e) || e.metaKey || e.ctrlKey || document.querySelector('[role=dialog]')) {
        return
      } else if (e.key === 'g') {
        g = e.timeStamp
      } else if (e.timeStamp - g < 800 && (e.key === 'f' || e.key === 'i')) {
        navigate(e.key === 'f' ? '/' : '/incidents')
        g = 0
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [ask, navigate])

  return (
    <div className="flex h-dvh overflow-hidden bg-paper">
      <Sidebar onSearch={() => setMenu(true)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[52px] shrink-0 items-center justify-between gap-6 border-b border-line px-6">
          <h1 className="text-title font-semibold">{title}</h1>
          <StatusSentence />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <CommandMenu open={menu} onOpenChange={setMenu} />
    </div>
  )
}

/** The sentence is the status. It crossfades with a 2 px blur bridge when it changes (DESIGN.md §9). */
function StatusSentence() {
  const { data: runs } = useRuns()
  const reduce = useReducedMotion()
  const text = runs ? fleetSentence(runs) : ''
  const alarm = runs?.some((r) => r.status === 'frozen')
  return (
    <div className="relative min-w-0 text-right" aria-live="polite">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.p
          key={text}
          initial={{ opacity: 0, filter: reduce ? 'none' : 'blur(2px)' }}
          animate={{ opacity: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, filter: reduce ? 'none' : 'blur(2px)', transition: { duration: 0.12 } }}
          transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
          className={cn('truncate', alarm ? 'text-alarm' : 'text-ink-2')}
        >
          {text}
        </motion.p>
      </AnimatePresence>
    </div>
  )
}

function Sidebar({ onSearch }: { onSearch: () => void }) {
  const { data: runs = [] } = useRuns()
  const ask = useAsk()
  const agents = [...new Set(runs.map((r) => r.agent))]

  return (
    <nav
      aria-label="Main"
      className="flex w-[232px] shrink-0 flex-col gap-6 border-r border-line bg-paper-2 px-3 py-4 max-[1099px]:w-14 max-[1099px]:px-2"
    >
      <div className="flex h-7 items-center gap-2 px-2 max-[1099px]:px-1.5">
        <Logo />
        <span className="text-title font-semibold tracking-[-0.02em] text-mirage max-[1099px]:hidden">Mirage</span>
      </div>

      <div className="flex flex-col gap-0.5">
        <NavItem to="/" icon={<LayoutList />} end>Fleet</NavItem>
        <NavItem to="/incidents" icon={<AlertTriangle />}>Incidents</NavItem>
      </div>

      {agents.length > 0 && (
        <div className="flex min-h-0 flex-col gap-0.5">
          <h2 className="px-2 pb-1 text-meta text-ink-3 max-[1099px]:hidden">Agents</h2>
          {agents.map((agent) => {
            const mine = runs.filter((r) => r.agent === agent)
            const latest = mine.at(-1)!
            return (
              <NavItem key={agent} to={`/runs/${latest.id}`} icon={<AgentAvatar agent={agent} state={mostUrgent(mine.map(avatarState))} />}>
                {agentName(agent)}
              </NavItem>
            )
          })}
        </div>
      )}

      <div className="mt-auto flex flex-col gap-0.5">
        <SideButton icon={<Search />} onClick={onSearch} label="Search" hint="⌘K" />
        <Tooltip content={<>Halts every run and revokes all tokens <Kbd>⇧⌘.</Kbd></>}>
          <button
            type="button"
            onClick={() => ask('stop')}
            className="pressable flex h-8 items-center gap-2.5 rounded-control px-2 text-control font-medium text-alarm hover:bg-alarm-wash [&_svg]:size-4"
          >
            <Octagon aria-hidden />
            <span className="max-[1099px]:sr-only">Stop all</span>
          </button>
        </Tooltip>
      </div>
    </nav>
  )
}

function NavItem({ to, icon, end, children }: { to: string; icon: ReactNode; end?: boolean; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      end={end}
      title={typeof children === 'string' ? children : undefined}
      className={({ isActive }) =>
        cn(
          'pressable flex h-8 items-center gap-2.5 rounded-control px-2 text-control font-medium text-ink-2 hover:bg-paper-3 hover:text-ink [&_svg]:size-4',
          isActive && 'bg-paper-3 text-ink',
        )
      }
    >
      {icon}
      <span className="truncate max-[1099px]:sr-only">{children}</span>
    </NavLink>
  )
}

function SideButton({ icon, label, hint, onClick }: { icon: ReactNode; label: string; hint: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="pressable flex h-8 items-center gap-2.5 rounded-control px-2 text-control font-medium text-ink-2 hover:bg-paper-3 hover:text-ink [&_svg]:size-4"
    >
      {icon}
      <span className="flex-1 text-left max-[1099px]:sr-only">{label}</span>
      <Kbd>
        <span className="max-[1099px]:hidden">{hint}</span>
      </Kbd>
    </button>
  )
}

/** Two heat lines over a road: the mirage. */
function Logo() {
  return (
    <svg viewBox="0 0 24 24" className="size-5 shrink-0" aria-hidden>
      <rect width="24" height="24" rx="6" className="fill-mirage" />
      <path d="M5 14c2.3-1.6 4.7-1.6 7 0s4.7 1.6 7 0M5 10c2.3-1.6 4.7-1.6 7 0s4.7 1.6 7 0" fill="none" className="stroke-paper" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

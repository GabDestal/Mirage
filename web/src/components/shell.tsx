// App shell (DESIGN.md §7): sidebar, 52 px header with the status sentence, content.
import { AlertTriangle, ChartNoAxesColumn, ChevronDown, KeyRound, LayoutList, MessageSquarePlus, Octagon, Search, Unplug } from 'lucide-react'
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
        navigate(e.key === 'f' ? '/fleet' : '/incidents')
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
  const currentRun = useMatches().at(-1)?.params.id

  return (
    <nav
      aria-label="Main"
      className="flex w-[256px] shrink-0 flex-col border-r border-line bg-paper-2 max-[767px]:w-[64px]"
    >
      <div className="flex h-[72px] shrink-0 items-center gap-3 px-6 max-[767px]:min-h-[44px] max-[767px]:justify-center max-[767px]:px-0">
        <Logo />
        <span className="text-title font-semibold tracking-[-0.02em] max-[767px]:hidden">Mirage</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-6 max-[767px]:px-2">
        <div className="flex flex-col gap-1">
          <NavItem to="/" icon={<MessageSquarePlus />} end>Ask Mirage</NavItem>
          <NavItem to="/incidents" icon={<AlertTriangle />}>Incidents</NavItem>
        </div>

        <details open className="group mt-5">
          <summary
            title="Analytics"
            className="pressable flex h-[40px] cursor-pointer list-none items-center gap-3 rounded-control px-3 text-body text-ink-2 hover:bg-paper-3 hover:text-ink max-[767px]:min-h-[44px] max-[767px]:justify-center max-[767px]:px-0 [&::-webkit-details-marker]:hidden"
          >
            <ChartNoAxesColumn className="size-[18px] shrink-0" aria-hidden />
            <span className="flex-1 max-[767px]:sr-only">Analytics</span>
            <ChevronDown className="size-4 shrink-0 -rotate-90 group-open:rotate-0 max-[767px]:hidden" aria-hidden />
          </summary>
          <div className="ml-5 border-l border-line pl-3 max-[767px]:ml-0 max-[767px]:border-0 max-[767px]:pl-0">
            <NavItem to="/fleet" icon={<LayoutList />}>Fleet</NavItem>
          </div>
        </details>

        <details open className="group mt-5">
          <summary
            title="Integrations"
            className="pressable flex h-[40px] cursor-pointer list-none items-center gap-3 rounded-control px-3 text-body text-ink-2 hover:bg-paper-3 hover:text-ink max-[767px]:min-h-[44px] max-[767px]:justify-center max-[767px]:px-0 [&::-webkit-details-marker]:hidden"
          >
            <Unplug className="size-[18px] shrink-0" aria-hidden />
            <span className="flex-1 max-[767px]:sr-only">Integrations</span>
            <ChevronDown className="size-4 shrink-0 -rotate-90 group-open:rotate-0 max-[767px]:hidden" aria-hidden />
          </summary>
          <div className="ml-5 border-l border-line pl-3 max-[767px]:ml-0 max-[767px]:border-0 max-[767px]:pl-0">
            <Tooltip content="API-key management is coming soon.">
              <button
                type="button"
                aria-disabled="true"
                aria-label="API keys, coming soon"
                className="flex h-[40px] w-full cursor-default items-center gap-3 rounded-control px-3 text-body text-ink-2 max-[767px]:min-h-[44px] max-[767px]:justify-center max-[767px]:px-0"
              >
                <KeyRound className="hidden size-[18px] max-[767px]:block" aria-hidden />
                <span className="flex-1 text-left max-[767px]:sr-only">API keys</span>
                <span className="text-meta max-[767px]:hidden">Soon</span>
              </button>
            </Tooltip>
          </div>
        </details>

        <details open className="group mt-7">
          <summary
            title="Agents"
            className="pressable mb-2 flex h-8 cursor-pointer list-none items-center gap-2 rounded-control px-3 text-ink-2 hover:bg-paper-3 hover:text-ink max-[767px]:min-h-[44px] max-[767px]:justify-center max-[767px]:px-0 [&::-webkit-details-marker]:hidden"
          >
            <ChevronDown className="size-3.5 shrink-0 -rotate-90 group-open:rotate-0" aria-hidden />
            <span className="text-[11px] font-medium tracking-[0.04em] uppercase max-[767px]:sr-only">Agents</span>
            <span className="ml-auto text-meta tabular max-[767px]:hidden">{agents.length}</span>
          </summary>
          <div className="flex flex-col gap-1">
            {agents.map((agent) => {
              const mine = runs.filter((r) => r.agent === agent)
              const target = mine.find((r) => r.status === 'frozen') ?? mine.at(-1)!
              return (
                <NavItem key={agent} to={`/runs/${target.id}`} active={mine.some((r) => r.id === currentRun)} icon={<AgentAvatar agent={agent} state={mostUrgent(mine.map(avatarState))} />}>
                  {agentName(agent)}
                </NavItem>
              )
            })}
            {agents.length === 0 && <p className="px-3 py-2 text-meta text-ink-2 max-[767px]:sr-only">No agents connected yet.</p>}
          </div>
        </details>
      </div>

      <div className="flex shrink-0 flex-col gap-1 border-t border-line p-3 max-[767px]:p-2">
        <SideButton icon={<Search />} onClick={onSearch} label="Search" hint="⌘K" />
        <Tooltip content={<>Halts every run and revokes all tokens <Kbd>⇧⌘.</Kbd></>}>
          <button
            type="button"
            onClick={() => ask('stop')}
            title="Stop all"
            className="pressable flex h-[40px] items-center gap-3 rounded-control px-3 text-body text-alarm hover:bg-alarm-wash max-[767px]:min-h-[44px] max-[767px]:justify-center max-[767px]:px-0 [&_svg]:size-[18px]"
          >
            <Octagon aria-hidden />
            <span className="max-[767px]:sr-only">Stop all</span>
          </button>
        </Tooltip>
      </div>
    </nav>
  )
}

function NavItem({ to, icon, end, active, children }: { to: string; icon: ReactNode; end?: boolean; active?: boolean; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      end={end}
      aria-current={active ? 'page' : undefined}
      title={typeof children === 'string' ? children : undefined}
      className={({ isActive }) =>
        cn(
          'pressable flex h-[40px] items-center gap-3 rounded-control px-3 text-body text-ink-2 hover:bg-paper-3 hover:text-ink max-[767px]:min-h-[44px] max-[767px]:justify-center max-[767px]:px-0',
          (isActive || active) && 'bg-paper-3 font-medium text-ink',
        )
      }
    >
      <span className="flex size-5 shrink-0 items-center justify-center [&>svg]:size-[18px]">{icon}</span>
      <span className="truncate max-[767px]:sr-only">{children}</span>
    </NavLink>
  )
}

function SideButton({ icon, label, hint, onClick }: { icon: ReactNode; label: string; hint: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      className="pressable flex h-[40px] items-center gap-3 rounded-control px-3 text-body text-ink-2 hover:bg-paper-3 hover:text-ink max-[767px]:min-h-[44px] max-[767px]:justify-center max-[767px]:px-0 [&_svg]:size-[18px]"
    >
      {icon}
      <span className="flex-1 text-left max-[767px]:sr-only">{label}</span>
      <span className="max-[767px]:hidden"><Kbd>{hint}</Kbd></span>
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

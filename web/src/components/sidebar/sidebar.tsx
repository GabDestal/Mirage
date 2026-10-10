// Adapted from Opereit dashboard sidebar at 0a7a79fcab2c3d4c08156e81040302ffcdc473ce.
import { Collapsible } from '@base-ui/react/collapsible'
import { LayoutList, OctagonAlert, Play } from 'lucide-react'
import { NavLink, useLocation, useMatches } from 'react-router'
import { useEvents, useIncidents, useRuns } from '@/api/client'
import { useAsk } from '@/components/actions'
import { AgentAvatar } from '@/components/avatar'
import { Kbd, Tooltip } from '@/components/ui/tooltip'
import { agentName, avatarState, mostUrgent, resumeAllOn } from '@/lib/runs'
import { cn } from '@/lib/utils'
import { MascotAskIcon } from './icons/mascot-ask'
import { ChevronRightMediumIcon } from './icons/chevron-right-medium'
import { MagnifierIcon } from './icons/magnifier'
import { NAV_ITEMS, type NavItem } from './nav-links'
import { SidebarSection } from './sidebar-section'

export const Sidebar = ({ onSearch }: { onSearch: () => void }) => {
  const ask = useAsk()
  const { data: events = [] } = useEvents()
  const { data: runs = [] } = useRuns()
  const { data: incidents = [] } = useIncidents()
  const resumable = resumeAllOn(runs, incidents, events)

  return (
    <aside aria-label="Main" className="mirage-sidebar flex h-full w-(--sidebar-width) flex-col overflow-hidden border-r border-r-neutral-200 bg-neutral-50 antialiased">
      <div className="sidebar-brand flex items-center justify-between gap-1.5 px-3.5 pt-3.5 pb-5">
        <img className="sidebar-mark" src="/brand/mirage-mark.svg" width="72" height="43" alt="Mirage" />
      </div>
      <div className="sidebar-scroll min-h-0 flex-1 overflow-y-auto px-2.5">
        <nav aria-label="Assistant" className="pb-3">
          <ul>
            <li>
              <NavLink to="/" end title="Ask Miragio" className={NAV_LINK_CLASS_NAME}>
                <MascotAskIcon className="size-4 shrink-0" aria-hidden />
                <span className="sidebar-label min-w-0 truncate text-sm leading-5">Ask Miragio</span>
              </NavLink>
            </li>
          </ul>
        </nav>
        <nav aria-label="Navigation" className="pb-5">
          <NavItemList items={[
            { icon: LayoutList, labelKey: 'Fleet', to: '/fleet', children: [] },
            ...NAV_ITEMS,
          ]} />
        </nav>
        <AgentsSection />
      </div>
      <div className="sidebar-footer border-t !border-t-neutral-200 p-2">
        <ul className="flex flex-col gap-0.5">
          <li>
            <button type="button" title="Search" onClick={onSearch} className={cn(NAV_LINK_CLASS_NAME, 'w-full')}>
              <MagnifierIcon className="size-4 shrink-0" aria-hidden />
              <span className="sidebar-label min-w-0 truncate text-sm leading-5">Search</span>
              <kbd className="sidebar-hint ml-auto font-mono text-[10px]">⌘K</kbd>
            </button>
          </li>
          <li>
            {resumable ? (
              <Tooltip content="Lifts Stop all and restarts every halted agent">
                <button type="button" title="Resume all" onClick={() => ask('resumeAll')} className={cn(NAV_LINK_CLASS_NAME, 'w-full')}>
                  <Play className="size-4 shrink-0" aria-hidden />
                  <span className="sidebar-label min-w-0 truncate text-sm leading-5">Resume all</span>
                </button>
              </Tooltip>
            ) : <Tooltip content={<>Halts every run and revokes all tokens <Kbd>⇧⌘.</Kbd></>}>
              <button type="button" title="Stop all" onClick={() => ask('stop')} className={cn(NAV_LINK_CLASS_NAME, 'sidebar-stop w-full')}>
                <OctagonAlert className="size-4 shrink-0" aria-hidden />
                <span className="sidebar-label min-w-0 truncate text-sm leading-5">Stop all</span>
              </button>
            </Tooltip>}
          </li>
        </ul>
      </div>
    </aside>
  )
}

const NavItemList = ({ items }: { items: NavItem[] }) => (
  <ul className="flex flex-col gap-0.5">
    {items.map((item) => (
      <li key={item.labelKey}>
        {item.children.length ? <NavItemGroup item={item} childItems={item.children} /> : <NavItemLink item={item} />}
      </li>
    ))}
  </ul>
)

const NavItemContent = ({ item: { icon: Icon, mobileIcon: MobileIcon, labelKey }, hasChildren }: { item: NavItem; hasChildren?: boolean }) => (
  <>
    {Icon ? <Icon className={cn('size-4 shrink-0', MobileIcon && 'hidden md:block')} aria-hidden /> : null}
    {MobileIcon ? <MobileIcon className="sidebar-mobile-icon size-4 shrink-0" aria-hidden /> : null}
    <span className="sidebar-label min-w-0 truncate text-sm leading-5">{labelKey}</span>
    {hasChildren ? (
      <ChevronRightMediumIcon className="sidebar-chevron ml-auto size-3.5 shrink-0 transition-transform duration-150 ease-out-strong group-data-[panel-open]:rotate-90 motion-reduce:transition-none" aria-hidden />
    ) : null}
  </>
)

const NavItemLink = ({ item }: { item: NavItem }) => item.disabled ? (
  <Tooltip content="API-key management is coming soon.">
    <button type="button" aria-disabled="true" aria-label="API keys, coming soon" title="API keys, coming soon" className={cn(NAV_LINK_CLASS_NAME, 'sidebar-disabled w-full')}>
      <NavItemContent item={item} />
    </button>
  </Tooltip>
) : item.to ? (
  <NavLink to={item.to} title={item.labelKey} className={NAV_LINK_CLASS_NAME}>
    <NavItemContent item={item} />
  </NavLink>
) : null

const NavItemGroup = ({ item, childItems }: { item: NavItem; childItems: NavItem[] }) => {
  const { pathname } = useLocation()
  const hasActiveChild = childItems.some((child) => child.to !== undefined && pathname.startsWith(child.to))

  return (
    <Collapsible.Root defaultOpen={hasActiveChild}>
      <Collapsible.Trigger title={item.labelKey} data-active-child={hasActiveChild ? '' : undefined} className={cn(NAV_LINK_CLASS_NAME, NAV_LINK_ACTIVE_CHILD_CLASS_NAME, 'group w-full')}>
        <NavItemContent item={item} hasChildren />
      </Collapsible.Trigger>
      <Collapsible.Panel className="h-[var(--collapsible-panel-height)] overflow-hidden transition-[height,opacity] duration-150 ease-out-strong data-ending-style:h-0 data-ending-style:opacity-0 data-ending-style:duration-100 data-starting-style:h-0 data-starting-style:opacity-0 motion-reduce:transition-[opacity]">
        <ul className="sidebar-children relative ml-4 flex flex-col gap-0.5 pt-0.5 pl-2.5 before:absolute before:top-0 before:bottom-1 before:left-0 before:w-px before:bg-neutral-200 before:content-['']">
          {childItems.map((child) => <li key={child.labelKey}><NavItemLink item={child} /></li>)}
        </ul>
      </Collapsible.Panel>
    </Collapsible.Root>
  )
}

const AgentsSection = () => {
  const { data: runs = [] } = useRuns()
  const agents = [...new Set(runs.map((r) => r.agent))]
  const currentRun = useMatches().at(-1)?.params.id

  return (
    <SidebarSection label="Agents">
      <ul className="flex flex-col gap-0.5">
        {agents.map((agent) => {
          const mine = runs.filter((r) => r.agent === agent)
          const target = mine.find((r) => r.status === 'frozen') ?? mine.at(-1)!
          return (
            <li key={agent}>
              <NavLink to={`/runs/${target.id}`} title={agentName(agent)} aria-current={mine.some((r) => r.id === currentRun) ? 'page' : undefined} className={NAV_LINK_CLASS_NAME}>
                <AgentAvatar agent={agent} state={mostUrgent(mine.map(avatarState))} />
                <span className="sidebar-label min-w-0 truncate text-sm leading-5">{agentName(agent)}</span>
              </NavLink>
            </li>
          )
        })}
        {agents.length === 0 && <li className="sidebar-label px-2 text-sm leading-5 text-neutral-600">No agents connected yet.</li>}
      </ul>
    </SidebarSection>
  )
}

export const NAV_LINK_CLASS_NAME =
  'flex h-7.5 items-center gap-2.5 px-2 rounded-lg text-neutral-600 hover:bg-neutral-200/50 hover:text-neutral-950 aria-[current=page]:bg-neutral-200/85 aria-[current=page]:text-neutral-950 focus-visible:outline-none focus-visible:inset-ring-1 focus-visible:inset-ring-brand-blue-500 text-sm'

const NAV_LINK_ACTIVE_CHILD_CLASS_NAME =
  'not-data-[panel-open]:data-[active-child]:bg-neutral-200/85 not-data-[panel-open]:data-[active-child]:text-neutral-950'

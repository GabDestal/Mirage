// ⌘K: jump anywhere, run any action (DESIGN.md §11). Never animated (§9).
import { Command } from 'cmdk'
import { ArrowRight, OctagonAlert, Play, Search, ShieldOff, Snowflake } from 'lucide-react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { useEvents, useIncidents, useRuns } from '@/api/client'
import { useAsk } from '@/components/actions'
import { AgentAvatar } from '@/components/avatar'
import { avatarState, canResume, resumeAllOn, resumeBlock, runLabel } from '@/lib/runs'

export function CommandMenu({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const ask = useAsk()
  const { data: runs = [] } = useRuns()
  const { data: incidents = [] } = useIncidents()
  const { data: events = [] } = useEvents()
  const resumable = resumeAllOn(runs, incidents, events)
  const run = (fn: () => void) => () => {
    onOpenChange(false)
    fn()
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command menu"
      overlayClassName="fixed inset-0 z-40 bg-ink/10"
      contentClassName="fixed top-[18vh] left-1/2 z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-node bg-paper shadow-float"
    >
      <div className="flex items-center gap-2 border-b border-line px-4">
        <Search className="size-4 text-ink-3" aria-hidden />
        <Command.Input placeholder="Search runs, pages, actions" className="h-12 flex-1 bg-transparent outline-none" />
      </div>
      <Command.List className="max-h-[360px] overflow-y-auto p-2 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-meta [&_[cmdk-group-heading]]:text-ink-3">
        <Command.Empty className="px-2 py-6 text-center text-ink-2">Nothing matches.</Command.Empty>

        <Command.Group heading="Actions">
          {runs.filter((r) => r.status === 'frozen').map((r) => (
            <Item key={`u${r.id}`} icon={<Snowflake />} onSelect={run(() => ask('unfreeze', r))} hint="⌘U">
              Unfreeze {runLabel(r, runs)}
            </Item>
          ))}
          {runs.filter((r) => r.status === 'frozen' || r.status === 'running').map((r) => (
            <Item key={`k${r.id}`} icon={<ShieldOff />} onSelect={run(() => ask('kill', r))} hint="⌘⌫">
              Kill {runLabel(r, runs)}
            </Item>
          ))}
          {runs.filter((r) => canResume(r, runs) && !resumeBlock(r, incidents)).map((r) => (
            <Item key={`r${r.id}`} icon={<Play />} onSelect={run(() => ask('resume', r))}>
              Resume {runLabel(r, runs)}
            </Item>
          ))}
          {resumable ? (
            <Item icon={<Play />} onSelect={run(() => ask('resumeAll'))}>Resume all agents</Item>
          ) : (
            <Item icon={<OctagonAlert />} onSelect={run(() => ask('stop'))} hint="⇧⌘.">
              <span className="text-alarm">Stop all agents</span>
            </Item>
          )}
        </Command.Group>

        <Command.Group heading="Go to">
          <Item icon={<ArrowRight />} onSelect={run(() => navigate('/'))} hint="⌘1">Ask Miragio</Item>
          <Item icon={<ArrowRight />} onSelect={run(() => navigate('/fleet'))} hint="⌘2">Fleet</Item>
          <Item icon={<ArrowRight />} onSelect={run(() => navigate('/incidents'))} hint="⌘3">Incidents</Item>
          <Item icon={<ArrowRight />} onSelect={run(() => navigate('/integrations'))} hint="⌘4">Integrations & API Keys</Item>
          {runs.map((r) => (
            <Item key={r.id} icon={<AgentAvatar agent={r.agent} state={avatarState(r)} />} value={`${runLabel(r, runs)} ${r.id}`} onSelect={run(() => navigate(`/runs/${r.id}`))}>
              {runLabel(r, runs)} <span className="font-mono text-code text-ink-3">{r.id}</span>
            </Item>
          ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  )
}

function Item({ icon, hint, children, ...props }: { icon: ReactNode; hint?: string; children: ReactNode; value?: string; onSelect: () => void }) {
  return (
    <Command.Item
      {...props}
      className="flex h-9 cursor-pointer items-center gap-3 rounded-control px-2 text-ink data-[selected=true]:bg-paper-2 [&_svg]:size-4 [&_svg]:text-ink-3"
    >
      {icon}
      <span className="flex-1 truncate">{children}</span>
      {hint && <kbd className="font-sans text-meta text-ink-3">{hint}</kbd>}
    </Command.Item>
  )
}

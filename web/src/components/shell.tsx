import { useEffect, useState } from 'react'
import { Outlet, useMatches, useNavigate } from 'react-router'
import { useEventStream } from '@/api/stream'
import { useAsk } from '@/components/actions'
import { Sidebar } from '@/components/sidebar/sidebar'
import { CommandMenu } from '@/components/command-menu'
import { Tooltip } from '@/components/ui/tooltip'
import { isDemo } from '@/lib/demo'
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
    const onKey = (e: KeyboardEvent) => {
      if (typing(e) || e.altKey || document.querySelector('[role=dialog]')) return
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setMenu((m) => !m)
      } else if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === '.' || e.key === '>')) {
        e.preventDefault()
        ask('stop')
      } else if ((e.metaKey || e.ctrlKey) && !e.shiftKey) {
        const path = e.key === '1' ? '/' : e.key === '2' ? '/fleet' : e.key === '3' ? '/incidents' : e.key === '4' ? '/integrations' : undefined
        if (path) {
          e.preventDefault()
          navigate(path)
        }
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [ask, navigate])

  return (
    <div className={cn('flex h-dvh overflow-hidden bg-paper', title === 'Chat' && 'shell--chat')}>
      <Sidebar onSearch={() => setMenu(true)} />
      <div className="flex min-w-0 flex-1 flex-col">
        {isDemo && <div className="border-b border-neutral-200 bg-neutral-50 px-4 py-2 text-xs text-neutral-600">
          <Tooltip side="bottom" content={<span className="max-w-64 text-pretty">Agents and incident evidence are recorded or simulated. Miragio uses real Bedrock, MCP tools and human approvals.</span>}>
            <span tabIndex={0} className="rounded-sm focus-visible:outline focus-visible:outline-brand-blue-500">Demo background · Live Miragio</span>
          </Tooltip>
        </div>}
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <CommandMenu open={menu} onOpenChange={setMenu} />
    </div>
  )
}

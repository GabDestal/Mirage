import { useEffect, useState } from 'react'
import { Outlet, useMatches, useNavigate } from 'react-router'
import { useRuns } from '@/api/client'
import { useEventStream } from '@/api/stream'
import { useAsk } from '@/components/actions'
import { Sidebar } from '@/components/sidebar/sidebar'
import { CommandMenu } from '@/components/command-menu'
import { cn } from '@/lib/utils'

const typing = (e: KeyboardEvent) =>
  e.target instanceof HTMLElement && (e.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName))

export function Shell() {
  useEventStream()
  const [menu, setMenu] = useState(false)
  const navigate = useNavigate()
  const ask = useAsk()
  const { data: runs = [] } = useRuns()
  const title = (useMatches().at(-1)?.handle as { title?: string } | undefined)?.title ?? ''

  useEffect(() => {
    let g = 0
    const onKey = (e: KeyboardEvent) => {
      if (typing(e) || e.altKey || document.querySelector('[role=dialog]')) {
        g = 0
        return
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setMenu((m) => !m)
      } else if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === '.' || e.key === '>')) {
        e.preventDefault()
        ask('stop')
      } else if (e.metaKey || e.ctrlKey) {
        g = 0
        return
      } else if (e.key === 'g') {
        g = e.timeStamp
      } else if (g > 0 && e.timeStamp - g < 800) {
        const path = e.key === 'a' ? '/' : e.key === 'f' ? '/fleet' : e.key === 'k' ? '/integrations' : e.key === 'i' ? '/incidents'
          : /^[1-9]$/.test(e.key) && runs[Number(e.key) - 1] ? `/runs/${runs[Number(e.key) - 1].id}` : undefined
        if (path) {
          e.preventDefault()
          navigate(path)
        }
        g = 0
      }
    }
    // Handle G K before Fleet's row-navigation K.
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [ask, navigate, runs])

  return (
    <div className={cn('flex h-dvh overflow-hidden bg-paper', title === 'Chat' && 'shell--chat')}>
      <Sidebar onSearch={() => setMenu(true)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <CommandMenu open={menu} onOpenChange={setMenu} />
    </div>
  )
}

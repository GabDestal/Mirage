import { useEffect, useState } from 'react'
import { Outlet, useMatches, useNavigate } from 'react-router'
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

// App shell (DESIGN.md §7): sidebar, 52 px header with the status sentence, content.
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Outlet, useMatches, useNavigate } from 'react-router'
import { useRuns } from '@/api/client'
import { useEventStream } from '@/api/stream'
import { useAsk } from '@/components/actions'
import { Sidebar } from '@/components/sidebar/sidebar'
import { CommandMenu } from '@/components/command-menu'
import { fleetSentence } from '@/lib/runs'
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

// Mirage hands the fix to the user's own coding agent: copy the prompt, open the agent, paste.
import { Copy, ExternalLink, X } from 'lucide-react'
import { Dialog } from 'radix-ui'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'

// Same URLs as engine/handoff.py. No prompt in the URL: neither agent documents a prefill param.
const AGENTS = [
  { name: 'Claude Code', url: 'https://claude.ai/code' },
  { name: 'Codex', url: 'https://chatgpt.com/codex/cloud' },
] as const

async function copy(prompt: string, agent?: string) {
  try {
    await navigator.clipboard.writeText(prompt)
    toast(agent ? `Prompt copied. Paste it into ${agent}.` : 'Prompt copied.')
  } catch { toast.error('Clipboard unavailable. Select and copy the prompt in the drawer.') }
}

// light: pin light tokens when opened from a page that ignores the app theme (chat).
export function HandoffDrawer({ open, onClose, prompt, error, light }: { open: boolean; onClose: () => void; prompt?: string; error?: string; light?: boolean }) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={`${light ? 'theme-light ' : ''}fixed inset-0 z-40 bg-ink/20 animate-[fade_var(--dur-fast)_var(--ease-out)]`} />
        <Dialog.Content className={`${light ? 'theme-light ' : ''}fixed inset-y-0 right-0 z-50 flex w-[min(520px,100vw)] flex-col gap-5 border-l border-line bg-paper p-6 text-ink shadow-float animate-[drawer_var(--dur-sheet)_var(--ease-drawer)]`}>
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1.5">
              <Dialog.Title className="text-title font-semibold">Hand off to coding agent</Dialog.Title>
              <Dialog.Description className="text-ink-2 text-pretty">
                Mirage doesn’t write the fix. Your coding agent does, then proves it with <code className="font-mono text-meta">mirage detonate</code> against this snapshot. You merge the PR.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild><Button variant="ghost" aria-label="Close" className="px-2"><X /></Button></Dialog.Close>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {AGENTS.map((agent) => (
              <Button key={agent.name} variant="primary" disabled={!prompt} onClick={() => {
                // Open first, inside the click, so the new tab is not treated as a popup.
                window.open(agent.url, '_blank', 'noopener,noreferrer')
                void copy(prompt!, agent.name)
              }}>Open in {agent.name}<ExternalLink /></Button>
            ))}
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-meta text-ink-2">This prompt includes access scoped to this incident. Share it only with your coding agent.</p>
              <Button disabled={!prompt} onClick={() => void copy(prompt!)}><Copy />Copy prompt</Button>
            </div>
            {error ? <p role="alert" className="text-alarm">{error}</p>
              : <pre tabIndex={0} aria-label="Handoff prompt" className="min-h-0 flex-1 overflow-auto rounded-control border border-line bg-paper-2 p-3 font-mono text-meta whitespace-pre-wrap text-ink outline-none focus-visible:border-ink">{prompt ?? 'Loading prompt…'}</pre>}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

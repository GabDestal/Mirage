// Radix tooltip, restyled: floats with the soft shadow, scales from the trigger (DESIGN.md §9).
import { Tooltip as T } from 'radix-ui'
import type { ReactNode } from 'react'

export const TooltipProvider = ({ children }: { children: ReactNode }) => (
  <T.Provider delayDuration={400} skipDelayDuration={300}>{children}</T.Provider>
)

export function Tooltip({ content, side = 'right', children }: { content: ReactNode; side?: 'top' | 'right' | 'bottom' | 'left'; children: ReactNode }) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={6}
          className="z-50 flex origin-(--radix-tooltip-content-transform-origin) items-center gap-2 rounded-control bg-paper px-2.5 py-1.5 text-meta text-ink shadow-float animate-[pop_160ms_var(--ease-out)] data-[state=instant-open]:animate-none"
        >
          {content}
        </T.Content>
      </T.Portal>
    </T.Root>
  )
}

/** A keyboard shortcut, as shown in tooltips and menus. */
export const Kbd = ({ children }: { children: ReactNode }) => (
  <kbd className="font-sans text-meta text-ink-3 tabular">{children}</kbd>
)

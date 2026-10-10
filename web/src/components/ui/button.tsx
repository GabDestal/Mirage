// shadcn-style button, restyled per DESIGN.md §11: 32 px, 13/500, ink primary, one per screen.
import { Slot } from 'radix-ui'
import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

const VARIANTS = {
  primary: 'bg-ink text-paper hover:bg-ink/85',
  secondary: 'border border-line bg-paper text-ink hover:bg-paper-2',
  ghost: 'text-ink-2 hover:bg-paper-2 hover:text-ink',
  destructive: 'text-alarm hover:bg-alarm-wash',
}

type Props = ComponentProps<'button'> & { variant?: keyof typeof VARIANTS; asChild?: boolean }

export function Button({ variant = 'secondary', asChild, className, ...props }: Props) {
  const Comp = asChild ? Slot.Root : 'button'
  return (
    <Comp
      className={cn(
        'pressable inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-control px-3 text-control font-medium whitespace-nowrap',
        'disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0',
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  )
}

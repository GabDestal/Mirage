// Temporary stand-in for web/src/agents/avatars.tsx (built in parallel). Same props, crude drawing.
import { cn } from '@/lib/utils'
import type { AvatarState } from '@/components/avatar'

export function AgentAvatar({ agent, state, size = 20 }: { agent: string; state: AvatarState; size?: 20 | 32 | 64 }) {
  return (
    <span
      role="img"
      aria-label={`${agent}, ${state}`}
      style={{ width: size, height: size, fontSize: size * 0.5 }}
      className={cn(
        'inline-grid shrink-0 place-items-center rounded-full bg-paper-3 font-medium text-ink-2 select-none',
        'transition-[color,background-color,box-shadow] duration-[240ms]',
        state === 'frozen' && 'bg-alarm-wash text-alarm ring-1 ring-alarm',
        state === 'killed' && 'text-ink-3 opacity-60',
        state === 'mirage' && 'bg-mirage-wash shimmer',
        state === 'idle' && 'text-ink-3',
      )}
    >
      {agent.charAt(0).toUpperCase()}
    </span>
  )
}

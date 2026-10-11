import type { ComponentType, SVGProps } from 'react'
import { KeyRound, ShieldCheck } from 'lucide-react'
import { IconAgentsIcon } from './icons/icon-agents'

export type NavItem = {
  icon?: ComponentType<SVGProps<SVGSVGElement>>
  labelKey: string
  to?: string
  disabled?: boolean
  mobileIcon?: ComponentType<SVGProps<SVGSVGElement>>
  children: NavItem[]
}

export const NAV_ITEMS: NavItem[] = [
  { icon: ShieldCheck, labelKey: 'Rules', mobileIcon: ShieldCheck, to: '/rules', children: [] },
  {
    icon: IconAgentsIcon,
    labelKey: 'API keys',
    mobileIcon: KeyRound,
    to: '/integrations',
    children: [],
  },
]

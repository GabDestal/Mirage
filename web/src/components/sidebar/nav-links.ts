import type { ComponentType, SVGProps } from 'react'
import { KeyRound } from 'lucide-react'
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
  {
    icon: IconAgentsIcon,
    labelKey: 'Integrations',
    mobileIcon: KeyRound,
    to: '/integrations',
    children: [],
  },
]

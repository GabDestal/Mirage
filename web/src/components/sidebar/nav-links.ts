import type { ComponentType, SVGProps } from 'react'
import { KeyRound, LayoutList } from 'lucide-react'
import { Chart5Icon } from './icons/chart5'
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
    icon: Chart5Icon,
    labelKey: 'Analytics',
    children: [{ labelKey: 'Fleet', to: '/fleet', mobileIcon: LayoutList, children: [] }],
  },
  {
    icon: IconAgentsIcon,
    labelKey: 'Integrations',
    children: [{ labelKey: 'API keys', disabled: true, mobileIcon: KeyRound, children: [] }],
  },
]

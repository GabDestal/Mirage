This sidebar reuses the Opereit dashboard implementation at
`0a7a79fcab2c3d4c08156e81040302ffcdc473ce` from
`apps/dashboard/src/ui/layout/sidebar/{sidebar.tsx,sidebar-section.tsx,nav-links.ts,carriers-section.tsx}`,
the actual SVGs from `src/ui/icons`, and the typography/palette from `src/index.css`.

`NAV_LINK_CLASS_NAME`, `NavItemGroup` and `SidebarSection` retain the source classes
and Base UI Collapsible primitive, including its active-child styling, keyboard
semantics and 150ms open / 100ms close transitions. `ease-out-strong` is undefined
in the source theme, so the source's effective Tailwind default easing remains.

Mirage supplies its logo, routes and run data. Agents use the carrier-list structure
with existing stateful Mirage avatars; Search and Stop all replace the account menu.
API keys is a disabled placeholder. Organization, permission and translation hooks
are unnecessary here. The existing accessible 64px mobile icon rail remains.

The scoped 256px width equals the source's 16rem at a 16px root; Mirage keeps its
14px root. Scoped 4px spacing, 14px/20px text and 450 weight preserve the source's
computed dimensions without changing other screens. Inter reuses Mirage's local
font; JetBrains Mono is copied from the source with its OFL license.

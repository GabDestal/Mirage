import { useId, type ReactNode } from "react";
import { Collapsible } from "@base-ui/react/collapsible";
import { ChevronRightMediumIcon } from "./icons/chevron-right-medium";

export const SidebarSection = ({
    label,
    action,
    children,
}: {
  label: string;
  action?: ReactNode;
  children: ReactNode;
}) => {
    const labelId = useId();

    return (
        <Collapsible.Root defaultOpen className="flex flex-col gap-2 pb-5">
            <div className="flex h-4 items-center gap-1.5 px-2">
                <Collapsible.Trigger title={label} className="group -mx-1 flex min-w-0 flex-1 items-center gap-1 rounded-md px-1 text-neutral-600 transition-colors duration-100 ease-out-strong hover:text-neutral-950 focus-visible:outline-none focus-visible:inset-ring-1 focus-visible:inset-ring-brand-blue-500">
                    <ChevronRightMediumIcon className="size-3 shrink-0 transition-transform duration-150 ease-out-strong group-data-[panel-open]:rotate-90 motion-reduce:transition-none" />
                    <span
                        id={labelId}
                        className="sidebar-label min-w-0 truncate text-left font-mono text-[10px] uppercase"
                    >
                        {label}
                    </span>
                </Collapsible.Trigger>
                {action}
            </div>
            <Collapsible.Panel className="h-[var(--collapsible-panel-height)] overflow-hidden transition-[height,opacity] duration-150 ease-out-strong data-ending-style:h-0 data-ending-style:opacity-0 data-ending-style:duration-100 data-starting-style:h-0 data-starting-style:opacity-0 motion-reduce:transition-[opacity]">
                <nav aria-labelledby={labelId}>{children}</nav>
            </Collapsible.Panel>
        </Collapsible.Root>
    );
};

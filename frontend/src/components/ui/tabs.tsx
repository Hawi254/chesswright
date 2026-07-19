import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"

import { cn } from "@/lib/utils"

function Tabs({ className, ...props }: TabsPrimitive.Root.Props) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn("flex flex-col gap-3", className)} {...props} />
}

function TabsList({ className, ...props }: TabsPrimitive.List.Props) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn("inline-flex items-center gap-1 border-b border-[var(--cw-line)]", className)}
      {...props}
    />
  )
}

function TabsTab({ className, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-tab"
      className={cn(
        "border-b-2 border-transparent px-3 py-2 font-condensed text-xs uppercase tracking-[0.08em] text-[var(--cw-muted)] transition-colors hover:text-[var(--cw-text)] data-active:border-[var(--cw-copper)] data-active:text-[var(--cw-copper)]",
        className,
      )}
      {...props}
    />
  )
}

function TabsPanel({ className, ...props }: TabsPrimitive.Panel.Props) {
  return <TabsPrimitive.Panel data-slot="tabs-panel" className={cn("mt-4", className)} {...props} />
}

export { Tabs, TabsList, TabsTab, TabsPanel }

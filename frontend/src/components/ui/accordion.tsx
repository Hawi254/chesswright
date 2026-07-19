import { Children, cloneElement, isValidElement, useState } from 'react'
import type { ReactElement, ReactNode } from 'react'

import { cn } from '@/lib/utils'

export interface AccordionProps {
  defaultOpen?: string[]
  children: ReactNode
}

export function Accordion({ defaultOpen = [], children }: AccordionProps) {
  const [openIds, setOpenIds] = useState<Set<string>>(new Set(defaultOpen))

  function toggle(value: string) {
    setOpenIds((prev) => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  return (
    <div className="flex flex-col gap-2">
      {Children.map(children, (child) => {
        if (!isValidElement(child)) return child
        const element = child as ReactElement<AccordionItemProps>
        return cloneElement(element, {
          isOpen: openIds.has(element.props.value),
          onToggle: () => toggle(element.props.value),
        })
      })}
    </div>
  )
}

export interface AccordionItemProps {
  value: string
  title: string
  children: ReactNode
  isOpen?: boolean
  onToggle?: () => void
}

export function AccordionItem({
  title,
  children,
  isOpen = false,
  onToggle,
}: AccordionItemProps) {
  return (
    <div className="rounded-md border border-[var(--cw-line)] bg-[var(--cw-panel)]">
      <button
        type="button"
        aria-expanded={isOpen}
        onClick={onToggle}
        className={cn(
          'flex w-full items-center justify-between px-4 py-3 text-left',
          'font-condensed text-xs uppercase tracking-[0.08em] text-[var(--cw-text)]',
        )}
      >
        {title}
        <span aria-hidden="true">{isOpen ? '−' : '+'}</span>
      </button>
      <div
        className="grid transition-[grid-template-rows] duration-200 ease-out"
        style={{ gridTemplateRows: isOpen ? '1fr' : '0fr' }}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="px-4 pb-4">{children}</div>
        </div>
      </div>
    </div>
  )
}

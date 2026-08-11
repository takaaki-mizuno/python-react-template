import { Search } from 'lucide-react'
import type { FormEvent, ReactNode } from 'react'

import { Input } from '@/components/atoms/input'
import { cn } from '@/lib/css'

type AdminCrudToolbarProps = {
  searchValue: string
  searchPlaceholder: string
  onSearchChange: (value: string) => void
  onSearchSubmit: () => void
  action: ReactNode
  children?: ReactNode
  className?: string
}

export function AdminCrudToolbar({
  searchValue,
  searchPlaceholder,
  onSearchChange,
  onSearchSubmit,
  action,
  children,
  className,
}: AdminCrudToolbarProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSearchSubmit()
  }

  return (
    <div
      className={cn(
        'flex flex-col gap-3 border-b bg-background px-4 py-4 sm:px-6 lg:flex-row lg:items-end lg:justify-between',
        className,
      )}
    >
      <div className="grid flex-1 gap-3 sm:grid-cols-[minmax(16rem,1fr)_auto_auto]">
        <form className="relative" onSubmit={handleSubmit}>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="ユーザー検索"
            className="pl-9"
            maxLength={320}
            placeholder={searchPlaceholder}
            value={searchValue}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </form>
        {children}
      </div>
      <div className="flex shrink-0 items-center justify-end">{action}</div>
    </div>
  )
}

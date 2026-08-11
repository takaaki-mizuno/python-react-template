import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/atoms/button'

type AdminPaginationProps = {
  offset: number
  limit: number
  total: number
  onOffsetChange: (offset: number) => void
}

export function AdminPagination({
  offset,
  limit,
  total,
  onOffsetChange,
}: AdminPaginationProps) {
  const start = total === 0 ? 0 : offset + 1
  const end = Math.min(total, offset + limit)
  const previousOffset = Math.max(0, offset - limit)
  const nextOffset = offset + limit
  const hasPrevious = offset > 0
  const hasNext = nextOffset < total

  return (
    <div className="flex items-center justify-between border-t px-4 py-3 text-sm sm:px-6">
      <p className="text-muted-foreground">
        {start}-{end} / {total}
      </p>
      <div className="flex items-center gap-2">
        <Button
          aria-label="前のページ"
          disabled={!hasPrevious}
          size="icon-sm"
          type="button"
          variant="outline"
          onClick={() => onOffsetChange(previousOffset)}
        >
          <ChevronLeft className="size-4" />
        </Button>
        <Button
          aria-label="次のページ"
          disabled={!hasNext}
          size="icon-sm"
          type="button"
          variant="outline"
          onClick={() => onOffsetChange(nextOffset)}
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  )
}

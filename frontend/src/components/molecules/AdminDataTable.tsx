import { useTranslation } from 'react-i18next'
import type { ReactNode } from 'react'

import { cn } from '@/lib/css'

export type AdminDataTableColumn<T> = {
  key: string
  header: string
  className?: string
  render: (row: T) => ReactNode
}

type AdminDataTableProps<T> = {
  columns: Array<AdminDataTableColumn<T>>
  rows: Array<T>
  getRowKey: (row: T) => string
  loading?: boolean
  emptyMessage: string
}

export function AdminDataTable<T>({
  columns,
  rows,
  getRowKey,
  loading = false,
  emptyMessage,
}: AdminDataTableProps<T>) {
  const { t } = useTranslation('admin')

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] border-collapse text-sm">
        <thead>
          <tr className="border-b bg-muted/40 text-left text-xs font-medium uppercase text-muted-foreground">
            {columns.map((column) => (
              <th
                key={column.key}
                className={cn('px-4 py-3', column.className)}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length > 0 ? (
            rows.map((row) => (
              <tr
                key={getRowKey(row)}
                className="border-b last:border-b-0 hover:bg-muted/30"
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn('px-4 py-3 align-middle', column.className)}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td
                className="px-4 py-12 text-center text-muted-foreground"
                colSpan={columns.length}
              >
                {loading ? t('common.loading') : emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

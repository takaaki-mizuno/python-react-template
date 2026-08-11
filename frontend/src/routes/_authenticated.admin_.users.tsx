import { createFileRoute, useNavigate } from '@tanstack/react-router'
import type { AdminUserSearchParams } from '@/lib/adminSearchParams'

import { AdminUsersPage } from '@/components/organisms/AdminUsers/AdminUsersPage'
import { parseAdminUserSearchParams } from '@/lib/adminSearchParams'
import { requirePermission } from '@/lib/authGuard'

const AdminUsersRoutePage = () => {
  const filters = Route.useSearch()
  const navigate = useNavigate({ from: '/admin/users' })

  return (
    <AdminUsersPage
      filters={filters}
      onFiltersChange={(nextFilters: AdminUserSearchParams) => {
        void navigate({ search: nextFilters })
      }}
    />
  )
}

export const Route = createFileRoute('/_authenticated/admin_/users')({
  beforeLoad: (options) => requirePermission('admin:access', options),
  validateSearch: parseAdminUserSearchParams,
  component: AdminUsersRoutePage,
})

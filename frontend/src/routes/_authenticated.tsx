import { Outlet, createFileRoute } from '@tanstack/react-router'

import { requireAuth } from '@/lib/authGuard'

export const Route = createFileRoute('/_authenticated')({
  beforeLoad: requireAuth,
  component: Outlet,
})

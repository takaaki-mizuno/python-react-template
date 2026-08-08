import { createFileRoute } from '@tanstack/react-router'

import { requirePermission } from '@/lib/authGuard'

const AdminPage = () => {
  return (
    <main className="landing-shell py-16">
      <div className="grid gap-6">
        <h1 className="text-3xl font-semibold text-landing-ink">管理</h1>
      </div>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/admin')({
  beforeLoad: (options) => requirePermission('admin:access', options),
  component: AdminPage,
})

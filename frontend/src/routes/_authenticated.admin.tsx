import { createFileRoute } from '@tanstack/react-router'

import { Card, CardContent, CardHeader } from '@/components/atoms/card'
import { requirePermission } from '@/lib/authGuard'

const AdminPage = () => {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
      <Card>
        <CardHeader>
          <h1 className="text-3xl font-semibold tracking-tight">管理</h1>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            管理者向け機能のプレースホルダーです。
          </p>
        </CardContent>
      </Card>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/admin')({
  beforeLoad: (options) => requirePermission('admin:access', options),
  component: AdminPage,
})

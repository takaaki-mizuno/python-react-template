import { Link, createFileRoute } from '@tanstack/react-router'
import { Users } from 'lucide-react'

import { Button } from '@/components/atoms/button'
import { requirePermission } from '@/lib/authGuard'

const AdminPage = () => {
  return (
    <main className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-10 sm:px-6 lg:px-8">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold tracking-normal">管理</h1>
        <p className="text-sm text-muted-foreground">
          管理者向け機能への入口です。
        </p>
      </div>
      <section className="grid gap-4 border-t py-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="grid gap-1">
            <h2 className="text-lg font-semibold">ユーザー管理</h2>
            <p className="text-sm text-muted-foreground">
              ユーザーの作成、検索、ロール変更、削除を行います。
            </p>
          </div>
          <Button asChild>
            <Link search={{ offset: 0 }} to="/admin/users">
              <Users className="size-4" />
              開く
            </Link>
          </Button>
        </div>
      </section>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/admin')({
  beforeLoad: (options) => requirePermission('admin:access', options),
  component: AdminPage,
})

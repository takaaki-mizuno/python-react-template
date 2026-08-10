import { Link, createFileRoute } from '@tanstack/react-router'

import { Badge } from '@/components/atoms/badge'
import { Button } from '@/components/atoms/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from '@/components/atoms/card'
import { useAuthSession } from '@/hooks/useAuthSession'
import { hasPermission } from '@/lib/permissions'

const AppPage = () => {
  const { user } = useAuthSession()

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="grid gap-6">
        <div className="space-y-3">
          <Badge variant="outline">ダッシュボード</Badge>
          <h1 className="text-3xl font-semibold tracking-tight">アプリ</h1>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <h2 className="text-lg font-semibold">アカウント</h2>
              <CardDescription>
                メールアドレスと削除操作を管理します。
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link to="/app/settings">アカウント設定</Link>
              </Button>
            </CardContent>
          </Card>
          {hasPermission(user, 'admin:access') ? (
            <Card>
              <CardHeader>
                <h2 className="text-lg font-semibold">管理</h2>
                <CardDescription>
                  管理者向けの操作領域へ移動します。
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline">
                  <Link to="/admin">管理画面を開く</Link>
                </Button>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/app')({
  component: AppPage,
})

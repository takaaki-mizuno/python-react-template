import { Link, createFileRoute } from '@tanstack/react-router'

import { useAuthSession } from '@/hooks/useAuthSession'
import { hasPermission } from '@/lib/permissions'

const AppPage = () => {
  const { user } = useAuthSession()

  return (
    <main className="landing-shell py-16">
      <div className="grid gap-6">
        <h1 className="text-3xl font-semibold text-landing-ink">アプリ</h1>
        <Link
          className="w-fit text-sm font-medium text-landing-accent underline-offset-4 hover:underline"
          to="/app/settings"
        >
          アカウント設定
        </Link>
        {hasPermission(user, 'admin:access') ? (
          <Link
            className="w-fit text-sm font-medium text-landing-accent underline-offset-4 hover:underline"
            to="/admin"
          >
            管理
          </Link>
        ) : null}
      </div>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/app')({
  component: AppPage,
})

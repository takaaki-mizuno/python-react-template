import { Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useAuthSession } from '@/hooks/useAuthSession'

export default function AuthMenu() {
  const navigate = useNavigate()
  const { user, logout } = useAuthSession()
  const [logoutError, setLogoutError] = useState<string | null>(null)

  const handleLogout = async () => {
    setLogoutError(null)

    try {
      await logout.mutateAsync()
      await navigate({ to: '/login', search: { redirect: '/app' } })
    } catch {
      setLogoutError(
        'ログアウトに失敗しました。時間をおいて再度お試しください。',
      )
    }
  }

  if (!user) {
    return (
      <>
        <Link
          className="site-nav-link"
          search={{ redirect: '/app' }}
          to="/login"
        >
          ログイン
        </Link>
        <Link
          className="site-nav-link"
          search={{ redirect: '/app' }}
          to="/register"
        >
          新規登録
        </Link>
      </>
    )
  }

  return (
    <div className="flex items-center gap-3">
      <span className="hidden text-sm text-landing-muted sm:inline">
        {user.email}
      </span>
      <button
        className="site-nav-link"
        disabled={logout.isPending}
        onClick={handleLogout}
        type="button"
      >
        ログアウト
      </button>
      {logoutError ? (
        <p className="text-sm text-red-600" role="alert">
          {logoutError}
        </p>
      ) : null}
    </div>
  )
}

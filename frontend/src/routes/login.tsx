import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'

import LoginForm from '@/components/organisms/Auth/LoginForm'
import { ApiError } from '@/lib/apiError'
import { loginWithPassword } from '@/lib/authApi'
import { queryKeys } from '@/lib/queryKeys'

function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { redirect } = Route.useSearch()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const login = useMutation({
    mutationFn: loginWithPassword,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.root })
      await navigate({ to: redirect })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) {
        setErrorMessage('メールアドレスまたはパスワードが正しくありません。')
        return
      }
      if (error instanceof ApiError && error.status === 422) {
        setErrorMessage('入力内容を確認してください。')
        return
      }
      setErrorMessage(
        'ログインに失敗しました。時間をおいて再度お試しください。',
      )
    },
  })

  return (
    <main className="landing-shell grid max-w-xl gap-6 py-16">
      <h1 className="text-3xl font-semibold text-landing-ink">ログイン</h1>
      <LoginForm
        errorMessage={errorMessage}
        isPending={login.isPending}
        onSubmit={(values) => {
          setErrorMessage(null)
          login.mutate(values)
          return Promise.resolve()
        }}
      />
    </main>
  )
}

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>) => {
    const allowList = new Set(['/app'])
    const candidate =
      typeof search.redirect === 'string' ? search.redirect : '/app'
    return {
      redirect: allowList.has(candidate) ? candidate : '/app',
    }
  },
  component: LoginPage,
})

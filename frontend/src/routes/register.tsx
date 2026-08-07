import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Link,
  createFileRoute,
  redirect,
  useNavigate,
} from '@tanstack/react-router'

import { OidcProviderButton } from '@/components/molecules/OidcProviderButton'
import { AuthFormShell } from '@/components/organisms/Auth/AuthFormShell'
import RegisterForm from '@/components/organisms/Auth/RegisterForm'
import { toUserMessage } from '@/lib/apiError'
import {
  currentUserQueryOptions,
  fetchOidcProviders,
  registerWithPassword,
  startOidcLogin,
} from '@/lib/authApi'
import { normalizeRedirectHref } from '@/lib/authRedirect'
import { queryKeys } from '@/lib/queryKeys'

function RegisterPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { redirect: redirectHref } = Route.useSearch()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const providers = useQuery({
    queryKey: queryKeys.auth.oidcProviders,
    queryFn: fetchOidcProviders,
    retry: false,
  })

  const register = useMutation({
    mutationFn: registerWithPassword,
    onSuccess: async (user) => {
      queryClient.setQueryData(queryKeys.auth.me, user)
      await navigate({ href: redirectHref })
    },
    onError: (error) => {
      setErrorMessage(
        toUserMessage(error, {
          code: {
            EMAIL_ALREADY_REGISTERED:
              'このメールアドレスはすでに登録されています。ログインしてください。',
            REGISTER_RATE_LIMITED:
              '登録試行回数が多すぎます。時間をおいて再度お試しください。',
            WEAK_PASSWORD: 'パスワードの条件を確認してください。',
          },
          status: { 422: '入力内容を確認してください。' },
          fallback: '登録に失敗しました。時間をおいて再度お試しください。',
        }),
      )
    },
  })

  return (
    <AuthFormShell title="新規登録">
      <RegisterForm
        errorMessage={errorMessage}
        isPending={register.isPending}
        onSubmit={(values) => {
          setErrorMessage(null)
          register.mutate(values)
        }}
      />
      {providers.data && providers.data.length > 0 ? (
        <div className="grid gap-3">
          {providers.data.map((provider) => (
            <OidcProviderButton
              key={provider.providerId}
              isDisabled={providers.isFetching}
              onClick={() => startOidcLogin(provider.providerId, redirectHref)}
              provider={provider}
            />
          ))}
        </div>
      ) : null}
      <p className="text-sm text-landing-muted">
        すでにアカウントをお持ちの方は{' '}
        <Link
          className="font-medium text-landing-accent underline-offset-4 hover:underline"
          search={{ redirect: redirectHref }}
          to="/login"
        >
          ログイン
        </Link>
      </p>
    </AuthFormShell>
  )
}

export const Route = createFileRoute('/register')({
  validateSearch: (search: Record<string, unknown>) => {
    return {
      redirect: normalizeRedirectHref(search.redirect),
    }
  },
  beforeLoad: async ({ context, search }) => {
    let user = null
    try {
      user = await context.queryClient.fetchQuery(currentUserQueryOptions())
    } catch {
      return
    }

    if (user) {
      throw redirect({ href: search.redirect })
    }
  },
  component: RegisterPage,
})

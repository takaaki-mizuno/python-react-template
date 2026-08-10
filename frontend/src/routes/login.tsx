import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Link,
  createFileRoute,
  redirect,
  useNavigate,
} from '@tanstack/react-router'

import { Button } from '@/components/atoms/button'
import { Separator } from '@/components/atoms/separator'
import { OidcProviderButton } from '@/components/molecules/OidcProviderButton'
import { AuthFormShell } from '@/components/organisms/Auth/AuthFormShell'
import LoginForm from '@/components/organisms/Auth/LoginForm'
import { toUserMessage } from '@/lib/apiError'
import {
  currentUserQueryOptions,
  fetchOidcProviders,
  loginWithPassword,
  startOidcLogin,
} from '@/lib/authApi'
import { normalizeRedirectHref } from '@/lib/authRedirect'
import { queryKeys } from '@/lib/queryKeys'

function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { oidcError, redirect: redirectHref } = Route.useSearch()
  const [errorMessage, setErrorMessage] = useState<string | null>(() =>
    oidcLoginErrorMessage(oidcError),
  )
  const providers = useQuery({
    queryKey: queryKeys.auth.oidcProviders,
    queryFn: fetchOidcProviders,
    retry: false,
  })

  const login = useMutation({
    mutationFn: loginWithPassword,
    onSuccess: async (user) => {
      queryClient.setQueryData(queryKeys.auth.me, user)
      await navigate({ href: redirectHref })
    },
    onError: (error) => {
      setErrorMessage(
        toUserMessage(error, {
          code: {
            INVALID_CREDENTIALS:
              'メールアドレスまたはパスワードが正しくありません。',
            LOGIN_RATE_LIMITED:
              'ログイン試行回数が多すぎます。時間をおいて再度お試しください。',
          },
          status: { 422: '入力内容を確認してください。' },
          fallback: 'ログインに失敗しました。時間をおいて再度お試しください。',
        }),
      )
    },
  })

  return (
    <AuthFormShell title="ログイン">
      <LoginForm
        errorMessage={errorMessage}
        isPending={login.isPending}
        onSubmit={(values) => {
          setErrorMessage(null)
          login.mutate(values)
        }}
      />
      {providers.data && providers.data.length > 0 ? (
        <div className="grid gap-3">
          <div className="flex items-center gap-3">
            <Separator className="flex-1" />
            <span className="text-xs text-muted-foreground">または</span>
            <Separator className="flex-1" />
          </div>
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
      <p className="text-sm text-muted-foreground">
        アカウントをお持ちでない方は{' '}
        <Button asChild className="h-auto p-0" variant="link">
          <Link search={{ redirect: redirectHref }} to="/register">
            アカウントを作成
          </Link>
        </Button>
      </p>
    </AuthFormShell>
  )
}

export const Route = createFileRoute('/login')({
  validateSearch: (
    search: Record<string, unknown>,
  ): { redirect: string; oidcError?: string } => {
    return {
      redirect: normalizeRedirectHref(search.redirect),
      ...(typeof search.oidcError === 'string'
        ? { oidcError: search.oidcError }
        : {}),
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
  component: LoginPage,
})

function oidcLoginErrorMessage(code: string | undefined): string | null {
  if (!code) {
    return null
  }
  const messages: Record<string, string> = {
    OIDC_IDENTITY_LINK_REQUIRED:
      '既存アカウントでログインしてから連携してください。',
    OIDC_IDENTITY_LINK_DISABLED:
      'このプロバイダーでは既存アカウントへの連携が許可されていません。',
    OIDC_EMAIL_NOT_VERIFIED:
      '確認済みメールアドレスを取得できなかったためログインできませんでした。',
    OIDC_PROVISIONING_DISABLED:
      'このプロバイダーでは新規アカウントを作成できません。',
    OIDC_AUTHORIZATION_RATE_LIMITED:
      '認証リクエストが多すぎます。時間をおいて再度お試しください。',
    OIDC_PROVIDER_UNAVAILABLE:
      '認証プロバイダーに接続できませんでした。時間をおいて再度お試しください。',
    OIDC_PROVIDER_METADATA_INVALID:
      '認証プロバイダー設定に問題があります。管理者に連絡してください。',
    OIDC_PROVIDER_ACCESS_DENIED:
      '認証プロバイダーでログインがキャンセルされました。',
    OIDC_IDENTITY_UNAVAILABLE:
      'このアカウントは現在利用できません。管理者に連絡してください。',
    OIDC_REAUTH_AUTHENTICATION_REQUIRED:
      '再認証のセッションが切れました。もう一度ログインしてください。',
  }
  return messages[code] ?? 'OAuth/OIDCログインに失敗しました。'
}

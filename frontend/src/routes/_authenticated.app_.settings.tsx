import { useState } from 'react'
import { Link, createFileRoute, useNavigate } from '@tanstack/react-router'

import type { AccountDeletionInvalidField } from '@/components/organisms/Auth/AccountDeletionPanel'
import type { AccountDeletionOidcReauthProvider } from '@/lib/apiError'
import { AccountDeletionPanel } from '@/components/organisms/Auth/AccountDeletionPanel'
import {
  ApiError,
  accountDeletionOidcReauthProviders,
  toUserMessage,
} from '@/lib/apiError'
import { startOidcReauth } from '@/lib/authApi'
import { useAccountDeletion } from '@/hooks/useAccountDeletion'
import { useAuthSession } from '@/hooks/useAuthSession'

type AccountDeletionErrorFeedback = {
  message: string
  invalidField: AccountDeletionInvalidField | null
  linkedProviders?: Array<AccountDeletionOidcReauthProvider>
}

const SettingsPage = () => {
  const navigate = useNavigate()
  const search = Route.useSearch()
  const { user } = useAuthSession()
  const [errorFeedback, setErrorFeedback] =
    useState<AccountDeletionErrorFeedback | null>(null)
  const [dismissedQueryFeedbackKey, setDismissedQueryFeedbackKey] = useState<
    string | null
  >(null)
  const accountDeletion = useAccountDeletion()
  const queryFeedback = accountDeletionQueryFeedback(search)
  const queryFeedbackKey = queryFeedback
    ? `${search.oidcError ?? ''}:${search.oidcReauth ?? ''}`
    : null
  const displayedQueryFeedback =
    queryFeedbackKey === dismissedQueryFeedbackKey ? null : queryFeedback
  const displayedFeedback = errorFeedback ?? displayedQueryFeedback

  if (!user) {
    return null
  }

  return (
    <main className="landing-shell py-12">
      <div className="grid max-w-xl gap-8">
        <div className="grid gap-2">
          <Link className="site-nav-link w-fit px-0" to="/app">
            アプリに戻る
          </Link>
          <h1 className="text-2xl font-semibold text-landing-ink">
            アカウント設定
          </h1>
        </div>
        <AccountDeletionPanel
          currentEmail={user.email}
          errorMessage={displayedFeedback?.message ?? null}
          invalidField={displayedFeedback?.invalidField ?? null}
          isPending={accountDeletion.isPending}
          linkedProviders={displayedFeedback?.linkedProviders ?? []}
          onFieldChange={(field) => {
            if (queryFeedbackKey) {
              setDismissedQueryFeedbackKey(queryFeedbackKey)
            }
            setErrorFeedback((current) =>
              current?.invalidField === field ? null : current,
            )
          }}
          onReauth={(providerId) => {
            startOidcReauth(providerId, '/app/settings')
          }}
          onSubmit={(payload) => {
            if (queryFeedbackKey) {
              setDismissedQueryFeedbackKey(queryFeedbackKey)
            }
            setErrorFeedback(null)
            accountDeletion.mutate(payload, {
              onSuccess: () => {
                void navigate({ to: '/' })
              },
              onError: (error) => {
                setErrorFeedback(toAccountDeletionErrorFeedback(error))
              },
            })
          }}
        />
      </div>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/app_/settings')({
  validateSearch: (
    search: Record<string, unknown>,
  ): { oidcError?: string; oidcReauth?: string } => ({
    ...(typeof search.oidcError === 'string'
      ? { oidcError: search.oidcError }
      : {}),
    ...(typeof search.oidcReauth === 'string'
      ? { oidcReauth: search.oidcReauth }
      : {}),
  }),
  component: SettingsPage,
})

function accountDeletionQueryFeedback(search: {
  oidcError?: string
  oidcReauth?: string
}): AccountDeletionErrorFeedback | null {
  if (search.oidcReauth === 'success') {
    return {
      message:
        '再認証が完了しました。もう一度アカウント削除を実行してください。',
      invalidField: null,
    }
  }
  if (!search.oidcError) {
    return null
  }
  const messages: Record<string, string> = {
    OIDC_REAUTH_SUBJECT_MISMATCH:
      '再認証されたアカウントが現在のユーザーと一致しません。',
    OIDC_REAUTH_STALE:
      '再認証の有効期限が切れています。もう一度お試しください。',
    OIDC_REAUTH_AUTH_TIME_REQUIRED:
      'このプロバイダーでは削除に必要な再認証時刻を確認できませんでした。',
    OIDC_PROVIDER_ACCESS_DENIED:
      '認証プロバイダーで再認証がキャンセルされました。',
    OIDC_PROVIDER_UNAVAILABLE:
      '認証プロバイダーに接続できませんでした。時間をおいて再度お試しください。',
    OIDC_IDENTITY_UNAVAILABLE:
      'この連携アカウントは現在利用できません。管理者に連絡してください。',
  }
  return {
    message:
      messages[search.oidcError] ??
      '再認証に失敗しました。もう一度お試しください。',
    invalidField: null,
  }
}

function toAccountDeletionErrorFeedback(
  error: unknown,
): AccountDeletionErrorFeedback {
  const validationField = accountDeletionValidationField(error)
  if (validationField) {
    return {
      message:
        validationField === 'confirmEmail'
          ? 'メールアドレスを入力してください。'
          : '現在のパスワードを入力してください。',
      invalidField: validationField,
    }
  }

  const retryAfterMessage = accountDeletionRetryAfterMessage(error)
  if (retryAfterMessage) {
    return {
      message: retryAfterMessage,
      invalidField: null,
    }
  }

  return {
    message: toUserMessage(error, {
      code: {
        ACCOUNT_DELETION_CONFIRMATION_MISMATCH:
          '入力されたメールアドレスが現在のアカウントと一致しません。',
        ACCOUNT_DELETION_REAUTH_REQUIRED:
          'アカウント削除には現在のパスワード入力が必要です。',
        ACCOUNT_DELETION_INVALID_PASSWORD: '現在のパスワードが一致しません。',
        ACCOUNT_DELETION_REAUTH_RATE_LIMITED:
          '確認の試行回数が多すぎます。時間をおいて再度お試しください。',
        ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED:
          accountDeletionOidcReauthProviders(error).length > 0
            ? 'アカウント削除にはOAuth/OIDC再認証が必要です。'
            : '再認証できる連携プロバイダーがありません。サポートに連絡してください。',
      },
      status: { 422: '入力内容を確認してください。' },
      fallback:
        'アカウント削除に失敗しました。時間をおいて再度お試しください。',
    }),
    invalidField: accountDeletionInvalidField(error),
    linkedProviders: accountDeletionOidcReauthProviders(error),
  }
}

function accountDeletionRetryAfterMessage(error: unknown): string | null {
  if (
    !(error instanceof ApiError) ||
    error.status !== 429 ||
    error.code !== 'ACCOUNT_DELETION_REAUTH_RATE_LIMITED' ||
    error.retryAfterSeconds === null
  ) {
    return null
  }

  return `確認の試行回数が多すぎます。${formatRetryAfter(error.retryAfterSeconds)}に再度お試しください。`
}

function formatRetryAfter(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}秒後`
  }

  const minutes = Math.ceil(seconds / 60)
  if (minutes < 60) {
    return `${minutes}分後`
  }

  return `${Math.ceil(minutes / 60)}時間後`
}

function accountDeletionValidationField(
  error: unknown,
): AccountDeletionInvalidField | null {
  if (!(error instanceof ApiError) || error.status !== 422) {
    return null
  }
  for (const detail of error.details) {
    const field = validationDetailField(detail)
    if (field === 'confirmEmail' || field === 'password') {
      return field
    }
  }
  return null
}

function validationDetailField(detail: unknown): string | null {
  if (typeof detail !== 'object' || detail === null || Array.isArray(detail)) {
    return null
  }
  const loc = (detail as { loc?: unknown }).loc
  if (!Array.isArray(loc)) {
    return null
  }
  const field = loc.at(-1)
  return typeof field === 'string' ? field : null
}

function accountDeletionInvalidField(
  error: unknown,
): AccountDeletionInvalidField | null {
  if (!(error instanceof ApiError)) {
    return null
  }
  if (error.code === 'ACCOUNT_DELETION_CONFIRMATION_MISMATCH') {
    return 'confirmEmail'
  }
  if (
    error.code === 'ACCOUNT_DELETION_REAUTH_REQUIRED' ||
    error.code === 'ACCOUNT_DELETION_INVALID_PASSWORD'
  ) {
    return 'password'
  }
  return null
}

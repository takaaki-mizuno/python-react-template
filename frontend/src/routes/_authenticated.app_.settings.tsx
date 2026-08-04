import { useState } from 'react'
import { Link, createFileRoute, useNavigate } from '@tanstack/react-router'

import type { AccountDeletionInvalidField } from '@/components/organisms/Auth/AccountDeletionPanel'
import { AccountDeletionPanel } from '@/components/organisms/Auth/AccountDeletionPanel'
import { ApiError, toUserMessage } from '@/lib/apiError'
import { useAccountDeletion } from '@/hooks/useAccountDeletion'
import { useAuthSession } from '@/hooks/useAuthSession'

type AccountDeletionErrorFeedback = {
  message: string
  invalidField: AccountDeletionInvalidField | null
}

const SettingsPage = () => {
  const navigate = useNavigate()
  const { user } = useAuthSession()
  const [errorFeedback, setErrorFeedback] =
    useState<AccountDeletionErrorFeedback | null>(null)
  const accountDeletion = useAccountDeletion()

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
          errorMessage={errorFeedback?.message ?? null}
          invalidField={errorFeedback?.invalidField ?? null}
          isPending={accountDeletion.isPending}
          onSubmit={(payload) => {
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
  component: SettingsPage,
})

function toAccountDeletionErrorFeedback(
  error: unknown,
): AccountDeletionErrorFeedback {
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
      },
      status: { 422: '入力内容を確認してください。' },
      fallback:
        'アカウント削除に失敗しました。時間をおいて再度お試しください。',
    }),
    invalidField: accountDeletionInvalidField(error),
  }
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

import { useState } from 'react'
import type { FormEvent } from 'react'

import type { AccountDeletionOidcReauthProvider } from '@/lib/apiError'
import { Button } from '@/components/atoms/button'
import { AuthFormFeedback } from '@/components/molecules/AuthFormFeedback'
import { AuthTextField } from '@/components/molecules/AuthTextField'
import { OidcProviderButton } from '@/components/molecules/OidcProviderButton'

export type AccountDeletionInvalidField = 'confirmEmail' | 'password'

export type AccountDeletionPanelProps = {
  currentEmail: string
  errorMessage?: string | null
  invalidField?: AccountDeletionInvalidField | null
  isPending?: boolean
  linkedProviders?: Array<AccountDeletionOidcReauthProvider>
  onFieldChange?: (field: AccountDeletionInvalidField) => void
  onReauth?: (providerId: string) => void
  onSubmit: (payload: { confirmEmail: string; password?: string }) => void
}

export function AccountDeletionPanel({
  currentEmail,
  errorMessage = null,
  invalidField = null,
  isPending = false,
  linkedProviders = [],
  onFieldChange,
  onReauth,
  onSubmit,
}: AccountDeletionPanelProps) {
  const [confirmEmail, setConfirmEmail] = useState('')
  const [password, setPassword] = useState('')
  const errorId = 'account-deletion-error'

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit({
      confirmEmail,
      password: password === '' ? undefined : password,
    })
  }

  return (
    <form className="grid gap-4" noValidate onSubmit={handleSubmit}>
      <div className="grid gap-1">
        <h2 className="text-base font-semibold text-landing-ink">
          アカウント削除
        </h2>
        <p className="text-sm text-landing-ink/70">{currentEmail}</p>
      </div>
      <AuthTextField
        autoComplete="off"
        describedBy={errorMessage ? errorId : undefined}
        disabled={isPending}
        id="account-delete-confirm-email"
        invalid={invalidField === 'confirmEmail'}
        label="メールアドレスを入力して削除を確認"
        onChange={(value) => {
          setConfirmEmail(value)
          onFieldChange?.('confirmEmail')
        }}
        type="email"
        value={confirmEmail}
      />
      <AuthTextField
        autoComplete="current-password"
        describedBy={errorMessage ? errorId : undefined}
        disabled={isPending}
        id="account-delete-password"
        invalid={invalidField === 'password'}
        label="現在のパスワード"
        onChange={(value) => {
          setPassword(value)
          onFieldChange?.('password')
        }}
        type="password"
        value={password}
      />
      <AuthFormFeedback id={errorId} message={errorMessage} />
      {linkedProviders.length > 0 ? (
        <div className="grid gap-3">
          {linkedProviders.map((provider) => (
            <OidcProviderButton
              key={provider.providerId}
              isDisabled={isPending}
              onClick={() => onReauth?.(provider.providerId)}
              provider={provider}
            />
          ))}
        </div>
      ) : null}
      <Button disabled={isPending} type="submit" variant="destructive">
        アカウントを削除
      </Button>
    </form>
  )
}

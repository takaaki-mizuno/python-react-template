import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { FormEvent } from 'react'

import type { AccountDeletionOidcReauthProvider } from '@/lib/apiError'
import { Button } from '@/components/atoms/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from '@/components/atoms/card'
import { AuthFormFeedback } from '@/components/molecules/AuthFormFeedback'
import { AuthTextField } from '@/components/molecules/AuthTextField'
import { OidcProviderButton } from '@/components/molecules/OidcProviderButton'

export type AccountDeletionInvalidField = 'confirm_email' | 'password'

export type AccountDeletionPanelProps = {
  currentEmail: string
  errorMessage?: string | null
  invalidField?: AccountDeletionInvalidField | null
  isPending?: boolean
  linkedProviders?: Array<AccountDeletionOidcReauthProvider>
  onFieldChange?: (field: AccountDeletionInvalidField) => void
  onReauth?: (providerId: string) => void
  onSubmit: (payload: { confirm_email: string; password?: string }) => void
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
  const { t } = useTranslation('auth')
  const [confirmEmail, setConfirmEmail] = useState('')
  const [password, setPassword] = useState('')
  const errorId = 'account-deletion-error'

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit({
      confirm_email: confirmEmail,
      password: password === '' ? undefined : password,
    })
  }

  return (
    <Card>
      <CardHeader>
        <h2 className="text-xl font-semibold tracking-tight">
          {t('accountDeletion.title')}
        </h2>
        <CardDescription>{currentEmail}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4" noValidate onSubmit={handleSubmit}>
          <AuthTextField
            autoComplete="off"
            describedBy={errorMessage ? errorId : undefined}
            disabled={isPending}
            id="account-delete-confirm-email"
            invalid={invalidField === 'confirm_email'}
            label={t('accountDeletion.confirmEmailLabel')}
            onChange={(value) => {
              setConfirmEmail(value)
              onFieldChange?.('confirm_email')
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
            label={t('accountDeletion.passwordLabel')}
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
                  key={provider.provider_id}
                  isDisabled={isPending}
                  onClick={() => onReauth?.(provider.provider_id)}
                  provider={provider}
                />
              ))}
            </div>
          ) : null}
          <Button disabled={isPending} type="submit" variant="destructive">
            {t('accountDeletion.submit')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

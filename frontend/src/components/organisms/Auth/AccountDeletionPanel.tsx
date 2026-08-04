import { useState } from 'react'
import type { FormEvent } from 'react'

import { Button } from '@/components/atoms/button'
import { AuthTextField } from '@/components/molecules/AuthTextField'

export type AccountDeletionInvalidField = 'confirmEmail' | 'password'

export type AccountDeletionPanelProps = {
  currentEmail: string
  errorMessage?: string | null
  invalidField?: AccountDeletionInvalidField | null
  isPending?: boolean
  onSubmit: (payload: { confirmEmail: string; password?: string }) => void
}

export function AccountDeletionPanel({
  currentEmail,
  errorMessage = null,
  invalidField = null,
  isPending = false,
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
    <form className="grid gap-4" onSubmit={handleSubmit}>
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
        onChange={setConfirmEmail}
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
        onChange={setPassword}
        type="password"
        value={password}
      />
      {errorMessage ? (
        <p className="text-sm text-red-600" id={errorId} role="alert">
          {errorMessage}
        </p>
      ) : null}
      <Button disabled={isPending} type="submit" variant="destructive">
        アカウントを削除
      </Button>
    </form>
  )
}

import { useState } from 'react'
import type { FormEvent } from 'react'

import { Button } from '@/components/atoms/button'
import { AuthTextField } from '@/components/molecules/AuthTextField'

export type RegisterValues = {
  email: string
  password: string
}

export default function RegisterForm({
  errorMessage,
  isPending,
  onSubmit,
}: {
  errorMessage: string | null
  isPending: boolean
  onSubmit: (values: RegisterValues) => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [validationMessage, setValidationMessage] = useState<string | null>(
    null,
  )
  const [invalidFields, setInvalidFields] = useState<Set<string>>(new Set())
  const displayError = validationMessage ?? errorMessage
  const errorId = 'register-form-error'

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setValidationMessage(null)
    setInvalidFields(new Set())

    if (password.length < 12) {
      setValidationMessage('パスワードは12文字以上で入力してください。')
      setInvalidFields(new Set(['password']))
      return
    }

    if (password !== passwordConfirmation) {
      setValidationMessage('パスワードが一致しません。')
      setInvalidFields(new Set(['password', 'passwordConfirmation']))
      return
    }

    onSubmit({ email, password })
  }

  return (
    <form className="grid gap-4" onSubmit={handleSubmit}>
      <AuthTextField
        autoComplete="email"
        describedBy={displayError ? errorId : undefined}
        id="register-email"
        label="メールアドレス"
        onChange={setEmail}
        required
        type="email"
        value={email}
      />
      <AuthTextField
        autoComplete="new-password"
        describedBy={displayError ? errorId : undefined}
        id="register-password"
        invalid={invalidFields.has('password')}
        label="パスワード"
        onChange={setPassword}
        required
        type="password"
        value={password}
      />
      <AuthTextField
        autoComplete="new-password"
        describedBy={displayError ? errorId : undefined}
        id="register-password-confirmation"
        invalid={invalidFields.has('passwordConfirmation')}
        label="パスワード確認"
        onChange={setPasswordConfirmation}
        required
        type="password"
        value={passwordConfirmation}
      />
      {displayError ? (
        <p className="text-sm text-red-600" id={errorId} role="alert">
          {displayError}
        </p>
      ) : null}
      <Button
        className="bg-landing-ink text-white hover:bg-landing-ink/90"
        disabled={isPending}
        type="submit"
      >
        アカウントを作成
      </Button>
    </form>
  )
}

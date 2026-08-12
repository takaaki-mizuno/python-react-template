import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { FormEvent } from 'react'

import { Button } from '@/components/atoms/button'
import { AuthFormFeedback } from '@/components/molecules/AuthFormFeedback'
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
  const { t } = useTranslation('auth')
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
      setValidationMessage(t('feedback.passwordTooShort'))
      setInvalidFields(new Set(['password']))
      return
    }

    if (password !== passwordConfirmation) {
      setValidationMessage(t('feedback.passwordMismatch'))
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
        label={t('fields.email')}
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
        label={t('fields.password')}
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
        label={t('fields.passwordConfirmation')}
        onChange={setPasswordConfirmation}
        required
        type="password"
        value={passwordConfirmation}
      />
      <AuthFormFeedback id={errorId} message={displayError} />
      <Button disabled={isPending} type="submit">
        {t('actions.createAccount')}
      </Button>
    </form>
  )
}

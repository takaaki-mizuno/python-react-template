import { useState } from 'react'
import type { FormEvent } from 'react'

import { Button } from '@/components/atoms/button'
import { AuthTextField } from '@/components/molecules/AuthTextField'

export type LoginValues = {
  email: string
  password: string
}

export default function LoginForm({
  errorMessage,
  onSubmit,
  isPending,
}: {
  errorMessage: string | null
  onSubmit: (values: LoginValues) => void
  isPending: boolean
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit({ email, password })
  }
  const errorId = 'login-form-error'

  return (
    <form className="grid gap-4" onSubmit={handleSubmit}>
      <AuthTextField
        autoComplete="email"
        describedBy={errorMessage ? errorId : undefined}
        id="login-email"
        label="メールアドレス"
        onChange={setEmail}
        required
        type="email"
        value={email}
      />
      <AuthTextField
        autoComplete="current-password"
        describedBy={errorMessage ? errorId : undefined}
        id="login-password"
        label="パスワード"
        onChange={setPassword}
        required
        type="password"
        value={password}
      />
      {errorMessage ? (
        <p className="text-sm text-red-600" id={errorId} role="alert">
          {errorMessage}
        </p>
      ) : null}
      <Button
        className="bg-landing-ink text-white hover:bg-landing-ink/90"
        disabled={isPending}
        type="submit"
      >
        ログイン
      </Button>
    </form>
  )
}

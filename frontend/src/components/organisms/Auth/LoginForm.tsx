import { useState } from 'react'
import type { FormEvent } from 'react'

type LoginValues = {
  email: string
  password: string
}

export default function LoginForm({
  errorMessage,
  onSubmit,
  isPending,
}: {
  errorMessage: string | null
  onSubmit: (values: LoginValues) => Promise<void>
  isPending: boolean
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await onSubmit({ email, password })
  }

  return (
    <form className="grid gap-4" onSubmit={handleSubmit}>
      <label className="grid gap-2">
        <span>メールアドレス</span>
        <input
          className="rounded-lg border border-slate-300 px-3 py-2"
          onChange={(event) => setEmail(event.target.value)}
          required
          type="email"
          value={email}
        />
      </label>
      <label className="grid gap-2">
        <span>パスワード</span>
        <input
          className="rounded-lg border border-slate-300 px-3 py-2"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />
      </label>
      {errorMessage ? <p role="alert">{errorMessage}</p> : null}
      <button
        className="rounded-lg bg-landing-ink px-4 py-2 font-semibold text-white disabled:opacity-60"
        disabled={isPending}
        type="submit"
      >
        ログイン
      </button>
    </form>
  )
}

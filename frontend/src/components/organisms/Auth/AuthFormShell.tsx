import type { ReactNode } from 'react'

type AuthFormShellProps = {
  children: ReactNode
  title: string
}

export function AuthFormShell({ children, title }: AuthFormShellProps) {
  return (
    <main className="landing-shell grid max-w-xl gap-6 py-16">
      <h1 className="text-3xl font-semibold text-landing-ink">{title}</h1>
      {children}
    </main>
  )
}

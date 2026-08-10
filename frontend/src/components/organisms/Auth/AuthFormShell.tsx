import type { ReactNode } from 'react'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from '@/components/atoms/card'

type AuthFormShellProps = {
  children: ReactNode
  description?: string
  title: string
}

export function AuthFormShell({
  children,
  description,
  title,
}: AuthFormShellProps) {
  return (
    <main className="mx-auto flex min-h-[calc(100dvh_-_var(--app-header-height))] w-full max-w-md items-center px-4 py-12">
      <Card className="w-full">
        <CardHeader>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description ? (
            <CardDescription>{description}</CardDescription>
          ) : null}
        </CardHeader>
        <CardContent className="grid gap-6">{children}</CardContent>
      </Card>
    </main>
  )
}

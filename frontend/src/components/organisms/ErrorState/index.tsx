import { Link } from '@tanstack/react-router'
import type { LanguageCode } from '@/lib/i18n/languages'

import { Badge } from '@/components/atoms/badge'
import { Button } from '@/components/atoms/button'
import { Card, CardContent, CardHeader } from '@/components/atoms/card'

type ErrorStateProps = {
  message: string
  primaryAction?:
    | {
        label: string
        to: '/app'
      }
    | {
        label: string
        params: { locale: LanguageCode }
        to: '/{-$locale}'
      }
  statusCode: string
  title: string
}

export function ErrorState({
  message,
  primaryAction,
  statusCode,
  title,
}: ErrorStateProps) {
  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-16 sm:px-6 lg:px-8">
      <Card>
        <CardHeader>
          <Badge className="w-fit" variant="outline">
            {statusCode}
          </Badge>
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        </CardHeader>
        <CardContent className="grid gap-5">
          <p className="text-muted-foreground">{message}</p>
          {primaryAction ? (
            <Button asChild className="w-fit">
              {primaryAction.to === '/app' ? (
                <Link to={primaryAction.to}>{primaryAction.label}</Link>
              ) : (
                <Link params={primaryAction.params} to={primaryAction.to}>
                  {primaryAction.label}
                </Link>
              )}
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </main>
  )
}

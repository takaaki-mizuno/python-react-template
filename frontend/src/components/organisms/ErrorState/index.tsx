import { Link } from '@tanstack/react-router'

type ErrorStateProps = {
  message: string
  primaryAction?: {
    label: string
    to: '/' | '/app'
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
    <main className="landing-shell py-16">
      <div className="grid max-w-xl gap-4">
        <p className="text-sm font-semibold text-landing-accent">
          {statusCode}
        </p>
        <h1 className="text-3xl font-semibold text-landing-ink">{title}</h1>
        <p className="text-landing-muted">{message}</p>
        {primaryAction ? (
          <Link
            className="inline-flex h-10 w-fit items-center rounded-md bg-landing-ink px-4 text-sm font-medium text-white hover:bg-landing-ink/90"
            to={primaryAction.to}
          >
            {primaryAction.label}
          </Link>
        ) : null}
      </div>
    </main>
  )
}

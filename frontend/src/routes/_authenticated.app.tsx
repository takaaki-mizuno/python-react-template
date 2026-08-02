import { createFileRoute } from '@tanstack/react-router'

const AppPage = () => {
  return (
    <main className="landing-shell py-16">
      <h1 className="text-3xl font-semibold text-landing-ink">アプリ</h1>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/app')({
  component: AppPage,
})

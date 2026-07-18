import { createFileRoute, redirect } from '@tanstack/react-router'

import { ApiError } from '@/lib/apiError'
import { currentUserStrictQueryOptions } from '@/lib/authApi'

function AppPage() {
  return (
    <main className="landing-shell py-16">
      <h1 className="text-3xl font-semibold text-landing-ink">アプリ</h1>
    </main>
  )
}

export const Route = createFileRoute('/app')({
  beforeLoad: async ({ context, location }) => {
    try {
      await context.queryClient.fetchQuery(currentUserStrictQueryOptions())
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        throw redirect({
          to: '/login',
          search: { redirect: location.pathname },
        })
      }
      throw error
    }
  },
  component: AppPage,
})

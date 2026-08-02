import { redirect } from '@tanstack/react-router'

import { currentUserQueryOptions } from './authApi'
import type { QueryClient } from '@tanstack/react-query'

export async function requireAuth({
  context,
  location,
}: {
  context: { queryClient: QueryClient }
  location: { href: string }
}) {
  // Keep this server-confirming guard even with intent preloads. If protected
  // route count grows enough for hover preloads to become noisy, revisit with
  // a short auth-specific staleTime instead of trusting arbitrary stale cache.
  const user = await context.queryClient.fetchQuery(currentUserQueryOptions())

  if (!user) {
    throw redirect({
      to: '/login',
      search: { redirect: location.href },
    })
  }
}

import { redirect } from '@tanstack/react-router'

import { currentUserQueryOptions } from './authApi'
import {
  detectPreferredPublicLanguage,
  localizedAuthPath,
} from './i18n/publicLocale'
import { hasPermission } from './permissions'
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
      href: localizedLoginHref(location.href),
    })
  }
}

export async function requirePermission(
  permission: string,
  options: {
    context: { queryClient: QueryClient }
    location: { href: string }
  },
) {
  await requireAnyPermission([permission], options)
}

export async function requireAnyPermission(
  permissions: Array<string>,
  options: {
    context: { queryClient: QueryClient }
    location: { href: string }
  },
) {
  const user = await options.context.queryClient.ensureQueryData(
    currentUserQueryOptions(),
  )

  if (!user) {
    throw redirect({
      href: localizedLoginHref(options.location.href),
    })
  }

  if (!permissions.some((permission) => hasPermission(user, permission))) {
    throw redirect({ to: '/forbidden' })
  }
}

function localizedLoginHref(redirectHref: string): string {
  const params = new URLSearchParams({ redirect: redirectHref })
  return `${localizedAuthPath('login', detectPreferredPublicLanguage())}?${params.toString()}`
}

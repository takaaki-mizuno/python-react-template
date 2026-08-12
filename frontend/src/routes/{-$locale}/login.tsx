import { createFileRoute, redirect } from '@tanstack/react-router'

import { LoginPage } from '../-login'
import { currentUserQueryOptions } from '@/lib/authApi'
import { normalizeRedirectHref } from '@/lib/authRedirect'
import { defaultLanguage, isLanguageCode } from '@/lib/i18n/languages'

export const Route = createFileRoute('/{-$locale}/login')({
  validateSearch: (
    search: Record<string, unknown>,
  ): { redirect: string; oidcError?: string } => {
    return {
      redirect: normalizeRedirectHref(search.redirect),
      ...(typeof search.oidcError === 'string'
        ? { oidcError: search.oidcError }
        : {}),
    }
  },
  beforeLoad: async ({ context, search }) => {
    let user = null
    try {
      user = await context.queryClient.fetchQuery(currentUserQueryOptions())
    } catch {
      return
    }

    if (user) {
      throw redirect({ href: search.redirect })
    }
  },
  component: LocalizedLoginRoute,
})

function LocalizedLoginRoute() {
  const params = Route.useParams()
  const search = Route.useSearch()
  const localeParam = params.locale
  const locale =
    localeParam && isLanguageCode(localeParam) ? localeParam : defaultLanguage

  return (
    <LoginPage
      locale={locale}
      oidcError={search.oidcError}
      redirectHref={search.redirect}
    />
  )
}

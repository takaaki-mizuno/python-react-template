import { createFileRoute, redirect } from '@tanstack/react-router'

import { RegisterPage } from '../-register'
import { currentUserQueryOptions } from '@/lib/authApi'
import { normalizeRedirectHref } from '@/lib/authRedirect'
import { defaultLanguage, isLanguageCode } from '@/lib/i18n/languages'

export const Route = createFileRoute('/{-$locale}/register')({
  validateSearch: (search: Record<string, unknown>) => {
    return {
      redirect: normalizeRedirectHref(search.redirect),
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
  component: LocalizedRegisterRoute,
})

function LocalizedRegisterRoute() {
  const params = Route.useParams()
  const search = Route.useSearch()
  const localeParam = params.locale
  const locale =
    localeParam && isLanguageCode(localeParam) ? localeParam : defaultLanguage

  return <RegisterPage locale={locale} redirectHref={search.redirect} />
}

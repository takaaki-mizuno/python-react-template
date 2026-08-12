import {
  Outlet,
  createFileRoute,
  notFound,
  redirect,
} from '@tanstack/react-router'

import {
  detectPreferredPublicLanguage,
  localeFromPathname,
  withLocaleInPath,
} from '@/lib/i18n/publicLocale'

export const Route = createFileRoute('/{-$locale}')({
  beforeLoad: ({ location, params }) => {
    const locale = params.locale ?? localeFromPathname(location.pathname)
    if (!locale) {
      // Memory history can surface a legacy fragment through searchStr during
      // optional-param canonicalization, so preserve it before redirecting.
      const [, hashFromSearchStr = ''] = location.searchStr.split('#')
      const hash =
        location.hash || (hashFromSearchStr ? `#${hashFromSearchStr}` : '')
      throw redirect({
        to: withLocaleInPath(
          location.pathname,
          detectPreferredPublicLanguage(),
        ),
        search: true,
        hash: hash ? () => hash.replace(/^#/, '') : undefined,
      })
    }
    if (locale !== 'en' && locale !== 'ja') {
      throw notFound()
    }
    return { locale }
  },
  component: LocaleLayout,
})

function LocaleLayout() {
  return <Outlet />
}

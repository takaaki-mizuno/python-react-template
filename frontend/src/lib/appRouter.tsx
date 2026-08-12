import { createRouter } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import type { DefaultOptions } from '@tanstack/react-query'
import type { AnyRouter, RouterHistory } from '@tanstack/react-router'

import { ErrorState } from '@/components/organisms/ErrorState'
import {
  detectPreferredPublicLanguage,
  isLocalizedAuthPath,
  localizedAuthPath,
} from '@/lib/i18n/publicLocale'
import { queryKeys } from '@/lib/queryKeys'
import { createAppQueryClient } from '@/lib/queryClient'
import { routeTree } from '@/routeTree.gen'

export function createAppRouter(options?: {
  history?: RouterHistory
  queryClientOptions?: DefaultOptions
}) {
  const routerRef: { current?: AnyRouter } = {}
  const queryClient = createAppQueryClient({
    defaultOptions: options?.queryClientOptions,
    onUnauthorized: () => {
      queryClient.setQueryData(queryKeys.auth.me, null)

      const router = routerRef.current
      if (!router || isAuthPage(router.state.location.pathname)) {
        return
      }

      // Most current auth endpoints normalize 401 locally; this handler covers
      // future authenticated API queries/mutations that surface ApiError(401).
      const params = new URLSearchParams({ redirect: currentHref(router) })
      void router.navigate({
        href: `${localizedAuthPath('login', detectPreferredPublicLanguage())}?${params.toString()}`,
      })
    },
    onForbidden: () => {
      const router = routerRef.current
      if (!router || router.state.location.pathname === '/forbidden') {
        return
      }

      void router.navigate({ to: '/forbidden' })
    },
  })
  const router = createRouter({
    routeTree,
    history: options?.history,
    context: { queryClient },
    defaultPreload: 'intent',
    defaultNotFoundComponent: NotFoundErrorPage,
    defaultErrorComponent: UnexpectedErrorPage,
    scrollRestoration: true,
    defaultStructuralSharing: true,
    defaultPreloadStaleTime: 0,
  })
  routerRef.current = router

  return { router, queryClient }
}

function isAuthPage(pathname: string): boolean {
  return (
    // Legacy auth paths can appear briefly before optional-locale canonicalization.
    pathname === '/login' ||
    pathname === '/register' ||
    isLocalizedAuthPath(pathname)
  )
}

function currentHref(router: AnyRouter): string {
  const { pathname, searchStr, hash } = router.state.location

  return `${pathname}${searchStr}${hash}`
}

function NotFoundErrorPage() {
  const { t } = useTranslation('common')

  return (
    <ErrorState
      message={t('errors.notFound.message')}
      primaryAction={{
        label: t('actions.backToTop'),
        params: { locale: detectPreferredPublicLanguage() },
        to: '/{-$locale}',
      }}
      statusCode="404"
      title={t('errors.notFound.title')}
    />
  )
}

function UnexpectedErrorPage() {
  const { t } = useTranslation('common')

  return (
    <ErrorState
      message={t('errors.unexpected.message')}
      primaryAction={{
        label: t('actions.backToTop'),
        params: { locale: detectPreferredPublicLanguage() },
        to: '/{-$locale}',
      }}
      statusCode="500"
      title={t('errors.unexpected.title')}
    />
  )
}

export type AppRouter = ReturnType<typeof createAppRouter>['router']

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter
  }
}

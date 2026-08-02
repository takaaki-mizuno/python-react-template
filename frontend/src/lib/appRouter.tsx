import { createRouter } from '@tanstack/react-router'
import type { DefaultOptions } from '@tanstack/react-query'
import type { AnyRouter, RouterHistory } from '@tanstack/react-router'

import { ErrorState } from '@/components/organisms/ErrorState'
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
      void router.navigate({
        to: '/login',
        search: { redirect: currentHref(router) },
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
    defaultNotFoundComponent: () => (
      <ErrorState
        message="指定されたページは存在しないか、移動した可能性があります。"
        primaryAction={{ label: 'トップへ戻る', to: '/' }}
        statusCode="404"
        title="ページが見つかりません"
      />
    ),
    defaultErrorComponent: () => (
      <ErrorState
        message="時間をおいて再度お試しください。問題が続く場合は管理者へ連絡してください。"
        primaryAction={{ label: 'トップへ戻る', to: '/' }}
        statusCode="500"
        title="問題が発生しました"
      />
    ),
    scrollRestoration: true,
    defaultStructuralSharing: true,
    defaultPreloadStaleTime: 0,
  })
  routerRef.current = router

  return { router, queryClient }
}

function isAuthPage(pathname: string): boolean {
  return pathname === '/login' || pathname === '/register'
}

function currentHref(router: AnyRouter): string {
  const { pathname, searchStr, hash } = router.state.location

  return `${pathname}${searchStr}${hash}`
}

export type AppRouter = ReturnType<typeof createAppRouter>['router']

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter
  }
}

import {
  Outlet,
  createRootRouteWithContext,
  useRouterState,
} from '@tanstack/react-router'

import Header from '../components/organisms/Header'
import RouteDevtools from '../components/organisms/RouteDevtools'
import type { QueryClient } from '@tanstack/react-query'
import { landingNavigation } from '@/components/organisms/LandingPage/data'

export type RouterContext = {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
})

function RootLayout() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })

  return (
    <>
      <Header
        navigationItems={pathname === '/' ? landingNavigation : undefined}
      />
      <Outlet />
      <RouteDevtools />
    </>
  )
}

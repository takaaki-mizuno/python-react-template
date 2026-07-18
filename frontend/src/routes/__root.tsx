import { Outlet, createRootRouteWithContext } from '@tanstack/react-router'

import Header from '../components/organisms/Header'
import RouteDevtools from '../components/organisms/RouteDevtools'
import type { QueryClient } from '@tanstack/react-query'

export type RouterContext = {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => (
    <>
      <Header />
      <Outlet />
      <RouteDevtools />
    </>
  ),
})

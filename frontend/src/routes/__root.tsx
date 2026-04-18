import { Outlet, createRootRoute } from '@tanstack/react-router'

import Header from '../components/organisms/Header'
import RouteDevtools from '../components/organisms/RouteDevtools'

export const Route = createRootRoute({
  component: () => (
    <>
      <Header />
      <Outlet />
      <RouteDevtools />
    </>
  ),
})

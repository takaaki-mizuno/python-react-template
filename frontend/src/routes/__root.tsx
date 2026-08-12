import {
  Outlet,
  createRootRouteWithContext,
  useRouterState,
} from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import Header from '../components/organisms/Header'
import RouteDevtools from '../components/organisms/RouteDevtools'
import type { QueryClient } from '@tanstack/react-query'
import { landingSectionIds } from '@/components/organisms/LandingPage/data'
import { DocumentMetadataManager } from '@/lib/i18n/DocumentMetadataManager'
import { LanguageSyncManager } from '@/lib/i18n/LanguageSyncManager'
import { isLocalizedLandingPath } from '@/lib/i18n/publicLocale'

export type RouterContext = {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
})

function RootLayout() {
  const { t } = useTranslation('landing')
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const landingNavigation = landingSectionIds.map((id) => ({
    id,
    href: `#${id}`,
    label: t(`navigation.${id}`),
  }))

  return (
    <>
      <LanguageSyncManager />
      <DocumentMetadataManager />
      <Header
        navigationItems={
          isLocalizedLandingPath(pathname) ? landingNavigation : undefined
        }
      />
      <Outlet />
      <RouteDevtools />
    </>
  )
}

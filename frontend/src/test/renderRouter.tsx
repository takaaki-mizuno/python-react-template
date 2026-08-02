import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createMemoryHistory } from '@tanstack/react-router'
import { render } from '@testing-library/react'
import type { DefaultOptions, QueryClient } from '@tanstack/react-query'
import type { RenderResult } from '@testing-library/react'
import type { ReactNode } from 'react'

import type { AppRouter } from '@/lib/appRouter'
import { createAppRouter } from '@/lib/appRouter'

type RenderWithRouterOptions = {
  initialEntries?: Array<string>
  queryClientOptions?: DefaultOptions
  seed?: (queryClient: QueryClient) => void
  children?: ReactNode
}

type RenderWithRouterResult = RenderResult & {
  router: AppRouter
  queryClient: QueryClient
}

export function renderWithRouter(
  options: RenderWithRouterOptions = {},
): RenderWithRouterResult {
  const { router, queryClient } = createAppRouter({
    history: createMemoryHistory({
      initialEntries: options.initialEntries ?? ['/'],
    }),
    queryClientOptions: options.queryClientOptions,
  })

  options.seed?.(queryClient)

  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        {options.children}
      </QueryClientProvider>,
    ),
    router,
    queryClient,
  }
}

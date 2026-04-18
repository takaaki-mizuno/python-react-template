import { Suspense, lazy } from 'react'

const LazyRouteDevtools = import.meta.env.DEV
  ? lazy(async () => {
      const [{ TanStackDevtools }, { TanStackRouterDevtoolsPanel }] =
        await Promise.all([
          import('@tanstack/react-devtools'),
          import('@tanstack/react-router-devtools'),
        ])

      const DevtoolsPanel = () => {
        return (
          <TanStackDevtools
            config={{
              position: 'bottom-right',
            }}
            plugins={[
              {
                name: 'TanStack Router',
                render: <TanStackRouterDevtoolsPanel />,
              },
            ]}
          />
        )
      }

      return { default: DevtoolsPanel }
    })
  : null

const RouteDevtools = () => {
  if (!LazyRouteDevtools) {
    return null
  }

  return (
    <Suspense fallback={null}>
      <LazyRouteDevtools />
    </Suspense>
  )
}

export default RouteDevtools

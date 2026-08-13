import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from './apiError'
import type { DefaultOptions } from '@tanstack/react-query'

export type AppQueryClientHandlers = {
  onUnauthorized?: () => void
  onForbidden?: (error: ApiError) => void
  defaultOptions?: DefaultOptions
}

export function createAppQueryClient(
  handlers: AppQueryClientHandlers = {},
): QueryClient {
  const { defaultOptions } = handlers
  const queryDefaults = { ...defaultOptions?.queries }
  const mutationDefaults = { ...defaultOptions?.mutations }

  queryDefaults.retry ??= (failureCount, error) => {
    if (isUnauthorizedOrForbidden(error)) {
      return false
    }

    return failureCount < 2
  }
  mutationDefaults.retry ??= false

  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        handleAuthError(error, handlers)
      },
    }),
    mutationCache: new MutationCache({
      onError: (error) => {
        handleAuthError(error, handlers)
      },
    }),
    defaultOptions: {
      ...defaultOptions,
      queries: queryDefaults,
      mutations: mutationDefaults,
    },
  })
}

function handleAuthError(
  error: unknown,
  handlers: AppQueryClientHandlers,
): void {
  if (!(error instanceof ApiError)) {
    return
  }

  if (error.status === 401) {
    handlers.onUnauthorized?.()
    return
  }

  if (error.status === 403 && error.code !== 'csrf_validation_failed') {
    handlers.onForbidden?.(error)
  }
}

function isUnauthorizedOrForbidden(error: unknown): boolean {
  return error instanceof ApiError && [401, 403].includes(error.status)
}

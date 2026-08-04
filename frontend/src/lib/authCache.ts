import { queryKeys } from './queryKeys'
import type { QueryClient } from '@tanstack/react-query'

export function clearAuthenticatedCache(queryClient: QueryClient) {
  queryClient.clear()
  queryClient.setQueryData(queryKeys.auth.me, null)
}

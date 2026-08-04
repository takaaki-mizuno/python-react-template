import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { currentUserQueryOptions, logoutCurrentSession } from '@/lib/authApi'
import { clearAuthenticatedCache } from '@/lib/authCache'

export function useAuthSession() {
  const queryClient = useQueryClient()
  const meQuery = useQuery(currentUserQueryOptions())

  const logout = useMutation({
    mutationFn: logoutCurrentSession,
    onSuccess: () => {
      clearAuthenticatedCache(queryClient)
    },
  })

  return {
    user: meQuery.data ?? null,
    isLoading: meQuery.isLoading,
    error: meQuery.error,
    logout,
  }
}

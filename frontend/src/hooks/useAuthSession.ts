import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { currentUserQueryOptions, logoutCurrentSession } from '@/lib/authApi'
import { queryKeys } from '@/lib/queryKeys'

export function useAuthSession() {
  const queryClient = useQueryClient()
  const meQuery = useQuery(currentUserQueryOptions())

  const logout = useMutation({
    mutationFn: logoutCurrentSession,
    onSuccess: () => {
      queryClient.clear()
      queryClient.setQueryData(queryKeys.auth.me, null)
    },
  })

  return {
    user: meQuery.data ?? null,
    isLoading: meQuery.isLoading,
    error: meQuery.error,
    logout,
  }
}

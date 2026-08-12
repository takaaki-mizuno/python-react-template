import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  currentUserQueryOptions,
  logoutCurrentSession,
  updateCurrentUser,
} from '@/lib/authApi'
import { clearAuthenticatedCache } from '@/lib/authCache'
import { clearLastResolvedLanguage } from '@/lib/i18n/storage'
import { queryKeys } from '@/lib/queryKeys'

export function useAuthSession() {
  const queryClient = useQueryClient()
  const meQuery = useQuery(currentUserQueryOptions())

  const logout = useMutation({
    mutationFn: logoutCurrentSession,
    onSuccess: () => {
      clearLastResolvedLanguage()
      clearAuthenticatedCache(queryClient)
    },
  })

  const updateLanguage = useMutation({
    mutationFn: updateCurrentUser,
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.auth.me, user)
    },
  })

  return {
    user: meQuery.data ?? null,
    isLoading: meQuery.isLoading,
    error: meQuery.error,
    logout,
    updateLanguage,
  }
}

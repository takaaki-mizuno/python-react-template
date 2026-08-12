import { useMutation, useQueryClient } from '@tanstack/react-query'

import type { DeleteAccountPayload } from '@/lib/authApi'
import { deleteCurrentAccount } from '@/lib/authApi'
import { clearAuthenticatedCache } from '@/lib/authCache'
import { clearLastResolvedLanguage } from '@/lib/i18n/storage'

export function useAccountDeletion() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: DeleteAccountPayload) =>
      deleteCurrentAccount(payload),
    onSuccess: () => {
      clearLastResolvedLanguage()
      clearAuthenticatedCache(queryClient)
    },
  })
}

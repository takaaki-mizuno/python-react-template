import { useMutation, useQueryClient } from '@tanstack/react-query'

import type { DeleteAccountPayload } from '@/lib/authApi'
import { deleteCurrentAccount } from '@/lib/authApi'
import { clearAuthenticatedCache } from '@/lib/authCache'

export function useAccountDeletion() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: DeleteAccountPayload) =>
      deleteCurrentAccount(payload),
    onSuccess: () => {
      clearAuthenticatedCache(queryClient)
    },
  })
}

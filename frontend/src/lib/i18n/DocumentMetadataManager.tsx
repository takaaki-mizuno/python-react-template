import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useRouterState } from '@tanstack/react-router'

import { syncDocumentMetadata } from './documentMetadata'

export function DocumentMetadataManager() {
  const { i18n } = useTranslation()
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })

  useEffect(() => {
    syncDocumentMetadata(pathname)
  }, [pathname, i18n.language])

  return null
}

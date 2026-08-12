import { useEffect, useState } from 'react'
import { useRouterState } from '@tanstack/react-router'

import i18n from './i18n'
import { resolveLanguage } from './languageResolver'
import { publicLanguageChangeEvent, writeLastResolvedLanguage } from './storage'
import { useAuthSession } from '@/hooks/useAuthSession'

export function LanguageSyncManager() {
  const [publicPreferenceVersion, setPublicPreferenceVersion] = useState(0)
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const { user } = useAuthSession()

  useEffect(() => {
    const handleChange = () =>
      setPublicPreferenceVersion((version) => version + 1)
    window.addEventListener(publicLanguageChangeEvent, handleChange)
    return () =>
      window.removeEventListener(publicLanguageChangeEvent, handleChange)
  }, [])

  useEffect(() => {
    const nextLanguage = resolveLanguage(pathname, user?.languageCode ?? null)
    if (i18n.language !== nextLanguage) {
      void i18n.changeLanguage(nextLanguage)
    }
    writeLastResolvedLanguage(nextLanguage)
  }, [pathname, publicPreferenceVersion, user?.languageCode])

  return null
}

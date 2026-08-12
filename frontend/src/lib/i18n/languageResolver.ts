import {
  detectPreferredPublicLanguage,
  localeFromPathname,
} from './publicLocale'
import { readLastResolvedLanguage, readPublicLanguage } from './storage'
import type { LanguageCode } from './languages'

export function resolveLanguage(
  pathname: string,
  userLanguage: LanguageCode | null,
): LanguageCode {
  const publicLocale = localeFromPathname(pathname)
  if (publicLocale) {
    return publicLocale
  }

  if (userLanguage) {
    return userLanguage
  }

  return (
    readPublicLanguage() ??
    readLastResolvedLanguage() ??
    detectPreferredPublicLanguage()
  )
}

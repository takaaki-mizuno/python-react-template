import {
  defaultLanguage,
  isLanguageCode,
  normalizeLanguageCode,
} from './languages'
import { readPublicLanguage } from './storage'
import type { LanguageCode } from './languages'

export function localeFromPathname(pathname: string): LanguageCode | null {
  const segment = pathname.split('/').filter(Boolean)[0]
  return segment && isLanguageCode(segment) ? segment : null
}

export function stripLocaleFromPathname(pathname: string): string {
  const locale = localeFromPathname(pathname)
  if (!locale) {
    return pathname
  }
  const stripped = pathname.slice(locale.length + 1)
  return stripped.startsWith('/') ? stripped || '/' : `/${stripped}`
}

export function withLocaleInPath(
  pathname: string,
  language: LanguageCode,
): string {
  const stripped = stripLocaleFromPathname(pathname)
  return stripped === '/' ? `/${language}/` : `/${language}${stripped}`
}

export function isLocalizedLandingPath(pathname: string): boolean {
  return /^\/(en|ja)\/?$/.test(pathname)
}

export function isLocalizedAuthPath(pathname: string): boolean {
  return /^\/(en|ja)\/(login|register)\/?$/.test(pathname)
}

export function localizedAuthPath(
  route: 'login' | 'register',
  language: LanguageCode,
): `/${LanguageCode}/${typeof route}` {
  return `/${language}/${route}`
}

export function detectPreferredPublicLanguage(): LanguageCode {
  const stored = readPublicLanguage()
  if (stored) {
    return stored
  }

  const languages = window.navigator.languages.length
    ? window.navigator.languages
    : [window.navigator.language]
  for (const language of languages) {
    const normalized = normalizeLanguageCode(language)
    if (normalized) {
      return normalized
    }
  }
  return defaultLanguage
}

import { isLanguageCode } from './languages'
import type { LanguageCode } from './languages'

const publicLanguageKey = 'app.publicLanguage'
const lastResolvedLanguageKey = 'app.lastResolvedLanguage'
export const publicLanguageChangeEvent = 'app.publicLanguage.change'

type StorageKey = typeof publicLanguageKey | typeof lastResolvedLanguageKey

function readLanguage(key: StorageKey): LanguageCode | null {
  try {
    const value = window.localStorage.getItem(key)
    return value && isLanguageCode(value) ? value : null
  } catch {
    return null
  }
}

function writeLanguage(key: StorageKey, language: LanguageCode): void {
  try {
    window.localStorage.setItem(key, language)
  } catch {
    // Storage can be unavailable in hardened browsers or sandboxed contexts.
  }
}

function removeLanguage(key: StorageKey): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // Storage can be unavailable in hardened browsers or sandboxed contexts.
  }
}

export function readPublicLanguage(): LanguageCode | null {
  return readLanguage(publicLanguageKey)
}

export function writePublicLanguage(language: LanguageCode): void {
  writeLanguage(publicLanguageKey, language)
  dispatchPublicLanguageChange()
}

export function readLastResolvedLanguage(): LanguageCode | null {
  return readLanguage(lastResolvedLanguageKey)
}

export function writeLastResolvedLanguage(language: LanguageCode): void {
  writeLanguage(lastResolvedLanguageKey, language)
}

export function clearLastResolvedLanguage(): void {
  removeLanguage(lastResolvedLanguageKey)
}

function dispatchPublicLanguageChange(): void {
  try {
    window.dispatchEvent(new Event(publicLanguageChangeEvent))
  } catch {
    // Ignore non-browser test environments.
  }
}

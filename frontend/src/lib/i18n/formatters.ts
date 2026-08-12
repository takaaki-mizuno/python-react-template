import type { LanguageCode } from './languages'

const dateTimeLocales: Record<LanguageCode, string> = {
  ja: 'ja-JP',
  en: 'en-US',
}

export function formatDateTime(
  value: Date | number | string,
  languageCode: LanguageCode,
): string {
  return new Intl.DateTimeFormat(dateTimeLocales[languageCode], {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

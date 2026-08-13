import type { LanguageCode } from './languages'

const dateTimeLocales: Record<LanguageCode, string> = {
  ja: 'ja-JP',
  en: 'en-US',
}

export function formatUnixTimestampSeconds(
  value: number,
  languageCode: LanguageCode,
): string {
  return new Intl.DateTimeFormat(dateTimeLocales[languageCode], {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value * 1000))
}

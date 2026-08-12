export type LanguageCode = 'en' | 'ja'

export const supportedLanguages = [
  'en',
  'ja',
] as const satisfies ReadonlyArray<LanguageCode>
export const defaultLanguage: LanguageCode = 'ja'

export const languageOptions: ReadonlyArray<{
  code: LanguageCode
  label: string
}> = [
  { code: 'en', label: 'English' },
  { code: 'ja', label: '日本語' },
]

export function isLanguageCode(value: string): value is LanguageCode {
  return supportedLanguages.includes(value as LanguageCode)
}

export function normalizeLanguageCode(value: string): LanguageCode | null {
  const primarySubtag = value.trim().split('-')[0]?.toLowerCase()
  return primarySubtag && isLanguageCode(primarySubtag) ? primarySubtag : null
}

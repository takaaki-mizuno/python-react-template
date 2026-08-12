import { Languages } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { LanguageCode } from '@/lib/i18n/languages'
import { Button } from '@/components/atoms/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/atoms/dropdown-menu'
import { languageOptions } from '@/lib/i18n/languages'

type LanguageSwitcherProps = {
  currentLanguage: LanguageCode
  isPending?: boolean
  onChangeLanguage: (language: LanguageCode) => void
}

export function LanguageSwitcher({
  currentLanguage,
  isPending = false,
  onChangeLanguage,
}: LanguageSwitcherProps) {
  const { t } = useTranslation('common')

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={t('language.trigger')}
          aria-busy={isPending || undefined}
          className="shrink-0"
          size="icon"
          type="button"
          variant="outline"
        >
          <Languages className="size-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuLabel>{t('language.label')}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          onValueChange={(value) => {
            if (value === currentLanguage) {
              return
            }
            onChangeLanguage(value as LanguageCode)
          }}
          value={currentLanguage}
        >
          {languageOptions.map((language) => (
            <DropdownMenuRadioItem
              disabled={isPending}
              key={language.code}
              value={language.code}
            >
              {language.code === 'en'
                ? t('language.english')
                : t('language.japanese')}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

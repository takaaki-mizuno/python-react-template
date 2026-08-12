import { Link, useNavigate, useRouterState } from '@tanstack/react-router'
import { Menu, XIcon } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import AuthMenu from './AuthMenu'
import HeaderNav from './HeaderNav'
import type { NavigationItem } from './types'
import type { LanguageCode } from '@/lib/i18n/languages'
import { Alert, AlertDescription } from '@/components/atoms/alert'
import { Button } from '@/components/atoms/button'
import { LanguageSwitcher } from '@/components/molecules/LanguageSwitcher'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/atoms/sheet'
import { useAuthSession } from '@/hooks/useAuthSession'
import { toUserMessage } from '@/lib/apiError'
import { resolveLanguage } from '@/lib/i18n/languageResolver'
import {
  isLocalizedAuthPath,
  isLocalizedLandingPath,
  localeFromPathname,
  withLocaleInPath,
} from '@/lib/i18n/publicLocale'
import { writePublicLanguage } from '@/lib/i18n/storage'

export type { NavigationItem } from './types'

type HeaderProps = {
  navigationItems?: ReadonlyArray<NavigationItem>
}

export default function Header({ navigationItems = [] }: HeaderProps) {
  const { t } = useTranslation('common')
  const navigate = useNavigate()
  const location = useRouterState({
    select: (state) => ({
      hash: state.location.hash,
      pathname: state.location.pathname,
      searchStr: state.location.searchStr,
    }),
  })
  const { user, updateLanguage } = useAuthSession()
  const [isOpen, setIsOpen] = useState(false)
  const [languageError, setLanguageError] = useState<string | null>(null)
  const hasNavigation = navigationItems.length > 0
  const publicLocale = localeFromPathname(location.pathname)
  const isPublicRoute =
    isLocalizedLandingPath(location.pathname) ||
    isLocalizedAuthPath(location.pathname) ||
    location.pathname === '/' ||
    location.pathname === '/login' ||
    location.pathname === '/register' ||
    (!user && location.pathname === '/forbidden')
  const currentLanguage = resolveLanguage(
    location.pathname,
    user?.languageCode ?? null,
  )

  const handleChangeLanguage = (language: LanguageCode) => {
    setLanguageError(null)

    if (isPublicRoute) {
      writePublicLanguage(language)
      if (
        publicLocale ||
        location.pathname === '/' ||
        isLocalizedAuthPath(location.pathname)
      ) {
        void navigate({
          href: `${withLocaleInPath(location.pathname, language)}${location.searchStr}${location.hash}`,
        })
      }
      return
    }

    updateLanguage.mutate(
      { languageCode: language },
      {
        onError: (error) =>
          setLanguageError(
            toUserMessage(error, {
              fallback: t('language.updateFailed'),
            }),
          ),
      },
    )
  }

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75">
      <div className="mx-auto flex h-[var(--app-header-height)] w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link
          aria-label={t('header.home')}
          className="flex min-h-11 items-center gap-2 font-semibold tracking-tight"
          params={{ locale: currentLanguage }}
          to="/{-$locale}"
        >
          <img
            alt=""
            aria-hidden="true"
            className="size-7"
            src="/site-mark.svg"
          />
          <span>python-react-template</span>
        </Link>

        {hasNavigation ? <HeaderNav items={navigationItems} /> : null}

        <div className="flex items-center gap-2">
          <div className="relative">
            <LanguageSwitcher
              currentLanguage={currentLanguage}
              isPending={updateLanguage.isPending}
              onChangeLanguage={handleChangeLanguage}
            />
            {languageError ? (
              <Alert
                className="absolute top-full right-0 z-50 mt-2 w-[min(calc(100vw-2rem),22rem)] pr-10 shadow-md"
                variant="destructive"
              >
                <AlertDescription>{languageError}</AlertDescription>
                <Button
                  aria-label={t('actions.closeLanguageError')}
                  className="absolute top-2 right-2 size-7"
                  onClick={() => setLanguageError(null)}
                  size="icon"
                  type="button"
                  variant="ghost"
                >
                  <XIcon className="size-4" aria-hidden="true" />
                </Button>
              </Alert>
            ) : null}
          </div>
          <AuthMenu />

          {hasNavigation ? (
            <Sheet open={isOpen} onOpenChange={setIsOpen}>
              <SheetTrigger asChild>
                <Button
                  aria-label={t('actions.openMenu')}
                  className="lg:hidden"
                  size="icon"
                  type="button"
                  variant="outline"
                >
                  <Menu className="size-5" aria-hidden="true" />
                </Button>
              </SheetTrigger>
              <SheetContent showCloseButton={false} side="right">
                <SheetHeader>
                  <SheetTitle>{t('header.sections')}</SheetTitle>
                </SheetHeader>
                <div className="mt-6 px-4">
                  <HeaderNav
                    items={navigationItems}
                    mobile
                    onNavigate={() => setIsOpen(false)}
                  />
                </div>
                <SheetClose asChild>
                  <Button
                    aria-label={t('actions.closeMenu')}
                    className="absolute top-4 right-4"
                    size="icon"
                    type="button"
                    variant="ghost"
                  >
                    <XIcon className="size-4" aria-hidden="true" />
                  </Button>
                </SheetClose>
              </SheetContent>
            </Sheet>
          ) : null}
        </div>
      </div>
    </header>
  )
}

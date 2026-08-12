import { Link, useNavigate } from '@tanstack/react-router'
import { Loader2, LogOut, UserRound, XIcon } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, AlertDescription } from '@/components/atoms/alert'
import { Avatar, AvatarFallback } from '@/components/atoms/avatar'
import { Button } from '@/components/atoms/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/atoms/dropdown-menu'
import { useAuthSession } from '@/hooks/useAuthSession'
import {
  detectPreferredPublicLanguage,
  localizedAuthPath,
} from '@/lib/i18n/publicLocale'

export default function AuthMenu() {
  const { t } = useTranslation(['auth', 'common'])
  const navigate = useNavigate()
  const { user, logout } = useAuthSession()
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const publicLanguage = detectPreferredPublicLanguage()
  const loginHref = `${localizedAuthPath('login', publicLanguage)}?redirect=/app`

  const handleLogout = async () => {
    setLogoutError(null)

    try {
      await logout.mutateAsync()
      await navigate({ href: loginHref })
    } catch {
      setLogoutError(t('auth:account.logoutFailed'))
    }
  }

  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <Button asChild variant="ghost">
          <Link
            params={{ locale: publicLanguage }}
            search={{ redirect: '/app' }}
            to="/{-$locale}/login"
          >
            {t('auth:actions.login')}
          </Link>
        </Button>
        <Button asChild>
          <Link
            params={{ locale: publicLanguage }}
            search={{ redirect: '/app' }}
            to="/{-$locale}/register"
          >
            {t('auth:actions.register')}
          </Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="relative flex items-center gap-3">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            aria-label={
              logout.isPending
                ? t('auth:account.loggingOut', { email: user.email })
                : t('auth:account.menu', { email: user.email })
            }
            className="gap-2 data-[pending=true]:opacity-70"
            aria-busy={logout.isPending || undefined}
            data-pending={logout.isPending || undefined}
            variant="outline"
          >
            <Avatar className="size-6">
              <AvatarFallback>
                {logout.isPending ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <UserRound className="size-4" aria-hidden="true" />
                )}
              </AvatarFallback>
            </Avatar>
            <span className="hidden max-w-48 truncate sm:inline">
              {user.email}
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>{t('auth:account.label')}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={logout.isPending}
            onSelect={() => {
              void handleLogout()
            }}
          >
            <LogOut className="size-4" aria-hidden="true" />
            {t('auth:account.logout')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {logoutError ? (
        <Alert
          className="absolute top-full right-0 z-50 mt-2 w-[min(calc(100vw-2rem),22rem)] pr-10"
          variant="destructive"
        >
          <AlertDescription className="text-destructive!">
            {logoutError}
          </AlertDescription>
          <Button
            aria-label={t('common:actions.closeLogoutError')}
            className="absolute top-2 right-2 size-7 text-destructive hover:text-destructive"
            onClick={() => setLogoutError(null)}
            size="icon"
            type="button"
            variant="ghost"
          >
            <XIcon className="size-4" aria-hidden="true" />
          </Button>
        </Alert>
      ) : null}
    </div>
  )
}

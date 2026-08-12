import { Link, createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/atoms/badge'
import { Button } from '@/components/atoms/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from '@/components/atoms/card'
import { useAuthSession } from '@/hooks/useAuthSession'
import { hasPermission } from '@/lib/permissions'

const AppPage = () => {
  const { t } = useTranslation('app')
  const { user } = useAuthSession()

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="grid gap-6">
        <div className="space-y-3">
          <Badge variant="outline">{t('dashboard.badge')}</Badge>
          <h1 className="text-3xl font-semibold tracking-tight">
            {t('dashboard.title')}
          </h1>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <h2 className="text-lg font-semibold">
                {t('dashboard.account.title')}
              </h2>
              <CardDescription>
                {t('dashboard.account.description')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link to="/app/settings">
                  {t('dashboard.account.settingsLink')}
                </Link>
              </Button>
            </CardContent>
          </Card>
          {hasPermission(user, 'admin:access') ? (
            <Card>
              <CardHeader>
                <h2 className="text-lg font-semibold">
                  {t('dashboard.admin.title')}
                </h2>
                <CardDescription>
                  {t('dashboard.admin.description')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline">
                  <Link to="/admin">{t('dashboard.admin.open')}</Link>
                </Button>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/app')({
  component: AppPage,
})

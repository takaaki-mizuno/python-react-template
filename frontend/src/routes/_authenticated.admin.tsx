import { Link, createFileRoute } from '@tanstack/react-router'
import { Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/atoms/button'
import { requirePermission } from '@/lib/authGuard'

const AdminPage = () => {
  const { t } = useTranslation('admin')

  return (
    <main className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-10 sm:px-6 lg:px-8">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold tracking-normal">
          {t('home.title')}
        </h1>
        <p className="text-sm text-muted-foreground">{t('home.description')}</p>
      </div>
      <section className="grid gap-4 border-t py-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="grid gap-1">
            <h2 className="text-lg font-semibold">{t('home.users.title')}</h2>
            <p className="text-sm text-muted-foreground">
              {t('home.users.description')}
            </p>
          </div>
          <Button asChild>
            <Link search={{ offset: 0 }} to="/admin/users">
              <Users className="size-4" />
              {t('home.users.open')}
            </Link>
          </Button>
        </div>
      </section>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/admin')({
  beforeLoad: (options) => requirePermission('admin:access', options),
  component: AdminPage,
})

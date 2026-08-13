import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { FormEvent } from 'react'
import type { TFunction } from 'i18next'
import type {
  AdminRole,
  AdminUserCreatePayload,
  AdminUserListItem,
  AdminUserListParams,
  AdminUserUpdatePayload,
} from '@/lib/adminUsersApi'
import type { AdminUserSearchParams } from '@/lib/adminSearchParams'
import type { AdminDataTableColumn } from '@/components/molecules/AdminDataTable'
import type { AdminUserFormState } from './types'

import { Alert, AlertDescription } from '@/components/atoms/alert'
import { Badge } from '@/components/atoms/badge'
import { Button } from '@/components/atoms/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/atoms/dialog'
import { Input } from '@/components/atoms/input'
import { Label } from '@/components/atoms/label'
import { AdminConfirmDialog } from '@/components/molecules/AdminConfirmDialog'
import { AdminCrudToolbar } from '@/components/molecules/AdminCrudToolbar'
import { AdminDataTable } from '@/components/molecules/AdminDataTable'
import { AdminPagination } from '@/components/molecules/AdminPagination'
import {
  createAdminUser,
  deleteAdminUser,
  fetchAdminRoles,
  fetchAdminUsers,
  updateAdminUser,
} from '@/lib/adminUsersApi'
import { toUserMessage } from '@/lib/apiError'
import { formatUnixTimestampSeconds as formatLocalizedTimestamp } from '@/lib/i18n/formatters'
import { defaultLanguage, normalizeLanguageCode } from '@/lib/i18n/languages'
import { queryKeys } from '@/lib/queryKeys'

const PAGE_LIMIT = 20

type AdminUsersPageProps = {
  filters: AdminUserSearchParams
  onFiltersChange: (filters: AdminUserSearchParams) => void
}

type FormMode =
  | { type: 'create' }
  | { type: 'edit'; user: AdminUserListItem }
  | null

const emptyForm: AdminUserFormState = {
  email: '',
  password: '',
  is_active: true,
  roles: [],
}

export function AdminUsersPage({
  filters,
  onFiltersChange,
}: AdminUsersPageProps) {
  const { t, i18n } = useTranslation('admin')
  const queryClient = useQueryClient()
  const [searchValue, setSearchValue] = useState(filters.query ?? '')
  const [formMode, setFormMode] = useState<FormMode>(null)
  const [form, setForm] = useState<AdminUserFormState>(emptyForm)
  const [formFeedback, setFormFeedback] = useState<string | null>(null)
  const [deleteFeedback, setDeleteFeedback] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AdminUserListItem | null>(
    null,
  )
  const currentLanguage =
    normalizeLanguageCode(i18n.resolvedLanguage ?? i18n.language) ??
    defaultLanguage

  useEffect(() => {
    setSearchValue(filters.query ?? '')
  }, [filters.query])

  const listParams = useMemo<AdminUserListParams>(
    () => ({
      offset: filters.offset,
      limit: PAGE_LIMIT,
      query: filters.query,
      is_active: filters.is_active,
      role: filters.role,
    }),
    [filters],
  )

  const usersQuery = useQuery({
    queryKey: queryKeys.adminUsers.list(listParams),
    queryFn: () => fetchAdminUsers(listParams),
  })
  const rolesQuery = useQuery({
    queryKey: queryKeys.adminUsers.roles,
    queryFn: fetchAdminRoles,
  })
  const roles = rolesQuery.data ?? []

  const createMutation = useMutation({
    mutationFn: (payload: AdminUserCreatePayload) => createAdminUser(payload),
    onSuccess: () => {
      setFormMode(null)
      setFormFeedback(null)
      void invalidateAdminUserQueries(queryClient)
    },
    onError: (error) => setFormFeedback(adminUserErrorMessage(error, t)),
  })
  const updateMutation = useMutation({
    mutationFn: ({
      userId,
      payload,
    }: {
      userId: string
      payload: AdminUserUpdatePayload
    }) => updateAdminUser(userId, payload),
    onSuccess: () => {
      setFormMode(null)
      setFormFeedback(null)
      void invalidateAdminUserQueries(queryClient)
    },
    onError: (error) => setFormFeedback(adminUserErrorMessage(error, t)),
  })
  const deleteMutation = useMutation({
    mutationFn: (userId: string) => deleteAdminUser(userId),
    onSuccess: () => {
      setDeleteTarget(null)
      setDeleteFeedback(null)
      void invalidateAdminUserQueries(queryClient)
    },
    onError: (error) => setDeleteFeedback(adminUserErrorMessage(error, t)),
  })

  const columns = useMemo<Array<AdminDataTableColumn<AdminUserListItem>>>(
    () => [
      {
        key: 'email',
        header: t('users.table.email'),
        render: (user) => (
          <div className="grid gap-1">
            <span className="font-medium">{user.email}</span>
            <span className="text-xs text-muted-foreground">{user.id}</span>
          </div>
        ),
      },
      {
        key: 'status',
        header: t('users.table.status'),
        render: (user) => (
          <Badge variant={user.is_active ? 'secondary' : 'outline'}>
            {user.is_active
              ? t('users.status.active')
              : t('users.status.inactive')}
          </Badge>
        ),
      },
      {
        key: 'roles',
        header: t('users.table.roles'),
        render: (user) => (
          <div className="flex flex-wrap gap-1">
            {user.roles.length > 0 ? (
              user.roles.map((roleCode) => (
                <Badge key={roleCode} variant="outline">
                  {roleCode}
                </Badge>
              ))
            ) : (
              <span className="text-muted-foreground">
                {t('users.table.noRoles')}
              </span>
            )}
          </div>
        ),
      },
      {
        key: 'last_login_at',
        header: t('users.table.lastLogin'),
        render: (user) =>
          user.last_login_at
            ? formatLocalizedTimestamp(user.last_login_at, currentLanguage)
            : t('users.table.neverLoggedIn'),
      },
      {
        key: 'created_at',
        header: t('users.table.createdAt'),
        render: (user) =>
          formatLocalizedTimestamp(user.created_at, currentLanguage),
      },
      {
        key: 'updated_at',
        header: t('users.table.updatedAt'),
        render: (user) =>
          formatLocalizedTimestamp(user.updated_at, currentLanguage),
      },
      {
        key: 'actions',
        header: '',
        className: 'w-28 text-right',
        render: (user) => (
          <div className="flex justify-end gap-1">
            <Button
              aria-label={t('users.table.editUser', { email: user.email })}
              size="icon-sm"
              type="button"
              variant="ghost"
              onClick={() => openEditForm(user)}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              aria-label={t('users.table.deleteUser', { email: user.email })}
              size="icon-sm"
              type="button"
              variant="ghost"
              onClick={() => {
                setDeleteFeedback(null)
                setDeleteTarget(user)
              }}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ),
      },
    ],
    [currentLanguage, t],
  )

  const users = usersQuery.data?.data ?? []
  const total = usersQuery.data?.count ?? 0
  const offset = usersQuery.data?.offset ?? filters.offset
  const limit = usersQuery.data?.limit ?? PAGE_LIMIT
  const isFormPending = createMutation.isPending || updateMutation.isPending
  const hasFilter =
    Boolean(filters.query) ||
    filters.is_active !== undefined ||
    Boolean(filters.role)

  const updateFilters = (next: Partial<AdminUserSearchParams>) => {
    onFiltersChange({ ...filters, ...next, offset: next.offset ?? 0 })
  }

  const openCreateForm = () => {
    setFormFeedback(null)
    setForm(emptyForm)
    setFormMode({ type: 'create' })
  }

  const openEditForm = (user: AdminUserListItem) => {
    setFormFeedback(null)
    setForm({
      email: user.email,
      password: '',
      is_active: user.is_active,
      roles: user.roles,
    })
    setFormMode({ type: 'edit', user })
  }

  const closeForm = () => {
    setFormFeedback(null)
    setFormMode(null)
  }

  const submitForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!formMode) {
      return
    }
    setFormFeedback(null)
    if (formMode.type === 'create') {
      createMutation.mutate({
        email: form.email,
        password: form.password,
        is_active: form.is_active,
        roles: form.roles,
      })
      return
    }
    updateMutation.mutate({
      userId: formMode.user.id,
      payload: compactUpdatePayload(form, formMode.user),
    })
  }

  return (
    <main className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold tracking-normal">
          {t('users.title')}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('users.description')}
        </p>
      </div>

      <section className="overflow-hidden rounded-lg border bg-background">
        <AdminCrudToolbar
          action={
            <Button type="button" onClick={openCreateForm}>
              <Plus className="size-4" />
              {t('users.create')}
            </Button>
          }
          searchPlaceholder={t('users.searchPlaceholder')}
          searchValue={searchValue}
          onSearchChange={setSearchValue}
          onSearchSubmit={() =>
            updateFilters({ query: searchValue.trim() || undefined })
          }
        >
          <label className="grid gap-1 text-xs font-medium text-muted-foreground">
            {t('users.status.label')}
            <select
              aria-label={t('users.status.filter')}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={
                filters.is_active === undefined
                  ? 'all'
                  : String(filters.is_active)
              }
              onChange={(event) =>
                updateFilters({
                  is_active:
                    event.target.value === 'all'
                      ? undefined
                      : event.target.value === 'true',
                })
              }
            >
              <option value="all">{t('users.status.all')}</option>
              <option value="true">{t('users.status.active')}</option>
              <option value="false">{t('users.status.inactive')}</option>
            </select>
          </label>
          <label className="grid gap-1 text-xs font-medium text-muted-foreground">
            {t('users.role.label')}
            <select
              aria-label={t('users.role.filter')}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={filters.role ?? ''}
              onChange={(event) =>
                updateFilters({ role: event.target.value || undefined })
              }
            >
              <option value="">{t('users.role.all')}</option>
              {roles.map((role) => (
                <option key={role.code} value={role.code}>
                  {role.display_name}
                </option>
              ))}
            </select>
          </label>
        </AdminCrudToolbar>
        <AdminDataTable
          columns={columns}
          emptyMessage={
            hasFilter ? t('users.table.emptyFiltered') : t('users.table.empty')
          }
          getRowKey={(user) => user.id}
          loading={usersQuery.isLoading}
          rows={users}
        />
        <AdminPagination
          limit={limit}
          offset={offset}
          total={total}
          onOffsetChange={(nextOffset) =>
            onFiltersChange({ ...filters, offset: nextOffset })
          }
        />
      </section>

      <Dialog
        open={formMode !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !isFormPending) {
            closeForm()
          }
        }}
      >
        {formMode ? (
          <DialogContent
            className="w-full max-w-lg gap-5"
            showCloseButton={false}
          >
            <form className="grid gap-5" onSubmit={submitForm}>
              <div className="grid gap-1">
                <DialogTitle>
                  {formMode.type === 'create'
                    ? t('users.form.createTitle')
                    : t('users.form.editTitle')}
                </DialogTitle>
                <DialogDescription>
                  {t('users.form.description')}
                </DialogDescription>
              </div>
              {formFeedback ? (
                <Alert variant="destructive">
                  <AlertDescription>{formFeedback}</AlertDescription>
                </Alert>
              ) : null}
              <div className="grid gap-4">
                <label className="grid gap-2">
                  <Label>{t('users.form.email')}</Label>
                  <Input
                    required
                    autoComplete="email"
                    type="email"
                    value={form.email}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        email: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="grid gap-2">
                  <Label>{t('users.form.password')}</Label>
                  <Input
                    autoComplete="new-password"
                    minLength={12}
                    required={formMode.type === 'create'}
                    type="password"
                    value={form.password}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        password: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    checked={form.is_active}
                    className="size-4"
                    type="checkbox"
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        is_active: event.target.checked,
                      }))
                    }
                  />
                  {t('users.form.active')}
                </label>
                <fieldset className="grid gap-2">
                  <legend className="text-sm font-medium">
                    {t('users.form.roles')}
                  </legend>
                  <div className="grid gap-2 rounded-md border p-3">
                    {roles.length > 0 ? (
                      roles.map((role) => (
                        <label
                          key={role.code}
                          className="flex items-start gap-2 text-sm"
                        >
                          <input
                            checked={form.roles.includes(role.code)}
                            className="mt-0.5 size-4"
                            type="checkbox"
                            onChange={() => toggleRole(role)}
                          />
                          <span className="grid gap-0.5">
                            <span>{role.display_name}</span>
                            <span className="text-xs text-muted-foreground">
                              {role.code}
                            </span>
                          </span>
                        </label>
                      ))
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        {t('users.form.noAvailableRoles')}
                      </span>
                    )}
                  </div>
                </fieldset>
              </div>
              <div className="flex justify-end gap-2">
                <Button
                  disabled={isFormPending}
                  type="button"
                  variant="outline"
                  onClick={closeForm}
                >
                  {t('common.cancel')}
                </Button>
                <Button disabled={isFormPending} type="submit">
                  {formMode.type === 'create'
                    ? t('users.form.createSubmit')
                    : t('users.form.saveSubmit')}
                </Button>
              </div>
            </form>
          </DialogContent>
        ) : null}
      </Dialog>

      <AdminConfirmDialog
        confirmLabel={t('users.delete.confirmLabel')}
        description={
          deleteTarget
            ? t('users.delete.description', { email: deleteTarget.email })
            : ''
        }
        errorMessage={deleteFeedback}
        isPending={deleteMutation.isPending}
        open={deleteTarget !== null}
        title={t('users.delete.title')}
        onCancel={() => {
          setDeleteFeedback(null)
          setDeleteTarget(null)
        }}
        onConfirm={() => {
          if (deleteTarget) {
            setDeleteFeedback(null)
            deleteMutation.mutate(deleteTarget.id)
          }
        }}
      />
    </main>
  )

  function toggleRole(role: AdminRole) {
    setForm((current) => ({
      ...current,
      roles: current.roles.includes(role.code)
        ? current.roles.filter((roleCode) => roleCode !== role.code)
        : [...current.roles, role.code],
    }))
  }
}

function compactUpdatePayload(
  form: AdminUserFormState,
  original: AdminUserListItem,
): AdminUserUpdatePayload {
  const payload: AdminUserUpdatePayload = {}
  if (form.email !== original.email) {
    payload.email = form.email
  }
  if (form.password.trim()) {
    payload.password = form.password
  }
  if (form.is_active !== original.is_active) {
    payload.is_active = form.is_active
  }
  if (!hasSameStringSet(form.roles, original.roles)) {
    payload.roles = form.roles
  }
  return payload
}

function hasSameStringSet(left: Array<string>, right: Array<string>): boolean {
  if (left.length !== right.length) {
    return false
  }
  const rightValues = new Set(right)
  return left.every((value) => rightValues.has(value))
}

function invalidateAdminUserQueries(
  queryClient: ReturnType<typeof useQueryClient>,
) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.adminUsers.root }),
    queryClient.invalidateQueries({ queryKey: queryKeys.auth.me }),
  ])
}

function adminUserErrorMessage(error: unknown, t: TFunction<'admin'>): string {
  return toUserMessage(error, {
    code: {
      email_already_registered: t('users.errors.emailAlreadyRegistered'),
      weak_password: t('users.errors.weakPassword'),
      role_not_found: t('users.errors.roleNotFound'),
    },
    fallback: t('users.errors.fallback'),
  })
}

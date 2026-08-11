import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import type { FormEvent } from 'react'
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
  isActive: true,
  roles: [],
}

export function AdminUsersPage({
  filters,
  onFiltersChange,
}: AdminUsersPageProps) {
  const queryClient = useQueryClient()
  const [searchValue, setSearchValue] = useState(filters.search ?? '')
  const [formMode, setFormMode] = useState<FormMode>(null)
  const [form, setForm] = useState<AdminUserFormState>(emptyForm)
  const [formFeedback, setFormFeedback] = useState<string | null>(null)
  const [deleteFeedback, setDeleteFeedback] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AdminUserListItem | null>(
    null,
  )

  useEffect(() => {
    setSearchValue(filters.search ?? '')
  }, [filters.search])

  const listParams = useMemo<AdminUserListParams>(
    () => ({
      offset: filters.offset,
      limit: PAGE_LIMIT,
      search: filters.search,
      isActive: filters.isActive,
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
    onError: (error) => setFormFeedback(adminUserErrorMessage(error)),
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
    onError: (error) => setFormFeedback(adminUserErrorMessage(error)),
  })
  const deleteMutation = useMutation({
    mutationFn: (userId: string) => deleteAdminUser(userId),
    onSuccess: () => {
      setDeleteTarget(null)
      setDeleteFeedback(null)
      void invalidateAdminUserQueries(queryClient)
    },
    onError: (error) => setDeleteFeedback(adminUserErrorMessage(error)),
  })

  const columns = useMemo<Array<AdminDataTableColumn<AdminUserListItem>>>(
    () => [
      {
        key: 'email',
        header: 'メールアドレス',
        render: (user) => (
          <div className="grid gap-1">
            <span className="font-medium">{user.email}</span>
            <span className="text-xs text-muted-foreground">{user.id}</span>
          </div>
        ),
      },
      {
        key: 'status',
        header: '状態',
        render: (user) => (
          <Badge variant={user.isActive ? 'secondary' : 'outline'}>
            {user.isActive ? '有効' : '停止'}
          </Badge>
        ),
      },
      {
        key: 'roles',
        header: 'ロール',
        render: (user) => (
          <div className="flex flex-wrap gap-1">
            {user.roles.length > 0 ? (
              user.roles.map((roleCode) => (
                <Badge key={roleCode} variant="outline">
                  {roleCode}
                </Badge>
              ))
            ) : (
              <span className="text-muted-foreground">なし</span>
            )}
          </div>
        ),
      },
      {
        key: 'lastLoginAt',
        header: '最終ログイン',
        render: (user) =>
          user.lastLoginAt ? formatDateTime(user.lastLoginAt) : '未ログイン',
      },
      {
        key: 'createdAt',
        header: '作成日時',
        render: (user) => formatDateTime(user.createdAt),
      },
      {
        key: 'updatedAt',
        header: '更新日時',
        render: (user) => formatDateTime(user.updatedAt),
      },
      {
        key: 'actions',
        header: '',
        className: 'w-28 text-right',
        render: (user) => (
          <div className="flex justify-end gap-1">
            <Button
              aria-label={`${user.email} を編集`}
              size="icon-sm"
              type="button"
              variant="ghost"
              onClick={() => openEditForm(user)}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              aria-label={`${user.email} を削除`}
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
    [],
  )

  const users = usersQuery.data?.items ?? []
  const total = usersQuery.data?.total ?? 0
  const offset = usersQuery.data?.offset ?? filters.offset
  const limit = usersQuery.data?.limit ?? PAGE_LIMIT
  const isFormPending = createMutation.isPending || updateMutation.isPending
  const hasFilter =
    Boolean(filters.search) ||
    filters.isActive !== undefined ||
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
      isActive: user.isActive,
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
        isActive: form.isActive,
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
        <h1 className="text-2xl font-semibold tracking-normal">ユーザー管理</h1>
        <p className="text-sm text-muted-foreground">
          管理画面からユーザー、状態、ロールを一括で管理します。
        </p>
      </div>

      <section className="overflow-hidden rounded-lg border bg-background">
        <AdminCrudToolbar
          action={
            <Button type="button" onClick={openCreateForm}>
              <Plus className="size-4" />
              ユーザー作成
            </Button>
          }
          searchPlaceholder="メールアドレスで検索"
          searchValue={searchValue}
          onSearchChange={setSearchValue}
          onSearchSubmit={() =>
            updateFilters({ search: searchValue.trim() || undefined })
          }
        >
          <label className="grid gap-1 text-xs font-medium text-muted-foreground">
            状態
            <select
              aria-label="状態フィルタ"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={
                filters.isActive === undefined
                  ? 'all'
                  : String(filters.isActive)
              }
              onChange={(event) =>
                updateFilters({
                  isActive:
                    event.target.value === 'all'
                      ? undefined
                      : event.target.value === 'true',
                })
              }
            >
              <option value="all">すべて</option>
              <option value="true">有効</option>
              <option value="false">停止</option>
            </select>
          </label>
          <label className="grid gap-1 text-xs font-medium text-muted-foreground">
            ロール
            <select
              aria-label="ロールフィルタ"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              value={filters.role ?? ''}
              onChange={(event) =>
                updateFilters({ role: event.target.value || undefined })
              }
            >
              <option value="">すべて</option>
              {roles.map((role) => (
                <option key={role.code} value={role.code}>
                  {role.displayName}
                </option>
              ))}
            </select>
          </label>
        </AdminCrudToolbar>
        <AdminDataTable
          columns={columns}
          emptyMessage={
            hasFilter
              ? '条件に一致するユーザーはいません。'
              : 'ユーザーはまだ登録されていません。'
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
                  {formMode.type === 'create' ? 'ユーザー作成' : 'ユーザー編集'}
                </DialogTitle>
                <DialogDescription>
                  メールアドレス、状態、ロールを設定します。
                </DialogDescription>
              </div>
              {formFeedback ? (
                <Alert variant="destructive">
                  <AlertDescription>{formFeedback}</AlertDescription>
                </Alert>
              ) : null}
              <div className="grid gap-4">
                <label className="grid gap-2">
                  <Label>メールアドレス</Label>
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
                  <Label>パスワード</Label>
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
                    checked={form.isActive}
                    className="size-4"
                    type="checkbox"
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        isActive: event.target.checked,
                      }))
                    }
                  />
                  有効
                </label>
                <fieldset className="grid gap-2">
                  <legend className="text-sm font-medium">ロール</legend>
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
                            <span>{role.displayName}</span>
                            <span className="text-xs text-muted-foreground">
                              {role.code}
                            </span>
                          </span>
                        </label>
                      ))
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        選択可能なロールがありません。
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
                  キャンセル
                </Button>
                <Button disabled={isFormPending} type="submit">
                  {formMode.type === 'create' ? '作成する' : '保存する'}
                </Button>
              </div>
            </form>
          </DialogContent>
        ) : null}
      </Dialog>

      <AdminConfirmDialog
        confirmLabel="削除する"
        description={
          deleteTarget
            ? `${deleteTarget.email} を削除します。削除済みユーザーは管理CRUDの対象外になります。`
            : ''
        }
        errorMessage={deleteFeedback}
        isPending={deleteMutation.isPending}
        open={deleteTarget !== null}
        title="ユーザーを削除"
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
  if (form.isActive !== original.isActive) {
    payload.isActive = form.isActive
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

function adminUserErrorMessage(error: unknown): string {
  return toUserMessage(error, {
    code: {
      EMAIL_ALREADY_REGISTERED: 'このメールアドレスは既に登録されています。',
      WEAK_PASSWORD: 'パスワードは12文字以上128文字以下で入力してください。',
      ROLE_NOT_FOUND: '指定されたロールが見つかりません。',
    },
    fallback: 'ユーザー管理の操作に失敗しました。',
  })
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('ja-JP', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

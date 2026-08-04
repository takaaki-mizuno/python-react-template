# Phase 6 Account Deletion 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **重要:** この Phase は現在のブランチで進める。worktree は使わない。ユーザー指示により、この計画更新作業では `git add` / `git commit` を実行しない。

**Goal:** 認証済みユーザーが自分のアカウントを削除できる公開 API と frontend 導線を追加し、Phase 5 で整備した `deleted_at` / session revoke / audit / email 再登録契約を user-facing workflow として完成させる。

**Architecture:** `DELETE /api/auth/me` を公開 account deletion endpoint として追加する。Backend は既存の CSRF middleware と `require_current_session` に乗せ、認証方式本体の `AuthUsecase` とは別に `AccountDeletionUsecase` を新設して、`UnitOfWorkInterface`、`AuthRepository.mark_user_deleted()`、`AuthRepository.revoke_sessions_for_user()`、user-owned data cleanup を 1 transaction に閉じる。Frontend は `/app/settings` に account settings UI を追加し、成功時に auth を含む query cache を消して `/` へ遷移する。

**Tech Stack:** FastAPI / SQLModel / Injector / PostgreSQL / Pytest / React 19 / TanStack Router / TanStack Query / Vitest / Tailwind CSS / shadcn/ui atoms

---

## 背景

`documents/reviews/20260801-review.md` の P3-3 では、ユーザー削除機能を作ると監査ログや session FK 方針が未決で詰まることが指摘された。Phase 5 (`documents/plans/20260803-phase5-residual-p2-p3-doc-sync.md`) では、その前提として次を実装済みである。

- `users.deleted_at` を追加し、`is_active = 凍結・停止`、`deleted_at = 退会または論理削除` と定義した。
- 通常の active user lookup は `deleted_at IS NULL` を含む。
- 認証時だけ `find_user_by_id_for_authentication()` で削除済み user も観測し、残存 session を revoke して `SESSION_REVOKED_DELETED_USER` を監査する。
- `uq_users_email_lower_active` は `deleted_at IS NULL` の partial unique index であり、削除済み user の email は再登録可能である。
- `mark_user_deleted()`、`revoke_sessions_for_user()`、`USER_MARKED_DELETED` は Phase 6 用の先行契約として backend に存在する。
- physical delete 時の FK は `auth_sessions.user_id` が `CASCADE`、`auth_audit_logs.user_id` / `session_id` が `SET NULL` になる。

一方、Phase 5 は公開 API と UI を明示的に対象外にした。現在は内部 contract はあるが、ユーザーが自分で退会できる workflow がない。Phase 6 ではこの穴を閉じる。

## 現行コードの分析

- `backend/app/controllers/auth_controller.py` は `GET /api/auth/me`、`POST /api/auth/logout`、cookie set/clear helper を持つ。`DELETE /api/auth/me` はここへ追加するのが最小変更である。
- `backend/app/bootstrap/csrf.py` は `DELETE` を unsafe method として扱い、`/api` 配下を既定で CSRF 検証する。新 endpoint に個別 CSRF dependency を書く必要はない。
- `backend/app/usecases/auth_usecase.py` は `UnitOfWorkInterface.transaction()` を使うが、ここへ sample item cleanup を直接入れると AuthModule / SampleModule の境界を越える。Phase 6 では `AccountDeletionUsecase` を独立させ、account management の orchestration として cross-domain cleanup を担わせる。
- `backend/app/services/auth_repository.py` の `mark_user_deleted()` は `USER_MARKED_DELETED` audit log を同じ repository 操作で作る。ただし現在の audit log は `session_id=None` であり、現在 session を紐付ける contract は持たない。
- `backend/app/models/sample_item_schemas.py` には `SQLModelConfig(alias_generator=to_camel, populate_by_name=True, extra="forbid")` の camelCase DTO 基底がある。`AccountDeletionRequest` は field-level alias ではなく、auth schema 側にも同型の基底を用意して載せる。
- `frontend/src/lib/apiClient.ts` は `delete()`、CSRF header 付与、CSRF 403 時の 1 回 retry、AbortSignal 透過を既に持つ。
- `frontend/src/hooks/useAuthSession.ts` は logout 成功時に `queryClient.clear()` してから `queryKeys.auth.me` を `null` にする。account deletion 成功時も同じ cache policy を使う。
- `frontend/src/routes/_authenticated.app.tsx` はまだ placeholder に近く、`<Outlet />` を持たない。TanStack Router の flat file routing で `_authenticated.app.settings.tsx` を作ると `/app` の子 route になり表示されないため、Phase 6 では trailing underscore の `_authenticated.app_.settings.tsx` を使い、`/app` の子ではない `/app/settings` route にする。
- `sample_items.owner_user_id` は `users.id` への FK `ON DELETE CASCADE` を持つが、account deletion は logical delete なので physical cascade は発火しない。Phase 6 で sample item を削除するなら明示的な repository method が必要である。

## 方針とその理由

### 採用方針

1. 公開 API として `DELETE /api/auth/me` を実装する。
2. Endpoint は認証必須にし、`require_current_session` で取得した current user だけを削除対象にする。
3. Endpoint は CSRF middleware の既定保護に乗せる。`AUTH_CSRF_EXEMPT_PATHS` には追加しない。
4. Request body は `{"confirmEmail": "<current email>", "password": "..."}` とする。`confirmEmail` は必須、`password` は optional field だが、current user が `password_hash IS NOT NULL` の場合だけ必須にする。
5. Password 保有ユーザーは account deletion 前に password 再認証を要求する。OAuth-only user (`password_hash IS NULL`) は password 再認証できないため、`confirmEmail` のみで通す。
6. 削除は logical delete とし、`users.deleted_at` と `users.updated_at` を設定する。`users.is_active` は変更しない。
7. 削除済み user の email は保持する。`uq_users_email_lower_active` により、削除後の同一 email 再登録は許可する。
8. 復元 API は作らない。Phase 6 の user-facing contract は不可逆な退会として扱う。
9. `auth_audit_logs` には成功時の `USER_MARKED_DELETED` を残す。公開 account deletion 経由では current session id と request IP を既存 column に記録する。個人情報追加を避けるため、Phase 6 では audit detail に email や user_agent を追加しない。
10. 削除時は current session を含む対象 user の全 active session を revoke する。
11. `sample_items` は account deletion と同時に削除する。テンプレート上の user-owned sample resource に独立した保持要件はないため、退会後も user-owned data を残すより削除を既定にする。
12. 成功時は 204 を返し、session cookie と CSRF cookie を clear する。
13. Password 再認証失敗は既存 login/register rate limiter のうち IP bucket と email+IP bucket だけを使う。email 単独 bucket には記録せず、成功時も login rate limiter の failure bucket を reset しない。このため、退会確認の password 失敗は login lockout にも影響し、直前の login 失敗は退会確認の 429 にも影響する。この結合は Phase 6 では許容し、専用 scope は後続の必要性が出るまで追加しない。
14. 新しい user-owned table の cleanup 漏れはメタデータ検査テストで落とす。Phase 6 時点の handled table は `sample_items` のみとする。
15. Frontend は `/app/settings` を追加し、削除確認 UI、confirm email 入力、password 入力、成功後 logout 相当の cache clear、`/` への遷移を提供する。
16. `/app/settings` への導線は `/app` のみから提供し、Header は変更しない。Header の account menu は role / account navigation をまとめて設計する後続 Phase まで広げない。
17. docs は backend / frontend の正典 (`AGENTS.md`) と references、Phase 6 plan に反映する。DB schema 変更は行わない。

### 採用理由

- `DELETE /api/auth/me` は既存の `GET /api/auth/me` と同じ resource を対象にするため、API surface として自然である。
- CSRF middleware は routing 前に unsafe API を拒否する設計なので、新 endpoint もこれに乗せるほうが repo の規約に合う。
- `confirmEmail` は誤操作防止であり、認証要素ではない。Phase 6 では password 保有ユーザーに password 再認証を要求し、OAuth-only user だけ `confirmEmail` にフォールバックすることで、テンプレートの既定値を安全側に寄せる。
- `deleted_at` のみを正とすると、Phase 5 の「`is_active` は凍結・停止、`deleted_at` は退会」という意味づけを壊さない。
- email を保持しても active unique index から再登録は可能であり、過去 user と新 user は UUID で区別できる。ただし同じ email で再登録された後は旧 user の復元が partial unique index 違反でできなくなるため、Phase 6 の退会は明示的に不可逆として扱う。
- sample item を物理削除することで、「user-owned resource は account deletion 時に方針をコードで強制する」というテンプレートとして重要な手本を残せる。sample CRUD はサンプルデータであり保持要件がないため soft delete は追加しない。将来 physical purge を入れた場合も `ON DELETE CASCADE` は最後の cleanup であり、account deletion 時の明示削除とは役割が異なる。
- cookie clear と query cache clear を logout と同じ流れに揃えると、削除後に stale user data が画面や cache に残るリスクを下げられる。
- 削除後は `/` へ遷移する。退会済みユーザーを `redirect=/app` 付き login へ送ると、削除済みアカウントではログインできないうえ、authenticated guard の redirect と競合する。

## スコープ

### 対象

- `DELETE /api/auth/me` の backend API。
- Account deletion request DTO と error code。
- Account deletion 専用 usecase / interface / DI module。
- sample item 全件削除 repository method。
- user-owned table cleanup のメタデータ検査テスト。
- Backend unit / integration tests。
- Frontend API function、hook または mutation helper、account settings route、confirmation UI。
- Frontend unit / route tests。
- `backend/AGENTS.md`、`frontend/AGENTS.md`、`documents/references/`、Phase 6 plan の同期。

### 対象外

- DB migration。Phase 5 の schema を前提にし、Phase 6 では新規 column / table / index を追加しない。
- メール再確認、OAuth provider re-authentication。
- 削除済み email の匿名化。
- 削除済み user の復元 API / admin recovery UI。
- 監査ログ detail schema の追加。
- Injector multibinding による cleanup registry。Phase 6 は `AccountDeletionUsecase` とメタデータ検査テストで cleanup 漏れを強制する。
- account deletion 完了メール送信。

## 変更予定ファイル

### Backend

- Modify: `backend/app/models/auth_schemas.py`
  - `AuthSchema` camelCase DTO 基底と `AccountDeletionRequest` を追加する。public JSON は camelCase の `confirmEmail` / `password`。
- Modify: `backend/app/models/auth_errors.py`
  - `AccountDeletionConfirmationMismatchError`、`AccountDeletionReauthRequiredError`、`AccountDeletionInvalidPasswordError` を追加する。
- Create: `backend/app/interfaces/usecases/account_deletion_usecase_interface.py`
  - account deletion 専用 usecase interface。
- Create: `backend/app/usecases/account_deletion_usecase.py`
  - current user の email 確認、password 再認証、sample item 削除、`mark_user_deleted()`、`revoke_sessions_for_user()` を 1 transaction で行う。
- Modify: `backend/app/interfaces/usecases/__init__.py`
  - `AccountDeletionUsecaseInterface` を re-export する。
- Modify: `backend/app/bootstrap/modules.py`
  - `AccountDeletionModule` を追加し、`AccountDeletionUsecaseInterface` を bind する。
- Modify: `backend/app/bootstrap/container.py`
  - `AccountDeletionModule` を Injector modules に追加する。
- Modify: `backend/app/controllers/auth_dependencies.py`
  - `get_account_deletion_usecase` dependency を追加する。
- Modify: `backend/app/interfaces/services/sample_item_repository_interface.py`
  - `delete_all_for_owner(owner_user_id: UUID) -> None` を追加する。
- Modify: `backend/app/services/sample_item_repository.py`
  - `DELETE FROM sample_items WHERE owner_user_id = :owner_user_id` を実装する。
- Modify: `backend/app/controllers/auth_controller.py`
  - `DELETE /api/auth/me` route、error responses、cookie clear を追加する。
- Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
  - controller wiring、400、204、cookie clear を追加する。
- Create: `backend/tests/unit/usecases/test_account_deletion_usecase.py`
  - transaction 内の削除順序、confirmEmail mismatch、password 再認証、rate limit、session revoke を追加する。
- Create: `backend/tests/unit/usecases/test_account_deletion_coverage.py`
  - `users` を参照する user-owned table が account deletion cleanup 対象に含まれることをメタデータから検査する。
- Modify: `backend/tests/unit/services/test_sample_item_repository.py`
  - owner scope delete statement / persist contract を追加する。
- Create: `backend/tests/integration/services/test_sample_item_repository.py`
  - owner scope cleanup の DB integration test を追加する。
- Modify: `backend/tests/integration/test_auth_controller.py`
  - account deletion happy path、CSRF 必須、再登録、旧 session 拒否、sample item cleanup を追加する。
- Modify: `backend/AGENTS.md`
  - Phase 6 account deletion 規約を追加する。
- Modify: `documents/references/backend-app-structure.md`
  - account deletion usecase と user-owned cleanup 規約を追加する。

### Frontend

- Modify: `frontend/src/lib/authApi.ts`
  - `deleteCurrentAccount({ confirmEmail, password })` を追加する。
- Create: `frontend/src/lib/authCache.ts`
  - logout / account deletion 共通の `clearAuthenticatedCache(queryClient)` helper。
- Modify: `frontend/src/hooks/useAuthSession.ts`
  - logout 成功時に `clearAuthenticatedCache()` を使う。
- Create: `frontend/src/hooks/useAccountDeletion.ts`
  - account deletion 専用 mutation。成功時に `clearAuthenticatedCache()` を使う。
- Create: `frontend/src/hooks/useAccountDeletion.test.tsx`
  - account deletion mutation の cache clear policy を確認する。
- Create: `frontend/src/components/organisms/Auth/AccountDeletionPanel.tsx`
  - email 確認入力、password 入力、送信中 state、error message、destructive button を持つ UI。
- Create: `frontend/src/components/organisms/Auth/AccountDeletionPanel.test.tsx`
  - 入力値送信、password autocomplete、error 表示を確認する。
- Modify: `frontend/src/components/molecules/AuthTextField.tsx`
  - `disabled?: boolean` prop を追加し、account deletion pending state で入力欄を disabled にできるようにする。
- Create: `frontend/src/routes/_authenticated.app_.settings.tsx`
  - `/app/settings` route。current user を表示し、`AccountDeletionPanel` を配置する。
- Create: `frontend/src/routes/app.settings.test.tsx`
  - deletion 成功で API call、cache clear、`/` redirect が起きることを確認する。
- Modify: `frontend/src/routes/_authenticated.app.tsx`
  - settings への導線を追加する。
- Modify: `frontend/AGENTS.md`
  - account settings / deletion UI の配置規約を追加する。
- Modify: `documents/references/frontend-app-structure.md`
  - TanStack Router の trailing underscore と account settings route 規約を追加する。

## API 契約

### `DELETE /api/auth/me`

- Auth: required. `require_current_session` を通す。
- CSRF: required. `CSRFMiddleware` により `csrf_token` cookie と `X-CSRF-Token` header を検証する。
- Request:

```json
{
  "confirmEmail": "user@example.com",
  "password": "current-password"
}
```

`password` は optional field だが、password 保有ユーザーでは必須。OAuth-only user (`password_hash IS NULL`) は `confirmEmail` のみで削除できる。

- Success: `204 No Content`
- Success side effects:
  - `users.deleted_at` と `users.updated_at` を同じ timezone-aware `now` に更新する。
  - `sample_items` の対象 user 所有 row を削除する。
  - 対象 user の未 revoke session をすべて revoke する。
  - `USER_MARKED_DELETED` audit log を作成する。
  - session cookie と CSRF cookie を `Max-Age=0` で clear する。
- Error:
  - 400 `ACCOUNT_DELETION_CONFIRMATION_MISMATCH`: `confirmEmail` が current user email と一致しない。
  - 400 `ACCOUNT_DELETION_REAUTH_REQUIRED`: current user が password 保有ユーザーで、`password` が未指定。
  - 400 `ACCOUNT_DELETION_INVALID_PASSWORD`: password 再認証に失敗した。401 にすると frontend の global unauthorized handler と競合するため account deletion 専用 400 とする。
  - 401 `UNAUTHORIZED`: session が無い、失効済み、削除済み user、inactive user。
  - 403 `CSRF_VALIDATION_FAILED`: CSRF cookie/header が無い、または session-bound CSRF が不一致。
  - 429 `ACCOUNT_DELETION_REAUTH_RATE_LIMITED`: password 再認証失敗が既定回数を超えた。
  - 422 validation error envelope: body 不正。

## 具体的なタスク

### Task 1: Phase 6 の baseline と前提を固定する

**Files:**
- Read: `backend/AGENTS.md`
- Read: `frontend/AGENTS.md`
- Read: `documents/plans/20260803-phase5-residual-p2-p3-doc-sync.md`
- Read: `backend/app/controllers/auth_controller.py`
- Read: `backend/app/usecases/auth_usecase.py`
- Read: `backend/app/models/sample_item_schemas.py`
- Read: `backend/app/bootstrap/modules.py`
- Read: `backend/app/bootstrap/container.py`
- Read: `frontend/src/lib/authApi.ts`
- Read: `frontend/src/hooks/useAuthSession.ts`
- Read: `frontend/src/routes/_authenticated.app.tsx`
- Read: `frontend/src/lib/appRouter.tsx`

- [x] **Step 1.1: 変更前 status を確認する**

Run:

```bash
rtk git status --short
```

Expected:

- 作業前の未コミット差分を把握する。
- ユーザー作業と思われる差分を revert しない。

- [x] **Step 1.2: Phase 5 contract が残っていることを確認する**

Run:

```bash
rtk grep -n "mark_user_deleted\|revoke_sessions_for_user\|USER_MARKED_DELETED\|deleted_at" backend/app backend/tests backend/AGENTS.md
```

Expected:

- `AuthRepositoryInterface.mark_user_deleted()` が存在する。
- `AuthRepositoryInterface.revoke_sessions_for_user()` が存在する。
- `AuthEventType.USER_MARKED_DELETED` が存在する。
- `backend/AGENTS.md` に Phase 5 認証永続化規約がある。

- [x] **Step 1.3: DB migration が不要であることを確認する**

Run:

```bash
rtk grep -n "deleted_at\|uq_users_email_lower_active\|sample_items" backend/alembic/versions backend/app/models
```

Expected:

- `users.deleted_at` と active email partial unique index は既存 migration にある。
- `sample_items.owner_user_id` は既存 table にある。
- Phase 6 で新規 revision を作らない判断を確認する。

### Task 2: Backend request / error contract を追加する

**Files:**
- Modify: `backend/app/models/auth_schemas.py`
- Modify: `backend/app/models/auth_errors.py`

- [x] **Step 2.1: `AccountDeletionRequest` の failing unit test を追加する**

Add assertions to an existing schema/model unit test or create `backend/tests/unit/models/test_auth_schemas.py` if no suitable file exists.

Required assertions:

- `AccountDeletionRequest.model_validate({"confirmEmail": "user@example.com"}).confirm_email == "user@example.com"`
- `AccountDeletionRequest.model_validate({"confirmEmail": "user@example.com", "password": "Password123!"}).password == "Password123!"`
- `AccountDeletionRequest.model_validate({"confirmEmail": "user@example.com"}).password is None`
- `AccountDeletionRequest.model_validate({"confirm_email": "user@example.com"}).confirm_email == "user@example.com"` for internal compatibility, matching the existing `populate_by_name=True` sample DTO pattern.
- `AccountDeletionRequest(confirm_email="user@example.com").model_dump(by_alias=True)` uses `confirmEmail`.
- `AccountDeletionRequest.model_validate({"confirmEmail": "user@example.com", "unexpected": True})` is validation error because request DTOs must forbid extra fields.
- Missing `confirmEmail` is validation error.

- [x] **Step 2.2: `AccountDeletionRequest` を追加する**

Implementation requirements:

- Add `AuthSchema(SQLModel)` in `backend/app/models/auth_schemas.py`.
- `AuthSchema.model_config` must match the sample DTO pattern:

```python
SQLModelConfig(alias_generator=to_camel, populate_by_name=True, extra="forbid")
```

- Class name: `AccountDeletionRequest`
- Base: `AuthSchema`
- Field name: `confirm_email`
- Public JSON: `confirmEmail`
- `confirm_email` type: `EmailStr`
- `password` type: `str | None`
- `password` field: `Field(default=None, max_length=128)`
- Do not migrate existing `RegisterRequest` / `LoginRequest` / `CsrfTokenResponse` in this task. They currently use explicit camelCase or all-lower field names and migration would broaden the Phase unnecessarily.

- [x] **Step 2.3: account deletion domain errors を追加する**

Implementation requirements:

- Add `AccountDeletionConfirmationMismatchError(Exception)` to `backend/app/models/auth_errors.py`.
- Add `AccountDeletionReauthRequiredError(Exception)` to `backend/app/models/auth_errors.py`.
- Add `AccountDeletionInvalidPasswordError(Exception)` to `backend/app/models/auth_errors.py`.
- Do not attach email address to the exception message.

- [x] **Step 2.4: schema/error tests を実行する**

Run:

作業ディレクトリ: `backend/`

```bash
rtk uv run pytest tests/unit/models -q
```

Expected:

- New schema test passes.
- Existing model tests pass.

### Task 3: sample item cleanup repository を追加する

**Files:**
- Modify: `backend/app/interfaces/services/sample_item_repository_interface.py`
- Modify: `backend/app/services/sample_item_repository.py`
- Modify: `backend/tests/unit/services/test_sample_item_repository.py`
- Create: `backend/tests/integration/services/test_sample_item_repository.py`

- [x] **Step 3.1: unit test で owner scope delete contract を先に書く**

Required assertions:

- `delete_all_for_owner(owner_user_id)` builds a `DELETE FROM sample_items` statement.
- Statement contains `sample_items.owner_user_id = ...`.
- Method returns `None`; account deletion does not need rowcount and must not expose a value no caller uses.
- Repository uses `UnitOfWorkInterface.session_scope()` and `_persist()` like existing write methods.

- [x] **Step 3.2: interface に method を追加する**

Signature:

```python
async def delete_all_for_owner(self, owner_user_id: UUID) -> None:
    raise NotImplementedError
```

- [x] **Step 3.3: concrete repository に method を追加する**

Implementation requirements:

- Import SQLAlchemy `delete` if not already imported.
- Use `delete(SampleItem).where(col(SampleItem.owner_user_id) == owner_user_id)`.
- Persist through the existing `_persist(session)` helper.
- Return `None`.

- [x] **Step 3.4: integration test で他 user の item を消さないことを確認する**

Required flow:

- Create user A and user B.
- Create at least one `sample_items` row for each user.
- Call `delete_all_for_owner(user_a.id)`.
- Assert user A item is gone.
- Assert user B item remains.

- [x] **Step 3.5: sample repository tests を実行する**

Run:

作業ディレクトリ: `backend/`

```bash
rtk uv run pytest tests/unit/services/test_sample_item_repository.py -q
```

Expected:

- New owner cleanup unit test passes.

If PostgreSQL is available:

```bash
rtk uv run pytest tests/integration/services/test_sample_item_repository.py tests/integration/test_sample_item_controller.py -q -ra
```

Expected:

- `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test` を設定した状態で実行し、missing `TEST_DATABASE_URL` による skip がない。
- Existing repository/sample integration behavior remains green.

### Task 4: AccountDeletionUsecase を独立して追加する

**Files:**
- Create: `backend/app/interfaces/usecases/account_deletion_usecase_interface.py`
- Create: `backend/app/usecases/account_deletion_usecase.py`
- Modify: `backend/app/interfaces/usecases/__init__.py`
- Modify: `backend/app/bootstrap/modules.py`
- Modify: `backend/app/bootstrap/container.py`
- Create: `backend/tests/unit/usecases/test_account_deletion_usecase.py`
- Create: `backend/tests/unit/usecases/test_account_deletion_coverage.py`

- [x] **Step 4.1: usecase unit test で confirmEmail mismatch を先に書く**

Required assertions:

- Calling `AccountDeletionUsecase.delete_account(auth_context, confirm_email="other@example.com", password=None, ip_address="127.0.0.1")` raises `AccountDeletionConfirmationMismatchError`.
- No transaction starts.
- No sample item deletion occurs.
- No `mark_user_deleted()` occurs.
- No `revoke_sessions_for_user()` occurs.

- [x] **Step 4.2: usecase unit test で password 保有ユーザーの再認証を先に書く**

Required assertions:

- If `auth_context.user.password_hash is not None` and `password is None`, raise `AccountDeletionReauthRequiredError`.
- If `auth_context.user.password_hash is not None` and password verification fails, raise `AccountDeletionInvalidPasswordError`.
- Password verification calls `PasswordHashExecutor.verify(raw_password, password_hash)` in the existing argument order.
- On password failure, call existing rate limiter `record_failure(rate_limit_ip, normalized_email, include_email_bucket=False)`.
- On password success, do not call `record_success()` because account deletion must not clear login failure buckets.
- If `auth_context.user.password_hash is None`, do not call password verification and allow deletion with only `confirmEmail`.

- [x] **Step 4.3: usecase unit test で reauth rate limit を先に書く**

Required assertions:

- Before verifying password for a password user, call `is_allowed(rate_limit_ip, normalized_email)`.
- If not allowed, raise `RateLimitExceededError` with the auth settings window seconds.
- Rate-limited account deletion does not start transaction and does not write audit log.
- `rate_limit_ip` is `ip_address or "unknown"`.

- [x] **Step 4.4: usecase unit test で transaction 内 orchestration を先に書く**

Required assertions:

- confirm email comparison is case-insensitive and trims surrounding spaces.
- Operation order inside transaction is:
  1. delete sample items for current user
  2. mark user deleted with a single `deleted_at`
  3. revoke all sessions for current user with the same timestamp
- All three operations observe `unit_of_work.in_transaction is True`.
- `revoke_sessions_for_user()` receives current user id and the same `deleted_at` timestamp.

- [x] **Step 4.5: account deletion usecase interface を追加する**

Signature:

```python
async def delete_account(
    self,
    auth_context: AuthenticatedSessionContext,
    confirm_email: str,
    password: str | None,
    ip_address: str | None,
) -> None:
    raise NotImplementedError
```

- [x] **Step 4.6: `AccountDeletionUsecase` を実装する**

Implementation requirements:

- Constructor dependencies:
  - `AuthRepositoryInterface`
  - `SampleItemRepositoryInterface`
  - `UnitOfWorkInterface`
  - `LoginRateLimiterInterface`
  - `AuthSettings`
  - `PasswordHashExecutor`
- Normalize both emails with `strip().lower()`.
- On mismatch, raise `AccountDeletionConfirmationMismatchError`.
- If `auth_context.user.password_hash is not None`:
  - Check rate limit with `self._auth_rate_limiter.is_allowed(rate_limit_ip, normalized_email)`.
  - If not allowed, raise `RateLimitExceededError(self._auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)`.
  - If `password is None`, raise `AccountDeletionReauthRequiredError`.
  - Verify password with `await self._password_hash_executor.verify(password, auth_context.user.password_hash)`.
  - On failed verify, call `record_failure(rate_limit_ip, normalized_email, include_email_bucket=False)` and raise `AccountDeletionInvalidPasswordError`.
- If `auth_context.user.password_hash is None`, skip password verification and rate limiter. OAuth-only reauth is outside Phase 6.
- Compute `deleted_at = utcnow()` once before the transaction.
- Use `async with self._unit_of_work.transaction():`.
- Await `self._sample_item_repository.delete_all_for_owner(auth_context.user.id)`.
- Await `self._auth_repository.mark_user_deleted(auth_context.user.id, deleted_at)`.
- Await `self._auth_repository.revoke_sessions_for_user(auth_context.user.id, deleted_at)`.
- Do not call `AuthUsecase.logout()`; account deletion has stronger semantics and must revoke all sessions, not only current session.
- Do not change `user.is_active`.

- [x] **Step 4.7: DI module に account deletion usecase を bind する**

Implementation requirements:

- Add `AccountDeletionModule(Module)` in `backend/app/bootstrap/modules.py`.
- Bind `AccountDeletionUsecaseInterface` to `AccountDeletionUsecase` with `scope=singleton`.
- Add `AccountDeletionModule()` to `build_container()` after `AuthModule()` and `SampleModule()`.
- Do not add `SampleItemRepositoryInterface` to `AuthUsecase`.

- [x] **Step 4.8: user-owned table coverage test を追加する**

Create `backend/tests/unit/usecases/test_account_deletion_coverage.py`:

```python
from sqlmodel import SQLModel

import app.models  # noqa: F401

AUTH_INTERNAL_TABLES = {"auth_sessions", "auth_audit_logs"}
HANDLED_TABLES = {"sample_items"}


def test_every_user_owned_table_is_handled_on_account_deletion() -> None:
    user_owned = {
        table.name
        for table in SQLModel.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.column.table.name == "users" and table.name not in AUTH_INTERNAL_TABLES
    }
    assert user_owned == HANDLED_TABLES, (
        "users を参照する新しい table を追加した場合、"
        "AccountDeletionUsecase の削除方針を決めて HANDLED_TABLES を更新すること"
    )
```

This test is the Phase 6 enforcement mechanism for detecting undecided cleanup policy. It does not prove that `AccountDeletionUsecase` actually deletes the table; the usecase orchestration tests and repository integration tests must still verify the concrete cleanup calls. If a future user-owned table is added and account deletion cleanup is not decided, the unit suite must fail.

- [x] **Step 4.9: account deletion usecase tests を実行する**

Run:

作業ディレクトリ: `backend/`

```bash
rtk uv run pytest tests/unit/usecases/test_account_deletion_usecase.py tests/unit/usecases/test_account_deletion_coverage.py -q
```

Expected:

- New account deletion orchestration tests pass.
- Coverage test fails if `sample_items` is removed from handled tables or a new user-owned table is introduced without updating the cleanup policy.

### Task 5: `DELETE /api/auth/me` controller を追加する

**Files:**
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Modify: `backend/tests/unit/bootstrap/test_csrf_middleware.py` only if an additional endpoint-specific CSRF assertion is needed

- [x] **Step 5.1: controller unit test で 204 と cookie clear を先に書く**

Required setup:

- Add `StubAccountDeletionUsecase` with `delete_account_called`, `deleted_confirm_email`, `deleted_password`, and async `delete_account(...)`.
- Stub an authenticated `AuthenticatedSessionContext`.
- Set `session_token` and `csrf_token` cookies.
- Send `DELETE /api/auth/me` with JSON `{"confirmEmail": "user@example.com", "password": "Password123!"}` and `X-CSRF-Token`.

Required assertions:

- Response status is 204.
- `delete_account_called is True`.
- Stub receives `confirm_email == "user@example.com"`.
- Stub receives `password == "Password123!"`.
- `Set-Cookie` clears session cookie with `Max-Age=0`.
- `Set-Cookie` clears `csrf_token` with `Max-Age=0`.

- [x] **Step 5.2: controller unit test で mismatch を 400 envelope にする**

Required assertions:

- Stub raises `AccountDeletionConfirmationMismatchError`.
- Response status is 400.
- Response body has `error.code == "ACCOUNT_DELETION_CONFIRMATION_MISMATCH"`.
- Cookies are not cleared on 400.

- [x] **Step 5.3: controller unit test で password 再認証 error を 400 envelope にする**

Required assertions:

- Stub raises `AccountDeletionReauthRequiredError`; response status is 400 and code is `ACCOUNT_DELETION_REAUTH_REQUIRED`.
- Stub raises `AccountDeletionInvalidPasswordError`; response status is 400 and code is `ACCOUNT_DELETION_INVALID_PASSWORD`.
- These errors must not be returned as 401 because frontend global unauthorized handling treats 401 as session loss.

- [x] **Step 5.4: controller unit test で reauth rate limit を 429 envelope にする**

Required assertions:

- Stub raises `RateLimitExceededError(3600)`.
- Response status is 429.
- Response code is `ACCOUNT_DELETION_REAUTH_RATE_LIMITED`.
- `Retry-After` is `3600`.

- [x] **Step 5.5: controller unit test で未認証は 401 にする**

Required assertions:

- `auth_context=None` means `require_current_session` rejects before usecase delete.
- Response status is 401.
- Stub `delete_account_called is False`.

- [x] **Step 5.6: route を実装する**

Implementation requirements:

- Add `get_account_deletion_usecase = inject(AccountDeletionUsecaseInterface)` in `backend/app/controllers/auth_dependencies.py`.
- Add `DELETE_ACCOUNT_ERROR_RESPONSES` with 400 / 401 / 403 / 422 / 429 models.
- Decorator: `@router.delete("/me", status_code=204, responses=DELETE_ACCOUNT_ERROR_RESPONSES)`.
- Parameters:
  - `payload: AccountDeletionRequest`
  - `request: Request`
  - `response: Response`
  - `auth_context: AuthenticatedSessionContext = Depends(require_current_session)`
  - `auth_settings: AuthSettings = Depends(get_auth_settings)`
  - `account_deletion_usecase: AccountDeletionUsecaseInterface = Depends(get_account_deletion_usecase)`
- On success:
  - call `account_deletion_usecase.delete_account(auth_context=auth_context, confirm_email=payload.confirm_email, password=payload.password, ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS))`
  - clear session and CSRF cookies using existing helpers
  - set status code 204
  - return response
- On `AccountDeletionConfirmationMismatchError`:
  - raise `api_error(400, "ACCOUNT_DELETION_CONFIRMATION_MISMATCH", "Account deletion confirmation did not match")`
- On `AccountDeletionReauthRequiredError`:
  - raise `api_error(400, "ACCOUNT_DELETION_REAUTH_REQUIRED", "Password confirmation is required")`
- On `AccountDeletionInvalidPasswordError`:
  - raise `api_error(400, "ACCOUNT_DELETION_INVALID_PASSWORD", "Password confirmation failed")`
- On `RateLimitExceededError`:
  - raise `api_error(429, "ACCOUNT_DELETION_REAUTH_RATE_LIMITED", "Too many account deletion confirmation attempts", headers={"Retry-After": str(error.retry_after_seconds or auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)})`

- [x] **Step 5.7: OpenAPI contract unit test を追加する**

Required assertions:

- `client.app.openapi()["paths"]["/api/auth/me"]["delete"]` exists.
- Its `tags` includes `"auth"`.
- Its request body schema references `AccountDeletionRequest`.
- Its responses include 204 / 400 / 401 / 403 / 422 / 429.

- [x] **Step 5.8: controller tests を実行する**

Run:

作業ディレクトリ: `backend/`

```bash
rtk uv run pytest tests/unit/controllers/test_auth_controller_dependency.py -q
```

Expected:

- Existing auth controller tests pass.
- New delete route tests pass.

### Task 6: Backend integration で end-to-end 契約を固定する

**Files:**
- Modify: `backend/tests/integration/test_auth_controller.py`

- [x] **Step 6.1: account deletion happy path integration test を追加する**

Required flow:

- `GET /api/auth/csrf`
- `POST /api/auth/register` with `delete-me@example.com`
- Save the first `session_token` and `csrf_token` from the same `client`.
- Clear the same `client` cookie jar. Do not create `with TestClient(client.app) as second_client`; running lifespan twice on the same app disposes the shared `AsyncEngine` and shuts down the shared `PasswordHashExecutor`.
- With the same `client`, get a fresh CSRF cookie without a session cookie.
- `POST /api/auth/login` for the same user to create a second independent session. Because `current_session_token` is absent, login must not revoke the first session.
- Save the second `session_token` and `csrf_token`.
- Clear the same `client` cookie jar again.
- Restore the first `session_token` and `csrf_token` to the same `client`.
- `GET /api/auth/me` returns 200
- Delete from the first client with `{"confirmEmail": "delete-me@example.com", "password": "Password123!"}` and current CSRF header.
- Assert 204
- Assert response clears session and CSRF cookies
- Assert `GET /api/auth/me` returns 401 after deletion
- Restore the second `session_token` and `csrf_token` to the same `client`.
- Assert `GET /api/auth/me` also returns 401, proving `revoke_sessions_for_user()` revoked sessions other than the deletion request's current session.
- Query DB and assert `users.deleted_at IS NOT NULL`
- Query DB and assert all sessions for old user have `revoked_at IS NOT NULL`
- Query DB and assert both saved session token hashes have `revoked_at IS NOT NULL`
- Query DB and assert one `USER_MARKED_DELETED` audit row exists for old user

- [x] **Step 6.2: missing / mismatched CSRF integration test を追加する**

Required assertions:

- Missing `X-CSRF-Token` on `DELETE /api/auth/me` returns 403 `CSRF_VALIDATION_FAILED`.
- Wrong session-bound CSRF returns 403 `CSRF_VALIDATION_FAILED`.
- User remains active (`deleted_at IS NULL`) after CSRF rejection.

- [x] **Step 6.3: confirmEmail mismatch integration test を追加する**

Required assertions:

- `DELETE /api/auth/me` with a different email returns 400 `ACCOUNT_DELETION_CONFIRMATION_MISMATCH`.
- User remains active.
- Session remains usable with `GET /api/auth/me` returning 200.

- [x] **Step 6.4: password 再認証 integration test を追加する**

Required assertions:

- Password user deletion with missing `password` returns 400 `ACCOUNT_DELETION_REAUTH_REQUIRED`.
- Password user deletion with wrong `password` returns 400 `ACCOUNT_DELETION_INVALID_PASSWORD`.
- Both failures keep `users.deleted_at IS NULL`.
- Correct password returns 204.
- OAuth-only behavior is covered by `backend/tests/unit/usecases/test_account_deletion_usecase.py`. Public register always creates a password hash, so integration coverage would require direct DB mutation and is not necessary for this Phase.

- [x] **Step 6.5: deleted email can be re-registered through public API**

Required flow:

- Register `reuse-delete@example.com`.
- Delete account with matching `confirmEmail`.
- Use correct `password`.
- Register `reuse-delete@example.com` again.
- Assert second register returns 201.
- Assert second user id differs from first user id.
- Assert `GET /api/auth/me` returns the second user.
- Assert old user remains deleted; do not attempt restore because same-email re-registration makes restore impossible by design.

- [x] **Step 6.6: sample_items are deleted with account**

Required flow:

- Register a user.
- Create at least one sample item through `POST /api/samples`.
- Delete account.
- Query DB and assert `sample_items` for old user id count is 0.

- [x] **Step 6.7: 二重送信 integration test を追加する**

Required assertions:

- Save `session_token` and `csrf_token` before the first delete because the 204 response clears the `TestClient` cookie jar.
- First `DELETE /api/auth/me` with correct body returns 204.
- Restore the saved old `session_token` and `csrf_token`, then send the second `DELETE /api/auth/me` with the saved `csrf_token` header.
- Second `DELETE /api/auth/me` with the restored old cookies returns 401 `UNAUTHORIZED` because the session was revoked.
- Second request does not create a second `USER_MARKED_DELETED` audit row.

- [x] **Step 6.8: auth integration tests を実行する**

Run:

作業ディレクトリ: `backend/`

```bash
rtk uv run pytest tests/integration/test_auth_controller.py -q -ra
```

Expected:

- `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test` を設定した状態で実行し、missing test DB による skip がない。
- Account deletion tests pass.

### Task 7: Frontend API と cache policy を追加する

**Files:**
- Modify: `frontend/src/lib/authApi.ts`
- Create: `frontend/src/lib/authCache.ts`
- Modify: `frontend/src/hooks/useAuthSession.ts`
- Modify: `frontend/src/hooks/useAuthSession.test.tsx`
- Create: `frontend/src/hooks/useAccountDeletion.ts`
- Create: `frontend/src/hooks/useAccountDeletion.test.tsx`

- [x] **Step 7.1: `deleteCurrentAccount()` の API test を追加する**

Required assertions:

- Calls `apiClient.delete<void>("/api/auth/me", { body: { confirmEmail, password } })`.
- Uses camelCase `confirmEmail` and lower camel `password`.

If mocking `fetch` rather than `apiClient`, assert:

- Request method is `DELETE`.
- Request body is `JSON.stringify({ confirmEmail: "user@example.com", password: "Password123!" })`.
- `X-CSRF-Token` header is attached when `csrf_token` cookie exists.

- [x] **Step 7.2: `deleteCurrentAccount()` を実装する**

Implementation requirements:

- Type:

```ts
export type DeleteAccountPayload = {
  confirmEmail: string
  password?: string
}
```

- Function:

```ts
export async function deleteCurrentAccount(
  payload: DeleteAccountPayload,
): Promise<void> {
  return apiClient.delete<void>('/api/auth/me', { body: payload })
}
```

- [x] **Step 7.3: `clearAuthenticatedCache()` を追加し logout test を更新する**

Implementation requirements:

- Create `frontend/src/lib/authCache.ts`.
- Export:

```ts
import type { QueryClient } from '@tanstack/react-query'

import { queryKeys } from './queryKeys'

export function clearAuthenticatedCache(queryClient: QueryClient) {
  queryClient.clear()
  queryClient.setQueryData(queryKeys.auth.me, null)
}
```

- Update `useAuthSession()` logout `onSuccess` to call `clearAuthenticatedCache(queryClient)`.
- Existing logout cache clear test must keep passing.

- [x] **Step 7.4: account deletion mutation の cache policy test を追加する**

Required assertions:

- On success, `queryClient.clear()` removes non-auth data.
- `queryKeys.auth.me` is set to `null` after clear.
- Behavior matches logout success policy.

- [x] **Step 7.5: `useAccountDeletion()` を実装する**

Implementation requirements:

- Create `frontend/src/hooks/useAccountDeletion.ts`.
- Use `useMutation({ mutationFn: deleteCurrentAccount, onSuccess: () => clearAuthenticatedCache(queryClient) })`.
- Do not add account deletion mutation to `useAuthSession()`. `useAuthSession()` remains the read/logout hook used by Header and guards.

- [x] **Step 7.6: frontend API/hook tests を実行する**

Run:

作業ディレクトリ: `frontend/`

```bash
rtk npm test -- authApi apiClient useAuthSession useAccountDeletion
```

Expected:

- New delete API / mutation cache tests pass.
- Existing API client unsafe DELETE tests remain green.

### Task 8: Account deletion UI を追加する

**Files:**
- Create: `frontend/src/components/organisms/Auth/AccountDeletionPanel.tsx`
- Create: `frontend/src/components/organisms/Auth/AccountDeletionPanel.test.tsx`
- Modify: `frontend/src/components/molecules/AuthTextField.tsx`
- Reuse: `frontend/src/components/atoms/button.tsx`
- Reuse: `frontend/src/components/atoms/input.tsx`
- Reuse: `frontend/src/components/molecules/AuthTextField.tsx`

- [x] **Step 8.1: UI test で入力欄と submit 可能条件を先に書く**

Required assertions:

- Current user email is visible.
- Confirm email input is rendered.
- Password input is rendered with `type="password"` and `autoComplete="current-password"`.
- Delete button is enabled when inputs are empty or mismatched, because backend is the source of truth for 400 responses.
- Pending state disables confirm email input, password input, and button.
- Confirm email and password inputs do not set the HTML `required` attribute. Backend validation owns missing-field / missing-password errors so the UI can display server 400 responses.

- [x] **Step 8.2: UI test で submit と error 表示を先に書く**

Required assertions:

- On submit, callback receives `{ confirmEmail: "<typed email value>", password: "<typed password value>" }`.
- If password is empty, callback receives `password: undefined` rather than an empty string.
- Pending state disables input and button.
- Error message is rendered with `role="alert"`.

- [x] **Step 8.3: `AuthTextField` に disabled prop を追加する**

Implementation requirements:

- Add `disabled?: boolean` to `AuthTextFieldProps`.
- Default `disabled = false`.
- Pass `disabled={disabled}` to `<Input />`.
- Existing `LoginForm` / `RegisterForm` tests must keep passing. They do not need to pass `disabled`.

- [x] **Step 8.4: `AccountDeletionPanel` を実装する**

Implementation requirements:

- Props:

```ts
type AccountDeletionPanelProps = {
  currentEmail: string
  errorMessage?: string | null
  isPending?: boolean
  onSubmit: (payload: { confirmEmail: string; password?: string }) => void
}
```

- Use `Button` with `variant="destructive"`.
- Use existing input/field components where possible.
- Use clear labels: `メールアドレスを入力して削除を確認` and destructive action label `アカウントを削除`.
- Add password label `現在のパスワード` and set `autoComplete="current-password"`.
- Pass `disabled={isPending}` to both `AuthTextField` instances.
- Do not pass `required` to account deletion fields. Empty email/password must reach backend validation and account deletion error handling.
- Do not disable submit solely because `confirmEmail` mismatches. Show server-provided `ACCOUNT_DELETION_CONFIRMATION_MISMATCH` message instead.
- Do not use browser `confirm()`; keep UI testable and accessible.

- [x] **Step 8.5: UI tests を実行する**

Run:

作業ディレクトリ: `frontend/`

```bash
rtk npm test -- AccountDeletionPanel
```

Expected:

- New component tests pass.

### Task 9: `/app/settings` route と導線を追加する

**Files:**
- Create: `frontend/src/routes/_authenticated.app_.settings.tsx`
- Create: `frontend/src/routes/app.settings.test.tsx`
- Modify: `frontend/src/routes/_authenticated.app.tsx`
- Modify generated route tree only through the existing TanStack Router plugin workflow, not by hand editing generated files if the repo uses generated route output.

- [x] **Step 9.1: route test で成功 workflow を先に書く**

Required flow:

- Mock `/api/auth/me` to return user.
- Mock `/api/auth/me` DELETE to return 204.
- Render `/app/settings`.
- Type matching email.
- Type password.
- Submit.
- Assert DELETE body contains `confirmEmail` and `password`.
- Assert navigation goes to `/`.
- Assert stale query data is cleared if test can observe query client.

- [x] **Step 9.2: route test で API error message を先に書く**

Required assertions:

- 400 `ACCOUNT_DELETION_CONFIRMATION_MISMATCH` maps to a Japanese user message asking the user to confirm the email.
- 400 `ACCOUNT_DELETION_REAUTH_REQUIRED` maps to a Japanese user message asking for the current password.
- 400 `ACCOUNT_DELETION_INVALID_PASSWORD` maps to a Japanese user message saying the password did not match.
- 429 `ACCOUNT_DELETION_REAUTH_RATE_LIMITED` maps to a Japanese user message asking the user to wait.
- 403 `CSRF_VALIDATION_FAILED` uses existing CSRF user message.
- Empty `confirmEmail` reaches backend validation and returns 422; it maps to `入力内容を確認してください。`.
- Non-ApiError uses fallback message.

- [x] **Step 9.3: settings route を実装する**

Implementation requirements:

- Use `_authenticated` layout, so route path is `/app/settings`.
- File name must be `frontend/src/routes/_authenticated.app_.settings.tsx`. The trailing underscore prevents this route from nesting under `/app`, because `_authenticated.app.tsx` is a page and does not render `<Outlet />`.
- Read current user from `useAuthSession()` or query cache.
- If user is unexpectedly null, rely on guard or show nothing until query resolves.
- On success:
  - Clear cache through account deletion mutation success handler.
  - Navigate to `/` using existing typed navigation: `navigate({ to: "/" })`.
- Use `toUserMessage()` with code override:
  - `ACCOUNT_DELETION_CONFIRMATION_MISMATCH`: `入力されたメールアドレスが現在のアカウントと一致しません。`
  - `ACCOUNT_DELETION_REAUTH_REQUIRED`: `アカウント削除には現在のパスワード入力が必要です。`
  - `ACCOUNT_DELETION_INVALID_PASSWORD`: `現在のパスワードが一致しません。`
  - `ACCOUNT_DELETION_REAUTH_RATE_LIMITED`: `確認の試行回数が多すぎます。時間をおいて再度お試しください。`
- Use `toUserMessage()` with status override:
  - `422`: `入力内容を確認してください。`

- [x] **Step 9.4: `/app` から settings へ導線を追加する**

Implementation requirements:

- Add a simple settings link on `/app`.
- Keep the page utilitarian; avoid marketing hero layout in app area.
- Use existing typography/classes and avoid nested cards.

- [x] **Step 9.5: Header を変更しないことを確認する**

Decision:

- Phase 6 では Header / AuthMenu に settings link を追加しない。
- `/app` から `/app/settings` への導線だけを追加する。
- Header の account menu は role / account navigation をまとめて設計する後続 Phase まで広げない。

- [x] **Step 9.6: route tests を実行する**

Run:

作業ディレクトリ: `frontend/`

```bash
rtk npm test -- app.settings app
```

Expected:

- `/app/settings` route tests pass.
- Existing `/app` auth guard tests still pass.

### Task 10: ドキュメントを同期する

**Files:**
- Modify: `backend/AGENTS.md`
- Modify: `frontend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/references/frontend-app-structure.md`
- Modify: `documents/plans/20260803-phase6-account-deletion-handoff.md`

- [x] **Step 10.1: backend account deletion 規約を追記する**

Add to `backend/AGENTS.md` near Phase 5 auth persistence rules:

- `DELETE /api/auth/me` is the canonical self-service account deletion endpoint.
- It requires authenticated session and CSRF middleware validation.
- It requires `confirmEmail` matching current user email.
- `confirmEmail` is an accidental deletion guard, not an authentication factor. Session hijack resistance still depends on CSRF middleware and cookie security.
- Password users require current password reauthentication; OAuth-only users fall back to `confirmEmail` until OAuth reauthentication is implemented.
- Account deletion password reauthentication uses the existing login rate limiter IP and email+IP buckets. Failed account deletion confirmation can contribute to login lockout, and prior login failures can cause account deletion confirmation to return 429.
- It sets `users.deleted_at`; it does not change `is_active`.
- It revokes all sessions for the user.
- It deletes `sample_items` owned by the user.
- It keeps deleted user email for audit/history while allowing re-registration through active partial unique index.
- Same-email re-registration makes restoring the old deleted user impossible without first resolving the active email uniqueness conflict.
- User row logical deletion and sample item physical deletion are intentionally asymmetric: user identity/audit history remains, sample content is removed because the sample resource has no retention requirement.
- New user-owned resources must update `AccountDeletionUsecase` and `tests/unit/usecases/test_account_deletion_coverage.py` before adding the resource.
- `test_account_deletion_coverage.py` detects undecided cleanup policy from SQLModel metadata for tables that directly reference `users`. It does not detect indirect ownership, FK-less `user_id` columns, or models that were not imported into SQLModel metadata. It does not prove the cleanup is actually executed; concrete usecase/repository tests must verify deletion behavior.

- [x] **Step 10.2: frontend account settings 規約を追記する**

Add to `frontend/AGENTS.md`:

- Account management UI lives under `/app/settings`.
- Destructive account operations use explicit typed confirmation and Japanese error messages through `toUserMessage()`.
- Account deletion success must clear all TanStack Query cache and set `queryKeys.auth.me` to `null`.
- Account deletion success navigates to `/`, not `/login?redirect=/app`.
- `/app/settings` uses `routes/_authenticated.app_.settings.tsx` with trailing underscore so it is protected by `_authenticated` but does not require `_authenticated.app.tsx` to render `<Outlet />`.
- Header / AuthMenu does not expose settings in Phase 6; `/app` owns the settings link.

- [x] **Step 10.3: backend reference を更新する**

Add to `documents/references/backend-app-structure.md`:

- `AccountDeletionUsecase` is the account management orchestration boundary.
- AuthUsecase must not depend on sample repositories.
- `tests/unit/usecases/test_account_deletion_coverage.py` detects user-owned cleanup policy coverage from SQLModel metadata, while `test_account_deletion_usecase.py` and repository integration tests verify the actual cleanup calls.
- Account deletion does not create a new DB migration in Phase 6.

- [x] **Step 10.4: frontend reference を更新する**

Add to `documents/references/frontend-app-structure.md`:

- Account settings route lives at `/app/settings`.
- Use TanStack Router trailing underscore when a protected route shares a path prefix with a page that has no `<Outlet />`.
- `routeTree.gen.ts` remains generated and must not be manually edited.

- [x] **Step 10.5: Phase 6 plan の進捗欄を更新する**

After implementation, add an execution log section to this file:

- Commands run.
- Test results.
- Any deviations from this plan.
- Any follow-up items intentionally left for later.

### Task 11: 全体 verification を実行する

**Files:**
- No source changes unless verification reveals a defect.

- [x] **Step 11.1: Backend unit quality gate を実行する**

Run:

作業ディレクトリ: `backend/`

```bash
rtk uv run ruff check .
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
rtk uv run mypy app manage.py
rtk uv run pytest tests/unit -q
```

Expected:

- All commands exit 0.

- [x] **Step 11.2: Backend integration target を実行する**

Run:

作業ディレクトリ: `backend/`

```bash
rtk uv run pytest tests/integration/test_auth_controller.py tests/integration/services/test_auth_repository.py tests/integration/test_sample_item_controller.py -q -ra
```

Expected:

- `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test` を設定した状態で実行し、missing `TEST_DATABASE_URL` による skip がない。
- All targeted integration tests pass.

- [x] **Step 11.3: Frontend quality gate を実行する**

Run:

作業ディレクトリ: `frontend/`

```bash
rtk npm run check:ci
rtk npm test
rtk npm run build
```

Expected:

- All commands exit 0.

- [x] **Step 11.4: Docker quality gate を実行する**

Run:

作業ディレクトリ: repository root

```bash
rtk docker compose config
rtk docker build --target runtime .
rtk docker build --target backend-dev .
```

Expected:

- All commands exit 0.
- Dockerfile is the repository-root `Dockerfile`; build context must be repository root because the Dockerfile copies both `frontend/` and `backend/`.
- Phase 6 does not edit Dockerfiles, but root `AGENTS.md` defines these as PR-before-merge quality gates, so they remain in the execution checklist.

- [x] **Step 11.5: OpenAPI smoke を実行する**

Required assertions:

- Start backend.
- Fetch `/openapi.json` in a non-production environment.
- Assert `/api/auth/me` contains a `delete` operation.
- Assert the operation tag is `auth`.
- Assert request body includes `confirmEmail` and optional `password`.

- [ ] **Step 11.6: Manual smoke を実施する**

Required flow:

- Start backend and frontend using repo-standard commands.
- Register a user.
- Open `/app/settings`.
- Type current email and current password, then delete account.
- Confirm redirect to `/`.
- Confirm `/api/auth/me` returns 401.
- Register again with the same email and confirm new login succeeds.

## 実行ログ

### 実装メモ

- Backend は `AccountDeletionUsecase` を `AuthUsecase` から独立させ、`SampleItemRepository.delete_all_for_owner()`、`AuthRepository.mark_user_deleted()`、`AuthRepository.revoke_sessions_for_user()` を 1 transaction 内で順に呼ぶ構成にした。
- Password 保有ユーザーは `password` 再認証を要求し、OAuth-only user (`password_hash IS NULL`) は `confirmEmail` のみで通す unit test を追加した。
- Password 再認証失敗は専用 `AccountDeletionInvalidPasswordError` で 400 `ACCOUNT_DELETION_INVALID_PASSWORD` に変換し、login の `InvalidCredentialsError` / 401 と混同しないようにした。
- `tests/unit/usecases/test_account_deletion_coverage.py` を追加し、SQLModel metadata 上の user-owned table が `sample_items` 以外に増えた場合に cleanup 方針未決として落ちるようにした。
- Frontend は `deleteCurrentAccount()`、`useAccountDeletion()`、`clearAuthenticatedCache()`、`AccountDeletionPanel`、`/app/settings` route を追加した。
- `/app/settings` は `routes/_authenticated.app_.settings.tsx` で定義し、`_authenticated` guard 配下に置きつつ、`_authenticated.app.tsx` に `<Outlet />` を要求しない構成にした。
- Header / AuthMenu は変更せず、`/app` から `/app/settings` への導線だけを追加した。

### 実行した主なコマンド

Backend:

```bash
rtk git status --short
rtk grep -n 'mark_user_deleted|revoke_sessions_for_user|USER_MARKED_DELETED|deleted_at' backend/app backend/tests backend/AGENTS.md
rtk grep -n 'deleted_at|uq_users_email_lower_active|sample_items' backend/alembic/versions backend/app/models
env UV_CACHE_DIR=.cache/uv uv run pytest tests/unit/models -q
env UV_CACHE_DIR=.cache/uv uv run pytest tests/unit/services/test_sample_item_repository.py -q
env UV_CACHE_DIR=.cache/uv uv run pytest tests/unit/usecases/test_account_deletion_usecase.py tests/unit/usecases/test_account_deletion_coverage.py -q
env UV_CACHE_DIR=.cache/uv uv run pytest tests/unit/controllers/test_auth_controller_dependency.py -q
env UV_CACHE_DIR=.cache/uv DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-upgrade
env UV_CACHE_DIR=.cache/uv TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/services/test_sample_item_repository.py tests/integration/test_sample_item_controller.py tests/integration/test_auth_controller.py -q -ra
env UV_CACHE_DIR=.cache/uv uv run ruff check .
env UV_CACHE_DIR=.cache/uv uv run isort . --check-only
env UV_CACHE_DIR=.cache/uv uv run yapf -dr app/ tests/ alembic/ manage.py
env UV_CACHE_DIR=.cache/uv uv run mypy app manage.py
env UV_CACHE_DIR=.cache/uv uv run pytest tests/unit -q
env UV_CACHE_DIR=.cache/uv TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_controller.py tests/integration/services/test_auth_repository.py tests/integration/test_sample_item_controller.py -q -ra
```

Frontend:

```bash
rtk npm test -- authApi apiClient useAuthSession useAccountDeletion
rtk npm test -- AccountDeletionPanel LoginForm RegisterForm
rtk npm test -- app.settings app
rtk npm run check:ci
rtk npm test
rtk npm run build
```

Docker / smoke:

```bash
rtk docker compose config
docker build --target runtime .
docker build --target backend-dev .
env UV_CACHE_DIR=.cache/uv ENVIRONMENT=local DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test AUTH_COOKIE_SECURE=false uv run python manage.py serve --host 127.0.0.1 --port 8001 --no-reload
curl -s http://127.0.0.1:8001/openapi.json -o /tmp/phase6-openapi.json
python3 -c 'import json; data=json.load(open("/tmp/phase6-openapi.json")); op=data["paths"]["/api/auth/me"]["delete"]; req=data["components"]["schemas"]["AccountDeletionRequest"]; print(op["tags"], sorted(op["responses"].keys()), req["properties"], req.get("required"))'
```

### 結果

- Backend unit: `285 passed, 1 warning`
- Backend targeted integration: `50 passed, 5 warnings`
- Additional backend integration target including sample repository: `44 passed, 5 warnings`
- Frontend focused tests: API/hook `22 passed`、Auth UI `13 passed`、route `20 passed`
- Frontend full tests: `103 passed`
- Frontend build: success
- Docker: `docker compose config`、`docker build --target runtime .`、`docker build --target backend-dev .` が成功
- OpenAPI smoke: `/api/auth/me` に `delete` があり、tag は `auth`、responses は `204 / 400 / 401 / 403 / 422 / 429`、request body は `AccountDeletionRequest` 参照で `confirmEmail` 必須・`password` optional

### 逸脱 / 注意

- sandbox 内の `uv` が `/Users/takaaki/.cache/uv` 書き込みまたは macOS system configuration 周りで失敗したため、検証コマンドは `UV_CACHE_DIR=.cache/uv` を指定し、一部は権限昇格で実行した。
- `docker build` は sandbox から Docker socket へ接続できなかったため、権限昇格で実行した。
- `npm test` では既存の jsdom `Window.scrollTo()` 未実装 warning と、error boundary 検証用の意図的な 500 stderr が出るが、テストは pass している。
- `npm run build` と Docker runtime build では既存の `%VITE_SITE_URL% is not defined` warning が出るが、build は成功している。
- 実ブラウザでの manual smoke はこの実装作業内では未実施。代わりに backend integration で register/delete/re-register、frontend route/component tests で `/app/settings` の入力・submit・redirect・error 表示を検証した。

### 後続候補

- 実ブラウザで `/app/settings` の manual smoke を行う。
- OAuth/passwordless login を導入する Phase で `AuthUserResponse` に `hasPassword` 相当を追加し、password field の表示条件を分岐する。
- `RegisterRequest` / `LoginRequest` と `AccountDeletionRequest` の schema base class を統一する。
- account deletion 専用 rate limiter scope が必要になった場合、login/register bucket 共有を切り離す。

### 追加レビュー対応ログ

- [x] 成功時の `USER_MARKED_DELETED` audit log に current session id と request IP を残す。
- [x] password 再認証失敗時に `ACCOUNT_DELETION_REAUTH_FAILED` audit log を current user / current session / request IP / user_agent 付きで作成する。
- [x] account deletion 再認証の rate limit 判定から email 単独 bucket を外し、IP bucket と email+IP bucket だけを見る専用判定にする。
- [x] password が空文字の場合は password 未指定と同じ `ACCOUNT_DELETION_REAUTH_REQUIRED` とし、hash verify と rate limit failure 記録を行わない。
- [x] 確認 email field を `autoComplete="off"` に変更する。
- [x] 削除エラー表示時に confirmEmail/password field へ `aria-invalid` を付与する。
- [x] `/app/settings` に `アカウント設定` の h1 と `/app` への戻り導線を追加する。
- [x] `/app/settings` の成功テストを、削除後の `/api/auth/me` 再取得が 401 になる実挙動に合わせる。
- [x] coverage test の保証範囲を AGENTS / reference / plan に注記する。
- [x] `mark_user_deleted()` の `session_id` / `ip_address` を省略不可 keyword-only argument にし、監査 context の暗黙省略を防ぐ。
- [x] `aria-invalid` は `ACCOUNT_DELETION_CONFIRMATION_MISMATCH` で confirmEmail、`ACCOUNT_DELETION_REAUTH_REQUIRED` / `ACCOUNT_DELETION_INVALID_PASSWORD` で password のみに立て、429 / CSRF では field を invalid にしない。
- [x] integration test の `USER_MARKED_DELETED` audit query から、TestClient では検証できない `audit.ip_address::text` select を削除し、current session 同一性の検証に絞る。

- 成功時の `USER_MARKED_DELETED` audit log に current session id と request IP を残すように `mark_user_deleted()` の repository 契約を拡張した。
- password 再認証失敗時に `ACCOUNT_DELETION_REAUTH_FAILED` audit log を current user / current session / request IP / user_agent 付きで作成するようにした。
- account deletion 再認証の rate limit 判定は email 単独 bucket を読まず、IP bucket と email+IP bucket だけを見る専用判定に変更した。
- password が空文字の場合は password 未指定と同じ `ACCOUNT_DELETION_REAUTH_REQUIRED` とし、hash verify と rate limit failure 記録を行わないようにした。
- 確認 email field は `autoComplete="off"` に変更し、error 表示時に confirmEmail/password field へ `aria-invalid` を付与した。
- `/app/settings` に page h1 と `/app` への戻り導線を追加した。
- `/app/settings` の成功テストは削除後の `/api/auth/me` 再取得が 401 になる現実の挙動に合わせた。
- `mark_user_deleted()` の `session_id` / `ip_address` は省略不可 keyword-only argument に変更し、監査 context なしで呼ぶ場合も `None` を明示させるようにした。
- `aria-invalid` は error code に対応する field だけに付与するように変更した。429 / CSRF など field に紐づかない error では input を invalid にしない。
- integration test の success audit query から `audit.ip_address::text` select を削除した。TestClient の direct client host は IP として解決できないため、IP の受け渡しは usecase / repository unit tests で検証し、integration は current session id の同一性に絞る。
- 追加レビュー対応後に以下を確認した:
  - Backend targeted unit: `54 passed, 1 warning`
  - Backend repository targeted unit/integration: `20 passed, 1 warning`
  - Backend unit: `288 passed, 1 warning`
  - Backend integration: `71 passed, 5 warnings`
  - Backend static checks: `ruff` / `isort --check-only` / `yapf -dr` / `mypy` pass
  - Frontend focused tests: `14 passed`
  - Frontend full tests: `104 passed`
  - Frontend `check:ci` pass
  - Frontend build pass。既存 warning として `%VITE_SITE_URL% is not defined` が残る

## 受け入れ条件

- [x] `DELETE /api/auth/me` is present in OpenAPI under auth tag.
- [x] Unauthenticated `DELETE /api/auth/me` returns 401 error envelope.
- [x] Missing or mismatched CSRF returns 403 `CSRF_VALIDATION_FAILED`.
- [x] Mismatched `confirmEmail` returns 400 `ACCOUNT_DELETION_CONFIRMATION_MISMATCH`.
- [x] Missing required password for a password user returns 400 `ACCOUNT_DELETION_REAUTH_REQUIRED`.
- [x] Wrong password for a password user returns 400 `ACCOUNT_DELETION_INVALID_PASSWORD`, not 401.
- [x] OAuth-only user with `password_hash IS NULL` can delete with `confirmEmail` only; this is covered in account deletion usecase unit tests because public register always creates a password hash.
- [x] Reauth password failures are rate-limited with 429 `ACCOUNT_DELETION_REAUTH_RATE_LIMITED`.
- [x] Reauth password failures write `ACCOUNT_DELETION_REAUTH_FAILED` with current user/session audit context.
- [x] Successful deletion returns 204 and clears session / CSRF cookies.
- [x] Successful deletion sets `users.deleted_at` and does not change `users.is_active`.
- [x] Successful deletion revokes every active session for the user.
- [x] A second client session for the same user is revoked and cannot access `/api/auth/me`.
- [x] Successful deletion writes `USER_MARKED_DELETED`.
- [x] Successful deletion writes `USER_MARKED_DELETED` with current session audit context.
- [x] Successful deletion deletes `sample_items` owned by the user.
- [x] A second `DELETE /api/auth/me` with saved-and-restored old cookies returns 401 and does not create a duplicate `USER_MARKED_DELETED` audit row.
- [x] Deleted user's old session cannot access `/api/auth/me`.
- [x] Same email can be registered again after deletion.
- [x] New user id differs from deleted user id.
- [x] Frontend `/app/settings` provides account deletion UI.
- [x] Frontend maps account deletion 422 validation errors, including empty `confirmEmail`, to `入力内容を確認してください。`.
- [x] Frontend deletion success clears query cache and redirects to `/`.
- [x] Header / AuthMenu remains unchanged; `/app` owns the settings link.
- [x] `tests/unit/usecases/test_account_deletion_coverage.py` fails when a new user-owned table references `users` without an explicit cleanup decision.
- [x] Backend and frontend AGENTS docs and `documents/references/` describe the Phase 6 account deletion contract.

## 後続 Phase 候補

- OAuth re-authentication before account deletion.
- Expose `hasPassword` or equivalent account-authentication-method metadata in `AuthUserResponse` when OAuth/passwordless login is introduced, so frontend can conditionally render password reauthentication UI.
- Email anonymization option for projects that require stronger PII erasure.
- Domain-specific resource cleanup registry once multiple user-owned resources exist.
- Dedicated account deletion reauthentication rate limiter write bucket, if login lockout coupling becomes unacceptable for projects that need stricter session-hijack containment.
- Consolidate `/app/settings` account deletion error metadata into one table that maps each backend error code to both user message and invalid field target.
- Admin-side deleted user audit viewer.
- Account deletion completion notification email.

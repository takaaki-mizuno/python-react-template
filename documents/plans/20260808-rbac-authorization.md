# RBAC 権限管理実装計画

> Superseded: 2026-08-10 の `documents/plans/20260810-code-managed-authorization.md` により、DB catalog と `authz-sync` は廃止された。この計画は履歴として残す。

> **Agentic worker 向け:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. タスクごとにチェックボックスを更新する。ユーザーから別途許可があるまで `git add` / `git commit` は行わない。

**Goal:** ユーザーに `admin` などの role を付与でき、アプリごとに permission code を柔軟に増やせる認可基盤を追加する。

**Architecture:** DB には `roles`、`permissions`、`user_roles`、`role_permissions` を追加し、role は permission の集合として扱う。Backend の session 認証時と login response 生成時に current user の role / permission code を解決し、FastAPI dependency で permission を検証する。Frontend は `/api/auth/me` と login/register response の `roles` / `permissions` を表示制御と route guard に使うが、最終的な認可は必ず Backend で行う。

**Tech Stack:** FastAPI, SQLModel, Alembic, Injector, PostgreSQL, React 19, TypeScript, TanStack Router, TanStack Query, Vitest, Pytest

---

## 背景

現在のテンプレートは認証済み session と account lifecycle は持っているが、アプリケーション権限を表す構造は持っていない。

- `backend/app/models/user.py` の `User` は `id`、`email`、`password_hash`、`is_active`、`deleted_at` などのみを持つ。
- `users.is_active` は既存ドキュメントで「凍結・停止」と定義済みであり、管理者権限ではない。
- `backend/app/models/auth_schemas.py` の `AuthUserResponse` は `id` と `email` のみを返す。
- `backend/app/controllers/auth_dependencies.py` の `require_current_session()` はログイン済みかどうかだけを確認する。
- `frontend/src/lib/authApi.ts` の `AuthUser` 型も `id` と `email` のみを持つ。
- `frontend/src/routes/forbidden.tsx` は存在するが、role / permission guard は未実装である。
- `documents/plans/20260718-admin-user-seed-design.md` は `admin@example.com` を「初期ログイン用の識別名」として扱い、権限上は通常ユーザーであると明記している。現時点の `backend/manage.py` には `seed-admin` コマンドも見当たらないため、今回の計画はその seed に依存しない。

過去の計画でも role / permission / `_admin` layout は後続フェーズ扱いになっていた。今回の計画は、その未実装領域を実装可能な形に分解する。

## 方針とその理由

### 1. `users.role` ではなく RBAC を採用する

`users` に `role = "admin"` のような単一カラムを追加する案は実装が速いが、アプリごとに権限種類が増えると破綻しやすい。テンプレートとしては、role と permission を分ける。

- `roles.code`: `admin`、`member`、`viewer` などの役割名。
- `permissions.code`: `admin:access`、`users:read`、`billing:manage` などの機能単位の権限。
- `user_roles`: user と role の割り当て。
- `role_permissions`: role に含まれる permission。

Backend の endpoint は role ではなく permission で守る。`admin` role は強い権限をまとめる便宜上の group とし、実際の判定は `admin:access` などの permission code で行う。

### 2. permission code はアプリが増やせる文字列にする

permission は DB row として保存し、`code` を安定した外部契約にする。派生アプリは migration ではなく seed / sync 処理で permission を増やせる。code は lowercase の `domain:action` 形式を推奨する。

例:

- `admin:access`
- `users:read`
- `users:write`
- `billing:manage`
- `reports:export`

Backend では `require_permission("users:write")` のように使う。Frontend では同じ code を route guard と表示制御に使う。

### 3. `/api/auth/me` に roles / permissions を返す

Frontend が navigation や route guard を実装できるよう、`AuthUserResponse` に `roles: list[str]` と `permissions: list[str]` を追加する。ただし、これは UI 制御用であり、セキュリティ境界ではない。Backend は各 protected endpoint で必ず permission dependency を使って再検証する。

### 4. session 認証時に権限を読み込む

`require_current_session()` はすべての認証必須 endpoint の入口なので、ここで `AuthenticatedSessionContext` に role / permission set を載せる。追加 query が発生するが、テンプレート規模では明快さを優先する。将来、大規模アプリで性能が問題になった場合は session 単位の短時間 cache や token version による invalidation を別計画で扱う。

### 5. login response は既存 user の実権限を返す

`frontend/src/routes/login.tsx` と `frontend/src/routes/register.tsx` は、成功 response をそのまま `queryKeys.auth.me` に書き込む。したがって login response が空権限を返すと、admin user でも login 直後の auth cache が権限なしになる。`register` 直後の新規 user は role 未付与なので空配列でよいが、`login` は既存 user の role / permission を解決して返す。

OIDC callback は backend redirect flow なので frontend は着地後に `/api/auth/me` を読み直す。ただし `IssuedAuthSession` に必須 field を追加すると OIDC 経路の dataclass 構築も壊れるため、OIDC login でも password login と同じく実権限を解決して `IssuedAuthSession` に載せる。

### 6. 権限変更は監査ログに残す

role 付与・剥奪はセキュリティ上の操作なので、既存の `auth_audit_logs` にイベントを残す。`AuthEventType` に `ROLE_GRANTED` と `ROLE_REVOKED` を追加し、対象 user、操作 user、role code を `detail_json` に入れる。

`AuthAuditLog.user_id` は actor user を入れる。target user は `detail_json.targetUserId` に入れる。1 request で複数 role の差分がある場合は、1 role grant / revoke につき 1 audit row を作る。controller は actor session id、IP address、user agent を usecase へ渡し、audit row に `session_id`、`ip_address`、`user_agent` を残す。

### 7. account deletion 時は user role assignment を削除する

`user_roles` は `users` への直接 FK を持つため、既存の `test_account_deletion_coverage.py` の対象になる。削除済み user は認証不可だが、将来の account restore や admin recovery と混ざると権限復元の扱いが曖昧になる。self-service account deletion では `user_roles` を物理削除し、復元が必要な派生アプリでは admin workflow 側で再付与する方針にする。

### 8. inactive user も権限管理対象にする

`users.is_active` は凍結・停止を表し、session authentication では inactive user を認証不可にする。ただし、管理操作としては inactive user の role を確認・剥奪できる必要がある。凍結後に admin role を剥奪する運用を妨げないため、role 管理 API と `authz-grant-role` CLI は deleted user を拒否するが inactive user は対象に含める。

### 9. admin 権限剥奪は復旧 CLI を前提に許可する

テンプレートでは「最後の admin を API で剥奪不可」にするための追加 query / lock を持たない。`admin:access` を持つ actor は任意 user の role set を置き換えられる強権者であり、自分や最後の admin から `admin` role を外すこともできる。誤操作からの復旧は `authz-grant-role` CLI で行う。この割り切りはテンプレートの単純さを優先した設計判断であり、派生アプリで管理 UI を公開する場合は「最後の admin 保護」を別計画で追加する。

### 10. unsafe admin API は CSRF middleware の対象にする

`PUT /api/admin/users/{userId}/roles` は unsafe `/api` request なので、既存 CSRF middleware の対象である。ブラウザ UI からは既存 `apiClient` を使い、管理スクリプトや curl で直接叩く場合は session cookie と `X-CSRF-Token` header を送る。新規 admin API を `AUTH_CSRF_EXEMPT_PATHS` に追加しない。

### 11. Frontend route 追加時は route tree を再生成する

TanStack Router の `routeTree.gen.ts` は git 管理下で、Vite plugin が生成する。`npm run check:ci` は Vite を通らず `tsc --noEmit` を実行するため、新規 route file を追加しただけでは typecheck が古い route tree を見て落ちる。`_authenticated.admin.tsx` 追加後は `npm test` または `npm run build` を先に実行して `frontend/src/routeTree.gen.ts` を再生成し、その差分も実装対象に含める。

### 12. Auth response の role / permission 配列は安定順にする

Backend 内部の `roles` / `permissions` は重複排除と membership check のため `frozenset[str]` で持つ。ただし public API response は安定順が必要なので、`AuthUserResponse` を作る helper では必ず `sorted(auth_context.roles)` と `sorted(auth_context.permissions)` を使う。

## 意思決定・逸脱・トレードオフ

### 人間の指示として確定している点

- 前回の推奨案である RBAC 寄り設計を採用する。
- 計画書は `documents/plans/` に作成する。
- Worktree は使わず、現在のブランチへ直接変更する。
- この計画作成作業では `git add` / `git commit` を行わない。
- ドキュメントと返答は日本語にする。

### こちらで行った設計判断

- `admin` を boolean や `users.role` ではなく `roles.code = "admin"` として扱う。
- endpoint 保護は role ではなく permission code で行う。
- Frontend へ roles / permissions を返すが、Backend 側の dependency を認可の正とする。
- 最小 seed として `admin` role と `admin:access` permission を扱えるようにするが、アプリ固有の permission は派生アプリが追加する。
- `roles.is_system` は今回追加しない。保護ロジックを持たない識別列は仕様を曖昧にするためである。
- 本格的な admin dashboard UI は今回の中核から外し、Backend API / CLI、Frontend guard、最小の protected sample route までを先に整える。
- `admin:access` 保持者は role 管理の強権者として扱う。最後の admin 保護は実装しない。
- 実装時には新規 `AuthorizationModule` を切らず、既存 `AuthModule` に authorization repository / usecase binding を追加した。現状の authorization は auth session、audit log、account deletion、OIDC login と密接に連携しており、module を分けても依存境界が明確になりにくいためである。将来 authorization が独立した外部 policy や tenant 境界を持つ場合は module 分離を再検討する。
- Frontend の `hasPermission()` は、Backend 契約としては `permissions` 必須である一方、既存 test fixture や古い cache shape に対しては fail closed で `false` を返すようにした。これは表示制御 helper で runtime crash を避けるための互換性判断であり、Backend の認可境界には影響しない。

### 検討した代替案

| 案 | 内容 | 採用可否 | 理由 |
|---|---|---:|---|
| 単一 `users.role` | `users` に `role` 文字列カラムを追加する | 不採用 | 小規模には速いが、複数 role、細かい permission、アプリごとの差分に弱い |
| permission のみ | `user_permissions` だけで直接 user に権限を付ける | 不採用 | 柔軟だが運用時に user ごとの差分が増え、管理しづらい |
| RBAC | role を user に付与し、role が permission を持つ | 採用 | admin などの役割と、アプリ固有 permission の両方を表現しやすい |
| ABAC / policy engine | 属性ベースまたは外部 policy engine を導入する | 不採用 | テンプレートには重すぎる。必要な派生アプリで別導入する |

## スコープ

### 対象

- Authorization DB schema の追加。
- SQLModel model / repository / usecase の追加。
- 現在 session の role / permission 読み込み。
- FastAPI permission dependency の追加。
- `AuthUserResponse` と Frontend `AuthUser` 型の拡張。
- Frontend permission helper と route guard の追加。
- role 付与・剥奪の Backend API または CLI の実装計画。
- account deletion 時の `user_roles` cleanup。
- unit / integration / frontend tests。
- `AGENTS.md` と reference docs への契約追記。

### 対象外

- 本格的な admin dashboard UI。ただし guard の腐敗を防ぐため、最小の `/admin` protected sample route は追加する。
- row-level permission、owner 以外も見える共有モデル、組織 / tenant 単位の権限。
- OAuth / OIDC provider scope と application permission の同期。
- JWT への permission 埋め込み。
- permission change のリアルタイム session invalidation。
- role hierarchy。
- deny rule。

## 追加・変更予定ファイル

### Backend

- Create: `backend/app/models/authorization.py`
- Create: `backend/app/models/authorization_schemas.py`
- Create: `backend/app/models/authorization_errors.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/auth_context.py`
- Modify: `backend/app/models/auth_schemas.py`
- Modify: `backend/app/models/auth_event_type.py`
- Create: `backend/app/interfaces/services/authorization_repository_interface.py`
- Create: `backend/app/services/authorization_repository.py`
- Create: `backend/app/interfaces/usecases/authorization_usecase_interface.py`
- Create: `backend/app/usecases/authorization_usecase.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/usecases/oauth_oidc_usecase.py`
- Modify: `backend/app/usecases/account_deletion_usecase.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Create: `backend/app/controllers/authorization_controller.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/app/bootstrap/container.py`
- Modify: `backend/app/bootstrap/modules.py`
- Modify: `backend/manage.py`
- Create: `backend/alembic/versions/20260808_0005_create_authorization_tables.py`

### Backend tests

- Create: `backend/tests/unit/models/test_authorization.py`
- Create: `backend/tests/unit/services/test_authorization_repository.py`
- Create: `backend/tests/unit/usecases/test_authorization_usecase.py`
- Create: `backend/tests/unit/controllers/test_auth_permission_dependencies.py`
- Create: `backend/tests/unit/controllers/test_authorization_controller.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Modify: `backend/tests/unit/bootstrap/test_route.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_usecase.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_coverage.py`
- Modify: `backend/tests/unit/test_manage.py`
- Create: `backend/tests/integration/services/test_authorization_repository.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Create: `backend/tests/integration/test_authorization_controller.py`
- Modify: `backend/tests/integration/test_manage_cli.py`

### Frontend

- Modify: `frontend/src/lib/authApi.ts`
- Create: `frontend/src/lib/permissions.ts`
- Modify: `frontend/src/lib/authGuard.ts`
- Modify: `frontend/src/routes/_authenticated.app.tsx`
- Create: `frontend/src/routes/_authenticated.admin.tsx`
- Modify: `frontend/src/routeTree.gen.ts`
- Modify: `frontend/src/routes/app.test.tsx`
- Create: `frontend/src/lib/permissions.test.ts`
- Create: `frontend/src/lib/authGuard.test.ts`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/src/hooks/useAccountDeletion.test.tsx`
- Modify: `frontend/src/hooks/useAuthSession.test.tsx`
- Modify: `frontend/src/routes/app.settings.test.tsx`
- Modify: `frontend/src/routes/login.test.tsx`
- Modify: `frontend/src/routes/register.test.tsx`

### Docs

- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`
- Modify: `frontend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/references/frontend-app-structure.md`

## データモデル設計

### `roles`

| column | type | null | note |
|---|---|---:|---|
| `id` | UUID | no | PK |
| `code` | varchar(64) | no | unique。例: `admin` |
| `display_name` | varchar(120) | no | UI / 管理用表示名 |
| `description` | varchar(500) | yes | 管理者向け説明 |
| `created_at` | timestamptz | no | `utcnow` |
| `updated_at` | timestamptz | no | `utcnow` |

### `permissions`

| column | type | null | note |
|---|---|---:|---|
| `id` | UUID | no | PK |
| `code` | varchar(120) | no | unique。例: `admin:access` |
| `display_name` | varchar(120) | no | UI / 管理用表示名 |
| `description` | varchar(500) | yes | 管理者向け説明 |
| `created_at` | timestamptz | no | `utcnow` |
| `updated_at` | timestamptz | no | `utcnow` |

### `user_roles`

| column | type | null | note |
|---|---|---:|---|
| `user_id` | UUID | no | FK `users.id`, `ON DELETE CASCADE` |
| `role_id` | UUID | no | FK `roles.id`, `ON DELETE CASCADE` |
| `assigned_at` | timestamptz | no | 付与日時 |
| `assigned_by_user_id` | UUID | yes | FK `users.id`, `ON DELETE SET NULL` |

PK は `(user_id, role_id)`。`assigned_by_user_id` は監査補助であり、正の監査は `auth_audit_logs` に残す。

### `role_permissions`

| column | type | null | note |
|---|---|---:|---|
| `role_id` | UUID | no | FK `roles.id`, `ON DELETE CASCADE` |
| `permission_id` | UUID | no | FK `permissions.id`, `ON DELETE CASCADE` |
| `created_at` | timestamptz | no | 作成日時 |

PK は `(role_id, permission_id)`。

### index / constraint 方針

SQLModel metadata と手書き Alembic migration を一致させる。`tests/integration/test_migration_consistency.py` が `command.check()` を実行するため、model 側にない index / constraint を migration だけに作らない。

- `roles.code`: `Index("uq_roles_code", "code", unique=True)` を `Role.__table_args__` に置き、migration も同じ unique index を作る。
- `permissions.code`: `Index("uq_permissions_code", "code", unique=True)` を `Permission.__table_args__` に置き、migration も同じ unique index を作る。
- `user_roles`: PK が `(user_id, role_id)` なので `user_id` 単独 index は追加しない。`role_id` 方向の lookup が必要な場合だけ `Index("ix_user_roles_role_id", "role_id")` を追加する。
- `role_permissions`: PK が `(role_id, permission_id)` なので `role_id` 単独 index は追加しない。permission から role を引くため `Index("ix_role_permissions_permission_id", "permission_id")` を追加する。
- `user_roles.assigned_by_user_id`: 監査補助の逆引き用途がないため index は追加しない。

## API 設計

### `GET /api/auth/me`

既存レスポンスに `roles` と `permissions` を追加する。

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "email": "admin@example.com",
  "roles": ["admin"],
  "permissions": ["admin:access", "users:read", "users:write"]
}
```

後方互換性のため、Frontend tests の既存 fixture は `roles: []` / `permissions: []` を追加して更新する。

### `PUT /api/admin/users/{userId}/roles`

指定 user の role set を置き換える。認証必須かつ `admin:access` permission 必須。
この endpoint は unsafe `/api` request なので CSRF middleware の対象である。Frontend は `apiClient` 経由で呼ぶ。curl 等から直接呼ぶ場合は session cookie と `X-CSRF-Token` header が必要である。

`admin:access` を持つ actor は任意 role を任意 user に付与・剥奪できる。最後の admin 保護はこのテンプレートでは実装せず、誤操作時の復旧は `authz-grant-role` CLI で行う。

Request:

```json
{
  "roles": ["admin", "member"]
}
```

Response:

```json
{
  "userId": "00000000-0000-0000-0000-000000000001",
  "roles": ["admin", "member"],
  "permissions": ["admin:access"]
}
```

Error:

- `401 UNAUTHORIZED`: session なし。
- `403 PERMISSION_DENIED`: `admin:access` がない。
- `404 USER_NOT_FOUND`: user が存在しない、または deleted。inactive user は対象に含める。
- `422 ROLE_NOT_FOUND`: request に未知の role code が含まれる。

### `GET /api/admin/users/{userId}/roles`

指定 user の現在の role / permission を返す。認証必須かつ `admin:access` permission 必須。管理 UI を後で作る場合に PUT 前の初期表示で使う。

Response:

```json
{
  "userId": "00000000-0000-0000-0000-000000000001",
  "roles": ["admin"],
  "permissions": ["admin:access"]
}
```

Error:

- `401 UNAUTHORIZED`: session なし。
- `403 PERMISSION_DENIED`: `admin:access` がない。
- `404 USER_NOT_FOUND`: user が存在しない、または deleted。inactive user は対象に含める。

### `GET /api/admin/roles`

管理画面や CLI 以外の確認用途として、role と permission の一覧を返す。認証必須かつ `admin:access` permission 必須。

Response:

```json
{
  "roles": [
    {
      "code": "admin",
      "displayName": "Administrator",
      "permissions": ["admin:access"]
    }
  ],
  "permissions": [
    {
      "code": "admin:access",
      "displayName": "Access administration"
    }
  ]
}
```

## 具体的なタスク

### Task 1: 実装前提とテスト配置を確認する

**Files:**

- Read: `backend/app/bootstrap/route.py`
- Read: `backend/tests/unit/bootstrap/test_route.py`
- Read: `backend/tests/unit/services/test_auth_repository.py`
- Read: `backend/tests/integration/services/test_auth_repository.py`
- Read: `backend/tests/integration/test_migration_consistency.py`
- Read: `frontend/src/routes/login.tsx`
- Read: `frontend/src/routes/register.tsx`

- [x] Step 1.1: `backend/app/bootstrap/route.py` を読み、新規 controller router は `_setup_api_routes()` に include することを確認する。`backend/app/controllers/__init__.py` は router 登録に使わない。
- [x] Step 1.2: `backend/tests/unit/bootstrap/test_route.py` を読み、新規 admin route が route setup で観測できる test を追加する方針を確認する。実装では専用 `test_authorization_module.py` に route wiring test を置いた。
- [x] Step 1.3: `backend/tests/unit/services/test_auth_repository.py` と `backend/tests/integration/services/test_auth_repository.py` を読み、repository の DB 実動作検証は integration test に置く方針を確認する。
- [x] Step 1.4: `backend/tests/integration/test_migration_consistency.py` を読み、SQLModel metadata と Alembic migration の一致が `command.check()` で検証されることを確認する。
- [x] Step 1.5: `frontend/src/routes/login.tsx` と `frontend/src/routes/register.tsx` を読み、成功 response が `queryKeys.auth.me` cache に直接保存されることを確認する。login response は既存 user の実権限を返す必要がある。

### Task 2: Authorization SQLModel と migration を追加する

**Files:**

- Create: `backend/app/models/authorization.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260808_0005_create_authorization_tables.py`
- Create: `backend/tests/unit/models/test_authorization.py`

- [x] Step 2.1: `backend/app/models/authorization.py` に `Role`、`Permission`、`UserRole`、`RolePermission` を追加する。`code` は DB unique とし、Python model 上は `str` とする。
- [x] Step 2.2: `Role.__table_args__` に `Index("uq_roles_code", "code", unique=True)` を定義する。`Permission.__table_args__` に `Index("uq_permissions_code", "code", unique=True)` を定義する。
- [x] Step 2.3: `UserRole.__table_args__` は PK `(user_id, role_id)` と `Index("ix_user_roles_role_id", "role_id")` にする。`user_id` 単独 index は作らない。
- [x] Step 2.4: `RolePermission.__table_args__` は PK `(role_id, permission_id)` と `Index("ix_role_permissions_permission_id", "permission_id")` にする。`role_id` 単独 index は作らない。
- [x] Step 2.5: `backend/app/models/__init__.py` で authorization model を import し、SQLModel metadata に table が載るようにする。
- [x] Step 2.6: Alembic revision `20260808_0005_create_authorization_tables.py` を作り、`down_revision = "20260806_0004"` にする。
- [x] Step 2.7: migration で `roles`、`permissions`、`user_roles`、`role_permissions` を作成する。制約名は既存 naming convention と `op.f("pk_roles")` のような具体名を使う。
- [x] Step 2.8: migration で model 側と同じ unique / lookup index だけを作る。`roles.code`、`permissions.code`、`user_roles.role_id`、`role_permissions.permission_id` が対象である。
- [x] Step 2.9: downgrade では index と table を逆順に drop する。権限定義と割当が消える destructive downgrade であることを migration docstring に明記する。
- [x] Step 2.10: `backend/tests/unit/models/test_authorization.py` に metadata table / constraint / index の unit test を追加する。
- [x] Step 2.11: `cd backend && uv run pytest tests/unit/models/test_authorization.py -q` を実行し、pass を確認する。
- [x] Step 2.12: PostgreSQL test DB を用意し、`cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_migration_consistency.py -q` を実行し、model と migration の差分がないことを確認する。

### Task 3: Authorization repository を追加する

**Files:**

- Create: `backend/app/interfaces/services/authorization_repository_interface.py`
- Create: `backend/app/services/authorization_repository.py`
- Create: `backend/tests/unit/services/test_authorization_repository.py`
- Create: `backend/tests/integration/services/test_authorization_repository.py`

- [x] Step 3.1: repository interface に `upsert_permission_definition()`、`upsert_role_definition()`、`replace_role_permissions()`、`list_roles_with_permissions()`、`get_user_authorization(user_id)`、`replace_user_roles(user_id, role_codes, assigned_by_user_id)`、`delete_roles_for_user(user_id)` を定義する。
- [x] Step 3.2: `AuthorizationRepository` を作り、既存 repository と同じく `UnitOfWorkInterface` と `session_scope()` を使う。
- [x] Step 3.3: `get_user_authorization()` は対象 user が存在しない、または `deleted_at is not None` の場合に `None` を返す。inactive user には通常どおり現在の role / permission result を返す。
- [x] Step 3.4: `replace_user_roles()` は unknown role code がある場合に `RoleNotFoundError` を投げ、部分更新しない。transaction は usecase 側の `UnitOfWorkInterface.transaction()` が張るため、repository は session_scope で outer transaction に join する。
- [x] Step 3.5: `replace_user_roles()` は role set の差分を計算し、既存 assignment を削除・不足 assignment を追加する。重複 role code は request normalization で 1 つにまとめる。戻り値は `granted_role_codes`、`revoked_role_codes`、`current_role_codes`、`current_permission_codes` を持つ domain result にする。
- [x] Step 3.6: `delete_roles_for_user()` は account deletion 用に `user_roles` を削除し、削除件数を返す。
- [x] Step 3.7: unit test では fake session で permission 欠落時に専用 error が返ることを検証する。method signature と transaction 境界は mypy / usecase test / integration test で補完する。
- [x] Step 3.8: integration test で role / permission upsert、role permission 置換、user への role 付与、permission 解決、role 置換、未知 role error、削除済み user の扱い、`delete_roles_for_user()` を実 DB で検証する。
- [x] Step 3.9: `cd backend && uv run pytest tests/unit/services/test_authorization_repository.py -q` 相当を実行し、pass を確認する。
- [x] Step 3.10: PostgreSQL test DB を用意し、`cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/services/test_authorization_repository.py -q` 相当を実行し、pass を確認する。

### Task 4: Authorization usecase と domain error を追加する

**Files:**

- Create: `backend/app/models/authorization_errors.py`
- Create: `backend/app/interfaces/usecases/authorization_usecase_interface.py`
- Create: `backend/app/usecases/authorization_usecase.py`
- Create: `backend/tests/unit/usecases/test_authorization_usecase.py`

- [x] Step 4.1: `RoleNotFoundError` と `AuthorizationUserNotFoundError` を定義する。permission 不足は controller dependency が `api_error()` へ直接変換するため、未使用の `PermissionDeniedError` は定義しない。
- [x] Step 4.2: usecase interface に `list_roles()`、`replace_user_roles(actor_context, target_user_id, role_codes, ip_address, user_agent)`、`get_user_authorization(user_id)` を定義する。`actor_context` は `AuthenticatedSessionContext` とし、actor user id と session id を audit に使う。
- [x] Step 4.3: `replace_user_roles()` は `AuthRepositoryInterface.find_user_by_id_for_authentication()` で target user を取得し、存在しない user と `deleted_at is not None` の user を `AuthorizationUserNotFoundError` として扱ってから authorization repository に委譲する。`is_active is False` の user は権限管理対象として許可する。`users` 読み取り method を authorization repository に重複実装しない。
- [x] Step 4.4: `replace_user_roles()` は `async with UnitOfWorkInterface.transaction():` で target user 確認、role 差分更新、audit log 作成を 1 transaction に閉じる。
- [x] Step 4.5: `replace_user_roles()` は `AuthEventType.ROLE_GRANTED` / `ROLE_REVOKED` の audit log を作る。`AuthAuditLog.user_id` は actor user id、`session_id` は actor session id、`ip_address` と `user_agent` は request context を入れる。
- [x] Step 4.6: audit log の `detail_json` には `actorUserId`、`targetUserId`、`roleCode`、`resultingRoles` を含める。1 role grant / revoke につき 1 audit row を作る。
- [x] Step 4.7: `get_user_authorization()` は user の role codes と permission codes を安定順で返す domain result を返す。
- [x] Step 4.8: unit / integration test で role 付与、role 剥奪、未知 role、target user 不在、transaction 境界、audit log の actor / target / session / IP / UA / detail を検証する。
- [x] Step 4.9: `cd backend && uv run pytest tests/unit/usecases/test_authorization_usecase.py -q` を実行し、pass を確認する。

### Task 5: DI module と AuthEventType を更新する

**Files:**

- Modify: `backend/app/bootstrap/modules.py`
- Modify: `backend/app/bootstrap/container.py`
- Modify: `backend/app/models/auth_event_type.py`
- Create: `backend/tests/unit/bootstrap/test_authorization_module.py`

- [x] Step 5.1: `AuthEventType` に `ROLE_GRANTED = "role_granted"` と `ROLE_REVOKED = "role_revoked"` を追加する。
- [x] Step 5.2: `backend/app/bootstrap/modules.py` に `AuthorizationRepositoryInterface` と `AuthorizationUsecaseInterface` の binding を追加する。
- [x] Step 5.3: 既存 `AuthModule` に含めるか、新規 `AuthorizationModule` を作る。実装では既存 `AuthModule` に含めた。
- [x] Step 5.4: 新規 `AuthorizationModule` は作らず、既存 module に含めた理由を本計画の意思決定欄に追記する。
- [x] Step 5.5: `backend/tests/unit/bootstrap/test_authorization_module.py` を作り、authorization repository / usecase binding と route wiring を検証する。
- [x] Step 5.6: `cd backend && uv run pytest tests/unit/bootstrap/test_authorization_module.py -q` 相当を実行し、pass を確認する。

### Task 6: Session auth context に roles / permissions を載せる

**Files:**

- Modify: `backend/app/models/auth_context.py`
- Modify: `backend/app/models/auth_schemas.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/usecases/oauth_oidc_usecase.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py`
- Modify: `backend/tests/integration/test_auth_controller.py`

- [x] Step 6.1: `AuthenticatedSessionContext` に `roles: frozenset[str]` と `permissions: frozenset[str]` を追加する。
- [x] Step 6.2: `IssuedAuthSession` にも `roles: frozenset[str]` と `permissions: frozenset[str]` を追加する。default 値は持たせず、すべての構築箇所で明示する。
- [x] Step 6.3: `AuthUsecase.__init__()` に `AuthorizationRepositoryInterface` を追加し、`backend/tests/unit/usecases/test_auth_usecase.py` の全 instantiation / stub を更新する。
- [x] Step 6.4: `OAuthOidcUsecase.__init__()` にも `AuthorizationRepositoryInterface` を追加し、OIDC login callback で `IssuedAuthSession.roles` / `IssuedAuthSession.permissions` に実権限を載せる。OIDC は redirect flow だが、dataclass contract を password login と揃える。
- [x] Step 6.5: `backend/tests/unit/controllers/test_auth_controller_dependency.py`、`backend/tests/unit/usecases/test_account_deletion_usecase.py`、`backend/tests/unit/usecases/test_oauth_oidc_usecase.py` など、既存 tests の `IssuedAuthSession` / `AuthenticatedSessionContext` stub をすべて `roles=frozenset()` / `permissions=frozenset()` 付きに更新する。
- [x] Step 6.6: `AuthUserResponse` に `roles: list[str]` と `permissions: list[str]` を追加する。`AuthUserResponse` は `AuthSchema` を継承していないが、追加 field は snake_case を含まないため public JSON でも `roles` / `permissions` のままである。
- [x] Step 6.7: `AuthUsecase.authenticate_session()` で user の有効性確認後に `AuthorizationRepositoryInterface.get_user_authorization(user.id)` を呼び、context に載せる。
- [x] Step 6.8: `AuthUsecase.login()` は既存 user の role / permission を解決し、`IssuedAuthSession.roles` / `IssuedAuthSession.permissions` に載せる。admin user が login した場合に `roles=["admin"]` と `permissions=["admin:access"]` が response cache に入ることを unit / integration test で確認する。
- [x] Step 6.9: `AuthUsecase.register()` は新規 user のため `roles=frozenset()` / `permissions=frozenset()` を返す。register 直後だけ空配列で正しい。
- [x] Step 6.10: `GET /api/auth/me`、register、login の response 生成を helper 関数へ寄せ、`roles=sorted(source.roles)` と `permissions=sorted(source.permissions)` を必ず使う。`frozenset` の反復順を public response に出さない。
- [x] Step 6.11: integration / unit test で `/api/auth/me` が role / permission を返すこと、未付与 user は空配列を返すこと、login response が既存 user の実権限を返すことを確認する。
- [x] Step 6.12: `cd backend && uv run pytest tests/unit/usecases/test_auth_usecase.py tests/unit/usecases/test_oauth_oidc_usecase.py tests/unit/controllers/test_auth_controller_dependency.py tests/integration/test_auth_controller.py -q` を実行し、pass を確認する。

### Task 7: Backend permission dependency を追加する

**Files:**

- Modify: `backend/app/controllers/auth_dependencies.py`
- Create: `backend/tests/unit/controllers/test_auth_permission_dependencies.py`

- [x] Step 7.1: `require_permission(permission_code: str)` を追加する。戻り値は FastAPI dependency callable とし、成功時は `AuthenticatedSessionContext` を返す。
- [x] Step 7.2: `require_any_permission(permission_codes: Sequence[str])` を追加する。複数 permission のいずれかでよい endpoint 用に使う。
- [x] Step 7.3: permission 不足時は `api_error(403, "PERMISSION_DENIED", "Permission denied")` を返す。
- [x] Step 7.4: `require_any_permission([])` を渡した場合は developer error として `ValueError` を投げる。endpoint 起動時に誤設定へ気づけるようにする。
- [x] Step 7.5: `require_all_permissions()` は初期実装では追加しない。必要な派生アプリで追加する。
- [x] Step 7.6: unit test で成功、session なし、permission 不足、any、空 list error を検証する。
- [x] Step 7.7: `cd backend && uv run pytest tests/unit/controllers/test_auth_permission_dependencies.py -q` を実行し、pass を確認する。

### Task 8: Role 管理 API を追加する

**Files:**

- Create: `backend/app/models/authorization_schemas.py`
- Create: `backend/app/controllers/authorization_controller.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/tests/unit/bootstrap/test_route.py`
- Create: `backend/tests/unit/controllers/test_authorization_controller.py`
- Create: `backend/tests/integration/test_authorization_controller.py`

- [x] Step 8.1: request / response DTO を `authorization_schemas.py` に定義する。`AuthSchema` と同じ `SQLModelConfig(alias_generator=to_camel, populate_by_name=True, extra="forbid")` を持つ `AuthorizationSchema` base class を作り、request / response は camelCase を正とする。auth schema への import 依存を避け、authorization DTO の base を同じ file 内で完結させる。
- [x] Step 8.2: `authorization_controller.py` に既存 controller と同じ `ErrorResponses` / `ERROR_RESPONSE` / `*_ERROR_RESPONSES` 定義を置き、OpenAPI error envelope を明示する。
- [x] Step 8.3: `GET /api/admin/roles` を追加し、`Depends(require_permission("admin:access"))` で守る。
- [x] Step 8.4: `GET /api/admin/users/{user_id}/roles` を追加し、同じく `admin:access` で守る。
- [x] Step 8.5: `PUT /api/admin/users/{user_id}/roles` を追加し、同じく `admin:access` で守る。unsafe `/api` request なので CSRF middleware 対象のままにし、個別 CSRF dependency や exempt 設定は追加しない。
- [x] Step 8.6: `backend/app/bootstrap/route.py` で `authorization_controller.router` を import し、`_setup_api_routes()` で include する。
- [x] Step 8.7: `backend/tests/unit/bootstrap/test_authorization_module.py` に authorization admin route が route setup に含まれることを検証する test を追加する。unknown API fallback は既存 route tests の責務として維持し、本タスクでは新規 authorization route の wiring に絞る。
- [x] Step 8.8: controller は usecase domain error を error envelope に変換する。
- [x] Step 8.9: unknown role は `422 ROLE_NOT_FOUND`、target user 不在または deleted は `404 USER_NOT_FOUND` にする。inactive user は role 管理対象として許可する。FastAPI validation の 422 と区別できるよう、error envelope code を必ず検証する。
- [x] Step 8.10: unit test で DB なしで controller response / error mapping を検証する。
- [x] Step 8.11: integration test で admin permission ありなら role 置換が成功し、permission なしなら 403 になること、CSRF なしの unsafe request は CSRF middleware により 403 になることを確認する。
- [x] Step 8.12: `cd backend && uv run pytest tests/unit/bootstrap/test_authorization_module.py tests/unit/controllers/test_authorization_controller.py tests/integration/test_authorization_controller.py -q` 相当を実行し、pass を確認する。

### Task 9: Authorization seed / sync CLI を追加する

**Files:**

- Create: `backend/app/config/authorization.py`
- Modify: `backend/manage.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `backend/tests/integration/test_manage_cli.py`

- [x] Step 9.1: `backend/app/config/authorization.py` に `DEFAULT_AUTHORIZATION_DEFINITIONS` を定義する。初期値は `admin` role と `admin:access` permission のみとし、派生アプリがここへ追加できるようにする。
- [x] Step 9.2: `manage.py` に `authz-sync` コマンドを追加し、`DATABASE_URL` 明示を必須にする。
- [x] Step 9.3: `authz-sync` は roles / permissions / role_permissions を upsert する。既存 user への role 付与は行わない。`display_name` と `description` は config 側の定義で更新し、値が変わった場合は `updated_at` を更新する。CLI operation は `container.get(UnitOfWorkInterface).transaction()` で全 upsert を 1 transaction に閉じ、途中失敗時に部分適用しない。
- [x] Step 9.4: `manage.py` に `authz-grant-role --email <email> --role <roleCode>` を追加する。local / development 限定にはしないが、`DATABASE_URL` 明示と存在確認を必須にする。
- [x] Step 9.5: `authz-grant-role` は deleted でない user を対象にする。inactive user も対象に含め、凍結中 user の権限復旧・剥奪運用を妨げない。
- [x] Step 9.6: CLI は平文 secret を出力せず、付与した role code と user email のみを出力する。
- [x] Step 9.7: `backend/tests/unit/test_manage.py` では `DATABASE_URL` 未設定時の拒否、datetime 等に関係しない CLI option validation、container operation が呼ばれることだけを fake / monkeypatch で検証する。
- [x] Step 9.8: `backend/tests/integration/test_manage_cli.py` で `authz-sync` の default 定義作成と、inactive user への `authz-grant-role` 成功および CLI audit を実 DB で検証する。unknown role / deleted user の詳細ケースは repository / usecase / controller の契約テストで補完する。
- [x] Step 9.9: `cd backend && uv run pytest tests/unit/test_manage.py -q` を実行し、pass を確認する。
- [x] Step 9.10: PostgreSQL test DB を用意し、`cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_manage_cli.py -q` 相当を実行し、pass を確認する。

### Task 10: Account deletion と user_roles cleanup を統合する

**Files:**

- Modify: `backend/app/usecases/account_deletion_usecase.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_usecase.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_coverage.py`
- Modify: `backend/tests/integration/services/test_authorization_repository.py`

- [x] Step 10.1: `AccountDeletionUsecase` に `AuthorizationRepositoryInterface` を注入する。
- [x] Step 10.2: account deletion transaction 内で `delete_roles_for_user(auth_context.user.id)` を呼ぶ。
- [x] Step 10.3: `test_account_deletion_coverage.py` の `HANDLED_TABLES` に `user_roles` を追加する。
- [x] Step 10.4: account deletion unit test で `delete_roles_for_user()` が呼ばれることを検証する。
- [x] Step 10.5: `backend/tests/integration/services/test_authorization_repository.py` で `delete_roles_for_user()` 実行後に対象 user の `user_roles` だけが消えることを確認する。
- [x] Step 10.6: `cd backend && uv run pytest tests/unit/usecases/test_account_deletion_usecase.py tests/unit/usecases/test_account_deletion_coverage.py -q` を実行し、pass を確認する。

### Task 11: Frontend AuthUser 型と permission helper を追加する

**Files:**

- Modify: `frontend/src/lib/authApi.ts`
- Create: `frontend/src/lib/permissions.ts`
- Create: `frontend/src/lib/permissions.test.ts`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/src/hooks/useAccountDeletion.test.tsx`
- Modify: `frontend/src/hooks/useAuthSession.test.tsx`
- Modify: `frontend/src/routes/app.settings.test.tsx`
- Modify: `frontend/src/routes/app.test.tsx`
- Modify: `frontend/src/routes/login.test.tsx`
- Modify: `frontend/src/routes/register.test.tsx`

- [x] Step 11.1: `AuthUser` に `roles: Array<string>` と `permissions: Array<string>` を追加する。
- [x] Step 11.2: test fixture の auth user response に `roles: []` / `permissions: []` を追加する。
- [x] Step 11.3: `permissions.ts` に `hasPermission(user, permissionCode)` と `hasAnyPermission(user, permissionCodes)` だけを追加する。role は response に含めるが、Frontend の初期 helper は permission check に寄せる。
- [x] Step 11.4: helper は `user: AuthUser | null | undefined` を受け付け、user がない場合は `false` を返す。
- [x] Step 11.5: `hasAnyPermission(user, [])` は `false` を返す。Backend dependency の空 list error と異なり、Frontend helper は表示制御なので fail closed にする。
- [x] Step 11.6: Header test の変更は auth user fixture の型更新だけに留める。admin link は Header ではなく `/app` page に置く。
- [x] Step 11.7: `cd frontend && npm test -- permissions.test.ts` を実行し、pass を確認する。

### Task 12: Frontend permission route guard を追加する

**Files:**

- Modify: `frontend/src/lib/authGuard.ts`
- Create: `frontend/src/lib/authGuard.test.ts`
- Modify: `frontend/src/routes/_authenticated.app.tsx`
- Create: `frontend/src/routes/_authenticated.admin.tsx`
- Modify: `frontend/src/routeTree.gen.ts`
- Modify: `frontend/src/routes/app.test.tsx`

- [x] Step 12.1: `requirePermission(permissionCode)` を追加する。`/_authenticated` parent guard 配下で使う前提にし、内部では `queryClient.ensureQueryData(currentUserQueryOptions())` を使って parent `requireAuth()` が直前に取得した `auth.me` cache を再利用する。直接使用した場合に user がなければ既存通り `/login?redirect=<current href>` へ送る。
- [x] Step 12.2: user はいるが permission がない場合は `/forbidden` へ redirect する。
- [x] Step 12.3: `requireAnyPermission(permissionCodes)` を追加する。`requireAllPermissions()` は初期実装では追加しない。
- [x] Step 12.4: 既存 `requireAuth()` の挙動は変えない。
- [x] Step 12.5: `frontend/src/routes/_authenticated.admin.tsx` を作り、`beforeLoad: requirePermission("admin:access")` を設定する。画面は最小の protected sample とし、本格的な admin dashboard は作らない。
- [x] Step 12.6: `frontend/src/routes/_authenticated.app.tsx` に、current user が `admin:access` を持つ場合だけ `/admin` への link を表示する。これにより helper / guard の使用例をテンプレート内に残す。
- [x] Step 12.7: `_authenticated.admin.tsx` 追加後、`cd frontend && npm test -- app.test.tsx` を実行して Vite / TanStack Router plugin 経由で `frontend/src/routeTree.gen.ts` を再生成する。生成差分を実装差分に含める。
- [x] Step 12.8: unit test で未ログイン、permission あり、permission なし、fetch 5xx の挙動を検証する。
- [x] Step 12.9: `app.test.tsx` で `/admin` は permission なしなら `/forbidden` へ遷移し、permission ありなら admin sample page が表示されることを検証する。
- [x] Step 12.10: `app.test.tsx` で `/admin` navigation が `/api/auth/me` を 1 回だけ呼ぶことを検証する。親 `requireAuth()` の `fetchQuery()` と子 `requirePermission()` の `ensureQueryData()` が二重 request を起こさないことを固定する。
- [x] Step 12.11: `CSRF_VALIDATION_FAILED` など mutation 由来 403 は引き続き `/forbidden` へ自動遷移しないことを既存 `app.test.tsx` で確認する。
- [x] Step 12.12: role 変更 API を Frontend から呼ぶ画面は今回作らない。後続で作る場合は成功時に `queryClient.invalidateQueries({ queryKey: queryKeys.auth.me })` を呼び、自分自身の権限変更が auth cache に反映されるようにすることを `frontend/AGENTS.md` に記載する。
- [x] Step 12.13: `cd frontend && npm test -- authGuard.test.ts app.test.tsx` を実行し、pass を確認する。

### Task 13: Backend authorization smoke を integration test に固定する

**Files:**

- Modify: `backend/tests/integration/test_authorization_controller.py`
- Modify: `backend/tests/integration/test_auth_controller.py`

- [x] Step 13.1: fresh test DB に migration head を適用する。
- [x] Step 13.2: `backend/tests/integration/test_authorization_controller.py` に test helper `_sync_default_authorization(async_session)` を置き、`backend/app/config/authorization.py` の `DEFAULT_AUTHORIZATION_DEFINITIONS` を読み、`admin` role と `admin:access` permission を作成する。CLI 経由の検証は Task 9 の `backend/tests/integration/test_manage_cli.py` に限定する。
- [x] Step 13.3: integration test 内で test user に `admin` role を付与する。
- [x] Step 13.4: login 後の `/api/auth/me` が `roles=["admin"]` と `permissions=["admin:access"]` を返すことを確認する。
- [x] Step 13.5: admin role なし user が admin API で 403 になることを確認する。
- [x] Step 13.6: admin role あり user が target user の role を置換できることを確認する。
- [x] Step 13.7: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_authorization_controller.py tests/integration/test_auth_controller.py -q` 相当を実行し、pass を確認する。

### Task 14: ドキュメントを更新する

**Files:**

- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`
- Modify: `frontend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/references/frontend-app-structure.md`

- [x] Step 14.1: `AGENTS.md` に「権限管理は RBAC。Backend の permission dependency が正。Frontend は表示制御のみ」と追記する。
- [x] Step 14.2: `backend/AGENTS.md` に authorization model、migration、dependency、audit、account deletion cleanup、admin API の CSRF 対象、最後の admin 保護をしない復旧 CLI 前提を追記する。
- [x] Step 14.3: `frontend/AGENTS.md` に `AuthUser.roles` / `AuthUser.permissions`、permission helper、route guard、role 変更後の `queryKeys.auth.me` invalidation 方針を追記する。
- [x] Step 14.4: `documents/references/backend-app-structure.md` に Authorization section を追加する。
- [x] Step 14.5: `documents/references/frontend-app-structure.md` に permission-based route guard の section を追加する。
- [x] Step 14.6: `documents/plans/20260718-admin-user-seed-design.md` は今回の実装対象にしない。更新する場合は別タスクで「admin seed が RBAC 追加後も通常ユーザーのままなのか、`admin` role を付与するのか」を決める。

### Task 15: 品質ゲートを実行する

**Files:**

- No source edit unless failures require fixes

- [x] Step 15.1: `cd backend && uv run ruff check .` を実行する。
- [x] Step 15.2: `cd backend && uv run isort . --check-only` を実行する。
- [x] Step 15.3: `cd backend && uv run yapf -dr app/ tests/ alembic/ manage.py` を実行する。
- [x] Step 15.4: `cd backend && uv run mypy app manage.py` を実行する。
- [x] Step 15.5: `cd backend && uv run pytest tests/unit` を実行する。
- [x] Step 15.6: PostgreSQL test DB を用意し、`cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration -q -ra` を実行する。
- [x] Step 15.7: `cd frontend && npm run check:ci` を実行する。
- [x] Step 15.8: `cd frontend && npm test` を実行する。
- [x] Step 15.9: `cd frontend && npm run build` を実行する。
- [x] Step 15.10: `docker compose config` を実行する。
- [x] Step 15.11: `docker build --target runtime -t python-react-template:runtime .` を repository root で実行する。
- [x] Step 15.12: `docker build --target backend-dev -t python-react-template:backend-dev .` を repository root で実行する。

## 実装順序

1. DB model / migration を先に作る。
2. repository / usecase / DI を作る。
3. session context と `/api/auth/me` を拡張する。
4. permission dependency を作る。
5. admin role management API / CLI を作る。
6. account deletion cleanup を統合する。
7. Frontend 型 / helper / guard を更新する。
8. docs と品質ゲートを仕上げる。

この順序なら、各段階で unit test が独立して失敗・成功を確認でき、Frontend は Backend API contract が固まってから更新できる。

## レビュー観点

- `users.is_active` を admin 権限として扱っていないこと。
- permission check が Frontend だけで完結していないこと。
- `require_current_session()` の既存 401 契約を壊していないこと。
- CSRF 403 と permission 403 の UI 挙動を混同していないこと。
- admin role 管理 API が CSRF middleware の対象のままであること。
- account deletion で `user_roles` の cleanup 方針が test に反映されていること。
- inactive user が role 管理 API / CLI の対象に含まれ、deleted user だけが拒否されていること。
- `authz-sync` が 1 transaction に閉じ、途中失敗時に部分適用しないこと。
- `admin@example.com` seed の既存設計に依存していないこと。
- OAuth/OIDC の provider scope と application permission を混同していないこと。
- OIDC login callback の `IssuedAuthSession` にも role / permission が明示されていること。
- login response が既存 user の実権限を返し、register response だけが空権限を返すこと。
- public response の `roles` / `permissions` が `sorted()` で安定順になっていること。
- 最後の admin を保護しない設計判断と、`authz-grant-role` CLI による復旧方針が docs に反映されていること。
- `/admin` route 追加後に `frontend/src/routeTree.gen.ts` が再生成されていること。
- `/admin` navigation で `/api/auth/me` が二重 fetch されないこと。
- role / permission code の追加方法が派生アプリにとって明確であること。

## 未解決ではないが、実装時に再確認すべき点

- `authz-grant-role` CLI を production でも許可するかは運用ポリシー次第である。この計画では `DATABASE_URL` 明示を安全策とし、環境では制限しない。
- 管理 UI は今回作らない。必要になった場合は `/api/admin/roles` と `PUT /api/admin/users/{userId}/roles` を使う別計画で作る。
- role assignment の変更後、既存 session は次回 request で DB から権限を読み直す。session token 自体は revoke しない。

## 実装メモ

- 2026-08-08: RBAC の model / migration / repository / usecase / permission dependency / admin API / CLI / Frontend guard を実装した。
- 2026-08-08: `uv run mypy app manage.py` は uv cache 権限と uv の macOS system-configuration panic により実行できなかったため、同じ backend virtualenv の `./.venv/bin/mypy app manage.py` で検証した。
- 2026-08-08: integration test は sandbox 内から `localhost:5432` へ接続できなかったため、権限付きで `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ./.venv/bin/pytest tests/integration -q -ra` を実行した。
- 2026-08-08: Claude Code レビュー後、`inactive` user を role 管理対象に維持しつつ、`UserRoleReplaceRequest.roles` 必須化、`GET /api/admin/roles` の permission catalog 追加、`PermissionNotFoundError` 分離、`authz-grant-role` CLI audit、`authz-sync` transaction 境界、role / permission upsert の条件付き `updated_at` 更新、auth 経路の user 再取得回避を反映した。
- 2026-08-08: 専用の `backend/tests/unit/services/test_authorization_repository.py`、`backend/tests/integration/services/test_authorization_repository.py`、`backend/tests/unit/controllers/test_authorization_controller.py`、`backend/tests/integration/test_authorization_controller.py`、`backend/tests/unit/bootstrap/test_authorization_module.py`、`frontend/src/lib/authGuard.test.ts` を追加した。`backend/tests/integration/test_manage_cli.py` には `authz-sync` と `authz-grant-role` の smoke を追加した。
- 2026-08-08: `app_test` は旧 0005 migration 適用済みだったため、保持対象でない test DB として `20260806_0004` へ downgrade 後に head へ upgrade し直し、`db-check` が差分なしになることを確認した。
- 2026-08-08: 再レビュー後、Step 11.2 の既存 Frontend auth user fixture 更新漏れを修正した。`login.test.tsx` では admin 権限付き login response が `queryKeys.auth.me` cache にそのまま保存されることを固定し、Header / hooks / settings / register の既存 fixture には `roles: []` / `permissions: []` を追加した。あわせて authorization route wiring test は OpenAPI の公開 `/api/...` path を検証する形へ変更し、Injector container からの実解決、`authz-grant-role` の user missing / role missing exit 1 も unit test で固定した。

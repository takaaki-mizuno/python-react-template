# ユーザー一覧をベースに、AdminCRUDの基礎を作る

documents/plans/20260808-rbac-authorization.md で権限管理の機能を追加した。詳細は @documents/references/rbac-authorization-operations.md

ここで、Adminのユーザー一覧の管理画面を作る。

- ユーザーのCRUDを作り、admin:access permissionで利用可能にする ( URLは /admin/users )
    - CRUDの一覧画面はFilterと検索をつける
    - ページネーションをつける（パラメータは offset と limit を利用する）
- ユーザーのCRUDは、すべての管理画面のCRUDのベースとするため、できる限り抽象化する
- 今後のCRUD作成のため、CRUDの作成方法を SKILL としてまとめる
- seed として管理者 ( admin@example.com / Password@123! ) のアカウントを作れるようにする

ということをお願いします。

---

## 2026-08-10 追記: 実装計画

この追記は、上記の要件メモを実装可能な粒度へ分解するための計画である。既存の要件本文は変更せず、ここから下を AI が追記した計画として扱う。

2026-08-10 のレビュー反映後、この追記内の AI 追記内容は本節の記述を正とする。古い記述と新しい記述が矛盾する場合は、レビュー反映後の方針・API 契約・タスクを優先する。

### 背景

`documents/plans/20260808-rbac-authorization.md` と `documents/references/rbac-authorization-operations.md` で、code-managed RBAC が導入済みである。現在の認可 catalog は `backend/app/config/authorization.py` を正とし、`admin` role は `admin:access` permission を持つ。既存 Admin API として `GET /api/admin/roles`、`GET /api/admin/users/{user_id}/roles`、`PUT /api/admin/users/{user_id}/roles` があり、すべて `admin:access` で保護されている。

一方、Frontend の `/admin` は `frontend/src/routes/_authenticated.admin.tsx` に存在するが、現状はプレースホルダーである。Backend には user-owned resource の例として `/api/samples` があり、controller / usecase / repository / schema / interface / test を分ける構成が確立している。今回のユーザーCRUDは、この既存構成に沿って Admin 領域の基礎を作る。

`documents/plans/20260718-admin-user-seed-design.md` には `seed-admin` の設計があるが、当時は admin 権限を表す属性が存在しなかったため、`admin@example.com` は通常ユーザーとして扱う前提だった。現在は code-managed RBAC が存在するため、今回の seed は user 作成または更新に加えて `admin` role 付与まで行う必要がある。

### 現状との矛盾・確認結果

- 既存 Admin API は `admin:access` で保護されている。今回も同じ permission を使う。
- 要件本文は `admin:access` permission を指定しており、既存 Admin API も `admin:access` で統一されているため、新しい `admin:user_management` permission は追加しない。
- DB catalog として `roles` / `permissions` / `role_permissions` table を復活させない。RBAC catalog は引き続きコード管理にする。
- user CRUD 用の新規 DB table は作らない。既存 `users`、`user_roles`、`auth_sessions`、`auth_audit_logs`、`auth_identities` を使う。
- 今回は Alembic migration を追加しない方針にする。`users` の検索・offset pagination はテンプレート規模の管理画面として既存 schema で実装し、性能要件が上がった時点で index 追加を別計画にする。
- 既存 `AuthRepository.mark_user_deleted()` は「削除時に `USER_MARKED_DELETED` audit を1件残す」という不変条件を持つ。Admin CRUD でもこの repository method を再利用し、Admin 固有 actor 情報は追加の `USER_DELETED_BY_ADMIN` audit として usecase 側で残す。
- 既存 `auth_errors.py` には `EmailAlreadyRegisteredError`、`UserNotFoundError`、`WeakPasswordError` がある。Admin CRUD 固有 error class は作らず、同じ domain error と API error code を再利用する。
- 既存 sample CRUD は cursor pagination、今回の Admin CRUD は要件により offset pagination を使う。今後の skill / reference では「Admin 一覧は offset、user-facing feed は cursor」を使い分けとして明記する。

### 方針とその理由

- Admin user CRUD の Backend endpoint は `/api/admin/users` 配下に追加し、`require_permission("admin:access")` で保護する。Frontend guard は表示制御であり、Backend permission dependency を認可境界にする既存方針を維持するため。
- Frontend route は `/admin/users` を追加し、既存 `/admin` は管理トップとしてユーザー管理への導線を置く。要件で URL が `/admin/users` と指定されているため、一覧・作成・編集・削除の主画面をこの URL に集約する。
- 一覧 API は offset pagination を正にし、`offset` と `limit` を query parameter にする。response には `total`、`offset`、`limit` を含め、Frontend が総件数とページ移動可否を判断できるようにする。
- Query parameter は API JSON と同じく public contract を camelCase にする。Python 側では `is_active: bool | None = Query(default=None, alias="isActive")` として明示し、今後の Admin CRUD でも camelCase query を標準にする。
- 検索 parameter は `search` とし、email の case-insensitive 部分一致に限定する。現行 user model は表示名や氏名を持たないため、検索対象を email に絞る。
- Filter は `isActive` と `role` を提供する。`isActive=true|false` で凍結状態を絞り込み、`role=<roleCode>` で `user_roles` を絞り込む。`deleted_at IS NULL` は常に適用し、削除済み user は管理一覧・詳細・更新対象に出さない。
- 削除は物理削除ではなく logical deletion とする。既存の account deletion 契約で `users.deleted_at` が削除状態、`is_active` が凍結・停止を表すため。
- Admin による削除では `AccountDeletionUsecase` の cleanup 順序に合わせ、sample items、role assignments、auth identities、`AuthRepository.mark_user_deleted()`、session revoke の順に処理する。
- Admin user update では `email`、`password`、`isActive`、`roles` を同一 request / transaction で更新できるようにする。UI の edit submit が user PATCH と role PUT の2段階になって部分成功することを避けるため。
- Password 更新時と `isActive=false` への変更時は対象 user の active sessions を revoke する。管理者による password reset はアカウント乗っ取り対応に使われ得るため、既存 session を残さない。
- Email 更新時は active sessions を revoke しない。email はログイン識別子だが既存 session token の検証材料ではないため。ただし audit には `email` を changed field として残し、OIDC identity は自動 unlink しない。
- OIDC-only user (`password_hash IS NULL`) に password を設定することは許可する。結果として password login と OIDC login の両方を持つ user になる。OIDC identity は provider subject の link として維持し、email 変更だけで削除・再link しない。
- Role 編集は既存 authorization repository の role 置き換えを使い、audit detail は共通の純関数で組み立てる。共通化するのは audit detail の形だけであり、role validation / dedupe / assignment 呼び出しは各 usecase が自分の transaction 境界で明示する。
- Admin user create は email、password、isActive、roles を受け取り、user 作成と role 付与を同一 transaction で処理する。作成直後に role 付与だけ失敗して中途半端な user が残ることを避けるため。
- Admin user CRUD の audit event を追加する。`AuthEventType` は DB enum ではなく string 保存なので migration は不要。作成・更新・削除の actor / target / changed fields を `detail_json` に残し、レビュー時に操作経緯を追えるようにする。
- CRUD 抽象化の実体は、Backend では `AdminOffsetPageRequest` / `AdminOffsetPageResult[T]` / search 正規化 helper、Frontend では generic な search-param parser、toolbar、pagination、table shell、confirm dialog にする。user lifecycle は auth / RBAC / session revoke / OIDC identity と結びつきが強いため、repository の generic base class は作らない。
- UI のデザイン方向は「Utility & Function」にする。管理者が繰り返し検索・比較・編集する画面なので、マーケティング的な余白や装飾ではなく、密度、可読性、明確な操作状態を優先する。
- 今後の CRUD 作成方法は project-local skill として `.agents/skills/admin-crud/SKILL.md` と `.claude/skills/admin-crud/SKILL.md` の両方にまとめる。既存 project-local skills が両ディレクトリに配置されており、Codex と Claude Code の双方から利用できるようにするため。`agents/openai.yaml` は既存 project-local skills に前例がないため作らない。
- Admin user create / password update は Argon2 hash を実行するが、今回は追加 rate limit を実装しない。`admin:access` で保護された管理操作であり、一般公開 registration/login endpoint の rate limit とは脅威面が異なるため。必要になった場合は admin mutation rate limit を別計画で扱う。

### 採用した設計判断・逸脱・トレードオフ

- 設計判断: `admin:access` のまま進める。要件本文が `admin:access` を指定しており、既存 Admin API も同 permission で保護済みのため。
- 設計判断: 削除済み user は Admin CRUD でも非表示・404 とする。既存 role 管理 API が deleted user を `USER_NOT_FOUND` とする契約に合わせるため。
- 設計判断: `is_active` は削除ではなく凍結・停止として UI に出す。`deleted_at` と意味が違うため、削除操作と有効/無効切替を混ぜない。
- 設計判断: `role` filter は code-managed catalog に存在する role code だけを許可する。未知 role assignment は運用上 `authz-check-assignments` / prune CLI で扱う既存方針に合わせるため。
- 設計判断: Admin user list item は `roles` だけを返し、`permissions` は detail response と role catalog response で扱う。permissions は roles から機械的に導出でき、一覧 100 件で毎回返すと冗長になるため。
- 設計判断: `AuthRepository` は Admin 都合の create/update で拡張せず、Admin user の create/update は `AdminUserRepository` に寄せる。ただし `mark_user_deleted()` だけは `USER_MARKED_DELETED` audit を1件残す既存不変条件を持つため、Admin delete でも `AuthRepository` を再利用する。
- 設計判断: `authz-prune-unknown-role-assignments` の audit detail は `resultingRoles` を持たない既存形式を維持する。unknown role prune には残存 role set という意味のある結果値がなく、無理に `resultingRoles: []` を足すと運用クエリと既存テストを壊すため。
- 逸脱: `documents/plans/20260718-admin-user-seed-design.md` の「seed user は通常ユーザー」という前提からは意図的に離れる。現在は RBAC が実装済みであり、管理画面利用の seed としては `admin` role 付与まで行う必要があるため。
- トレードオフ: 汎用 CRUD repository base class は作らない。将来の CRUD で再利用しやすい魅力はあるが、user CRUD は認証・認可の副作用が大きく、早期抽象化で安全性を落とすリスクが高い。代わりに pagination DTO、controller error mapping、Frontend toolbar / pagination / table shell / search-param parser / dialog を再利用単位にする。
- トレードオフ: offset pagination を採用する。cursor pagination より大規模データでの安定性は落ちるが、要件で `offset` / `limit` が指定されており、管理画面のフィルタ・検索・総件数表示との相性がよい。
- トレードオフ: email 部分一致検索に DB index を追加しない。`ILIKE '%term%'` は大規模 DB では遅くなり得るが、今回のテンプレートでは migration を避け、性能要件が明確化した時点で trigram index 等を別途検討する。

### API 契約

- `GET /api/admin/users`
  - query: `offset: int = 0`、`limit: int = 20`、`search: str | None`、`isActive: bool | None`、`role: str | None`
  - validation: `offset >= 0`、`1 <= limit <= 100`、`search` は trim 後 320 文字以下、`role` は既知 role code のみ
  - response: `{ "items": AdminUserListItemResponse[], "total": number, "offset": number, "limit": number }`
  - list item fields: `id`、`email`、`isActive`、`createdAt`、`updatedAt`、`lastLoginAt`、`roles`
  - sort: `createdAt desc, id desc`
- `POST /api/admin/users`
  - body: `{ "email": string, "password": string, "isActive": boolean, "roles": string[] }`
  - validation: email は `EmailStr`、password は 12-128 文字、roles は既知 role code のみ、duplicate role は順序維持で dedupe
  - success: `201 AdminUserResponse`
  - errors: `409 EMAIL_ALREADY_REGISTERED`、`422 WEAK_PASSWORD`、`422 ROLE_NOT_FOUND`
- `GET /api/admin/users/{userId}`
  - success: `200 AdminUserResponse`
  - detail fields: `id`、`email`、`isActive`、`createdAt`、`updatedAt`、`lastLoginAt`、`roles`、`permissions`
  - errors: missing / deleted user は `404 USER_NOT_FOUND`
- `PATCH /api/admin/users/{userId}`
  - body: `{ "email"?: string, "password"?: string, "isActive"?: boolean, "roles"?: string[] }`
  - validation: omitted と null を区別する。`email: null`、`password: null`、`isActive: null`、`roles: null` は reject する。empty body は no-op 200 とする。
  - atomicity: user fields と roles が同時指定された場合は同一 transaction で更新する。
  - success: `200 AdminUserResponse`
  - errors: `404 USER_NOT_FOUND`、`409 EMAIL_ALREADY_REGISTERED`、`422 WEAK_PASSWORD`、`422 ROLE_NOT_FOUND`
- `DELETE /api/admin/users/{userId}`
  - success: `204`
  - behavior: `AuthRepository.mark_user_deleted()` で `deleted_at` と `USER_MARKED_DELETED` audit を残し、active sessions を revoke し、role assignments と auth identities を削除する。加えて `USER_DELETED_BY_ADMIN` audit に actor 情報を残す。
  - errors: missing / deleted user は `404 USER_NOT_FOUND`
- 既存 `PUT /api/admin/users/{userId}/roles`
  - standalone role 管理 API として維持する。
  - Admin user edit UI は部分成功を避けるため、roles を含む `PATCH /api/admin/users/{userId}` を使う。
  - 既存 endpoint と新規 Admin user usecase は同じ role audit detail helper を使う。role validation / assignment 呼び出しは各 usecase が明示する。

### 変更予定ファイル

- Backend common admin CRUD
  - `backend/app/models/admin_pagination.py`
  - `backend/app/models/admin_query.py`
- Backend auth / authorization shared helpers
  - `backend/app/usecases/authorization_audit.py`
  - `backend/app/usecases/authorization_usecase.py`
- Backend model / schema
  - `backend/app/models/admin_user.py`
  - `backend/app/models/admin_user_schemas.py`
  - 既存 `backend/app/models/auth_errors.py` を再利用し、`admin_user_errors.py` は作成しない
- Backend interface / service / usecase
  - `backend/app/interfaces/services/admin_user_repository_interface.py`
  - `backend/app/services/admin_user_repository.py`
  - `backend/app/interfaces/usecases/admin_user_usecase_interface.py`
  - `backend/app/usecases/admin_user_usecase.py`
- Backend controller / DI / route
  - `backend/app/controllers/admin_user_controller.py`
  - `backend/app/bootstrap/modules.py`
  - `backend/app/bootstrap/route.py`
  - `backend/app/models/auth_event_type.py`
- CLI seed
  - `backend/manage.py`
- Backend tests
  - `backend/tests/unit/models/test_admin_user.py`
  - `backend/tests/unit/models/test_admin_pagination.py`
  - `backend/tests/unit/controllers/test_admin_user_controller.py`
  - `backend/tests/unit/services/test_admin_user_repository.py`
  - `backend/tests/unit/usecases/test_admin_user_usecase.py`
  - `backend/tests/unit/usecases/test_authorization_audit.py`
  - `backend/tests/unit/bootstrap/test_container.py`
  - `backend/tests/unit/bootstrap/test_route.py`
  - `backend/tests/unit/test_manage.py`
  - `backend/tests/integration/test_admin_user_controller.py`
  - `backend/tests/integration/test_manage_cli.py`
- Frontend API / state
  - `frontend/src/lib/adminUsersApi.ts`
  - `frontend/src/lib/adminUsersApi.test.ts`
  - `frontend/src/lib/adminSearchParams.ts`
  - `frontend/src/lib/adminSearchParams.test.ts`
  - `frontend/src/lib/queryKeys.ts`
- Frontend UI / route
  - `frontend/src/routes/_authenticated.admin.tsx`
  - `frontend/src/routes/_authenticated.admin.users.tsx`
  - `frontend/src/routes/admin.users.test.tsx`
  - `frontend/src/components/organisms/AdminUsers/AdminUsersPage.tsx`
  - `frontend/src/components/organisms/AdminUsers/AdminUsersPage.test.tsx`
  - `frontend/src/components/organisms/AdminUsers/types.ts`
  - `frontend/src/components/molecules/AdminCrudToolbar.tsx`
  - `frontend/src/components/molecules/AdminDataTable.tsx`
  - `frontend/src/components/molecules/AdminPagination.tsx`
  - `frontend/src/components/molecules/AdminConfirmDialog.tsx`
  - 必要になった shadcn atom: `dialog`、`table`、`checkbox`、`select` 相当。pinned local CLI が component library prompt で非対話実行できない場合は `npm exec -- shadcn view <name>` で registry content を確認し、この repo の alias に合わせて `src/components/atoms/` へ手で追加する。
- CRUD 作成 skill / docs
  - `.agents/skills/admin-crud/SKILL.md`
  - `.claude/skills/admin-crud/SKILL.md`
  - `documents/references/backend-app-structure.md`
  - `documents/references/frontend-app-structure.md`
  - `documents/references/rbac-authorization-operations.md`
  - `README.md`

### 具体的なタスク

#### Task 0: 実装前の安全確認

- [x] `rtk git status --short` を実行し、既存のユーザー差分を確認する。
- [x] `documents/plans/20260810-admin-crud.md` のこの追記を読み、実装時に計画本文を勝手に削除・大幅改変しない。
- [x] `documents/plans/20260810-admin-crud.md` の `---` より上の要件セクションは read-only として扱う。差分が出ていた場合は作業を中断し、ユーザーに確認する。
- [x] worktree は作らず現在のブランチで作業する。
- [x] この計画作成依頼では `git add` と `git commit` は禁止されているため、実装フェーズでもユーザーが明示するまで実行しない。
- [x] Backend 作業前に `backend/AGENTS.md` を読み直す。
- [x] Frontend 作業前に `frontend/AGENTS.md` を読み直す。
- [x] CRUD skill 作成前に skill creator の手順を確認する。

#### Task 1: Backend の Admin CRUD 共通抽象を追加する

- [x] `backend/app/models/admin_pagination.py` を作成し、`AdminOffsetPageRequest`、`AdminOffsetPageResult[T]` を定義する。
- [x] `AdminOffsetPageRequest` は `offset: int`、`limit: int` を持ち、controller で検証済みの値だけを保持する。
- [x] `AdminOffsetPageResult[T]` は `items: list[T]`、`total: int`、`offset: int`、`limit: int` を持つ generic dataclass にする。
- [x] `backend/app/models/admin_query.py` を作成し、Admin CRUD 共通の `normalize_admin_search(value: str | None, *, max_length: int = 320) -> str | None` を定義する。
- [x] `normalize_admin_search()` は trim 後の空文字を `None` にし、上限超過時は `ValueError` を出す。controller はこの `ValueError` を HTTP 422 に変換し、500 にしない。user 固有の `is_active` / `role` はここに置かない。
- [x] `backend/tests/unit/models/test_admin_pagination.py` を追加し、page result の型と値保持だけを小さく検証する。
- [x] `backend/tests/unit/models/test_admin_query.py` を追加し、`normalize_admin_search()` の trim、空文字、上限超過を検証する。
- [ ] `documents/references/backend-app-structure.md` 更新タスクで、Admin 一覧は offset pagination、user-facing feed は cursor pagination を使うという判断を必ず反映する。

#### Task 2: Backend の role audit detail 共有 helper を追加する

- [x] `backend/app/usecases/authorization_audit.py` を作成し、role grant/revoke audit の `detail_json` を組み立てる純関数 `role_audit_detail()` を定義する。
- [x] `role_audit_detail()` は `source`、`actor_user_id`、`target_user_id`、`role_code`、`resulting_roles` を受け、既存 API / CLI grant と同じ key (`source` がある場合のみ、`actorUserId`、`targetUserId`、`roleCode`、`resultingRoles`) を返す。
- [x] `role_audit_detail()` の docstring には、`source=None` の場合は `"source": null` ではなく `source` key 自体を省くことを明記する。
- [x] `role_audit_detail()` は audit log の保存を行わない。`create_audit_log()` の呼び出しは `AuthorizationUsecase`、`AdminUserUsecase`、`manage.py` の各 caller に残し、変更範囲を最小化する。
- [x] `AuthorizationUsecase.replace_user_roles()` を `role_audit_detail()` 使用へ変更し、既存 response / audit detail の形を維持する。
- [x] `manage.py authz-grant-role` と新規 `seed-admin` は `role_audit_detail()` を使う。
- [x] `manage.py authz-prune-unknown-role-assignments` は `role_audit_detail()` の対象外にし、既存の `resultingRoles` なし detail を維持する。unknown role prune には結果 role set が存在しないため。
- [x] `AuthRepository.mark_user_deleted()` は変更せず、Admin 用に同名 method を新設しない。
- [x] `AuthRepository` に Admin create/update 用 method は追加しない。Admin user の create/update は `AdminUserRepository` に実装する。
- [x] `backend/tests/unit/usecases/test_authorization_audit.py` を追加し、API / CLI grant / seed で使う audit detail が同じ key を持つこと、`source=None` では `source` key が含まれないことを検証する。
- [x] 既存 authorization usecase / CLI grant tests を更新し、共有 helper 化で既存 audit detail が変わっていないことを確認する。
- [x] prune tests は `resultingRoles` が追加されていないことを明示的に維持する。

#### Task 3: Backend の admin user domain 型と schema を追加する

- [x] `backend/app/models/admin_user.py` を作成し、list record / list result / update changes 用の dataclass を定義する。
- [x] `AdminUserListQuery` は `backend/app/models/admin_user.py` に定義し、`search: str | None`、`is_active: bool | None`、`role: str | None` を持つ。共通 `admin_query.py` には user 固有型を置かない。
- [x] `AdminUserRecord` は `User` と `roles: tuple[str, ...]` だけを持つ。`permissions` は repository では組み立てない。
- [x] `AdminUserDetail` は `User`、`roles: tuple[str, ...]`、`permissions: tuple[str, ...]` を持つ。permissions は usecase で `resolve_user_authorization()` から導出する。
- [x] `AdminUserUpdateChanges` は `email: str | None`、`password: str | None`、`is_active: bool | None`、`roles: tuple[str, ...] | None`、`fields_set: frozenset[str]` を持つ。
- [x] `backend/app/models/admin_user_errors.py` は作成しない。`EmailAlreadyRegisteredError`、`UserNotFoundError`、`WeakPasswordError` は既存 `backend/app/models/auth_errors.py` を再利用する。
- [x] `backend/app/models/admin_user_schemas.py` を作成し、camelCase alias と `extra="forbid"` を設定する。
- [x] `AdminUserListItemResponse` は `id`、`email`、`isActive`、`createdAt`、`updatedAt`、`lastLoginAt`、`roles` を返す。
- [x] `AdminUserResponse` は list item fields に加えて `permissions` を返す。
- [x] `AdminUserListResponse` は `items`、`total`、`offset`、`limit` を返す。
- [x] `AdminUserCreateRequest` は `email`、`password`、`isActive=true`、`roles=[]` を受ける。
- [x] `AdminUserUpdateRequest` は `email`、`password`、`isActive`、`roles` を optional にし、non-nullable patch field の `null` を validator で reject する。
- [x] `backend/tests/unit/models/test_admin_user.py` で camelCase serialization、extra forbid、patch null reject、empty patch の `model_fields_set`、list item に permissions が含まれないことを検証する。

#### Task 4: Backend repository interface と永続化実装を追加する

- [x] `backend/app/interfaces/services/admin_user_repository_interface.py` を作成する。
- [x] interface に `list_users(query: AdminUserListQuery, page: AdminOffsetPageRequest) -> AdminOffsetPageResult[AdminUserRecord]` を定義する。
- [x] interface に `get_user(user_id: UUID) -> User | None` を定義する。
- [x] interface に `create_user(email: str, password_hash: str, is_active: bool) -> User` を定義する。
- [x] interface に `update_user(user_id: UUID, changes: AdminUserUpdateChanges, password_hash: str | None) -> User` を定義する。ただし `roles` は repository では更新せず、usecase が authorization repository と `role_audit_detail()` を使って処理する。
- [x] `backend/app/services/admin_user_repository.py` を作成する。
- [x] `list_users()` は `User.deleted_at IS NULL` を必ず条件に入れる。
- [x] `list_users()` は `search` がある場合、trim/lower した値で `lower(users.email) LIKE %...%` を適用する。
- [x] `list_users()` は `is_active` が指定された場合だけ `users.is_active` 条件を適用する。
- [x] `list_users()` は `role` が指定された場合だけ `user_roles` を join または exists で参照し、対象 role code を持つ user に絞る。
- [x] `list_users()` は `created_at desc, id desc` で sort し、`offset` / `limit` を適用する。
- [x] `list_users()` は同じ filter で `total` を別 query で取得する。role 条件による重複が出ないよう `count(distinct users.id)` か exists を使う。
- [x] role code の一括取得は repository 内の private helper として実装し、`list_users()` が返す `AdminUserRecord.roles` を埋める。public interface には露出しない。
- [x] `get_user()` は missing / deleted user で `None` を返す。
- [x] `create_user()` と `update_user()` は partial unique index 衝突を既存 `EmailAlreadyRegisteredError` に変換する。
- [x] repository は `permissions_for_role_codes()` や `resolve_user_authorization()` を呼ばない。permissions 導出は usecase 側に限定する。
- [x] `backend/tests/unit/services/test_admin_user_repository.py` を追加し、list filter、search、role filter、offset/limit、deleted 除外、role 一括取得、duplicate email を検証する。

#### Task 5: Backend usecase を追加する

- [x] `backend/app/interfaces/usecases/admin_user_usecase_interface.py` を作成する。
- [x] interface に `list_users()`、`create_user()`、`get_user()`、`update_user()`、`delete_user()` を定義する。
- [x] `backend/app/usecases/admin_user_usecase.py` を作成する。
- [x] `list_users()` は `role` が指定された場合、`role_catalog_by_code()` に存在するか検証し、未知 role は `RoleNotFoundError` にする。
- [x] `list_users()` は repository から受けた roles に対して unknown role を public response へ出すかどうかを既存 authorization 方針に合わせる。既知 role だけを response に出し、unknown role は warning log と運用 CLI で扱う。
- [x] `create_user()` は email を trim/lower で正規化し、`validate_password_policy()` と `PasswordHashExecutor.hash()` を使う。
- [x] `create_user()` は user 作成、`USER_CREATED_BY_ADMIN` audit、role 置き換え audit を同一 `UnitOfWorkInterface.transaction()` 内で実行する。
- [x] `create_user()` は role code を dedupe し、未知 role があれば DB 書き込み前に `RoleNotFoundError` にする。
- [x] `create_user()` の role audit detail は Task 2 の `role_audit_detail()` で組み立てるが、role validation / dedupe / `AuthorizationRepositoryInterface.replace_user_roles()` 呼び出しは `AdminUserUsecase` 内で明示する。
- [x] `get_user()` は repository の `None` を既存 `UserNotFoundError` にし、permissions は `resolve_user_authorization()` で導出する。
- [x] `update_user()` は empty patch を no-op とし、更新後の detail response を返す。
- [x] `update_user()` は email 更新時に trim/lower する。
- [x] `update_user()` は password が指定された場合だけ policy validation と hash 更新を行う。
- [x] `update_user()` は roles が指定された場合、user field update と role replacement を同一 transaction で実行する。
- [x] `update_user()` の role audit detail は Task 2 の `role_audit_detail()` で組み立てるが、role validation / dedupe / `AuthorizationRepositoryInterface.replace_user_roles()` 呼び出しは `AdminUserUsecase` 内で明示する。
- [x] `update_user()` は password 変更時と `is_active=false` への変更時に `AuthRepository.revoke_sessions_for_user()` を呼ぶ。
- [x] `update_user()` は email 変更時だけでは session revoke しない。OIDC identity も自動 unlink しない。
- [x] `update_user()` は `USER_UPDATED_BY_ADMIN` audit を作り、`detail_json.changedFields` には `email`、`password`、`isActive`、`roles` の field name だけを残す。平文 password や password hash は audit に残さない。
- [x] `delete_user()` は自己削除も禁止しない。既存 RBAC 設計が最後の admin 保護を持たないため。
- [x] `delete_user()` は `AccountDeletionUsecase` の cleanup 順序に合わせ、sample items、roles、auth identities、`AuthRepository.mark_user_deleted()`、sessions revoke を同一 transaction 内で実行する。
- [x] `delete_user()` は `AuthRepository.mark_user_deleted()` により `USER_MARKED_DELETED` audit を維持し、別途 `USER_DELETED_BY_ADMIN` audit で actor 情報を残す。
- [x] `delete_user()` は deleted user の email 再利用を許可する既存 partial unique index 契約を壊さない。
- [x] user-owned resource を追加する後続実装では `AccountDeletionUsecase` と `AdminUserUsecase.delete_user()` の両方へ cleanup を追加する必要があることを、この usecase のテスト名またはコメントでも分かるようにする。
- [x] `backend/tests/unit/usecases/test_admin_user_usecase.py` で create/list/get/update/delete の正常系、弱い password、duplicate email、unknown role、deleted user、password change session revoke、inactive session revoke、email change no revoke、role update atomicity、delete audit 2 種、audit detail を検証する。

#### Task 6: Backend controller と route / DI を追加する

- [x] `backend/app/controllers/admin_user_controller.py` を作成する。
- [x] `router = APIRouter(prefix="/admin/users", tags=["admin"])` にする。
- [x] すべての endpoint で `require_permission("admin:access")` を dependency にする。
- [x] unsafe endpoint は既存 CSRF middleware の対象なので、個別 `Depends(require_csrf)` や CSRF exempt は追加しない。
- [x] controller は `Depends(inject(AdminUserUsecaseInterface))` で usecase を受け、`request.app.state.injector.get(...)` を直接呼ばない。
- [x] `GET /api/admin/users` は `Query(default=0, ge=0)` の `offset` と `Query(default=20, ge=1, le=100)` の `limit` を使う。
- [x] `GET /api/admin/users` は `search: str | None = Query(default=None, max_length=320)`、`role`、`is_active: bool | None = Query(default=None, alias="isActive")` を受け、usecase に渡す。
- [x] `normalize_admin_search()` 由来の `ValueError` は controller で HTTP 422 に変換する。FastAPI `Query(max_length=320)` と二重に守ることで、helper の直接利用時も 500 にしない。
- [x] `POST /api/admin/users` は `201` を返す。
- [x] `PATCH /api/admin/users/{user_id}` は user fields と roles の両方を受けられるようにし、部分成功しない atomic update endpoint とする。
- [x] `PATCH /api/admin/users/{user_id}` は missing user を `404 USER_NOT_FOUND`、duplicate email を `409 EMAIL_ALREADY_REGISTERED`、weak password を `422 WEAK_PASSWORD`、unknown role を `422 ROLE_NOT_FOUND` に変換する。
- [x] `DELETE /api/admin/users/{user_id}` は成功時 `204` を返す。
- [x] `RoleNotFoundError` は既存 authorization controller と同じ `422 ROLE_NOT_FOUND` details 形式にする。
- [x] `backend/app/bootstrap/modules.py` に `AdminUserRepositoryInterface` と `AdminUserUsecaseInterface` の binding を追加する。
- [x] `backend/app/bootstrap/route.py` に admin user router を include する。
- [x] `backend/app/models/auth_event_type.py` に `USER_CREATED_BY_ADMIN`、`USER_UPDATED_BY_ADMIN`、`USER_DELETED_BY_ADMIN` を追加する。
- [x] `backend/tests/unit/controllers/test_admin_user_controller.py` で error mapping、search 長超過の 422、`isActive` alias、request DTO、client IP / user agent 引き渡しを検証する。
- [x] `backend/tests/unit/bootstrap/test_container.py` で DI binding を検証する。
- [x] `backend/tests/unit/bootstrap/test_route.py` で `/api/admin/users` path が OpenAPI に出ることを検証する。
- [x] `backend/tests/integration/test_admin_user_controller.py` で permission required、CSRF required、list search/filter/pagination、create、get、patch user+roles atomic update、delete、role 初期付与を検証する。

#### Task 7: Backend 中間検証

- [x] `cd backend && uv run pytest tests/unit/models/test_admin_pagination.py tests/unit/models/test_admin_query.py tests/unit/models/test_admin_user.py -q`
- [x] `cd backend && uv run pytest tests/unit/usecases/test_authorization_audit.py tests/unit/usecases/test_authorization_usecase.py -q`
- [x] `cd backend && uv run pytest tests/unit/test_manage.py::test_authz_prune_unknown_role_assignments_deletes_and_audits -q`
- [x] `cd backend && uv run pytest tests/unit/services/test_admin_user_repository.py -q`
- [x] `cd backend && uv run pytest tests/unit/usecases/test_admin_user_usecase.py -q`
- [x] `cd backend && uv run pytest tests/unit/controllers/test_admin_user_controller.py -q`
- [x] `cd backend && uv run pytest tests/unit/bootstrap/test_route.py tests/unit/bootstrap/test_container.py -q`
- [x] PostgreSQL が起動している状態で `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest tests/integration/test_admin_user_controller.py -q -ra`

#### Task 8: `seed-admin` CLI を実装する

- [x] `backend/manage.py` に `@app.command("seed-admin")` を追加する。
- [x] command の先頭で `get_config().ENVIRONMENT.lower()` を確認し、`local` / `development` 以外では DB 接続前に exit code 1 で終了する。
- [x] mutating DB command なので `_get_explicit_database_settings("seed-admin")` を使い、`DATABASE_URL` 未設定では exit code 2 にする。
- [x] seed 対象は email `admin@example.com`、password `Password@123!`、role `admin`、`is_active=true` に固定する。
- [x] deleted でない既存 user がいる場合は password hash を再生成し、`is_active=true` に戻す。
- [x] deleted user しかいない場合は、新しい active user を作成する。既存 `find_user_by_email()` は deleted user を除外するため、この挙動になる。
- [x] user 作成または更新と `admin` role 付与を同一 transaction で実行する。
- [x] role 付与 audit は Task 2 の共有 helper を使い、`authz-grant-role` と同じ key を持つ detail にする。`source` は `cli-seed-admin` とする。
- [x] 平文 password は stdout / stderr / audit に出さない。
- [x] 既に admin role を持つ場合も成功扱いにし、冪等に完了する。
- [x] `backend/tests/unit/test_manage.py` に、local/development の成功、production 拒否、DATABASE_URL 必須、既存 user 更新、role 付与 audit のテストを追加する。
- [x] `backend/tests/integration/test_manage_cli.py` に、実 DB で `seed-admin` が user と `admin` role を作り、再実行で重複しないことを検証するテストを追加する。

#### Task 9: Frontend API client / search params / query key を追加する

- [x] `frontend/src/lib/queryKeys.ts` に `adminUsers.root`、`adminUsers.list(params)`、`adminUsers.detail(userId)`、`adminUsers.roles` を追加する。
- [x] `frontend/src/lib/adminSearchParams.ts` を作成し、`offset`、`search`、`isActive`、`role` の parse / default 丸め込み / serialize を共通化する。
- [x] `frontend/src/lib/adminUsersApi.ts` を作成する。
- [x] `AdminUserListItem`、`AdminUser`、`AdminUserListParams`、`AdminUserListResponse`、`AdminUserCreatePayload`、`AdminUserUpdatePayload` の型を定義する。
- [x] `fetchAdminUsers(params)` は `URLSearchParams` を使い、`offset`、`limit`、`search`、`isActive`、`role` を `/api/admin/users` に送る。
- [x] `fetchAdminUser(userId)` は `/api/admin/users/{userId}` を読む。
- [x] `createAdminUser(payload)` は `apiClient.post` を使う。
- [x] `updateAdminUser(userId, payload)` は `apiClient.patch` を使い、省略 field を送らない。roles 更新も同じ payload に含める。
- [x] `deleteAdminUser(userId)` は `apiClient.delete` を使う。
- [x] `fetchAdminRoles()` は既存 `/api/admin/roles` を読み、role selector に使う。
- [x] `frontend/src/lib/adminSearchParams.test.ts` で invalid offset、unknown boolean、空 search、role の serialize を検証する。
- [x] `frontend/src/lib/adminUsersApi.test.ts` で query serialization、CSRF 付き unsafe request、204 delete、error propagation を検証する。
- [x] `toUserMessage()` に admin user CRUD 用の code override を呼び出し側で渡す方針にし、共通 built-in message を増やしすぎない。

#### Task 10: Frontend の Admin CRUD 共通 UI 部品を作る

- [x] `frontend/src/components/molecules/AdminCrudToolbar.tsx` を作成し、検索 input、汎用 filter 定義、作成 button を props で受けるようにする。
- [x] toolbar は user 固有の status / role を直書きしない。`filters: Array<{ key, label, value, options, onChange }>` のような props で受ける。
- [x] `frontend/src/components/molecules/AdminDataTable.tsx` を作成し、columns 定義、loading state、empty state、row actions を props で受ける table shell にする。
- [x] `AdminDataTable` は sort 機能を実装しない。Backend API が sort parameter を持たないため。将来 sort が必要な CRUD では API 契約と同時に追加する。
- [x] `frontend/src/components/molecules/AdminPagination.tsx` を作成し、`offset`、`limit`、`total` から前へ/次へ、現在範囲、総件数を表示する。
- [x] `AdminPagination` は `limit` を固定 20 にする。limit selector は今回の scope から外す。API は limit を受けるが UI 操作を増やしすぎないため。
- [x] `frontend/src/components/molecules/AdminConfirmDialog.tsx` を作成し、削除確認に使う。破壊的操作は確認 dialog を必須にする。
- [x] shadcn atoms が不足する場合は、`frontend/AGENTS.md` と `documents/plans/20260808-frontend-shadcn-component-adoption.md` の実績に従う。`npm exec -- shadcn add <name> --yes` を試し、component library prompt で書き込まない場合は `npm exec -- shadcn view <name>` の内容を repo alias に合わせて追加する。
- [x] Radix-backed atom を追加してテストが落ちた場合は、`frontend/src/test/setup.ts` に必要最小限の jsdom polyfill を追加する。既に `ResizeObserver`、pointer capture、`scrollIntoView` はあるため重複追加しない。
- [x] UI は card の入れ子を避け、管理画面本体は表と toolbar を中心にした密度のある layout にする。
- [x] `frontend/src/components/organisms/AdminUsers/types.ts` に画面内部の form state / field error 型を置く。

#### Task 11: `/admin` と `/admin/users` の画面を実装する

- [x] `frontend/src/routes/_authenticated.admin.tsx` を管理トップにし、`/admin/users` への導線を置く。既存の `admin:access` guard は維持する。
- [x] `frontend/src/routes/_authenticated.admin_.users.tsx` を追加し、`beforeLoad` で `requirePermission("admin:access", options)` を呼ぶ。`_authenticated.admin.tsx` に nest させないため、TanStack Router の trailing underscore を使う。
- [x] route search params は `adminSearchParams.ts` の共通 parser で `offset`、`search`、`isActive`、`role` を parse する。
- [x] `AdminUsersPage` は React Query で role catalog と user list を取得する。
- [x] status filter は user 画面側で `すべて`、`有効`、`停止中` として定義し、`AdminCrudToolbar` へ props で渡す。
- [x] role filter は `/api/admin/roles` の role catalog から options を作り、`AdminCrudToolbar` へ props で渡す。
- [x] 一覧 loading 中は表の骨格か控えめな loading 状態を出し、layout shift を抑える。
- [x] empty state は検索/フィルタなしの空と、検索/フィルタ結果なしを区別する。
- [x] table columns は email、status、roles、lastLoginAt、createdAt、actions にする。
- [x] ID は詳細や audit 用に必要だが画面上は長すぎるため、行の補助情報または copy 可能な短縮表示にする。
- [x] create dialog は email、password、isActive、roles を入力できるようにする。
- [x] edit dialog は email、password optional、isActive、roles を編集できるようにする。submit は `PATCH /api/admin/users/{userId}` の1リクエストにし、user field と role 更新の部分成功を避ける。
- [x] edit dialog で password 欄が空の場合は password を送らない。
- [x] duplicate email、weak password、role not found、CSRF、permission denied、network error を日本語 message に変換する。
- [x] mutation 成功後は list query と detail query を invalidate し、`queryKeys.auth.me` も必要に応じて invalidate する。自分自身の roles / isActive を変えた場合の表示ズレを抑えるため。
- [x] 自分自身を inactive / delete / role 剥奪した場合、次の `/api/auth/me` または session authentication でログイン状態が変わり得る。UI は特別保護せず、API の結果に従う。最後の admin 保護を持たない既存 RBAC 方針に合わせる。
- [x] `frontend/src/routes/admin.users.test.tsx` で `/admin/users` guard、検索 query、pagination query、list rendering、empty state を検証する。
- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.test.tsx` で create/edit/delete/role update/error message/cache invalidation を検証する。

#### Task 12: Frontend 中間検証

- [x] `cd frontend && npm test -- adminSearchParams.test.ts`
- [x] `cd frontend && npm test -- adminUsersApi.test.ts`
- [x] `cd frontend && npm test -- admin.users.test.tsx`
- [x] `cd frontend && npm test -- AdminUsersPage.test.tsx`

#### Task 13: CRUD 作成方法を project-local skill にまとめる

- [x] `.agents/skills/admin-crud/` と `.claude/skills/admin-crud/` を作成する。
- [x] 両方に同一内容の `SKILL.md` を配置する。
- [x] frontmatter は `name: admin-crud`、description は「この repository で Admin CRUD を追加・変更する時に使う」ことが分かる文にする。
- [x] `agents/openai.yaml` は作成しない。既存 project-local skills に前例がなく、今回の skill は repository 内の人間・AI 開発者向け手順として十分なため。
- [x] skill 本文には、この計画で確立した Backend レイヤ構成を記載する。
- [x] skill 本文には、Admin endpoint は Backend で `require_permission("admin:access")` を必須にすることを明記する。
- [x] skill 本文には、Admin 一覧は offset pagination、user-facing feed は cursor pagination という使い分けを書く。
- [x] skill 本文には、camelCase query parameter を使う場合は FastAPI `Query(alias="...")` を明示することを書く。
- [x] skill 本文には、user-owned resource を追加したら `AccountDeletionUsecase` と `AdminUserUsecase.delete_user()` の両方に cleanup を追加することを書く。
- [x] skill 本文には、production の admin lockout 復旧は `authz-grant-role --email <email> --role admin` を使い、`seed-admin` は local/development 専用であることを書く。
- [x] skill 本文には、Frontend の標準構成として `lib/*Api.ts`、`adminSearchParams.ts`、`queryKeys`、route、organism、molecule を記載する。
- [x] skill 本文には、CSRF は `apiClient` に任せ、個別 component から `/api/auth/csrf` を直接 fetch しないことを書く。
- [x] skill 本文には、Backend は controller → usecase → repository の一方向依存を守ることを書く。
- [x] skill 本文には、CRUD resource ごとに汎用 repository base class を無理に継承させず、domain lifecycle と audit を優先する判断基準を書く。
- [x] skill validation が使える環境なら quick validate を実行する。実行できない場合は frontmatter、名前、description、不要ファイルがないことを手動確認する。

#### Task 14: ドキュメントを更新する

- [x] `documents/references/rbac-authorization-operations.md` に Admin user CRUD API の概要、permission、deleted user の扱い、seed-admin の運用を追記する。
- [x] `documents/references/rbac-authorization-operations.md` に、production の admin lockout 復旧は既存 `authz-grant-role --email <email> --role admin` を使うことを追記する。
- [x] `documents/references/backend-app-structure.md` に Admin CRUD の標準ファイル構成、offset / cursor pagination の使い分け、camelCase query alias の扱いを追記する。
- [x] `documents/references/backend-app-structure.md` に、user-owned resource 追加時は `AccountDeletionUsecase` と `AdminUserUsecase.delete_user()` の両方へ cleanup を追加することを追記する。
- [x] `documents/references/frontend-app-structure.md` に Admin CRUD route / component / API client / search-param parser の標準配置を追記する。
- [x] `documents/plans/20260718-admin-user-seed-design.md` には、既存設計が RBAC 導入前の前提であり今回の計画で admin role 付与まで扱うことを追記する。既存内容は消さない。
- [x] `README.md` の初回 migration 手順の後へ、`seed-admin` の手動実行コマンド、ログイン情報、再実行時の冪等性、local/development 専用であることを追記する。

#### Task 15: Backend 最終検証

- [x] `cd backend && uv run pytest tests/unit/models/test_admin_pagination.py -q`
- [x] `cd backend && uv run pytest tests/unit/models/test_admin_user.py -q`
- [x] `cd backend && uv run pytest tests/unit/usecases/test_authorization_audit.py -q`
- [x] `cd backend && uv run pytest tests/unit/services/test_admin_user_repository.py -q`
- [x] `cd backend && uv run pytest tests/unit/usecases/test_admin_user_usecase.py -q`
- [x] `cd backend && uv run pytest tests/unit/controllers/test_admin_user_controller.py -q`
- [x] `cd backend && uv run pytest tests/unit/bootstrap/test_route.py tests/unit/bootstrap/test_container.py -q`
- [x] `cd backend && uv run pytest tests/unit/test_manage.py -q`
- [x] `cd backend && uv run pytest tests/unit -q`
- [x] PostgreSQL が起動している状態で `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest tests/integration/test_admin_user_controller.py -q -ra`
- [x] PostgreSQL が起動している状態で `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest tests/integration/test_manage_cli.py -q -ra`
- [x] `cd backend && uv run ruff check .`
- [x] `cd backend && uv run isort . --check-only`
- [x] `cd backend && uv run yapf -dr app/ tests/ alembic/ manage.py`
- [x] `cd backend && uv run mypy app manage.py`

#### Task 16: Frontend 最終検証

- [x] `cd frontend && npm test -- adminSearchParams.test.ts`
- [x] `cd frontend && npm test -- adminUsersApi.test.ts`
- [x] `cd frontend && npm test -- admin.users.test.tsx`
- [x] `cd frontend && npm test -- AdminUsersPage.test.tsx`
- [x] `cd frontend && npm test`
- [x] `cd frontend && npm run check:ci`
- [x] `cd frontend && npm run build`
- [ ] local dev server で `/admin` と `/admin/users` を開き、admin user で表示できることを確認する。
- [ ] non-admin user で `/admin/users` にアクセスし、`/forbidden` へ遷移することを確認する。
- [ ] `seed-admin` 実行後、`admin@example.com` / `Password@123!` でログインし、`/admin/users` が利用できることを確認する。補足: Docker backend container では `ENVIRONMENT=local` 明示で `seed-admin` 成功まで確認済み。sandbox から host port へ接続できず、container 内 HTTP login smoke は実行中 app の cookie/環境設定により 403 だったため、ブラウザ操作としては未完了。

#### Task 17: 最終確認

- [x] `rtk git diff --stat` で変更範囲を確認する。
- [x] `rtk git diff -- documents/plans/20260810-admin-crud.md` でこの計画以外の意図しない書き換えがないことを確認する。補足: `---` より上の要件差分は、実装開始前から存在した復元済み未コミット差分であり、今回の実装では新たに変更していない。
- [x] `git add` と `git commit` は、ユーザーが明示するまで実行しない。
- [x] 実装完了報告には、実行した検証コマンドと、未実行の品質ゲートがあれば理由を含める。

### 2026-08-11 Claude Code レビュー対応追記

#### 背景

Claude Code レビューで、実装済みの Admin user CRUD に対して、出荷前に直すべき不具合と、計画上チェック済みになっているが実装・テストが不足している箇所が指摘された。精査した結果、少なくとも次の指摘は現行コード上でも再現し、修正対象とした。

- 作成 / 編集 / 削除 mutation の失敗 message が modal overlay の背後に表示され、ユーザーから見えない。
- `normalize_admin_search()` が production code から呼ばれておらず、API の検索 trim / blank-to-none / helper 上限超過 422 が成立していない。
- email 検索の `LIKE` pattern で `%` と `_` が未エスケープであり、`_` を含む email が誤マッチし得る。
- 一覧 API が DB 上の未知 role code をそのまま返し、詳細 API と public response 契約が食い違う。
- Frontend の edit submit が常に `email` / `isActive` / `roles` を送るため、backend の `fields_set` による audit changedFields が実操作を表さない。
- README の `seed-admin` 手順に `ENVIRONMENT=local` がなく、clean checkout の Docker Compose では既定 `production` として拒否される。
- 手書き modal は Radix Dialog の focus / Escape / aria 契約を満たしていなかった。

#### 対応方針とその理由

- 検索正規化は controller で行う。理由は、HTTP query parameter の解釈と `ValueError` から `422 INVALID_ADMIN_USER_QUERY` への変換を controller の責務として閉じられるため。
- `LIKE` wildcard escaping は repository の SQL 条件生成直前で行う。理由は、SQL dialect の `escape` 指定と一体で扱うべき永続化層の詳細だから。
- 一覧 response の未知 role code 除外は usecase で行う。理由は、detail API と同じ `resolve_user_authorization()` を通し、public response の role 契約を backend 境界で統一できるため。
- Frontend mutation error は page-level feedback ではなく、操作中の dialog 内 feedback として表示する。理由は、modal を閉じない失敗時にもユーザーが原因を見て修正できる必要があるため。
- PATCH payload は edit 元の list item と比較して差分だけを送る。理由は、backend の partial update / audit `changedFields` 契約を UI から壊さないため。
- Dialog は shadcn/Radix 由来の atom を追加して使う。理由は、focus trap、Escape close、`aria-labelledby` / `aria-describedby` を手書きで保守しないため。

#### 今回完了した具体的タスク

- [x] `backend/tests/unit/controllers/test_admin_user_controller.py` に、検索 trim が usecase query へ反映されることと、helper 上限超過が `422 INVALID_ADMIN_USER_QUERY` になることを先に追加し、現行実装で失敗することを確認した。
- [x] `backend/app/controllers/admin_user_controller.py` で `normalize_admin_search()` を `AdminUserListQuery` 作成前に呼び出すようにした。
- [x] `backend/tests/unit/services/test_admin_user_repository.py` に、検索 pattern の wildcard escaping と `ESCAPE` 句を検証するテストを先に追加し、現行実装で失敗することを確認した。
- [x] `backend/app/models/admin_query.py` に `escape_like_search()` を追加し、`backend/app/services/admin_user_repository.py` の email `LIKE` 条件で `%` / `_` / escape char をエスケープするようにした。
- [x] `backend/tests/unit/usecases/test_admin_user_usecase.py` に、一覧 response から未知 role code が除外されることを先に追加し、現行実装で失敗することを確認した。
- [x] `backend/app/usecases/admin_user_usecase.py` の `list_users()` で `resolve_user_authorization()` を通し、既知 role のみを `AdminUserRecord.roles` として返すようにした。
- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.test.tsx` に、作成 error が dialog 内 alert として表示されること、edit PATCH payload が差分だけになること、Escape で作成 dialog を閉じられることを追加し、現行実装で失敗することを確認した。
- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.tsx` で `formFeedback` / `deleteFeedback` を page-level `feedback` から分離し、作成 / 編集 / 削除失敗を対象 dialog 内に表示するようにした。
- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.tsx` の `compactUpdatePayload()` を、edit 元 user との差分だけを送る実装に変更した。
- [x] `frontend/src/components/atoms/dialog.tsx` を追加し、Radix Dialog ベースの `Dialog` / `DialogContent` / `DialogTitle` / `DialogDescription` を提供した。
- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.tsx` の作成 / 編集 dialog と、`frontend/src/components/molecules/AdminConfirmDialog.tsx` の削除確認を Radix Dialog atom に載せ替えた。
- [x] `README.md` の `seed-admin` 実行例に `ENVIRONMENT=local` を明示した。

#### 意思決定・逸脱・トレードオフ

- M1 訂正について: repository unit test は SQL を全く見ていないわけではなく、compiled SQL の部分文字列は検証していた。ただし wildcard pattern の値を検証していなかったため、C3 は落とせない状態だった。今回の対応では「SQL の存在」ではなく「escaped pattern と `ESCAPE` 句」を検証対象にした。
- H3 のうち `select` / `checkbox` / `table` の全面 shadcn atom 化は今回の修正範囲から外した。理由は、出荷前の機能破綻である modal error 表示、focus / Escape、search / audit 契約修正を優先し、入力部品の全面置換は UI 差分と回帰範囲が大きいため。Dialog だけは破壊的操作確認にも関わるため今回対応した。
- M4 の `AdminCrudToolbar` を宣言的 filters API に変更する件は未対応。既存 `children` API は再利用性が弱く、計画の記述とも完全には一致していない。次の CRUD 追加前に、`filters: Array<{ key, label, value, options, onChange }>` を受ける API へ寄せるのが望ましい。
- M5 の検索 submit button / debounce は未対応。現在も Enter submit が中心であり、操作発見性には改善余地がある。ただし API 契約破綻ではないため今回の必須修正から外した。
- Dead code のうち `normalize_admin_search()` は production code から利用されるようになった。`fetchAdminUser()` / `queryKeys.adminUsers.detail` / `serializeAdminUserSearchParams()` は今回削除していない。理由は、既存テストと今後の detail 画面 / CRUD skill の拡張余地に関わるため、削除する場合は別途 YAGNI 判断として行う。

#### 今回実行した検証

- [x] `cd backend && uv run pytest tests/unit/controllers/test_admin_user_controller.py tests/unit/services/test_admin_user_repository.py tests/unit/usecases/test_admin_user_usecase.py -q`
- [x] `cd frontend && npm test -- AdminUsersPage.test.tsx`
- [x] `cd backend && uv run ruff check .`
- [x] `cd backend && uv run isort . --check-only`
- [x] `cd backend && uv run yapf -dr app/ tests/ manage.py`
- [x] `cd backend && uv run pytest tests/unit -q`
- [x] `cd backend && uv run mypy app manage.py`
- [x] `cd backend && UV_CACHE_DIR=.cache/uv TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_admin_user_controller.py -q -ra`
- [x] `cd frontend && npm run check:ci`
- [x] `cd frontend && npm test`
- [x] `cd frontend && npm run build`

#### 残タスク

- [ ] `AdminCrudToolbar` を計画どおり宣言的 filter props に寄せ、status / role select の長い className と option mapping を次の CRUD でコピペしない形にする。
- [ ] 検索操作に明示 submit button または debounce を追加するか、Enter submit のままにするなら設計理由を UI 方針として記録する。
- [ ] `fetchAdminUser()` / `queryKeys.adminUsers.detail` / `serializeAdminUserSearchParams()` を残すか削除するかを、次の detail 画面要否と合わせて判断する。
- [ ] 実ブラウザで `/admin`、`/admin/users`、non-admin `/forbidden`、`seed-admin` 後ログインを確認する。

### 2026-08-11 Claude Code 再レビュー対応追記

#### 背景

前回レビュー対応後の再レビューで、Critical / High の大半は解消済みである一方、修正に伴う新規欠陥と、テスト補強なしに未検証のまま残った項目が指摘された。精査した結果、次の2点は実装上の欠陥として修正した。

- `AdminUsersPage` の page-level `feedback` state は非 `null` に設定される経路がなく、到達不能な dead state / dead UI になっていた。
- 作成 / 編集 dialog は送信中でも Escape / overlay 外クリックで閉じられ、サーバが 409 / 422 を返した場合に error が表示されない経路が残っていた。

また、次の項目は機能実装そのものは既に存在しているが、テスト根拠が不足していたため、unit / integration test を追加して契約を固定した。

- repository の count query が list query と同じ filter を持つこと。
- repository の offset / limit 値が SQL statement parameter に入ること。
- `/api/admin/users/{user_id}` が OpenAPI path に含まれること。
- empty PATCH が no-op で、transaction / audit / repository update を発生させないこと。
- Admin user list が deleted user を除外し、大文字小文字非依存検索と offset pagination を満たすこと。
- duplicate email の Admin user create が `409 EMAIL_ALREADY_REGISTERED` を返すこと。
- password update が対象 user の active session を revoke すること。
- create / update / delete / logical deletion の audit event が実 DB に残ること。
- Frontend mutation 成功後に `queryKeys.adminUsers.root` と `queryKeys.auth.me` を invalidate すること。

#### 対応方針とその理由

- 送信中 dialog close は、削除確認 dialog と同じく `!isPending` guard で抑止する。理由は、pending 中の close は mutation error の表示先を失わせるため。
- `feedback` state は削除する。理由は、非 `null` に設定される経路が存在しない状態で残すと、次に触る開発者が page-level error 表示の実装が存在すると誤読するため。
- integration test は大きい happy-path test に詰め込まず、duplicate / pagination / session revoke / audit の契約ごとに分ける。理由は、失敗時に壊れた契約が明確になるため。
- 既に意識的に先送りした `select` / `checkbox` / `table` の shadcn 化、toolbar filters API、検索 submit / debounce、dead code 整理は今回も未対応とする。理由は前回追記の判断を維持し、今回の scope は欠陥修正と既存契約のテスト補強に限定するため。

#### 今回完了した具体的タスク

- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.test.tsx` に、送信中に Escape を押しても作成 dialog が閉じず、その後の duplicate error が dialog 内 alert として表示されるテストを追加し、現行実装で失敗することを確認した。
- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.tsx` の作成 / 編集 dialog `onOpenChange` に `!isFormPending` guard を追加した。
- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.tsx` から到達不能な `feedback` state と page-level `Alert` を削除した。
- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.test.tsx` に、mutation 成功後の `adminUsers.root` / `auth.me` invalidation を検証するテストを追加した。
- [x] `backend/tests/unit/services/test_admin_user_repository.py` で count query の filter 一致、offset / limit parameter 値を検証するようにした。
- [x] `backend/tests/unit/bootstrap/test_route.py` で `/api/admin/users/{user_id}` path も OpenAPI に含まれることを検証するようにした。
- [x] `backend/tests/unit/models/test_admin_user.py` から、直前の dict 完全一致と重複するトートロジー assertion を削除した。
- [x] `backend/tests/unit/usecases/test_admin_user_usecase.py` に empty PATCH no-op のテストを追加した。
- [x] `backend/tests/integration/test_admin_user_controller.py` に、pagination / deleted 除外 / case-insensitive search のテストを追加した。
- [x] `backend/tests/integration/test_admin_user_controller.py` に duplicate email create が 409 になるテストを追加した。
- [x] `backend/tests/integration/test_admin_user_controller.py` に password update が対象 session を revoke するテストを追加した。
- [x] `backend/tests/integration/test_admin_user_controller.py` に Admin user mutation と logical deletion の audit event を検証するテストを追加した。

#### 意思決定・逸脱・トレードオフ

- New-2 は C1 の派生として修正した。送信中 close を許す UI はキャンセル操作として自然に見えるが、今回の mutation は error 表示先が dialog 内であるため、pending 中の close は禁止する方が一貫している。
- New-1 は削除した。page-level feedback を将来復活させる余地はあるが、現時点では使われておらず、残しても機能しない UI 契約に見えるため。
- integration test の audit 検証は event type の存在確認に留め、detail_json の完全一致までは追加しない。detail_json の細部は unit test で確認済みの領域があり、integration では DB transaction 経由で event が残ることを主目的にするため。
- Low 指摘のうち、offset 上限、WEAK_PASSWORD 文言の backend message 連動、pagination loading 中の `0-0 / 0` 点滅、columns `useMemo(..., [])`、field error 型追加は今回も未対応。いずれも出荷前ブロッカーではなく、UI polish / hardening として別タスクで扱う。

#### 今回実行した検証

- [x] `cd frontend && npm test -- AdminUsersPage.test.tsx`
- [x] `cd backend && uv run pytest tests/unit/services/test_admin_user_repository.py tests/unit/bootstrap/test_route.py tests/unit/models/test_admin_user.py tests/unit/usecases/test_admin_user_usecase.py -q`
- [x] `cd backend && UV_CACHE_DIR=.cache/uv TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_admin_user_controller.py -q -ra`
- [x] `cd frontend && npm run check:ci`
- [x] `cd backend && uv run ruff check .`
- [x] `cd backend && uv run isort . --check-only`
- [x] `cd backend && uv run yapf -dr app/ tests/ manage.py`
- [x] `cd backend && uv run pytest tests/unit -q`
- [x] `cd backend && uv run mypy app manage.py`
- [x] `cd frontend && npm test`
- [x] `cd backend && UV_CACHE_DIR=.cache/uv TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration -q -ra`
- [x] `cd frontend && npm run build`

#### 残タスク

- [ ] 実ブラウザで送信中 Escape / overlay 外クリック、作成 duplicate error、編集 weak password error、削除 error を確認する。
- [ ] offset 上限を入れるか、テンプレート規模では不要とする理由を API 契約に明記する。
- [ ] `WEAK_PASSWORD` の frontend 表示を backend error message に寄せるか、固定文言を維持する理由を決める。
- [ ] pagination loading 中の `0-0 / 0` 点滅を `placeholderData` 等で抑えるか判断する。
- [ ] field-specific error 型を Admin user form に導入するか、form-level に限定する設計理由を記録する。

### 2026-08-11 Claude Code 再々レビュー対応追記

#### 背景

再々レビューでは、前回対応した New-1 / New-2 とテスト不足は解消済みと判定された。一方で、`test_admin_users_list_paginates_case_insensitive_search_and_excludes_deleted` は `paginates` を名乗るものの、`offset=1` の response だけを見ており、offset が実際に skip として効いていることを integration test 単体では証明していない、という Low 指摘が残った。

#### 対応

- [x] `backend/tests/integration/test_admin_user_controller.py` の pagination integration test を強化し、同じ検索条件で `offset=0&limit=1` と `offset=1&limit=1` を両方叩くようにした。
- [x] 2つの response が同じ `total=3` を返すこと、各 page が1件ずつ返すこと、返却 ID が kept user に含まれること、かつ `offset=0` と `offset=1` の返却 ID が互いに素であることを検証するようにした。
- [x] deleted user がどちらの page にも出ないことも維持して検証するようにした。

#### 検証

- [x] `cd backend && uv run yapf -dr tests/integration/test_admin_user_controller.py`
- [x] `cd backend && UV_CACHE_DIR=.cache/uv TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_admin_user_controller.py -q -ra`

## 2026-08-11 現行 schema 注記

この計画は historical plan である。現行 schema は `documents/plans/20260811-db-schema-guideline-alignment.md` の DB schema alignment 方針を優先する。

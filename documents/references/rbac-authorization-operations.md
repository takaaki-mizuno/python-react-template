# RBAC 権限管理と運用

このドキュメントは、code-managed RBAC の設計意図、データ構造、変更手順、運用方法をまとめる。

## 結論

- Role / permission catalog はコードだけで管理する。
- Catalog の正は `backend/app/config/authorization.py` である。
- DB には user ごとの assignment として `user_roles(id, user_id, role_code, assigned_at, assigned_by_user_id, created_at, updated_at)` だけを保存する。
- Backend endpoint の認可は role ではなく permission code で行う。
- Frontend の role / permission は表示制御と route guard 用であり、セキュリティ境界ではない。

`roles`、`permissions`、`role_permissions` table と `authz-sync` は持たない。DB catalog を自由編集できるように見える運用上の曖昧さを避けるため、catalog はコードレビュー、テスト、deploy の流れに乗せる。

## DB テーブル

Authorization 用に残す table は `user_roles` だけである。

- `id`: UUID primary key。assignment identity は project 全体の PK ルールに合わせる。
- `user_id`: `users.id` への FK。user 削除時は cascade。
- `role_code`: code-defined role の文字列。FK は張らない。
- `assigned_at`: 付与時刻。DB では Unix timestamp milliseconds の `BIGINT`、Python では `datetime`。
- `assigned_by_user_id`: API 経由で付与した actor user。CLI 付与では `NULL`。
- `created_at` / `updated_at`: ログ・切り分け用の `TIMESTAMPTZ`。role assignment の一意性や業務判断には使わない。

Primary key は `id`。assignment の重複は unique index `uq_user_roles_user_id_role_code` で防ぐ。`role_code` には `ix_user_roles_role_code`、`assigned_by_user_id` には FK 用の `ix_user_roles_assigned_by_user_id` を張る。

## Migration

この repository の Alembic migration は、未適用の開発用 chain を squash した単一の初期 schema revision を正とする。

- Current head: `20260810_0001`
- File: `backend/alembic/versions/20260810_0001_initial_schema.py`
- `roles`、`permissions`、`role_permissions` は初期 migration でも作らない。
- `user_roles` は最初から `role_code` を持つ。

古い local DB が `alembic_version = 20260808_0005` などを持っている場合、squash 後の migration file からはその revision を解決できない。保持対象データがない local DB は作り直す。

```bash
docker compose down
rm -rf docker/postgres/data
docker compose up -d --build postgres backend frontend
```

`docker/postgres/data/` は PostgreSQL の実データであり、`.gitignore` 対象である。`docker/postgres/init/` は初期化 SQL だけを置くディレクトリで、既存 DB の永続データではない。

## Catalog

現在の catalog は `backend/app/config/authorization.py` にある。

```python
DEFAULT_AUTHORIZATION_PERMISSIONS = (
    PermissionDefinition(
        code="admin:access",
        display_name="Admin access",
        description="Access administrative endpoints.",
    ),
)

DEFAULT_AUTHORIZATION_DEFINITIONS = (
    RoleDefinition(
        code="admin",
        display_name="Admin",
        description="Full administrative access for this template.",
        permission_codes=("admin:access",),
    ),
)
```

`create_app()` は起動時に catalog を検証する。`authz-check-config` でも DB なしで同じ検証を実行できる。

## 権限解決

`GET /api/auth/me`、password login、register、OIDC login は `roles` と `permissions` を返す。

DB から `user_roles.role_code` を読み、既知 role だけを public `roles` に返す。未知 role code は public response には出さず、permission にも寄与させない。未知 role があっても認証 request は落とさず、warning log と `authz-check-assignments` で観測する。

## CLI

### Catalog 検査

```bash
cd backend
uv run python manage.py authz-check-config
```

DB は不要。duplicate code、空 catalog、空 code、長すぎる code、未知 permission 参照を検出する。

### Assignment 検査

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://... uv run python manage.py authz-check-assignments
```

`user_roles.role_code` のうち、code catalog に存在しない値を報告して exit code `1` にする。

### Unknown assignment 削除

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://... \
  uv run python manage.py authz-prune-unknown-role-assignments --yes
```

未知 role assignment を削除し、削除ごとに `ROLE_REVOKED` audit log を `source: "cli-prune"` で記録する。role rename には使わない。rename は old code から new code へ明示的に remap する migration または one-off script を用意する。

### Role 付与

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://... uv run python manage.py authz-grant-role \
  --email user@example.com \
  --role admin
```

指定 role は DB 接続前に code catalog で検証する。inactive user は対象に含め、deleted user は通常 user lookup で対象外にする。

Docker Compose の runtime DB に admin role を付与する場合:

```bash
docker compose exec -T backend uv run python manage.py authz-grant-role \
  --email user@example.com \
  --role admin
```

新規登録ユーザーには role は自動付与されない。admin API や admin 画面を使うには、対象ユーザーへ `admin` role を明示付与する。

### Admin seed

ローカルまたは development 環境では、管理画面確認用に `seed-admin` を使える。

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://... uv run python manage.py seed-admin
```

対象は `admin@example.com`、初期 password は `Password@123!`、role は `admin` 固定である。既存の未削除 user がいれば password hash と `is_active=true` を更新し、`admin` role を冪等に付与する。deleted user しかいない場合は新しい user を作る。production など許可外 environment では DB 接続前に失敗する。

## 権限を追加する手順

1. `DEFAULT_AUTHORIZATION_PERMISSIONS` に permission を追加する。
2. `DEFAULT_AUTHORIZATION_DEFINITIONS` の role に permission code を追加する。必要なら新しい role も追加する。
3. Backend endpoint を `require_permission("...")` または `require_any_permission((...))` で守る。
4. Frontend の表示制御や route guard が必要なら `hasPermission()` / `requirePermission()` を使う。
5. `authz-check-config` と該当 backend/frontend tests を通す。
6. deploy する。DB catalog sync は不要。

## Admin API

`GET /api/admin/roles` は code catalog から role / permission 一覧を返す。DB catalog は読まない。

`GET /api/admin/roles` は role catalog collection なので primary list を `data` で返す。一方、`GET /api/admin/users/{user_id}/roles` は特定 user の authorization state という単一 resource representation であり、`roles` / `permissions` を field として返す。これは collection envelope の統一漏れではない。

`PUT /api/admin/users/{user_id}/roles` は role set 置き換えである。未知 role を指定した場合は Problem Details `422 role_not_found`。対象 user が存在しない、または deleted user の場合は `404 user_not_found`。inactive user は role 管理対象として許可する。

`/api/admin/users` は user CRUD API である。`GET` は `offset` / `limit` pagination、email `query`、`is_active` filter、`role` filter を持ち、`data` / `count` / `offset` / `limit` を返す。`POST` は user 作成と初期 role 付与を同一 transaction で行う。`PATCH /api/admin/users/{user_id}` は email、password、`is_active`、roles を同一 request で更新し、UI から role API と分けて呼ぶ必要はない。password 変更と `is_active=false` は対象 user の session を revoke する。`DELETE` は logical deletion と cleanup を行い、`USER_MARKED_DELETED` と `USER_DELETED_BY_ADMIN` の audit を残す。

既存 DB に unknown role assignment が残っている user を admin API で編集する場合、public response には既知 role だけが返る。その既知 role set を `PUT` で保存すると、未知 role assignment は通常の role set 置き換え差分として削除され、`ROLE_REVOKED` audit が残る。retired role を一括削除したい場合は prune CLI を使い、rename の場合は明示 remap を先に行う。

## Rename と削除

Permission code rename は endpoint、Frontend guard、role definition を同時に更新する。旧 permission code を参照しているコードが残っていないことを確認する。

Role code rename は `user_roles.role_code` に既存文字列が残るため、明示的な remap が必要である。新 role を追加して deploy しただけでは既存 user の assignment は移らない。rename 時は prune ではなく、old code から new code へ更新する migration/script を使う。

Role を削除した場合、既存 DB に orphan assignment が残る可能性がある。その user は未知 role 由来の role/permission を失うが、既知 role 由来の権限は維持する。意図的に retired role を消す場合だけ `authz-prune-unknown-role-assignments --yes` を使う。

## Audit

API 経由の role 付与・剥奪は `ROLE_GRANTED` / `ROLE_REVOKED` として actor user/session を残す。

CLI 経由の `authz-grant-role` は `source: "cli"`、`authz-prune-unknown-role-assignments --yes` は `source: "cli-prune"` を `detail_json` に残す。誰が CLI を実行したかは shell history、deployment log、運用監査ログで追う前提である。

## Troubleshooting

- Docker を作り直したのに旧 DB が残る: PostgreSQL の実データは `docker/postgres/data/` にある。`docker/postgres/init/` を削除しても既存 DB は消えない。DB 初期化は `docker compose down` 後に `rm -rf docker/postgres/data` を実行する。
- `Can't locate revision identified by '20260808_0005'`: squash 前の local DB が残っている。保持対象データがない local DB は `docker/postgres/data/` を削除して作り直す。
- `role_not_found`: 指定 role code が `backend/app/config/authorization.py` にない。
- `permission_denied`: `/api/auth/me` の `permissions`、対象 role の `permission_codes`、endpoint の要求 permission を確認する。
- unknown role warning が出る: `authz-check-assignments` で対象 row を確認し、rename なら remap、retire なら prune を行う。
- 自分の role 変更が画面に反映されない: Backend は次回 request で再解決するが、Frontend の React Query cache は invalidate または reload が必要な場合がある。

## 参考

- 実装計画: `documents/plans/20260810-code-managed-authorization.md`
- 旧 RBAC 導入計画: `documents/plans/20260808-rbac-authorization.md`
- Backend 構造: `documents/references/backend-app-structure.md`
- Frontend 構造: `documents/references/frontend-app-structure.md`

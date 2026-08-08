# Backend アプリ構造

## 構成

`backend/app` が FastAPI アプリ本体。`backend/app/main.py` は `create_app()` を呼び、DI、middleware、route、static 配信を組み立てる。

```
backend/
  manage.py
  app/
    bootstrap/      # create_app, DI modules, route, middleware, error handlers
    config/         # BaseSettings
    controllers/    # HTTP 層
    interfaces/     # usecase / service(repository) interfaces
    libraries/      # clock, password hash, token, DB engine など
    models/         # SQLModel table, DTO, domain dataclass, domain errors
    services/       # 永続化 repository 実装
    usecases/       # application logic
  alembic/
  tests/
```

`services/` は現時点で repository 実装の置き場として使う。`repositories/` への改名は未実施であり、Phase 4 時点では `services/` を正とする。
`interfaces/libraries/` は rate limiter など横断 library interface の置き場であり、空 directory ではない。

## 依存方向

基本の依存方向は次の一方向。

```text
controllers -> usecases -> services -> models
```

- Controller は HTTP request / response、auth dependency、error envelope 変換を担当する。
- UseCase は HTTP DTO を返さず、domain model / domain result / domain error を返す。
- Service は SQLModel と `UnitOfWorkInterface` を使う永続化実装を担当する。
- Model は SQLModel table、request/response DTO、domain dataclass、domain error を置く。

## DI

DI は Injector を使う。`bootstrap/modules.py` で `CoreModule`、`DatabaseModule`、`AuthModule`、`SampleModule`、`AccountDeletionModule` を定義し、`bootstrap/container.py` が `Injector` を生成する。

Controller は `request.app.state.injector.get(...)` を直接呼ばない。`bootstrap/dependencies.py` の `inject(Interface)` を `Depends(...)` に渡す。

```python
get_sample_item_usecase = inject(SampleItemUsecaseInterface)

async def list_sample_items(
    usecase: SampleItemUsecaseInterface = Depends(get_sample_item_usecase),
):
    ...
```

`inject()` は Injector の `Any` を helper 内で `cast()` し、controller 側の型を保つ。

## Transaction

transaction 境界は `UnitOfWorkInterface` に置く。repository に `transaction()` を追加しない。

- `UnitOfWorkInterface.transaction()` は outer transaction を作る。
- nested transaction は savepoint ではなく outer transaction に join する。
- repository は `session_scope()` を使い、transaction session 内では `flush()`、transaction 外では `commit()` する。

## API と DTO

public API JSON は request / response とも camelCase を正とする。`populate_by_name=True` は internal / test compatibility であり、docs と curl 例には snake_case を出さない。

HTTP error は `ErrorResponse` envelope で返す。domain error は controller が `api_error()` へ変換する。

`Status` は healthz などの限定用途に使う。CRUD success response の模範にはしない。

## Authorization / RBAC

権限管理は RBAC を正とする。`users.is_active` は凍結・停止であり、管理者権限ではない。

- DB table は `roles`、`permissions`、`user_roles`、`role_permissions`。
- role は permission の集合で、endpoint 保護は role ではなく permission code で行う。
- 初期定義は `app/config/authorization.py` の `DEFAULT_AUTHORIZATION_PERMISSIONS` と `DEFAULT_AUTHORIZATION_DEFINITIONS` に置く。
- 定義同期は `python manage.py authz-sync` で行う。operation 全体を `UnitOfWorkInterface.transaction()` に閉じ、途中失敗で部分適用しない。
- 復旧用 role 付与は `python manage.py authz-grant-role --email <email> --role <roleCode>` を使う。inactive user も対象に含め、deleted user は通常 user lookup で対象外にする。
- `GET /api/auth/me` と login/register response は `roles: list[str]` と `permissions: list[str]` を返す。public response は安定順にする。
- 認可の正は Backend の FastAPI dependency である。`require_permission("admin:access")` / `require_any_permission([...])` を使い、Frontend の表示制御だけを信頼しない。
- `GET /api/admin/roles` は role 一覧と permission catalog を返す。`PUT /api/admin/users/{user_id}/roles` は role set 置換で、CSRF middleware の対象から外さない。
- role 付与・剥奪は `auth_audit_logs` に `ROLE_GRANTED` / `ROLE_REVOKED` として記録する。API 経由では actor user/session を、CLI 経由では `source: "cli"` を `detail_json` に残す。
- self-service account deletion は `user_roles` を物理削除する。復元が必要な派生アプリでは admin workflow 側で再付与する。

## Auth Persistence

- DB 接続は `DATABASE_URL` を正とする。Alembic も同じ設定から `postgresql+asyncpg://` URL を導出し、`ALEMBIC_DATABASE_URL` は使わない。`db-upgrade` / `db-downgrade` / `db-check` / `db-revision` / `db-prune-auth` と bare `alembic current/upgrade` は明示 `DATABASE_URL` を必須にし、既定値だけで DDL や schema check を実行しない。
- `users.is_active` は凍結、`users.deleted_at` は退会または論理削除を表す。通常の user lookup は `deleted_at IS NULL` を含める。
- 削除済み user は login、`GET /api/auth/me`、session authentication で認証不可。認証時だけ `find_user_by_id_for_authentication()` が deleted / inactive を観測して session revoke と audit に使う。
- 削除済み user の email は `uq_users_email_lower_active` partial unique index により再登録可能。active user 同士の重複は DB が拒否する。
- `DELETE /api/auth/me` は Phase 6 の公開 self-service account deletion endpoint。`AccountDeletionUsecase` が account management orchestration boundary であり、sample item cleanup、`mark_user_deleted()`、`revoke_sessions_for_user()` を 1 transaction に閉じる。`AuthUsecase` は sample repositories に依存しない。
- `mark_user_deleted()` は `deleted_at IS NULL` の user を初めて削除状態にした場合だけ `USER_MARKED_DELETED` audit log を同じ repository 操作内で作成する。すでに削除済みの user では `deleted_at` を上書きせず、audit log も追加しない。Phase 6 の公開 account deletion workflow はこの repository 契約を経由し、current session id と request IP を audit log に残す。`session_id` / `ip_address` は省略不可の keyword-only argument であり、監査 context なしで呼ぶ場合も `None` を明示する。
- OAuth-only account deletion caveat: `confirmEmail` is not an authentication factor. OAuth-only user (`password_hash IS NULL`) の削除は OAuth provider reauthentication 実装まで `confirmEmail` のみで許可している。顧客データ、課金、業務データを扱う派生プロジェクトでは、account deletion 公開前に OAuth reauthentication、削除猶予期間、または復元 workflow を設計する。
- account deletion の password 再認証失敗は `ACCOUNT_DELETION_REAUTH_FAILED` audit log を current user / current session / request IP / user_agent 付きで残す。rate limit は login rate limiter の IP bucket と email+IP bucket だけを読み、email 単独 bucket による退会妨害を避ける。
- `tests/unit/usecases/test_account_deletion_coverage.py` は SQLModel metadata に読み込まれた `users` への直接 FK table から user-owned cleanup policy coverage を検出する。間接所有、FK なしの `user_id` column、metadata に import されていない model は検出しない。実際の cleanup 呼び出しは `test_account_deletion_usecase.py` と repository integration tests で検証する。
- Phase 6 の account deletion は既存 schema を使うため、新しい DB migration を作らない。
- physical delete 時は sessions が CASCADE、audit logs の user/session 参照が SET NULL。
- `AuthSession.issued_at` は absolute TTL 起点で、`created_at` は監査用の作成時刻。session touch 時の expiry 再計算に `created_at` を使わない。
- Phase 5 migration `20260803_0003` の downgrade は destructive です。削除済み email を同じ DB で再登録済みの場合、旧 schema の global `lower(email)` unique index を復元できないため `Cannot downgrade 20260803_0003 after deleted email reuse` で停止します。重複 email がない場合でも、`users.deleted_at`、`auth_sessions.issued_at`、`auth_sessions.updated_at`、PostgreSQL `INET` 型への変更は rollback 時に失われます。
- `ip_address` columns は PostgreSQL `INET`、Python model boundary は `str | None`。
- auth repository は domain error を投げる。HTTP error envelope への変換は controller の責務。
- `db-prune-auth` は古い audit log と `expires_at` が threshold より前の session を削除する CLI。CLI bootstrap は FastAPI app を作らず DI container を使い、最後に `AsyncEngine.dispose()` を呼ぶ。両 threshold 指定時は audit log、expired session の順に実行するが、repository 操作ごとに commit されるため、途中失敗時は部分成功になり得る。
- audit log session retention: `auth_audit_logs.session_id` は `ON DELETE SET NULL`。session を物理削除しても audit log row は残り、session 参照だけが `NULL` になる。audit 保持期間中に session id が必要な場合は session retention を audit log retention 以上にし、`NULL` を許容する場合は削除済み session token の後続 replay を既知 session として監査できないことを受け入れる。

### Large Auth Migration Playbook

`20260803_0003` は fresh DB / template 初期導入 / small DB 向けには現 migration のまま維持する。既存派生プロジェクトで適用済みの Alembic revision を書き換える場合は、適用済み DB と未適用 DB の互換性を別計画で扱う。大規模 production DB へそのまま適用する前には、large auth migration として次を確認する。

- 対象 row count: `auth_audit_logs`、`auth_sessions`、`users` の件数と、`ip_address IS NOT NULL` の件数を確認する。
- Lock / rewrite risk: `ALTER COLUMN ... TYPE INET`、全行 `UPDATE`、`ALTER COLUMN ... SET NOT NULL`、index / FK 変更が maintenance window 内に収まるかを staging の production 相当データで測る。
- Blocking tolerance: auth endpoint の read/write を止められる時間、replica lag、statement timeout、lock timeout、rollback 時間を事前に決める。
- Downgrade policy: `INET` 型化、`issued_at` / `updated_at` backfill、partial unique index は rollback 時に情報を失うため、large DB では downgrade より forward fix を基本方針にする。

大規模 DB で downtime を短くしたい場合は、現 revision を直接適用せず、派生プロジェクト用の分割 migration を作る。

1. Nullable shadow columns を追加する。例: `auth_audit_logs.ip_address_inet INET NULL`、`auth_sessions.ip_address_inet INET NULL`、`auth_sessions.issued_at_new TIMESTAMPTZ NULL`、`auth_sessions.updated_at_new TIMESTAMPTZ NULL`。
2. Application dual-write または DB trigger を入れ、新規 / 更新行が旧 column と shadow column の両方へ書かれる期間を作る。dual-write を入れない場合は、backfill 中の新規行を拾う再実行手順を用意する。
3. batch backfill を小さな chunk で実行する。`id` range または `created_at` range で区切り、各 batch を短い transaction にして `lock_timeout` / `statement_timeout` を設定する。`INET` 変換では不正 IP を `NULL` に寄せるか、事前 quarantine table に退避する。
4. Backfill 完了後に validation query を実行する。例: shadow column の `NULL` 件数、旧 `ip_address` と `INET` 変換結果の不一致、`issued_at_new` / `updated_at_new` の未設定件数を確認する。
5. 短い maintenance window で write を止め、最終差分 backfill、NOT NULL 制約、column rename / drop、FK / index swap を行う。大きな index は可能なら `CREATE INDEX CONCURRENTLY` を別 migration に分ける。
6. Swap 後に `db-check` と auth smoke test を実行し、replica lag と error rate を確認してから write を戻す。

この playbook は派生プロジェクト向けの運用方針であり、テンプレート本体の fresh DB / small DB migration を複雑化しないための逃げ道である。

## Sample CRUD

`/api/samples` は新規 user-owned CRUD resource の模範実装。

主要ファイル:

- `models/sample_item.py`
- `models/sample_item_schemas.py`
- `models/sample_item_errors.py`
- `interfaces/services/sample_item_repository_interface.py`
- `services/sample_item_repository.py`
- `interfaces/usecases/sample_item_usecase_interface.py`
- `usecases/sample_item_usecase.py`
- `controllers/sample_controller.py`
- `alembic/versions/20260802_0002_create_sample_items.py`
- `tests/unit/models/test_sample_item.py`
- `tests/unit/services/test_sample_item_repository.py`
- `tests/unit/usecases/test_sample_item_usecase.py`
- `tests/unit/controllers/test_sample_controller.py`
- `tests/unit/controllers/test_sample_controller_dependency.py`
- `tests/integration/test_sample_item_controller.py`

新しい resource を作る場合は、この構成をコピーして、schema 変更前に `documents/plans/` とユーザー確認を必ず通す。

## OAuth/OIDC Client

Phase 8 の OAuth/OIDC client は password auth と session auth の既存契約を保ったまま、外部 provider identity だけを追加する。

- `auth_identities` は `users.id` に従属する provider identity table である。unique key は `(provider_id, provider_subject)` を正とし、email は補助情報として扱う。provider subject は login/link の primary identifier で、email 変更や再割当より安定している。
- `auth_oidc_authorization_states` は authorization code flow の DB-backed state を保持する。state hash、browser binding hash、nonce hash、PKCE verifier、provider id、purpose、expected user/session、redirect path、expiry、consumed time を持つ。
- browser binding cookie は authorization start ごとに `oidc_binding_<state_lookup_id>` として発行する。値は random lookup key で、DB には hash だけを保存する。Cookie は `HttpOnly`、`SameSite=Lax`、state TTL と同じ max-age、auth cookie と同じ Secure 判定を使い、callback consume 後または terminal failure 後に削除する。
- Callback は URL の `state` だけでは完了しない。state row、browser binding cookie、PKCE、nonce、issuer、audience、expiry、signature、safe alg、`email_verified`、purpose 別 expected user/session を検証してから user / identity / session を確定する。
- Redirect URI は `AUTH_OIDC_REDIRECT_BASE_URL` と provider callback path からだけ作る。request host 由来値を使わないため、Host header injection で authorization code を別 origin に流さない。
- `purpose=login` callback は成功時に保存済み internal redirect path へ戻り、失敗時は `/login?oidcError=<machine-code>` に戻る。`purpose=account_deletion_reauth` callback は成功時に `oidcReauth=success`、失敗時に `oidcError=<machine-code>` を保存済み redirect path へ merge する。既存 query / fragment は保持する。
- IdP が callback で `error=access_denied` 等を返した場合も、`state` と browser binding cookie が検証できるなら state row を consume し、`purpose=account_deletion_reauth` は login ではなく保存済み settings path へ `OIDC_PROVIDER_ACCESS_DENIED` を merge して戻す。`state` 自体が無い、または state context を解決できない場合だけ `/login?oidcError=OIDC_STATE_MISMATCH` 等に戻る。
- OIDC redirect query code は `backend/AGENTS.md` の対応表を正とする。新規 code を追加する場合は backend mapping、frontend message、audit event 有無、docs を同時に更新する。
- token 非保存を正とする。Backend は provider `access_token` / `refresh_token` を保存せず、URL、audit、frontend state にも出さない。保存するのは provider subject と allowlist 済み ID token claims だけである。
- Trusted verified email は provider 設定で明示された場合だけ自動作成・自動 link に使う。`AUTO_PROVISION=link-only` は新規 user 作成を拒否し、`LINK_MODE=manual | disabled` は自動 link を拒否する。
- OAuth-only account deletion は `auth_sessions.last_oidc_auth_time_at` と `AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` で freshness を判定する。削除 reauth では provider に `prompt=login` / `max_age=0` を送り、`auth_time` が missing、`OIDC_REAUTH_STALE`、`OIDC_REAUTH_AUTH_TIME_REQUIRED`、future leeway 超過の場合は削除を拒否し続ける。
- Same-user reauth は current session user/session と state の expected user/session、さらに provider subject が指す `auth_identities.user_id` の一致で検証する。別 provider account / 別 user の callback では session を置換せず、`OIDC_REAUTH_SUBJECT_MISMATCH` を settings redirect に載せる。
- Account deletion 成功時は `auth_identities` を同一 transaction で物理削除する。logical deleted user が provider subject unique index を占有し、同じ provider subject で再登録できない状態を避けるためである。
- OIDC state pruning は `db-prune-auth --oidc-states-before <ISO8601>` で expired / consumed state を削除する。未消費 active state は削除しない。
- `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` の response details は linked providers の public metadata (`providerId`, `displayName`) だけを返す。provider subject、claims、token、raw provider error は返さない。

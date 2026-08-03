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

DI は Injector を使う。`bootstrap/modules.py` で `CoreModule`、`DatabaseModule`、`AuthModule`、`SampleModule` を定義し、`bootstrap/container.py` が `Injector` を生成する。

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

## Auth Persistence

- DB 接続は `DATABASE_URL` を正とする。Alembic も同じ設定から `postgresql+asyncpg://` URL を導出し、`ALEMBIC_DATABASE_URL` は使わない。`db-upgrade` / `db-downgrade` / `db-check` / `db-revision` / `db-prune-auth` と bare `alembic current/upgrade` は明示 `DATABASE_URL` を必須にし、既定値だけで DDL や schema check を実行しない。
- `users.is_active` は凍結、`users.deleted_at` は退会または論理削除を表す。通常の user lookup は `deleted_at IS NULL` を含める。
- 削除済み user は login、`GET /api/auth/me`、session authentication で認証不可。認証時だけ `find_user_by_id_for_authentication()` が deleted / inactive を観測して session revoke と audit に使う。
- 削除済み user の email は `uq_users_email_lower_active` partial unique index により再登録可能。active user 同士の重複は DB が拒否する。
- Phase 5 では公開 `DELETE /api/auth/me` と frontend 退会 UI は追加しない。account deletion workflow は Phase 6 の対象。
- `mark_user_deleted()` は `USER_MARKED_DELETED` audit log を同じ repository 操作内で作成する。Phase 6 の公開 account deletion workflow はこの repository 契約を経由する。
- physical delete 時は sessions が CASCADE、audit logs の user/session 参照が SET NULL。
- `AuthSession.issued_at` は absolute TTL 起点で、`created_at` は監査用の作成時刻。session touch 時の expiry 再計算に `created_at` を使わない。
- `ip_address` columns は PostgreSQL `INET`、Python model boundary は `str | None`。
- auth repository は domain error を投げる。HTTP error envelope への変換は controller の責務。
- `db-prune-auth` は古い audit log と expired session を削除する CLI。CLI bootstrap は FastAPI app を作らず DI container を使い、最後に `AsyncEngine.dispose()` を呼ぶ。両 threshold 指定時は audit log、expired session の順に実行するが、repository 操作ごとに commit されるため、途中失敗時は部分成功になり得る。

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

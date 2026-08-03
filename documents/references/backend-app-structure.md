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

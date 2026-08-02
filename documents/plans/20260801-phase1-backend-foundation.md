# Phase 1 バックエンド基盤リファクタ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Worktree、`git add`、`git commit`、`git push`は使用しない。

**Goal:** `documents/reviews/20260801-review.md`のPhase 1「バックエンド基盤リファクタ」を、権限管理・OAuth・フロント認証拡張の前提になるバックエンド構造として整える。

**Architecture:** FastAPI controllerは`Depends`で依存を受け取り、DI containerはInjectorのclass binding/providerを使って依存グラフを構成する。DB transactionはrepositoryから独立したUnit of Workへ移し、複数repositoryをまたぐ将来機能でも1つのtransaction/sessionを共有できるようにする。HTTP errorは`create_app()`で登録した共通handlerに集約し、機械可読なerror envelopeを全経路へ適用する。

**Tech Stack:** Python 3.12、FastAPI、Starlette、Injector、SQLModel、SQLAlchemy AsyncEngine/AsyncSession、Typer、pytest、pytest-asyncio、PostgreSQL

---

## Global Constraints

- Worktreeは使わず、現在のbranchとworking treeで作業する。
- `git add`、`git commit`、`git push`、`git reset`、`git checkout --`、`git clean`は実行しない。
- 新規Alembic revisionは作らない。Phase 1はDB schemaを変更しない。
- 依存追加はしない。既存のPython/Node依存だけを使う。
- frontend実装は変更しない。error envelope導入によるfrontend runtime影響はコード読解と品質ゲートで確認し、`ApiError.body`整備はPhase 3へ残す。
- sample APIのURL、成功レスポンス形式、CRUD化は変更しない。
- 各Task完了後は`.superpowers/checkpoints/phase1/`へtracked patchとuntracked archiveを保存する。
- PostgreSQL integration testを実行する前に、`app_test`へ`python manage.py db-upgrade`を適用する。
- PostgreSQL integration testを1件だけ選択実行する場合も、必ず`TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test`を前置し、skip 0件を確認する。

---

## 背景

Phase 0では、SQLModel metadata/Alembic整合、SPA fallback、static起動、CSRF非ASCII 500、sample controllerの誤ったHTTP statusなど、他機能に依存しない即日修正を完了した。Phase 1では、レビュー文書の推奨修正順序に従い、今後の権限管理・OAuth・フロント認証導線の前提になるバックエンド基盤を直す。

対象はレビューの「Phase 1: バックエンド基盤リファクタ」に列挙された次の項目である。

- `P1-6`: controllerがDIをサービスロケータとして使い、`app.dependency_overrides`で差し替えできない。
- `P1-7`: DI containerが全依存を手動生成しており、機能追加時の編集点が多い。
- `P1-5`: `AsyncEngine`が破棄されず、TestClientやgraceful shutdownでconnection poolが残る。
- `P1-13`: transaction境界が`AuthRepositoryInterface`に閉じており、複数repositoryをまたげない。
- `P2-8`: `authenticate_session`が1リクエストで複数の独立session/transactionを開く。
- `P3-2`: repository instance属性として`ContextVar`を持っており、transaction管理の所在が曖昧。
- `P1-8`: エラーレスポンス形式が`{"detail": ...}`と`Status`形式に分裂している。
- `P1-9`: `create_app()`がlifespan、logging、docs制御、例外handlerを欠く。
- `P2-21`: productionでも`/docs`と`/openapi.json`が公開される。
- `P2-17`: `AuthenticatedSessionContext`がusecase具象moduleにあり、controllerが具象層をimportしている。
- `P2-18`: `register`/`login`が型注釈のない4要素tupleを返している。

今回の計画はバックエンドに限定する。レビュー上のPhase 2以降にあるArgon2 thread化、信頼プロキシ、Secure cookie既定反転、CSRF middleware化、`password_hash` nullable化、frontend query key統一、register UI、CI導入は扱わない。

## 現行コードの分析

現行実装には次の制約がある。

- `backend/app/bootstrap/container.py`は`configure()`内で`GetSampleIndexUsecase`、`AuthRepository`、`InMemoryLoginRateLimiter`、`AuthUsecase`を即時生成している。
- `build_engine_and_session_factory()`は`AsyncEngine`と`async_sessionmaker`を返すが、containerはengineを`_`で捨てており、disposeできない。
- `backend/app/bootstrap/create_app.py`は`FastAPI(title=...)`を作るだけで、lifespan、例外handler、logging設定、production docs制御がない。`environment`引数は未使用である。
- `auth_controller.py`と`sample_controller.py`はhandler内で`request.app.state.injector.get(...)`を直接呼ぶ。
- `auth_dependencies.py`も`request.app.state.injector.get(...)`を直接呼び、`AuthenticatedSessionContext`を`app.usecases.auth_usecase`からimportしている。
- `AuthRepository`は`transaction()`と`_session_scope()`を持ち、`ContextVar`をinstance属性として初期化している。
- `AuthUsecase`は`async with self._auth_repository.transaction():`に依存しているため、別repositoryを追加しても同じtransactionに参加できない。
- `register()`と`login()`は`return user, session, session_token, csrf_token`であり、interface側にも戻り値型がない。
- 統合テストは`TestClient(app)`を使うため、lifespanが正しく動くかを検証しやすい。
- Phase 0後の品質ゲートではbackend full pytestが86件成功しており、今回の作業はこの回帰を維持する必要がある。

## 方針とその理由

### 採用方針

1. まずcontroller dependencyをmodule-level alias経由の`Depends(...)`へ移し、controller単体テストでusecaseを差し替えられる状態にする。
2. 次にInjector module/providerへ移行し、`AsyncEngine`と`async_sessionmaker`をcontainerで明示的に保持する。
3. `create_app()`にlifespanを追加し、shutdown時にcontainerから取得した`AsyncEngine.dispose()`を必ずawaitする。
4. repositoryのtransaction管理を`UnitOfWorkInterface`へ切り出し、repositoryは`session_scope()`を借りるだけにする。
5. `AuthenticatedSessionContext`と発行済みsession戻り値を`models`へ移し、controller/usecase/interfaceが具象usecase moduleへ依存しない形にする。
6. error envelopeは`create_app()`の例外handlerで集約し、controllerは機械可読な`code`を持つHTTPExceptionだけを投げる。
7. docs制御とlogging初期化は`create_app()`に集約し、productionでは`/docs`、`/redoc`、`/openapi.json`を公開しない。

### 採用理由

- `Depends`化を先に行うと、後続のerror envelopeやauth response変更をDBなしのcontroller unit testで検証できる。
- `AsyncEngine`をDI登録してからlifespanを実装すると、app shutdownで同じengineをdisposeしたことを直接検証できる。
- UoWをrepositoryから分離すると、権限管理で`RoleRepository`や`AuditRepository`を追加してもusecaseが同じtransactionを使える。
- error envelopeをhandlerに集約すると、FastAPI標準のvalidation error、手動HTTPException、未捕捉例外を同じレスポンス契約へ揃えられる。
- `AuthenticatedSessionContext`と`IssuedAuthSession`をDTO/dataclassとして独立させると、controllerがusecase具象moduleをimportするレイヤ違反を解消し、OAuthやrole追加時にも戻り値を拡張しやすい。

### レビュー反映済みの設計修正

Claude Codeレビューで、初版計画には実装すると壊れる推奨コードが2箇所あることが分かったため、次の方針へ修正する。

- `inject()`は呼ぶたびに別closureを返すため、`Depends(inject(...))`をcontrollerへ直接書かない。Task 2の時点でmodule-level dependency alias方式に決め切り、controllerとtestsは同じcallableを参照する。
- SQLAlchemy 2.0のautobeginにより、`session.add()`後の`session.in_transaction()`はtransaction外sessionでも`True`になる。repositoryのcommit/flush判定には使わず、UoWが保持するtransaction sessionとのidentity判定を`is_transaction_session(session)`で公開する。
- docs公開判定は`ENVIRONMENT != "production"`ではなくallowlist方式にする。`local`、`development`、`test`以外ではdocsを閉じ、安全側に倒す。
- error envelope導入はfrontend runtimeを壊さない見込みだが、frontend testsに旧`detail`形式のmockが残る。Phase 1ではfrontend実装を変更しないが、品質ゲートとしてfrontend tests/buildも実行し、旧契約mockの追随は未対応事項に明記する。
- Phase 1を3本の計画書へ分割する案は採用しない。今回の計画はレビュー項目間の依存順序を1つの文書で追跡するためのものとし、実装時はTask単位でcheckpointを残して手戻りを抑える。

## スコープ外

- 新規Alembic revisionは作らない。Phase 1はschemaを変更しない。
- `password_hash` nullable化、naming convention、OAuth identity tableは扱わない。
- Argon2のthread化、rate limiterの抽象化、信頼プロキシ、Secure cookie既定反転、CSRF middleware化はPhase 2で扱う。
- frontend配下は変更しない。
- sample APIのREST再設計、CRUD化、末尾スラッシュ変更はPhase 4以降で扱う。
- `ruff`、`mypy`、GitHub Actions、docker-compose開発体験改善はPhase 4で扱う。
- `git add`、`git commit`、`git push`は実行しない。
- frontend実装は変更しない。ただしerror envelope導入後もfrontend runtimeが壊れないこと、既存frontend tests/buildが通ることはTask 10で検証する。

## チェックポイント方針

この作業では`git add`と`git commit`を使わないため、Task単位で復旧用patchとuntracked snapshotを保存する。保存先は`.gitignore`済みの`.superpowers/`配下に置き、`/tmp`には置かない。

- 各Task開始前に`rtk git status --short`で既存変更を確認する。
- 各Task完了後に次を実行する。`<N>`と`<short-name>`はTask番号と短い説明へ置き換える。

```bash
rtk proxy mkdir -p .superpowers/checkpoints/phase1/task<N>-<short-name>
rtk git diff --binary -- > .superpowers/checkpoints/phase1/task<N>-<short-name>/tracked.patch
rtk git ls-files --others --exclude-standard > .superpowers/checkpoints/phase1/task<N>-<short-name>/untracked-files.txt
rtk proxy tar -czf .superpowers/checkpoints/phase1/task<N>-<short-name>/untracked-files.tgz -T .superpowers/checkpoints/phase1/task<N>-<short-name>/untracked-files.txt
```

- `untracked-files.txt`が空の場合、`tar`が空archiveを作れない環境では`untracked-files.tgz`が無くてもよい。その場合は`untracked-files.txt`が空であることをcheckpoint結果に記録する。
- patch保存後に`rtk git diff --check`を実行し、whitespace errorを早期に潰す。
- 復旧が必要な場合は、人間に確認してから保存済みpatchとuntracked archiveを使う。計画実行者の判断だけで`git reset`、`git checkout --`、`git clean`は実行しない。
- `git add -N`は使わない。内容はstageされないが、今回の禁止事項に含めると解釈が割れるため、untracked archiveで保存する。

## 変更予定ファイル

### 作成するファイル

- `backend/app/bootstrap/dependencies.py`
  - InjectorからFastAPI dependencyとして依存を取り出す`inject()` factoryを定義する。
- `backend/app/bootstrap/error_handlers.py`
  - HTTPException、RequestValidationError、未捕捉Exceptionのhandler登録とerror envelope変換を定義する。
- `backend/app/bootstrap/modules.py`
  - Injectorの`Module`を`CoreModule`、`DatabaseModule`、`AuthModule`、`SampleModule`へ分割する。`CoreModule`は`get_config()`、`get_auth_settings()`をproviderから呼び、環境変数変更後のapp作成テストを可能にする。
- `backend/app/interfaces/services/unit_of_work_interface.py`
  - transaction境界とsession取得を表す抽象を定義する。
- `backend/app/services/unit_of_work.py`
  - `AsyncSession`のContextVarとtransaction/session_scope実装を持つUoWを定義する。
- `backend/app/models/auth_context.py`
  - `AuthenticatedSessionContext`と`IssuedAuthSession`を定義する。
- `backend/app/models/error.py`
  - `ErrorDetail`、`ErrorResponse`、validation detail DTOを定義する。
- `backend/tests/unit/bootstrap/test_dependencies.py`
  - `inject()`がDI解決とdependency override可能性を壊さないことを検証する。
- `backend/tests/unit/bootstrap/test_create_app.py`
  - lifespan、docs制御、error handler登録、logging初期化を検証する。
- `backend/tests/unit/bootstrap/test_error_handlers.py`
  - error envelopeのHTTPException/validation/unknown exception変換を検証する。
- `backend/tests/integration/services/test_unit_of_work.py`
  - PostgreSQL上でUoWのtransaction nesting、rollback、session reuse、ContextVar reset、複数repository session共有を検証する。
- `backend/tests/unit/controllers/test_auth_controller_dependency.py`
  - auth controllerをusecase stubで差し替えてテストする。
- `backend/tests/unit/controllers/test_sample_controller_dependency.py`
  - sample controllerをusecase stubで差し替えてテストする。

### 変更するファイル

- `backend/app/bootstrap/container.py`
  - 手動生成中心の`configure()`からmodule/provider構成へ移す。
- `backend/app/bootstrap/create_app.py`
  - 未使用`environment`引数を削除し、lifespan、docs制御、error handler、logging初期化を追加する。
- `backend/app/config/__init__.py`
  - module import時に`Config()`を生成する`config = Config()`を廃止し、`get_config()` lazy factoryへ置き換える。
- `backend/app/bootstrap/route.py`
  - route登録の責務は維持する。`route.py`から`error_handlers.py`や`dependencies.py`をimportしない構成にして、controller import以外の循環importを作らない。
- `backend/app/controllers/auth_controller.py`
  - `request.app.state.injector.get(...)`をやめ、usecase/settings/contextを`Depends`で受け取る。戻り値dataclassとerror helperへ追随する。
- `backend/app/controllers/auth_dependencies.py`
  - `get_request_auth_settings`を削除し、module-level alias経由の`inject(AuthSettings)` / `inject(AuthUsecaseInterface)`へ寄せる。`require_current_session`も`AuthUsecaseInterface`をdependencyとして受け取る。
- `backend/app/controllers/sample_controller.py`
- `GetSampleIndexUsecaseInterface`をmodule-level alias経由の`Depends(...)`で受け取る。
- `backend/app/controllers/healthz_controller.py`
  - error envelope導入後もhealthz成功レスポンスは`Status`のまま維持する。
- `backend/app/interfaces/services/auth_repository_interface.py`
  - `transaction()`を削除し、repositoryの責務を永続化操作だけにする。
- `backend/app/interfaces/usecases/auth_usecase_interface.py`
  - `AuthenticatedSessionContext | None`と`IssuedAuthSession`を戻り値型として明記する。
- `backend/app/services/auth_repository.py`
  - `UnitOfWorkInterface`を注入し、`transaction()`とinstance属性`ContextVar`を削除する。
- `backend/app/usecases/auth_usecase.py`
  - `UnitOfWorkInterface`を注入し、transactionをUoW経由にする。`AuthenticatedSessionContext`定義を削除し、`IssuedAuthSession`を返す。
- `backend/app/usecases/get_sample_index_usecase.py`
  - Injector class bindingに合わせてconstructorへ`@inject`を付ける。
- `backend/app/libraries/database_engine.py`
  - 変更しない。`async_sessionmaker[AsyncSession]`型は`modules.py`内のprovider注釈で扱う。
- `backend/tests/unit/usecases/test_auth_usecase.py`
  - repository stubとUoW stubを分け、`IssuedAuthSession`戻り値を検証する。
- `backend/tests/integration/test_auth_controller.py`
  - error envelope変更に合わせて`response.json()["detail"]`期待を更新する。
- `backend/tests/integration/conftest.py`
  - `client` fixtureを`try/finally`へ変更し、test失敗時も`InMemoryLoginRateLimiter.reset()`が実行されるようにする。
- `backend/AGENTS.md`
  - Phase 1で確立したcontroller dependency、UoW、error envelope、docs制御の規約を追記する。
- `documents/plans/20260801-phase1-backend-foundation.md`
  - 実装中に進捗と検証結果を更新する。

### 変更しないファイル

- `backend/alembic/versions/*`
- `backend/app/models/user.py`
- `backend/app/models/auth_session.py`
- `backend/app/models/auth_audit_log.py`
- `frontend/*`
- `docker-compose.yaml`

## 具体的なタスク

### Task 1: baselineとPhase 1境界を固定する

**Files:**
- Inspect: `documents/reviews/20260801-review.md`
- Inspect: `documents/plans/20260801-phase0-review-fixes.md`
- Inspect: `backend/AGENTS.md`
- Inspect: `backend/app/bootstrap/`
- Inspect: `backend/app/controllers/`
- Inspect: `backend/app/services/`
- Inspect: `backend/app/usecases/`
- Inspect: `backend/tests/`

- [x] **Step 1.1: working treeがcleanであることを確認する**

Repository rootで実行する。

```bash
rtk git status --short
```

Expected:

- 出力が空、またはPhase 1開始前から存在するユーザー変更だけである。
- 既存変更がある場合は内容を読んでPhase 1と競合しないことを確認する。
- `git add`、`git commit`、`git reset`、`git checkout --`は実行しない。

- [x] **Step 1.2: Phase 1対象をレビュー本文で再確認する**

```bash
rtk grep -n "Phase 1|P1-5|P1-6|P1-7|P1-8|P1-9|P1-13|P2-8|P2-17|P2-18|P2-21|P3-2" documents/reviews/20260801-review.md
```

Expected:

- Phase 1の推奨順序が次の並びであることを確認する。
  `P1-6 -> P1-7 -> P1-5 -> P1-13 + P2-8 + P3-2 -> P1-8 + P1-9 + P2-21 -> P2-17 + P2-18`

- [x] **Step 1.3: 既存のbackend品質ゲートを先に実行する**

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest -q
```

Expected:

- `db-upgrade`がexit 0で、`app_test`にauth tablesが作成される。
- Phase 1着手前のbackend full pytestが成功する。
- integration testsのskipが0件である。
- PostgreSQLが起動しておらず失敗した場合は、`rtk docker compose up -d postgres`を実行してから再実行する。
- `UndefinedTableError`または`relation ... does not exist`が出た場合は、`ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade`を再実行してからpytestを再実行する。
- それでも失敗する場合はPhase 1実装に入らず、失敗内容を本計画の「実行結果」へ記録して原因を切り分ける。

- [x] **Step 1.4: frontendのerror body依存を確認する**

Repository rootで実行する。

```bash
rtk grep -n "detail|ApiError|status|401|403|body" frontend/src/routes frontend/src/lib frontend/src/**/*.test.tsx frontend/src/**/*.test.ts
```

Expected:

- runtime側の`frontend/src/routes/login.tsx`、`frontend/src/routes/app.tsx`、`frontend/src/lib/authApi.ts`は主に`ApiError.status`で分岐しており、error envelope変更だけでは壊れない。
- `frontend/src/lib/apiClient.test.ts`、`frontend/src/routes/app.test.tsx`、`frontend/src/routes/login.test.tsx`には旧`{"detail": ...}`形式のmockが残る。
- Phase 1ではfrontend実装を変更しないが、旧mock追随は未対応事項に記録し、Task 10でfrontend品質ゲートを実行する。

- [x] **Step 1.5: 変更禁止事項を再確認する**

Run: なし。

Expected:

- DB schemaを変えない。
- frontendを変えない。
- dependency追加をしない。
- sample APIのURLや成功レスポンス形式を変えない。
- worktree、staging、commit、pushを行わない。

### Task 2: 汎用DI dependencyを追加し、controllerをDepends化する

**Review Items:** `P1-6`

**Interfaces:**
- Produces: `app.bootstrap.dependencies.inject(interface: type[T]) -> Callable[[Request], T]`
- Produces: `app.controllers.auth_dependencies.get_auth_settings: Callable[[Request], AuthSettings]`
- Produces: `app.controllers.auth_dependencies.get_auth_usecase: Callable[[Request], AuthUsecaseInterface]`
- Produces: `app.controllers.sample_controller.get_sample_index_usecase: Callable[[Request], GetSampleIndexUsecaseInterface]`
- Consumes: `Request.app.state.injector.get(interface)` from `build_container()`

**Files:**
- Create: `backend/app/bootstrap/dependencies.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/app/controllers/sample_controller.py`
- Create: `backend/tests/unit/bootstrap/test_dependencies.py`
- Create: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Create: `backend/tests/unit/controllers/test_sample_controller_dependency.py`
- Modify: `backend/tests/unit/controllers/test_auth_dependencies.py`

- [x] **Step 2.1: `inject()`のRED testを書く**

`backend/tests/unit/bootstrap/test_dependencies.py`を作成し、次を検証する。

- `inject(AuthSettings)`が`request.app.state.injector.get(AuthSettings)`の戻り値を返す。
- `inject(AuthSettings)`を2回呼ぶと別callableになるため、controllerで直接`Depends(inject(...))`を書くと`app.dependency_overrides`のkeyを再現できないことを確認する。
- dependency functionの戻り値型が指定interfaceのinstanceとして扱える。

実行:

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_dependencies.py -q
```

Expected:

- `ModuleNotFoundError: No module named 'app.bootstrap.dependencies'`で失敗する。
- callable identityの確認は、Task 2全体でmodule-level alias方式を採用する理由を固定するためのtestである。

- [x] **Step 2.2: `backend/app/bootstrap/dependencies.py`を追加する**

実装方針:

```python
from collections.abc import Callable
from typing import TypeVar

from fastapi import Request

T = TypeVar("T")


def inject(interface: type[T]) -> Callable[[Request], T]:

    def _resolve(request: Request) -> T:
        return request.app.state.injector.get(interface)

    return _resolve
```

Expected:

- `inject()`が返すcallableはFastAPI dependencyとして使える。ただしcontrollerには直接`Depends(inject(SomeInterface))`を書かず、必ずmodule-level aliasを介する。
- `inject()`自体はmemoizeしない。override可能性は各controller/dependency moduleに置くmodule-level aliasで担保する。
- この段階では例外handler導入前なので、DI解決失敗の変換はTask 8で扱う。

- [x] **Step 2.3: auth dependency aliasを定義し、死にwrapperを削除する**

`backend/app/controllers/auth_dependencies.py`を変更する。

- module-level aliasを定義する。

```python
get_auth_settings = inject(AuthSettings)
get_auth_usecase = inject(AuthUsecaseInterface)
```

- `get_request_auth_settings()`は削除する。このrepository内の唯一の呼び出し元は`auth_controller.py`であり、Step 2.4で`get_auth_settings`へ置き換えるため、互換維持の相手がいない。
- `backend/tests/unit/controllers/test_auth_dependencies.py`の`test_get_request_auth_settings_returns_injector_instance`は削除し、代わりに`get_auth_settings` aliasを直接呼んで同じsettings instanceが返るtestへ置き換える。
- `require_current_session()`は次の形に変更する。

```python
async def require_current_session(
    request: Request,
    usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> AuthenticatedSessionContext:
    ...
```

- `require_csrf()`も`AuthUsecaseInterface`を`Depends(get_auth_usecase)`で受け取る。
- `AuthenticatedSessionContext`のimport元変更はTask 7で行うため、この時点では既存importを維持してよい。

- [x] **Step 2.4: auth controllerをusecase dependency注入へ変更する**

`backend/app/controllers/auth_controller.py`を変更する。

- `get_csrf()`、`register()`、`login()`、`logout()`は`request.app.state.injector.get(AuthUsecaseInterface)`を呼ばない。
- `auth_controller.py`は`auth_dependencies.get_auth_usecase`と`auth_dependencies.get_auth_settings`をimportし、各handler引数に次を追加する。

```python
usecase: AuthUsecaseInterface = Depends(get_auth_usecase)
```

- `AuthSettings`は`Depends(get_auth_settings)`で受け取る。`Depends(get_request_auth_settings)`は使わない。
- `Request`はcookie、URL scheme、client IP、user-agent取得に必要なため残す。

- [x] **Step 2.5: sample controllerをusecase dependency注入へ変更する**

`backend/app/controllers/sample_controller.py`を変更する。

- module-level aliasを定義する。

```python
get_sample_index_usecase = inject(GetSampleIndexUsecaseInterface)
```

- route handlerはそのaliasだけを使う。

```python
@router.get("/")
async def sample_index(
    usecase: GetSampleIndexUsecaseInterface = Depends(
        get_sample_index_usecase
    ),
) -> Status:
    return usecase.handle("Hello, World!")
```

Expected:

- `Request` importは不要になる。
- API pathと成功レスポンスは変えない。

- [x] **Step 2.6: controller dependency overrideのGREEN testを書く**

`backend/tests/unit/controllers/test_auth_controller_dependency.py`にDB不要のFastAPI appを作り、実際にrouterが使うdependency callableをoverrideできることを検証する。

- controllerは`Depends(auth_dependencies.get_auth_usecase)`と`Depends(auth_dependencies.get_auth_settings)`を使う。
- testは`app.dependency_overrides[auth_dependencies.get_auth_usecase] = lambda: StubUsecase(...)`で差し替える。
- settingsも必要なtestでは`app.dependency_overrides[auth_dependencies.get_auth_settings] = lambda: AuthSettings(...)`で差し替える。

検証内容:

- `GET /auth/csrf`でstubの`issue_csrf_token()`が呼ばれ、cookieが設定される。
- `POST /auth/login`でstubの`login()`が返したuser情報が返る。
- `POST /auth/logout`でstubの`logout()`が呼ばれ、204になる。
- `POST /auth/login`と`POST /auth/logout`はroute-level dependencyの`require_csrf`を通るため、test requestには一致する`csrf_token` cookieと`X-CSRF-Token` headerを必ず付ける。DB-bound CSRF検証まで進ませるtestでは、stub usecaseの`validate_session_csrf()`が`True`を返すようにする。

- [x] **Step 2.7: sample controller dependency overrideのGREEN testを書く**

`backend/tests/unit/controllers/test_sample_controller_dependency.py`を作成する。

検証内容:

- `sample_controller.get_sample_index_usecase`をoverrideして`Status(success=True, message="stubbed")`を返せる。
- `GET /sample/`のresponse bodyがstub値になる。
- `request.app.state.injector`が存在しないappでもoverrideにより成功する。

- [x] **Step 2.8: targeted testsを実行する**

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_dependencies.py tests/unit/controllers/test_auth_dependencies.py tests/unit/controllers/test_auth_controller_dependency.py tests/unit/controllers/test_sample_controller_dependency.py -q
```

Expected:

- 追加・変更したunit testsがすべて成功する。
- 既存のCSRF testsが引き続き成功する。

### Task 3: Injector module/provider構成へ移行する

**Review Items:** `P1-7`

**Interfaces:**
- Consumes: `get_auth_settings() -> AuthSettings` from `app.config.auth`
- Produces: `get_config() -> Config` from `app.config`
- Produces: `CoreModule`, `DatabaseModule`, `AuthModule`, `SampleModule` in `app.bootstrap.modules`
- Produces: DI bindings for `Config`, `Logger`, `AuthSettings`, `AsyncEngine`, `async_sessionmaker[AsyncSession]`, `AuthUsecaseInterface`, `AuthRepositoryInterface`, `GetSampleIndexUsecaseInterface`

**Files:**
- Create: `backend/app/bootstrap/modules.py`
- Modify: `backend/app/config/__init__.py`
- Modify: `backend/app/bootstrap/container.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/usecases/get_sample_index_usecase.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/tests/unit/bootstrap/test_container.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`

- [x] **Step 3.1: container構成のRED testを書く**

`backend/tests/unit/bootstrap/test_container.py`へ次を追加する。

- `injector.get(AuthUsecaseInterface)`を2回呼ぶと同一instanceである。
- `injector.get(GetSampleIndexUsecaseInterface)`を2回呼ぶと同一instanceである。
- `injector.get(AuthRepositoryInterface)`を2回呼ぶと同一instanceである。
- `injector.get(AuthSettings)`は起動時に作られた同一instanceである。
- `injector.get(Config)`は`modules.get_config`をmonkeypatchした値を返す。
- `injector.get(AsyncEngine)`が取得できる。
- 既存の`test_build_container_binds_created_auth_settings_instance`は、`container_module.get_auth_settings`ではなく、Task 3で作成する`modules.get_auth_settings`をmonkeypatchする形へ更新する。`Config`も同じく`modules.get_config`をpatchする。

実行:

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_container.py -q
```

Expected:

- `app.bootstrap.modules`が未作成のため、初回実行は`ModuleNotFoundError: No module named 'app.bootstrap.modules'`で失敗する。
- Step 3.4完了後に再実行した場合、現行containerは`AuthUsecaseInterface`、`GetSampleIndexUsecaseInterface`、`AuthRepositoryInterface`をすでにinstance providerで束縛しているため、identity assertion自体は通る。
- Step 3.4完了後のRED主因は`AsyncEngine` bindingがないことである。
- 既存testのmonkeypatch対象を更新しないままTask 3を実装すると、予期しない失敗になるため、Step 3.1の時点でtest側のpatch先変更も明記しておく。

- [x] **Step 3.2: `Config`をlazy factoryへ移す**

`backend/app/config/__init__.py`を更新し、Task 3で作成する`CoreModule`が消費する`get_config()`を先に用意する。

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"


def get_config() -> Config:
    return Config()
```

Expected:

- module import時に`Config()`を生成する`config = Config()`は削除する。
- `load_dotenv()`と`os.getenv()`の二重読みをやめる。
- `ENVIRONMENT`の既定値はこのTaskでは現行挙動に近い`development`のまま維持する。docs非公開を安全側の既定にする変更はTask 9で行う。
- Task 3.4の`backend/app/bootstrap/modules.py`は`from app.config import Config, get_config`できる。

- [x] **Step 3.3: 実装クラスconstructorへ`@inject`を付ける**

対象:

- `AuthUsecase.__init__`
- `GetSampleIndexUsecase.__init__`

実装方針:

```python
from injector import inject


class AuthUsecase(AuthUsecaseInterface):

    @inject
    def __init__(
        self,
        auth_repository: AuthRepositoryInterface,
        auth_rate_limiter: InMemoryLoginRateLimiter,
        auth_settings: AuthSettings,
        logger: Logger,
    ) -> None:
        ...
```

Expected:

- constructor引数の型はinterfaceまたは具体的に必要な型を明示する。
- `Any`は使わない。
- `AuthRepository.__init__`はTask 5で`UnitOfWorkInterface`注入へ変えるため、このTaskでは`@inject`化しない。Task 3ではproviderで既存constructorへ`session_factory`を渡す暫定構成にする。

- [x] **Step 3.4: `backend/app/bootstrap/modules.py`を作成する**

module分割:

- `CoreModule`
  - `Config`
  - `Logger`
  - `AuthSettings`
- `DatabaseModule`
  - `AsyncEngine`
  - `async_sessionmaker[AsyncSession]`
- `AuthModule`
  - `AuthRepositoryInterface -> AuthRepository`
  - `InMemoryLoginRateLimiter`
  - `AuthUsecaseInterface -> AuthUsecase`
- `SampleModule`
  - `GetSampleIndexUsecaseInterface -> GetSampleIndexUsecase`

実装上の注意:

- `CoreModule`は`@provider`で`get_config()`と`get_auth_settings()`を呼ぶ。`Config`はmodule import時に固定せず、`create_app()` / `build_container()`呼び出し時点の環境変数を読む。
- `AsyncEngine`とsession factoryは同じ`build_engine_and_session_factory()`呼び出しから生成する。
- providerがengine/session factoryを別々に生成して2つのengineを作らないよう、`DatabaseResources` dataclassをmodule内で保持するか、`DatabaseModule.__init__()`で一度だけ生成する。
- `AuthRepositoryInterface`はTask 5までの暫定providerで`AuthRepository(session_factory=session_factory)`を返す。Task 5で`UnitOfWorkInterface`導入後にclass bindingへ切り替える。
- `InMemoryLoginRateLimiter`は`AuthSettings`からwindow/attempt設定を読んでproviderで生成する。

実装例:

```python
from dataclasses import dataclass
from logging import Logger, getLogger

from injector import Binder, Module, provider, singleton
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Config, get_config
from app.config.auth import AuthSettings, get_auth_settings
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.get_sample_index_usecase_interface import (
    GetSampleIndexUsecaseInterface,
)
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter
from app.libraries.database_engine import build_engine_and_session_factory
from app.services.auth_repository import AuthRepository
from app.usecases.auth_usecase import AuthUsecase
from app.usecases.get_sample_index_usecase import GetSampleIndexUsecase


@dataclass(slots=True)
class DatabaseResources:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


class CoreModule(Module):

    @singleton
    @provider
    def provide_config(self) -> Config:
        return get_config()

    @singleton
    @provider
    def provide_auth_settings(self) -> AuthSettings:
        return get_auth_settings()

    @singleton
    @provider
    def provide_logger(self) -> Logger:
        return getLogger("app")


class DatabaseModule(Module):

    def __init__(self) -> None:
        engine, session_factory = build_engine_and_session_factory()
        self._resources = DatabaseResources(engine, session_factory)

    @singleton
    @provider
    def provide_async_engine(self) -> AsyncEngine:
        return self._resources.engine

    @singleton
    @provider
    def provide_session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._resources.session_factory


class AuthModule(Module):

    def configure(self, binder: Binder) -> None:
        binder.bind(AuthUsecaseInterface, to=AuthUsecase, scope=singleton)

    @singleton
    @provider
    def provide_auth_repository(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> AuthRepositoryInterface:
        return AuthRepository(session_factory=session_factory)

    @singleton
    @provider
    def provide_rate_limiter(
        self,
        settings: AuthSettings,
    ) -> InMemoryLoginRateLimiter:
        return InMemoryLoginRateLimiter(
            window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
            max_attempts_per_email_ip=settings.AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP,
            max_attempts_per_ip=settings.AUTH_RATE_LIMIT_ATTEMPTS_PER_IP,
        )


class SampleModule(Module):

    def configure(self, binder: Binder) -> None:
        binder.bind(
            GetSampleIndexUsecaseInterface,
            to=GetSampleIndexUsecase,
            scope=singleton,
        )
```

- [x] **Step 3.5: `container.py`をmodule構成へ置き換える**

`build_container()`は次の責務だけにする。

```python
def build_container() -> Injector:
    return Injector(modules=[
        CoreModule(),
        DatabaseModule(),
        AuthModule(),
        SampleModule(),
    ])
```

Expected:

- `configure()`関数は削除する。
- 手動で`AuthUsecase(...)`や`AuthRepository(...)`をnewしない。
- import循環が起きないよう、controller moduleはcontainer/moduleからimportしない。

- [x] **Step 3.6: targeted testsを実行する**

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_container.py tests/unit/usecases/test_auth_usecase.py -q
```

Expected:

- container testsが成功する。
- usecase testsが既存stub構成のまま成功する。もしconstructor引数が変わる場合は、test側stubも実装後のpublic contractへ合わせる。

### Task 4: `create_app()`にlifespanとengine disposeを追加する

**Review Items:** `P1-5`, `P1-9`

**Interfaces:**
- Consumes: `build_container() -> Injector`
- Consumes: `injector.get(AsyncEngine).dispose() -> Awaitable[None]`
- Produces: `create_app() -> FastAPI` with lifespan-enabled shutdown

**Files:**
- Modify: `backend/app/bootstrap/create_app.py`
- Create: `backend/tests/unit/bootstrap/test_create_app.py`
- Modify: `backend/tests/integration/conftest.py`
- Modify: `backend/tests/integration/test_auth_controller.py`

- [x] **Step 4.1: lifespan disposeのRED testを書く**

`backend/tests/unit/bootstrap/test_create_app.py`を作成する。

検証内容:

- `create_app()`が返したappを`TestClient`でopen/closeすると、DI containerに登録された`AsyncEngine.dispose()`が1回awaitされる。
- `build_container()`をmonkeypatchして、`get(AsyncEngine)`がdispose可能なstub engineを返すinjectorに差し替える。

Expected:

- 現状はlifespanがないため、dispose呼び出しが0回で失敗する。

RED確認:

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_create_app.py::test_lifespan_disposes_async_engine_on_shutdown -q
```

Expected RED:

- `AssertionError`でdispose呼び出しが0回であることを確認する。

- [x] **Step 4.2: `create_app()`へlifespanを追加する**

実装方針:

```python
from contextlib import asynccontextmanager
from logging import getLogger

from sqlalchemy.ext.asyncio import AsyncEngine

logger = getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_error: BaseException | None = None
    try:
        yield
    except BaseException as error:
        app_error = error
        raise
    finally:
        try:
            await app.state.injector.get(AsyncEngine).dispose()
        except Exception:
            logger.exception("Failed to dispose database engine")
            if app_error is None:
                raise
```

Expected:

- `FastAPI(..., lifespan=lifespan)`で登録する。
- 通常shutdownでdisposeに失敗した場合はshutdown失敗として表面化させる。
- app本体の例外でlifespanを抜ける途中にdisposeも失敗した場合は、dispose失敗をlogに残し、元のapp例外をdispose例外で置き換えない。

- [x] **Step 4.3: integration fixtureのrate limiter reset位置を調整する**

`backend/tests/integration/conftest.py`の`client` fixtureは、test失敗時にもrate limiter stateを次のtestへ漏らさないようにする。rate limiter resetはengine disposeとは無関係だが、fixture cleanupとして`try/finally`へ直す価値がある。

採用方針:

```python
with TestClient(app) as test_client:
    try:
        yield test_client
    finally:
        app.state.injector.get(InMemoryLoginRateLimiter).reset()
```

- [x] **Step 4.4: targeted testsを実行する**

```bash
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/unit/bootstrap/test_create_app.py tests/integration/test_auth_controller.py::test_register_then_me_returns_current_user -q
```

Expected:

- unit testでdisposeが1回呼ばれる。
- integration smoke testが成功する。
- integration smoke testのskipが0件である。

### Task 5: Unit of Workを導入し、repositoryからtransaction管理を分離する

**Review Items:** `P1-13`, `P3-2`

**Interfaces:**
- Produces: `UnitOfWorkInterface.transaction() -> AbstractAsyncContextManager[None]`
- Produces: `UnitOfWorkInterface.session_scope() -> AbstractAsyncContextManager[AsyncSession]`
- Produces: `UnitOfWorkInterface.is_transaction_session(session: AsyncSession) -> bool`
- Consumes: `async_sessionmaker[AsyncSession]` binding from `DatabaseModule`
- Consumes: `AuthRepositoryInterface` methods from `AuthUsecase`

**Files:**
- Create: `backend/app/interfaces/services/unit_of_work_interface.py`
- Create: `backend/app/services/unit_of_work.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/app/interfaces/services/auth_repository_interface.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/bootstrap/modules.py`
- Create: `backend/tests/integration/services/test_unit_of_work.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`

- [x] **Step 5.1: UoW contractのRED testを書く**

`backend/tests/integration/services/test_unit_of_work.py`を作成する。UoWは`async with session.begin():`で実DB transactionを張るため、SQLite unit testではなくPostgreSQL integration testとして扱う。これは`backend/AGENTS.md`の「auth integration testはPostgreSQLを使う」に合わせる判断であり、Phase 4で削除候補の`aiosqlite`へ新しい依存を載せないためである。

検証内容:

- file先頭に`pytestmark = pytest.mark.integration`を置く。
- 既存`tests/integration/conftest.py`の`async_engine` fixtureから`async_sessionmaker`を作り、`UnitOfWork(session_factory=session_factory)`を生成する。
- `async with unit_of_work.transaction():`の内側で`session_scope()`を2回呼ぶと同じ`AsyncSession` instanceが返る。
- 同じ`UnitOfWorkInterface`を共有する`AuthRepository`とdummy `SecondRepository`を用意し、1つのtransaction内で両repositoryが同じ`AsyncSession` instanceを使う。
- transaction外で`session_scope()`を呼ぶと、新しいsessionが取得され、context exitでcloseされる。
- nested transactionでは内側が新しいDB transactionを開始せず、外側のsessionを共有する。
- exceptionが発生した場合はrollbackされ、ContextVarがresetされる。
- transaction終了後に別transactionを開始すると、前回sessionは再利用されない。
- `is_transaction_session(session)`はtransaction内のmanaged sessionだけで`True`を返し、transaction外のsessionでは`session.add()`後でも`False`を返す。

Expected:

- `ModuleNotFoundError`で失敗する。
- `TEST_DATABASE_URL`未設定時はintegration helperによりskipされる。Task 5.8とTask 10では`TEST_DATABASE_URL`を明示し、skip 0件を確認する。

RED確認:

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration/services/test_unit_of_work.py -q
```

Expected RED:

- `ModuleNotFoundError: No module named 'app.services.unit_of_work'`または`No module named 'app.interfaces.services.unit_of_work_interface'`で失敗する。
- skipは0件である。

- [x] **Step 5.2: UoW interfaceを定義する**

`backend/app/interfaces/services/unit_of_work_interface.py`を作成する。

```python
from abc import ABCMeta, abstractmethod
from contextlib import AbstractAsyncContextManager

from sqlmodel.ext.asyncio.session import AsyncSession


class UnitOfWorkInterface(metaclass=ABCMeta):

    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[None]:
        raise NotImplementedError

    @abstractmethod
    def session_scope(self) -> AbstractAsyncContextManager[AsyncSession]:
        raise NotImplementedError

    @abstractmethod
    def is_transaction_session(self, session: AsyncSession) -> bool:
        raise NotImplementedError
```

WHY: repositoryは`session.exec(statement)`を使うため、contract上もSQLModel版`AsyncSession`を返す。SQLAlchemy版`AsyncSession`には`exec()`が無く、Phase 4でmypyを入れた時にrepository層の型が破綻する。

- [x] **Step 5.3: UoW implementationを定義する**

`backend/app/services/unit_of_work.py`を作成する。

実装方針:

- module-levelに`ContextVar[tuple[object, AsyncSession] | None]`を1つ置く。
- constructorで`async_sessionmaker[AsyncSession]`を受け取る。
- constructorでUoW instanceごとのowner tokenを作る。
- `transaction()`は同じUoW instanceの既存transactionがあればyieldだけ行う。
- `transaction()`は別UoW instanceのtransactionが同一async contextに見えている場合、RuntimeErrorでfail fastする。
- `transaction()`は新規sessionを作った場合のみ`async with session.begin():`を張る。
- `session_scope()`は同じUoW instanceの既存transaction sessionがあればそれをyieldする。
- `session_scope()`も別UoW instanceのtransactionが同一async contextに見えている場合、RuntimeErrorでfail fastする。repositoryは`transaction()`ではなく`session_scope()`を直接使うため、ここも同じ不変条件を守る。
- transaction外の`session_scope()`はsessionを作ってyieldし、commitはしない。commit/flushの判断はrepositoryの`_persist()`が担う。
- `is_transaction_session(session)`はowner tokenとsession identityの両方を比較して判定する。`session.in_transaction()`はSQLAlchemy 2.0のautobeginでtransaction外sessionでも`True`になるため使わない。

WHY: `ContextVar`は同一async context内で共有されるため、sessionだけを保存するとUoW-Aのtransaction中にUoW-Bを使った場合、UoW-BがUoW-Aのsessionを自分のtransaction sessionと誤認する。owner tokenを併せて保存し、同じUoW instanceのtransactionだけを再利用する。ただし`ContextVar`の値は単一スロットなので、UoW-Bがtransactionを開くとUoW-Aのentryを上書きし、UoW-A側の`session_scope()`がtransactionを見失う。Phase 1ではUoWはsingleton運用を前提にし、別instanceのtransaction nestはfail fastで禁止する。

実装例:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from injector import inject
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface

_transaction_session: ContextVar[tuple[object, AsyncSession] | None] = (
    ContextVar(
        "unit_of_work_transaction_session",
        default=None,
    )
)


class UnitOfWork(UnitOfWorkInterface):
    """Request-scoped transaction coordinator.

    Nested ``transaction()`` calls join the current transaction; they do not
    create savepoints. Do not run parallel operations that share one transaction
    session with ``gather()`` or ``create_task()``.
    """

    @inject
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory
        self._context_owner = object()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        current = _transaction_session.get()
        if current is not None and current[0] is self._context_owner:
            yield
            return
        if current is not None:
            raise RuntimeError("Cannot open a different UnitOfWork transaction "
                               "inside an active transaction")

        async with self._session_factory() as session:
            token = _transaction_session.set((self._context_owner, session))
            try:
                async with session.begin():
                    yield
            finally:
                _transaction_session.reset(token)

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        current = _transaction_session.get()
        if current is not None and current[0] is self._context_owner:
            yield current[1]
            return
        if current is not None:
            raise RuntimeError("Cannot open a different UnitOfWork transaction "
                               "inside an active transaction")

        async with self._session_factory() as session:
            yield session

    def is_transaction_session(self, session: AsyncSession) -> bool:
        current = _transaction_session.get()
        return (
            current is not None
            and current[0] is self._context_owner
            and session is current[1]
        )
```

- [x] **Step 5.4: `AuthRepository`をUoW利用へ変更する**

変更内容:

- constructor引数を`unit_of_work: UnitOfWorkInterface`へ変更する。
- `self._transaction_session`と`transaction()`を削除する。
- `_session_scope()`を削除し、各メソッドで`async with self._unit_of_work.session_scope() as session:`を使う。
- `_persist()`はUoWの`is_transaction_session(session)`でcommit/flushを分岐する。
- `create_user()`の`IntegrityError` handlerに残る`session is not self._transaction_session.get()`判定も、`not self._unit_of_work.is_transaction_session(session)`へ置き換える。

推奨する最小実装:

```python
async def _persist(self, session: AsyncSession) -> None:
    if self._unit_of_work.is_transaction_session(session):
        await session.flush()
    else:
        await session.commit()
```

`create_user()`のrollback分岐:

```python
except IntegrityError as error:
    if not self._unit_of_work.is_transaction_session(session):
        await session.rollback()
    raise EmailAlreadyRegisteredError from error
```

注意:

- `session.in_transaction()`は使わない。`session.add()`がautobeginを起こすため、transaction外書き込みがflushのみになり、context close時にrollbackされる。
- `is_transaction_session()`はsession identityだけでなくUoW owner tokenも見る。複数のUoW instanceが同じasync contextで使われても、他instanceのtransaction sessionを誤って再利用しない。
- 別UoW instanceのtransaction / session_scopeを同じasync contextのtransaction内で開くことはできない。`ContextVar`単一スロット上書きによるtransaction境界脱出を防ぐため、`RuntimeError`でfail fastする。

- [x] **Step 5.5: `AuthRepositoryInterface`から`transaction()`を削除する**

Expected:

- repository interfaceは永続化操作だけを持つ。
- transaction境界は`UnitOfWorkInterface`だけが持つ。

- [x] **Step 5.6: `AuthUsecase`へUoWを注入する**

変更内容:

- constructorに`unit_of_work: UnitOfWorkInterface`を追加する。
- `async with self._auth_repository.transaction():`を`async with self._unit_of_work.transaction():`へ変更する。
- `register()`、`login()`、`logout()`のtransaction境界をUoWへ移す。

- [x] **Step 5.7: container moduleへUoW bindingを追加する**

`backend/app/bootstrap/modules.py`で次をbindする。

- `UnitOfWorkInterface -> UnitOfWork`
- `AuthRepositoryInterface -> AuthRepository`

Expected:

- `AuthRepository`はsession factoryではなくUoWを受け取る。
- `UnitOfWork`はsession factoryを受け取る。

- [x] **Step 5.8: targeted testsを実行する**

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration/services/test_unit_of_work.py tests/unit/usecases/test_auth_usecase.py tests/unit/bootstrap/test_container.py -q
```

Expected:

- `db-upgrade`がexit 0である。
- UoWのsession reuse/nesting/reset testsが成功する。
- UoW integration testのskipが0件である。
- usecase testsがUoW stub経由で成功する。
- containerがUoWを解決できる。

### Task 6: `authenticate_session`を1 request = 1 sessionへ寄せる

**Review Items:** `P2-8`

**Interfaces:**
- Consumes: `UnitOfWorkInterface.transaction()`
- Consumes: `AuthRepositoryInterface.find_active_session_by_token_hash(token_hash: str) -> AuthSession | None`
- Consumes: `AuthRepositoryInterface.find_user_by_id(user_id: UUID) -> User | None`
- Produces: `AuthUsecase.authenticate_session(...) -> AuthenticatedSessionContext | None`

**Files:**
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/integration/test_auth_controller.py`

- [x] **Step 6.1: `authenticate_session`がUoW transactionを使うRED testを書く**

`backend/tests/unit/usecases/test_auth_usecase.py`へUoW stubを追加し、次を検証する。

- `authenticate_session()`に有効session tokenがある場合、session lookup、user lookup、touch sessionが`UoWStub.in_transaction == True`の間に記録される。
- session tokenが無い場合はtransactionを開始しない。
- active sessionが無い場合でも、known rejected sessionのaudit確認はtransaction内で行う。

Expected:

- 現状は`authenticate_session()`がUoW transactionを使わないため失敗する。

RED確認:

```bash
cd backend
rtk uv run pytest tests/unit/usecases/test_auth_usecase.py::test_authenticate_session_uses_one_unit_of_work_transaction -q
```

Expected RED:

- repository stubの記録に`("find_active_session", False)`のようにtransaction外実行が残り、assertionが失敗する。
- `unit_of_work.transaction()`の呼び出し回数そのものではなく、repository操作がtransaction context内で実行されたかを検証する。

- [x] **Step 6.2: `authenticate_session()`をUoW transactionで囲む**

実装方針:

```python
async with self._unit_of_work.transaction():
    auth_session = await self._auth_repository.find_active_session_by_token_hash(...)
    ...
    user = await self._auth_repository.find_user_by_id(...)
    ...
    refreshed_session = await self._auth_repository.touch_session(...)
```

注意:

- `session_token`が無い場合はDBを触らず`None`を返す。
- `_audit_known_rejected_session()`は呼び出し元transactionがあれば同じsessionを使う。
- inactive userで`revoke_session()`する場合も同じtransaction内で行う。
- この変更により、`GET /api/auth/me`を含む認証付き読み取りリクエストでも、`touch_session()`のUPDATEを含むwrite transactionを張る。現行実装も認証成功時にUPDATEを実行しているためDB write自体は増えないが、transaction保持時間は伸びる。`AUTH_SESSION_TOUCH_INTERVAL_SECONDS`でtouch頻度を下げる最適化は`P2-15`としてPhase 2へ残す。

- [x] **Step 6.3: integrationでconnection/session過剰利用の回帰を確認する**

既存の`GET /api/auth/me`系integration testsを実行する。

```bash
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration/test_auth_controller.py::test_register_then_me_returns_current_user tests/integration/test_auth_controller.py::test_random_session_tokens_do_not_create_audit_rows -q
```

Expected:

- 現行挙動は維持される。
- known random tokenではaudit rowを作らない。
- integration testsのskipが0件である。

### Task 7: auth contextとsession発行戻り値をDTO/dataclassへ移す

**Review Items:** `P2-17`, `P2-18`

**Interfaces:**
- Produces: `AuthenticatedSessionContext(user: User, session: AuthSession)`
- Produces: `IssuedAuthSession(user: User, session: AuthSession, session_token: str, csrf_token: str)`
- Produces: `AuthUsecaseInterface.register(...) -> IssuedAuthSession`
- Produces: `AuthUsecaseInterface.login(...) -> IssuedAuthSession`
- Produces: `AuthUsecaseInterface.authenticate_session(...) -> AuthenticatedSessionContext | None`

**Files:**
- Create: `backend/app/models/auth_context.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/interfaces/usecases/auth_usecase_interface.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Modify: `backend/tests/integration/test_auth_controller.py`

- [x] **Step 7.1: interface戻り値型のRED/static確認を行う**

Run:

```bash
cd backend
rtk grep -n "AuthenticatedSessionContext|return user, session, session_token, csrf_token|def register|def login|authenticate_session" app tests
```

Expected:

- `AuthenticatedSessionContext`が`app/usecases/auth_usecase.py`に定義されている。
- `auth_controller.py`と`auth_dependencies.py`が具象usecase moduleからimportしている。
- `register()`/`login()`の戻り値型がinterfaceで明示されていない。

- [x] **Step 7.2: `auth_context.py`を作成する**

`backend/app/models/auth_context.py`:

```python
from dataclasses import dataclass

from app.models.auth_session import AuthSession
from app.models.user import User


@dataclass(slots=True)
class AuthenticatedSessionContext:
    user: User
    session: AuthSession


@dataclass(slots=True)
class IssuedAuthSession:
    user: User
    session: AuthSession
    session_token: str
    csrf_token: str
```

- [x] **Step 7.3: `AuthUsecaseInterface`へ戻り値型を明記する**

変更内容:

- `register(...) -> IssuedAuthSession`
- `login(...) -> IssuedAuthSession`
- `authenticate_session(...) -> AuthenticatedSessionContext | None`

Expected:

- interfaceから具象usecaseへのimportは発生しない。
- `app.models.auth_context`だけをimportする。

- [x] **Step 7.4: `AuthUsecase`の戻り値を`IssuedAuthSession`へ変更する**

変更内容:

- `AuthenticatedSessionContext` dataclass定義を`auth_usecase.py`から削除する。
- `register()`と`login()`はtupleではなく`IssuedAuthSession(...)`を返す。
- `_replace_session()`は内部helperとして`tuple[AuthSession, str, str]`を返し続けてよい。

- [x] **Step 7.5: controllerのtuple destructuringを置き換える**

`auth_controller.py`:

```python
issued_session = await usecase.login(...)
set_session_cookie(response, issued_session.session_token, ...)
set_csrf_cookie(response, issued_session.csrf_token, ...)
return AuthUserResponse(
    id=issued_session.user.id,
    email=issued_session.user.email,
)
```

同じ変更を`register()`にも適用する。

- [x] **Step 7.6: import元を全て`app.models.auth_context`へ変更する**

実行:

```bash
cd backend
rtk grep -n "app.usecases.auth_usecase import AuthenticatedSessionContext|AuthenticatedSessionContext" app tests
```

Expected:

- `AuthenticatedSessionContext`のimport元は`app.models.auth_context`だけになる。

- [x] **Step 7.7: targeted testsを実行する**

```bash
cd backend
rtk uv run pytest tests/unit/usecases/test_auth_usecase.py tests/unit/controllers/test_auth_controller_dependency.py tests/unit/controllers/test_auth_dependencies.py -q
```

Expected:

- usecase testsは`IssuedAuthSession`のfieldで検証する。
- controller/dependency testsが成功する。

### Task 8: error envelopeを導入し、HTTP/validation/unknown errorを正規化する

**Review Items:** `P1-8`, `P1-9`

**Interfaces:**
- Produces: `ErrorFieldDetail(loc: list[str | int], message: str, type: str)`
- Produces: `ErrorDetail(code: str, message: str, details: list[...])`
- Produces: `ErrorResponse(error: ErrorDetail)`
- Produces: `api_error(status_code: int, code: str, message: str, headers: dict[str, str] | None = None) -> HTTPException`
- Produces: `register_error_handlers(app: FastAPI) -> None`
- Consumes: `auth_dependencies.get_auth_usecase` and `get_auth_settings` from Task 2

**Files:**
- Create: `backend/app/models/error.py`
- Create: `backend/app/bootstrap/error_handlers.py`
- Modify: `backend/app/bootstrap/create_app.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/app/controllers/sample_controller.py`
- Create: `backend/tests/unit/bootstrap/test_error_handlers.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/tests/unit/controllers/test_sample_controller.py`

- [x] **Step 8.1: error response contractをRED testで固定する**

`backend/tests/unit/bootstrap/test_error_handlers.py`を作成し、TestClientで次を検証する。

- `raise HTTPException(status_code=401, detail="Unauthorized")`は`{"error": {"code": "UNAUTHORIZED", "message": "Unauthorized", "details": []}}`を返す。
- `raise HTTPException(status_code=409, detail={"code": "EMAIL_ALREADY_REGISTERED", "message": "Email already registered"})`はcode/messageを保持する。
- request validation errorはstatus 422、code `VALIDATION_ERROR`、detailsにfield pathとmessageを含む。
- 未捕捉`RuntimeError("boom")`はstatus 500、code `INTERNAL_SERVER_ERROR`、message `Internal server error`を返し、`boom`をresponse bodyに出さない。
- 未捕捉例外の検証では`TestClient(app, raise_server_exceptions=False)`を必ず使う。既定値のままだと500 responseではなく例外がtest processへ再送出される。

Expected:

- 現状はFastAPI標準の`detail`形式なので失敗する。

RED確認:

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_error_handlers.py -q
```

Expected RED:

- `ModuleNotFoundError: No module named 'app.bootstrap.error_handlers'`、またはresponse bodyが`detail`形式であることによるassertion failureで失敗する。

- [x] **Step 8.2: `models/error.py`を追加する**

推奨DTO:

```python
from typing import Any

from pydantic import BaseModel, Field


class ErrorFieldDetail(BaseModel):
    loc: list[str | int]
    message: str
    type: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[ErrorFieldDetail | dict[str, Any]] = Field(
        default_factory=list
    )


class ErrorResponse(BaseModel):
    error: ErrorDetail
```

注意:

- `SQLModel`は使わない。DB tableではないresponse DTOであり、`P2-9`でmodels directoryの整理対象になる可能性があるため、ORM基底への依存を増やさない。
- `Any`を使う場合はvalidation errorの外部schemaを保持するために限定する。

- [x] **Step 8.3: `error_handlers.py`を追加する**

責務:

- `register_error_handlers(app: FastAPI) -> None`
- `api_error(status_code: int, code: str, message: str, headers: dict[str, str] | None = None) -> HTTPException`
- `http_exception_handler`
- `validation_exception_handler`
- `unhandled_exception_handler`

status codeからの既定code:

- 400: `BAD_REQUEST`
- 401: `UNAUTHORIZED`
- 403: `FORBIDDEN`
- 404: `NOT_FOUND`
- 409: `CONFLICT`
- 422: `VALIDATION_ERROR`
- 429: `RATE_LIMITED`
- その他4xx: `HTTP_ERROR`
- 5xx: `INTERNAL_SERVER_ERROR`

実装例:

```python
from typing import Any

import logging

from fastapi import FastAPI
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request

from app.models.error import ErrorDetail, ErrorFieldDetail, ErrorResponse

logger = logging.getLogger(__name__)

_DEFAULT_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def api_error(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> FastAPIHTTPException:
    return FastAPIHTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    code, message, details = _error_parts(exc.status_code, exc.detail)
    return _json_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details = [
        ErrorFieldDetail(
            loc=list(error.get("loc", [])),
            message=str(error.get("msg", "Invalid input")),
            type=str(error.get("type", "value_error")),
        )
        for error in exc.errors()
    ]
    return _json_error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Validation failed",
        details=details,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return _json_error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="Internal server error",
    )


def _error_parts(
    status_code: int,
    detail: Any,
) -> tuple[str, str, list[ErrorFieldDetail | dict[str, Any]]]:
    if isinstance(detail, dict):
        code = str(detail.get("code") or _default_error_code(status_code))
        message = str(detail.get("message") or _default_error_message(status_code))
        raw_details = detail.get("details") or []
        details = raw_details if isinstance(raw_details, list) else [raw_details]
        return code, message, details
    if isinstance(detail, str):
        return _default_error_code(status_code), detail, []
    return _default_error_code(status_code), _default_error_message(status_code), []


def _json_error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorFieldDetail | dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or [],
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )


def _default_error_code(status_code: int) -> str:
    if status_code in _DEFAULT_ERROR_CODES:
        return _DEFAULT_ERROR_CODES[status_code]
    if status_code >= 500:
        return "INTERNAL_SERVER_ERROR"
    return "HTTP_ERROR"


def _default_error_message(status_code: int) -> str:
    if status_code == 500:
        return "Internal server error"
    return "HTTP error"
```

- [x] **Step 8.4: auth controllerのHTTPExceptionを機械可読code付きにする**

変更例:

- duplicate register: 409 `EMAIL_ALREADY_REGISTERED`
- weak password: 422 `WEAK_PASSWORD`
- register rate limit: 429 `REGISTER_RATE_LIMITED`
- invalid login: 401 `INVALID_CREDENTIALS`
- login rate limit: 429 `LOGIN_RATE_LIMITED`
- csrf failureはTask 8時点では`auth_dependencies.py`で403 `CSRF_VALIDATION_FAILED`へ変更する。

Expected:

- `Retry-After` headerは維持する。
- messageは既存フロント互換を考慮して英語短文を維持する。
- auth routerの`responses`にも`ErrorResponse`を宣言する。実際に返り得るstatusとして、`/register`は403/409/422/429、`/login`は401/403/422/429、`/logout`は403、`/me`は401をOpenAPI上でerror envelopeとして表現する。
- `/csrf`はroute-level `require_csrf`を持たないため403を個別宣言しない。未捕捉500は全体のerror handlerでenvelope化されるが、個別route responsesには列挙しない。

- [x] **Step 8.5: sample router responsesをerror envelopeへ更新する**

`sample_controller.py`の`responses`宣言を`ErrorResponse`形式へ変える。

注意:

- 成功レスポンス`Status(success=True, message="Hello, World!")`は変えない。
- healthzの成功レスポンスも変えない。
- `Status`をerror responseの宣言に使わない。

- [x] **Step 8.6: `create_app()`にerror handler登録を追加する**

`create_app()`で`setup_routes(app)`の前後どちらでもよいが、app作成直後に`register_error_handlers(app)`を呼ぶ。

Expected:

- unknown route 404もerror envelopeになる。
- static missing asset 404もerror envelopeになる可能性がある。Phase 0のroute testsはstatusとSPA fallback有無を主に見ているため、body期待があれば更新する。

- [x] **Step 8.7: integration testsのerror body期待を更新する**

`backend/tests/integration/test_auth_controller.py`で次を更新する。

- `response.json()["detail"] == "Unauthorized"`を`response.json()["error"]["code"] == "UNAUTHORIZED"`または`INVALID_CREDENTIALS`へ変更する。
- duplicate registerは`EMAIL_ALREADY_REGISTERED`を検証する。
- CSRF失敗は`CSRF_VALIDATION_FAILED`を検証する。
- 429は`Retry-After` headerを引き続き検証する。

- [x] **Step 8.8: targeted testsを実行する**

```bash
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/unit/bootstrap/test_error_handlers.py tests/unit/controllers/test_sample_controller.py tests/integration/test_auth_controller.py -q
```

Expected:

- error envelope関連テストが成功する。
- auth integration testsが新形式で成功する。
- auth integration testsのskipが0件である。

### Task 9: `create_app()`のloggingとproduction docs制御を整える

**Review Items:** `P1-9`, `P2-21`

**Interfaces:**
- Consumes: `get_config() -> Config` from Task 3
- Consumes: `injector.get(Config) -> Config`
- Produces: `_setup_logging(config: Config) -> None`
- Produces: docs allowlist behavior for `ENVIRONMENT in {"local", "development", "test"}`

**Files:**
- Modify: `backend/app/bootstrap/create_app.py`
- Modify: `backend/app/config/__init__.py`
- Inspect: `backend/app/config/auth.py`
- Inspect: `backend/.env.example`
- Modify: `backend/tests/unit/bootstrap/test_create_app.py`
- Inspect: `backend/tests/unit/config/test_auth_settings.py`
- Modify: `backend/AGENTS.md`

- [x] **Step 9.1: production docs制御のRED testを書く**

`backend/tests/unit/bootstrap/test_create_app.py`へ次を追加する。

- `ENVIRONMENT=production`で`create_app()`した場合、`GET /docs`、`GET /redoc`、`GET /openapi.json`が404になる。
- `ENVIRONMENT=prod`、`ENVIRONMENT=Production`、`ENVIRONMENT`未設定で`create_app()`した場合も、`GET /docs`、`GET /redoc`、`GET /openapi.json`が404になる。
- `ENVIRONMENT=local`で`create_app()`した場合、`GET /docs`または`GET /openapi.json`が200になる。

Expected:

- 現状はproductionでもdocsが公開されるため失敗する。

RED確認:

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_create_app.py::test_production_like_environments_disable_docs -q
```

Expected RED:

- `ENVIRONMENT=production`または未設定caseで`/docs`が200になり、404期待のassertionが失敗する。

- [x] **Step 9.2: logging初期化のRED testを書く**

検証内容:

- `LOG_LEVEL=DEBUG`を設定した場合、root loggerまたはアプリloggerの実効levelがDEBUGになる。
- 不正な`LOG_LEVEL=NOPE`では起動時に`ValueError`ではなく既定`INFO`へfallbackし、warning logを出す。

注意:

- `LOG_LEVEL`を追加する場合は`Config`か`AuthSettings`のどちらか一方に寄せる。この計画では`Config`をアプリ共通設定として使う。
- `logging.basicConfig()`を呼んだ回数はtestしない。既存handlerの有無でno-opになるため、実装詳細ではなく実効levelとwarning logを検証する。

RED確認:

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_create_app.py::test_create_app_applies_log_level_from_config tests/unit/bootstrap/test_create_app.py::test_create_app_falls_back_for_invalid_log_level -q
```

Expected RED:

- `Config`に`LOG_LEVEL`が無い、または`create_app()`がlogging設定を行わないため失敗する。

- [x] **Step 9.3: `Config`へ`LOG_LEVEL`を追加し、`ENVIRONMENT`既定値を安全側へ反転する**

Task 3で`get_config()`と`SettingsConfigDict`化は完了している前提で、`backend/app/config/__init__.py`を次の形へ差分更新する。

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"


def get_config() -> Config:
    return Config()
```

Expected:

- `get_config()`を再導入するのではなく、Task 3で作った関数を維持する。
- module-levelの`config = Config()`を戻さない。`Config`は`get_config()`経由でlazyに作り、`monkeypatch.setenv()`後に`create_app()`したtestが環境変数を反映できるようにする。
- `Config.ENVIRONMENT`の既定値はdocs制御のため安全側の`production`にする。
- `backend/.env.example`には`ENVIRONMENT=local`が既にあるため、local開発では明示的にdocsを有効化できる。
- `AuthSettings.ENVIRONMENT`の既定値はPhase 1では変更しない。cookie secure既定反転は`P1-12`としてPhase 2で扱う。
- `P2-20`全体の設定統一はPhase 4以降に残すが、今回追加するdocs/loggingが読む値は`Config`へ寄せる。

- [x] **Step 9.4: `create_app()`でdocs URLを制御する**

実装方針:

```python
config = injector.get(Config)
docs_enabled = config.ENVIRONMENT.lower() in {"local", "development", "test"}
app = FastAPI(
    title="Fast API Template",
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)
```

Expected:

- `environment`引数は削除する。
- testや呼び出し側に`create_app(environment=...)`が残っていないことを`rtk grep`で確認する。
- 未設定、typo、`prod`、`Production`ではdocsを公開しない。

- [x] **Step 9.5: logging初期化を追加する**

`create_app.py`に`_setup_logging(config: Config) -> None`を追加する。

実装方針:

- `LOG_LEVEL`を大文字化する。
- `logging.getLevelNamesMapping().get(level_name)`でlevelを引く。存在しなければ`INFO`へfallbackし、warningを出す。
- `logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")`を呼ぶ。

実装例:

```python
import logging

from app.config import Config

logger = logging.getLogger(__name__)


def _setup_logging(config: Config) -> None:
    level_name = config.LOG_LEVEL.upper()
    level = logging.getLevelNamesMapping().get(level_name)
    if level is None:
        logger.warning(
            "Invalid LOG_LEVEL=%s; falling back to INFO",
            config.LOG_LEVEL,
        )
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger().setLevel(level)
```

Expected:

- usecaseの`logger.info`が既定で出力対象になる。
- CORS/GZipはこのPhaseでは有効化しない。`create_app.py`に「CORSを有効化する場合はcredential付きwildcard originを使わない」というWHYコメントだけを残す。

- [x] **Step 9.6: AGENTSへPhase 1規約を追記する**

`backend/AGENTS.md`へ次を追記する。

- controllerは`request.app.state.injector.get(...)`を直接呼ばず、`Depends` dependencyで依存を受ける。
- transaction境界は`UnitOfWorkInterface`に置く。repositoryに`transaction()`を追加しない。
- auth controller/usecase/interfaceは`AuthenticatedSessionContext`を`app.models.auth_context`からimportする。
- HTTP errorはerror envelopeで返す。新規controllerは`api_error()`または共通例外handlerを使う。
- productionではdocsを公開しない。
- Phase 1完了時点では`Config.ENVIRONMENT`の既定値はdocs非公開のため`production`、`AuthSettings.ENVIRONMENT`の既定値はcookie secure反転前のため`local`で意図的に分裂している。Phase 2の`P1-12`でAuthSettings側も安全側へ反転するまで、片方へ安易に揃えない。
- local開発でdocsを見たい場合は、`backend/.env.example`を元に`backend/.env`を作り、`ENVIRONMENT=local`を明示する。

- [x] **Step 9.7: targeted testsを実行する**

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_create_app.py tests/unit/config/test_auth_settings.py -q
```

Expected:

- docs制御とlogging testsが成功する。
- auth settings既存testsが成功する。

### Task 10: DI/UoW/error envelopeの結合回帰を確認する

**Review Items:** Phase 1全体

**Interfaces:**
- Consumes: all interfaces produced by Tasks 2-9
- Produces: verification evidence for backend unit, backend integration, Alembic consistency, frontend quality gate, manual smoke

**Files:**
- Inspect: `backend/tests/integration/test_auth_controller.py`
- Inspect: `backend/tests/integration/test_migration_consistency.py`
- Modify: `documents/plans/20260801-phase1-backend-foundation.md`

- [x] **Step 10.1: backend unit testsを実行する**

```bash
cd backend
rtk uv run pytest tests/unit -q
```

Expected:

- unit testsがすべて成功する。
- error envelope変更によりbody期待が変わったテストは新形式へ更新済みである。

- [x] **Step 10.2: PostgreSQL付きintegration testsを実行する**

PostgreSQLが起動していない場合:

```bash
rtk docker compose up -d postgres
```

実行:

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q
```

Expected:

- `db-upgrade`がexit 0である。
- integration testsがすべて成功する。
- skipが0件である。
- engine disposeによりconnection leak warningが出ない。

- [x] **Step 10.3: Alembic整合を再確認する**

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-check
```

Expected:

- `No new upgrade operations detected.`が表示される。
- Phase 1で新規schema差分が発生していない。

- [x] **Step 10.4: manual smokeを実施する**

backendを起動する。既にport 8000で別processが動いている場合は、そのprocessが現在のworking treeを使っていることを確認してから流用する。

```bash
cd backend
rtk uv run python manage.py serve --host 127.0.0.1 --port 8000
```

別terminalで確認する。

```bash
rtk curl -i http://127.0.0.1:8000/api/healthz
rtk curl -i http://127.0.0.1:8000/api/auth/me
rtk curl -i http://127.0.0.1:8000/api/unknown
rtk curl -i http://127.0.0.1:8000/docs
```

Expected:

- `/api/healthz`は200で`{"success": true, "message": "ok"}`を返す。
- `/api/auth/me`は401でerror envelopeを返す。
- `/api/unknown`は404でerror envelopeを返す。
- `ENVIRONMENT`未設定で起動した場合、`/docs`は404を返す。local開発でdocsを見たい場合は`backend/.env`に`ENVIRONMENT=local`を明示して再起動する。

- [x] **Step 10.5: formattingを実行する**

```bash
cd backend
rtk uv run isort .
rtk uv run yapf -ir app/ tests/ alembic/ manage.py
```

Expected:

- import順とformatが整う。
- Alembic generated migrationを変更しない。`backend/pyproject.toml`の`skip_glob`が効いていることを確認する。

- [x] **Step 10.6: formatting checkを実行する**

```bash
cd backend
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
```

Expected:

- どちらもexit 0。
- yapf diffが出ない。

- [x] **Step 10.7: repository全体のdiff checkを実行する**

```bash
rtk git diff --check
rtk git status --short
```

Expected:

- whitespace errorがない。
- 変更ファイルにPhase 1と無関係なfrontend、migration、lockfileが含まれない。
- `git add`は実行しない。

- [x] **Step 10.8: frontend品質ゲートを実行する**

Phase 1ではfrontend実装を変更しないが、root `AGENTS.md`の品質ゲートに従ってfrontendも確認する。このゲートは「frontend fileを壊していないこと」の確認であり、backend error envelopeとのruntime統合を証明するものではない。error body依存の有無はStep 1.4のコード読解で確認する。

```bash
cd frontend
rtk npm run check
rtk npm test
rtk npm run build
```

Expected:

- `npm run check`が成功する。
- `npm test`が成功する。
- `npm run build`が成功する。
- frontend testsはfetchをstubしているため、backendのerror envelope変更そのものは検出しない。`npm test`成功をもってfrontend runtime安全性の証明と扱わない。
- Step 1.4でruntime側が`ApiError.body`に依存している箇所を見つけた場合は、Phase 1の範囲を越えるため実装前に人間へ確認する。

### Task 11: Phase 1の実行結果と残課題を計画書へ反映する

**Files:**
- Modify: `documents/plans/20260801-phase1-backend-foundation.md`

- [x] **Step 11.1: 進捗サマリーを更新する**

本計画の「進捗サマリー」で完了したTaskにチェックを入れる。

- [x] **Step 11.2: 実行結果を記録する**

次を「実行結果」へ追記する。

- 実行日時
- branch / HEAD
- 変更ファイル一覧
- targeted test結果
- unit test結果
- integration test結果
- `db-check`結果
- formatting結果
- manual smoke結果
- skip件数
- 未実行コマンドがある場合は理由

- [x] **Step 11.3: 未対応事項を更新する**

Phase 1で意図的に残したものを「未対応事項」へ追記する。

Expected:

- Phase 2へ渡す項目とPhase 4へ渡す項目が区別されている。
- 未対応事項ごとに、対応するレビュー項目IDと予定Phaseが明記されている。

## 進捗サマリー

- [x] Task 1: baselineとPhase 1境界を固定する
- [x] Task 2: 汎用DI dependencyを追加し、controllerをDepends化する
- [x] Task 3: Injector module/provider構成へ移行する
- [x] Task 4: `create_app()`にlifespanとengine disposeを追加する
- [x] Task 5: Unit of Workを導入し、repositoryからtransaction管理を分離する
- [x] Task 6: `authenticate_session`を1 request = 1 sessionへ寄せる
- [x] Task 7: auth contextとsession発行戻り値をDTO/dataclassへ移す
- [x] Task 8: error envelopeを導入し、HTTP/validation/unknown errorを正規化する
- [x] Task 9: `create_app()`のloggingとproduction docs制御を整える
- [x] Task 10: DI/UoW/error envelopeの結合回帰を確認する
- [x] Task 11: Phase 1の実行結果と残課題を計画書へ反映する

## 完了条件

- [x] controllerから`request.app.state.injector.get(...)`の直接呼び出しが消えている。
- [x] `auth_controller.py`と`sample_controller.py`がFastAPI `Depends`でusecase/settingsを受け取っている。
- [x] controller unit testで`app.dependency_overrides`によりusecaseを差し替えられる。
- [x] Injector containerがmodule/provider構成になり、usecase/repository/settings/rate limiterがsingletonとして解決される。
- [x] `AsyncEngine`がDI containerに登録され、`create_app()`のlifespan shutdownで`dispose()`される。
- [x] `AuthRepositoryInterface`から`transaction()`が削除されている。
- [x] `UnitOfWorkInterface`がtransactionとsession_scopeを提供している。
- [x] `UnitOfWorkInterface.is_transaction_session(session)`がtransaction sessionをidentityで判定し、repositoryが`session.in_transaction()`でcommit/flushを判定していない。
- [x] 2つ以上のrepositoryが同じUoW transaction内で同一`AsyncSession`を共有できることをPostgreSQL integration testで検証している。
- [x] `AuthRepository`がrepository-localな`ContextVar`を持っていない。
- [x] `AuthUsecase`がtransaction境界をUoW経由で張っている。
- [x] `authenticate_session`のsession lookup、user lookup、touch/revokeが1つのUoW transaction内で行われる。
- [x] `AuthenticatedSessionContext`が`app.models.auth_context`に移動している。
- [x] `register()`と`login()`が`IssuedAuthSession`を返し、interfaceにも戻り値型が明記されている。
- [x] HTTPException、RequestValidationError、未捕捉Exceptionがerror envelopeで返る。
- [x] auth系の409/422/429/401/403が機械可読な`error.code`を持つ。
- [x] auth routerのOpenAPI `responses`が`ErrorResponse`を宣言している。
- [x] sample controllerのerror response宣言が`Status`ではなくerror envelopeになっている。
- [x] `ENVIRONMENT`未設定、typo、production相当では`/docs`、`/redoc`、`/openapi.json`が公開されず、`local`、`development`、`test`でだけ公開される。
- [x] `create_app(environment=...)`の未使用引数が削除され、呼び出し側にも残っていない。
- [x] backend/AGENTS.mdにPhase 1で確立したDI/UoW/error envelope規約が追記されている。
- [x] frontend runtimeのerror処理が`ApiError.status`中心であり、Phase 1のerror envelope変更だけでは`ApiError.body`依存で壊れないことを確認している。
- [x] backend unit testsがすべて成功している。
- [x] PostgreSQL付きbackend integration testsがskip 0件で成功している。
- [x] frontend `npm run check`、`npm test`、`npm run build`が成功している。
- [x] `python manage.py db-check`がpending schema changeなしで成功している。
- [x] isort/yapf checkが成功している。
- [x] `git diff --check`がcleanである。
- [x] `git add`、`git commit`、`git push`を実行していない。

## 実行結果

実行日時: 2026-08-02 07:26:56 +07

branch / HEAD:

- branch: `feature/db-auth`
- HEAD: `64ff7f4`

変更ファイル一覧:

- `backend/AGENTS.md`
- `backend/app/bootstrap/container.py`
- `backend/app/bootstrap/create_app.py`
- `backend/app/bootstrap/dependencies.py`
- `backend/app/bootstrap/error_handlers.py`
- `backend/app/bootstrap/modules.py`
- `backend/app/bootstrap/route.py`
- `backend/app/config/__init__.py`
- `backend/app/controllers/auth_controller.py`
- `backend/app/controllers/auth_dependencies.py`
- `backend/app/controllers/healthz_controller.py`
- `backend/app/controllers/sample_controller.py`
- `backend/app/interfaces/services/auth_repository_interface.py`
- `backend/app/interfaces/services/unit_of_work_interface.py`
- `backend/app/interfaces/usecases/auth_usecase_interface.py`
- `backend/app/models/auth_context.py`
- `backend/app/models/error.py`
- `backend/app/services/auth_repository.py`
- `backend/app/services/unit_of_work.py`
- `backend/app/usecases/auth_usecase.py`
- `backend/app/usecases/get_sample_index_usecase.py`
- `backend/tests/integration/conftest.py`
- `backend/tests/integration/services/test_unit_of_work.py`
- `backend/tests/integration/test_auth_controller.py`
- `backend/tests/unit/bootstrap/test_container.py`
- `backend/tests/unit/bootstrap/test_create_app.py`
- `backend/tests/unit/bootstrap/test_dependencies.py`
- `backend/tests/unit/bootstrap/test_error_handlers.py`
- `backend/tests/unit/bootstrap/test_route.py`
- `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- `backend/tests/unit/controllers/test_auth_dependencies.py`
- `backend/tests/unit/controllers/test_sample_controller.py`
- `backend/tests/unit/controllers/test_sample_controller_dependency.py`
- `backend/tests/unit/services/test_auth_repository.py`
- `backend/tests/unit/usecases/test_auth_usecase.py`
- `AGENTS.md`
- `documents/plans/20260801-phase1-backend-foundation.md`

targeted test結果:

- Task 2: `tests/unit/bootstrap/test_dependencies.py tests/unit/controllers/test_auth_dependencies.py tests/unit/controllers/test_auth_controller_dependency.py tests/unit/controllers/test_sample_controller_dependency.py -q` -> 初回 `14 passed, 1 warning`
- Task 3: `tests/unit/bootstrap/test_container.py tests/unit/usecases/test_auth_usecase.py -q` -> `6 passed`
- Task 4: `tests/unit/bootstrap/test_create_app.py tests/integration/test_auth_controller.py::test_register_then_me_returns_current_user -q` -> `2 passed, 1 warning`
- Task 5: `tests/integration/services/test_unit_of_work.py tests/unit/usecases/test_auth_usecase.py tests/unit/bootstrap/test_container.py -q` -> 初回 `12 passed, 1 warning`
- レビュー修正後UoW targeted: `tests/integration/services/test_unit_of_work.py -q` -> `9 passed, 1 warning`
- 再レビュー修正後UoW targeted: `tests/integration/services/test_unit_of_work.py -q` -> `9 passed, 1 warning`
- 3回目レビュー修正後UoW targeted: `tests/integration/services/test_unit_of_work.py -q` -> `10 passed, 1 warning`
- Task 6: `tests/unit/usecases/test_auth_usecase.py::test_authenticate_session_uses_one_unit_of_work_transaction -q` -> `1 passed`
- Task 6 integration: `test_register_then_me_returns_current_user` / `test_random_session_tokens_do_not_create_audit_rows` -> `2 passed, 1 warning`
- Task 7: `tests/unit/usecases/test_auth_usecase.py tests/unit/controllers/test_auth_controller_dependency.py tests/unit/controllers/test_auth_dependencies.py -q` -> `16 passed, 1 warning`
- Task 8: `tests/unit/bootstrap/test_error_handlers.py tests/unit/controllers/test_sample_controller.py tests/integration/test_auth_controller.py -q` -> `35 passed, 4 warnings`
- Task 9: `tests/unit/bootstrap/test_create_app.py tests/unit/config/test_auth_settings.py -q` -> 初回 `10 passed, 1 warning`
- レビュー修正後controller/logging/healthz targeted: `tests/unit/controllers/test_auth_controller_dependency.py tests/unit/bootstrap/test_create_app.py tests/unit/bootstrap/test_route.py -q` -> `31 passed, 1 warning`
- 再レビュー修正後unit targeted: `tests/unit/bootstrap/test_container.py tests/unit/controllers/test_auth_controller_dependency.py tests/unit/services/test_auth_repository.py -q` -> `12 passed, 1 warning`

品質ゲート結果:

- baseline backend full pytest: `86 passed, 4 warnings`
- 正式backendゲート（`uv run pytest -q`、`TEST_DATABASE_URL`未設定）: `81 passed, 45 skipped, 1 warning`
- PostgreSQL env付きbackend full pytest（`TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest -q`）: `126 passed, 4 warnings`
- backend unit tests: `81 passed, 1 warning`
- backend integration tests: `45 passed, 4 warnings`
- `db-upgrade`: exit 0
- `db-check`: `No new upgrade operations detected.`
- `isort . --check-only`: exit 0
- `yapf -dr app/ tests/ alembic/ manage.py`: exit 0
- `git diff --check`: exit 0
- frontend `npm run check`: exit 0
- frontend `npm test`: `15 passed`
- frontend `npm run build`: exit 0。`%VITE_SITE_URL% is not defined` warningが3件出たが、buildは成功

manual smoke結果:

- `GET /api/healthz`: 200、`{"success":true,"message":"ok"}`
- `GET /api/auth/me`: 401、`{"error":{"code":"UNAUTHORIZED","message":"Unauthorized","details":[]}}`
- `GET /api/unknown`: 404、`{"error":{"code":"NOT_FOUND","message":"Not Found","details":[]}}`
- `GET /docs`: 404、`{"error":{"code":"NOT_FOUND","message":"Not Found","details":[]}}`

skip件数:

- `TEST_DATABASE_URL`未設定の正式backendゲートではintegration 45件がskipされる。
- `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test`を明示したbackend full pytest / integration実行でskipは0件。

未実行コマンド:

- なし。

## 未対応事項

- `P1-10`: Argon2 hash/verifyのthread化。Phase 2で対応する。
- `P1-11`: 信頼プロキシ配下のclient IP解決。Phase 2で対応する。
- `P1-12`: Secure cookie既定反転。Phase 2で対応する。
- `P1-14`: CSRF middleware化。Phase 2で対応する。
  - 2026-08-02時点では、pre-session CSRF cookieがある場合に`GET /api/auth/csrf`がtokenを再発行せず既存値をecho backする。session未確立時のCSRF tokenをどの信頼境界で扱うかをPhase 2で明確化し、必要ならmiddleware化と同時に再発行へ寄せる。
- `P1-15`: `manage.py serve`のreload/workers/port型改善。Phase 4で対応する。
- `P1-15`: lifespanのdispose失敗パスのテストを追加する。2026-08-02時点では`create_app.py`のlifespan終了処理で、起動時例外とdispose例外の扱いを分ける非自明な分岐があるが、`if app_error is None:`相当を壊しても検出する専用テストがない。
- `P1-16`: integration test必須化と品質ゲート強化。Phase 4で対応する。
  - 2026-08-02時点では`TEST_DATABASE_URL`未設定の`uv run pytest`でintegration 45件がskipされ、exit 0になる。PostgreSQL必須のCI gate化、またはintegration job分離はPhase 4で対応する。
  - pytestのcollection errorはunit auth controller testのbasename renameで解消したが、`tests/`配下へ`__init__.py`を追加する、または`--import-mode=importlib`へ切り替える恒久対策は未実施。同名basenameのtest fileを再追加すると再発し得るため、Phase 4のgate整備で決める。
- `P1-20`: `users.password_hash` nullable化。Phase 2で`P2-6` naming conventionと一緒に検討する。
- `P2-13`から`P2-19`: auth security細部。Phase 2で対応する。
- `P2-20`: 設定クラス全体の様式統一。Phase 1ではdocs/loggingに必要な`Config`最小整理だけ行い、全面統一はPhase 4以降で扱う。
- `P2-23`: ruff/mypy/CI導入。Phase 4で対応する。
  - frontendの`npm run check`はcheck-onlyではなく`prettier --write && eslint --fix`である。check-only lint/format gateの追加はPhase 4で対応する。
  - `UnitOfWorkStub`が`UnitOfWorkInterface`を継承しておらず、nested transaction非対応の簡易実装と死にコードを含む。Phase 4の型検査導入時に、test doubleもinterfaceを継承する方針へ揃える。
  - `AuthUsecase.__init__`の戻り値注釈が`-> None`ではなく誤って別型になっている箇所、`register()`の戻り値注釈欠落を型検査導入時に修正する。
- `P2-24`: `InMemoryLoginRateLimiter`のinterface化。Phase 2またはOAuth前に対応する。
- `P2-35` / `P3-8`: sample APIのREST化とCRUD模範実装化。Phase 4で対応する。
  - Phase 1完了時点ではsample controllerに401/403/404 response宣言が残るが、現在の`GET /api/sample/`実装からは到達不能。controller testもその宣言を固定しているため、REST CRUD模範実装化時に実際のerror pathとOpenAPI宣言を揃える。
  - static mount有効時、本番では既知API pathへの誤methodが405ではなく404になり、`Allow` headerも消えるケースがある。開発/CIのstaticなし挙動と差が出るため、SPA fallback/static mount整理時にAPI routing precedenceと405保持を検証する。
- `P2-9`: DTOとtable modelのdirectory分離。Phase 1では既存の`app.models.auth_schemas`、`app.models.status`に合わせて`app.models.auth_context`と`app.models.error`を置くが、`ErrorResponse`は`pydantic.BaseModel`で定義し、ORM基底には依存させない。Phase 5で`schemas/`等へ整理する。
- `P1-8`のfrontend追随: Phase 1ではfrontend runtimeが`ApiError.status`中心で動くことを確認し、frontend実装は変更しない。`ApiError.body`の型ガード、`toUserMessage()`、旧`{"detail": ...}`mockの整理はPhase 3の`P2-30`で対応する。
- `P1-8`の成功レスポンス整理: Phase 1完了時点では`/api/healthz`と`/api/sample/`の成功レスポンスに`Status(success, message)`が残る。`Status`をhealthz専用へ縮退し、sampleをREST CRUD模範へ置き換える作業は`P2-35` / `P3-8`で対応する。
- error envelopeのfallback分岐をPhase 4で直接テストする。2026-08-02時点では`error_handlers.py`のfallback系4分岐が未到達で、Phase 1の中心成果であるerror envelopeの防御が薄い。
- logging testをPhase 4で本番条件に近づける。pytestは起動時にroot loggerへhandlerを差し込むため、現行`test_create_app.py`のroot logger assertは`basicConfig()`がno-opになるpytest環境を見ている。handlerがない本番条件でroot levelを汚染しないかは別途検証する。
- `/api/auth/me`の200 unit testを追加する。2026-08-02時点では401 unit testはあるが、正常系はPostgreSQL必須のintegrationに寄っており、DBなし正式ゲートでは正常系退行を検出しにくい。
- UoW fail-fast例外はPhase 4で専用例外型へ切り出す。2026-08-02時点では`RuntimeError`を使っており、広い`pytest.raises(RuntimeError)`が誤発火を吸収し得る。
- fail-fastにより「各testを外側transactionで包んでrollbackする」fixture高速化パターンは使えない。現状はTRUNCATE cleanupなので実害はないが、integration test高速化を検討する場合はこの制約を前提にする。
- M-1〜M-5 / M-7はPhase 2以降へ送る。三値fail-open、405のerror code名、`api_error`命名、401 responseの`Cache-Control: no-store`、database URLの`hide_parameters`はPhase 1範囲外として残す。
- frontend Phase 3項目: `P1-19`、`P1-18`、`P1-17`、`P2-30`、`P0-4`は本計画の対象外。

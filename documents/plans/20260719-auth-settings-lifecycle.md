# 認証設定ライフサイクル統一 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Worktree、`git add`、`git commit`は使用しない。

**Goal:** `AuthSettings`をアプリ起動時に一度だけ生成し、認証usecaseと全controllerが同じ起動時snapshotを利用する構成へ統一する。

**Architecture:** `backend/app/bootstrap/container.py`を`AuthSettings`生成のcomposition rootとし、生成したインスタンスをInjectorのsingletonとして登録する。FastAPI controllerはrequestごとに設定を再生成せず、`request.app.state.injector`を使う共通dependencyから同じインスタンスを取得する。

**Tech Stack:** Python 3.12、FastAPI、Injector、Pydantic Settings、pytest、PostgreSQL 17

## Global Constraints

- Worktreeは作成せず、現在のブランチとworking treeを保持して作業する。
- `git add`、`git commit`、`git push`は実行しない。
- 依存追加、DB schema変更、Alembic migration追加、API surface変更は行わない。
- 認証設定はアプリ起動時snapshotとし、環境変数または`.env`変更後はアプリ再起動によって反映する。
- `AuthSettings`のfield名、default値、環境変数名は変更しない。
- production判定は引き続きfail-closedとし、`local`、`development`、`test`以外のHTTP requestではCookieへ`Secure`を付ける。
- `X-Forwarded-Proto`をapplication codeで信用しない既存方針を維持する。
- controller → usecase → repositoryの依存方向を変更しない。
- backend testはPostgreSQLの`app_test`を使用し、skipなしで実行する。
- 実装はテストを先に追加し、期待した理由でREDになることを確認してからproduction codeを変更する。
- M-3単独の作業ではbrowser手動E2Eを実施しない。認証全体の手動E2Eは`documents/plans/20260718-auth-resumption.md`の未完了Taskとして分離を維持する。
- shell commandはrepositoryの`AGENTS.md`に従い、各command segmentを`rtk`で始める。

---

## 背景

現在の`AuthSettings`には2つの異なるライフサイクルが混在している。

1. `backend/app/bootstrap/container.py`は起動時に`get_auth_settings()`を呼び、そのインスタンスを`AuthUsecase`と`InMemoryLoginRateLimiter`の構築に使う。
2. `backend/app/controllers/auth_controller.py`は`is_secure_request()`、`get_csrf()`、`register()`、`login()`の中で`get_auth_settings()`を再度呼ぶ。

このため、controllerへのrequestごとにPydantic Settingsが`.env`と環境変数を再評価する。1 request内でも、たとえば`get_csrf()`はTTL取得と`Secure`判定で別々の`AuthSettings`を生成し得る。一方、usecaseとrate limiterは起動時に取得した設定を保持し続ける。

この混在には次の改善余地がある。

- requestごとに不要な設定生成と`.env`読込が発生する。
- サポート外ではあるが、プロセス起動後に環境変数が変更された場合、controllerのCookie属性とTTLだけが変わり、usecaseのsession TTLやrate limiter設定は変わらない。
- controllerとusecaseが同じ設定snapshotを使うという保証がコード上にない。
- テストが環境変数の動的変更へ依存し、実運用の設定ライフサイクルが不明瞭になる。

通常運用では環境変数と`.env`をプロセス実行中に変更しないため、現状のsnapshot不一致が既知の本番障害を起こしているわけではない。M-3は、requestごとの設定生成と`.env`読込を除去し、設定の所有者とライフサイクルを一貫させる予防的リファクタリングとして扱う。

## 現行システムとの整合性

本計画の前提と現行システムに、実装を止める矛盾はない。

- `create_app()`は起動時に`build_container()`を一度呼び、Injectorを`app.state.injector`へ保存している。
- controllerは既にusecase取得で`request.app.state.injector`を利用している。
- `AuthUsecase`は既にconstructor injectionで`AuthSettings`を受け取る。
- 明示的な設定hot reload機能、requestごとの設定再読込要件、再起動なしで`.env`変更を反映する契約は存在しない。

したがって、既存のcomposition rootへ`AuthSettings`のsingleton bindingを追加する方法が、現在のアーキテクチャに最も自然である。

## 方針とその理由

### 採用方針

`AuthSettings`は`build_container()`実行時に一度生成し、同じインスタンスを次のconsumerへ渡す。

- `AuthUsecase`
- `InMemoryLoginRateLimiter`の構築処理
- FastAPI auth controller
- `is_secure_request()`のproduction判定

controllerではFastAPI dependency `get_request_auth_settings(request: Request) -> AuthSettings`を使い、`request.app.state.injector.get(AuthSettings)`から起動時snapshotを取得する。

### 採用理由

- 既存のInjectorを設定ライフサイクルの正として利用できる。
- global cacheを新設せず、appごとに独立した設定snapshotを持てる。
- testごとに新しいapp/containerを作れば、環境変数overrideを安全に反映できる。
- usecase、rate limiter、controllerが同じ設定生成時点を共有する。
- `.env`変更時に再起動が必要という一般的なserver設定モデルを明示できる。

## デザイン決定

### 決定1: 設定は起動時snapshotとする

アプリ起動後の環境変数や`.env`変更は、既存プロセスへ動的反映しない。変更を反映するにはbackendを再起動する。

理由は、usecaseとrate limiterが既に起動時設定を保持しており、controllerだけを動的に変える現状が一貫したhot reloadではないためである。

### 決定2: `get_auth_settings()`自体はcacheしない

`get_auth_settings()`はcomposition rootや独立した設定テストから呼べるfactoryとして残す。`functools.lru_cache`は追加しない。

理由は、global cacheが複数app、test isolation、環境変数overrideへ影響するためである。singletonの範囲はPython process全体ではなく、Injector/app単位に限定する。

### 決定3: request用の設定取得をFastAPI dependencyへ分離する

`backend/app/controllers/auth_dependencies.py`へ次の関数を追加する。

```python
def get_request_auth_settings(request: Request) -> AuthSettings:
    return request.app.state.injector.get(AuthSettings)
```

各endpointは`Depends(get_request_auth_settings)`で設定を受け取る。controller内で`get_auth_settings()`を直接呼ばない。

理由は、依存解決方法を1箇所に固定し、unit testでInjectorから同一インスタンスを取得する契約を直接検証できるためである。

### 決定4: `is_secure_request()`を純粋な判定関数に近づける

signatureを次へ変更する。

```python
def is_secure_request(request: Request, auth_settings: AuthSettings) -> bool:
```

関数内部で設定を生成せず、callerから渡された起動時snapshotだけを使用する。HTTPS判定とfail-closed方針は変更しない。

## 逸脱

元のM-3指摘は「`get_auth_settings()`をrequestごとに生成している」という性能面の指摘だった。本計画では単にcacheを付けるだけでなく、設定snapshotの所有者をInjectorへ統一する。

これは指摘からの意図的な拡張である。得られる価値は、requestごとのPydantic Settings生成と`.env`読込の除去、および設定の所有者・更新タイミングの一貫性と見通しの改善である。実行中の環境変数変更はサポート外なので、既知障害の根本原因修正とは位置づけない。将来controllerだけへ部分的なhot reloadを再導入する事故を防ぐための予防的整理として実施する。API、DB、認証方式、環境変数の意味は変更しない。

## トレードオフと不採用案

### 不採用案1: `get_auth_settings()`へ`lru_cache`を追加する

変更行数は少ないが、cacheがprocess globalになる。複数appを同一processで生成するtest、環境変数override、将来のapp factory利用時に`cache_clear()`管理が必要になるため採用しない。

### 不採用案2: requestごとの生成を維持する

環境変数変更を再起動なしで読み取れる可能性はあるが、usecaseとrate limiterは更新されない。部分的なhot reloadとなり、一貫性がないため採用しない。

### 不採用案3: module globalの`AuthSettings`を作る

import時に設定が確定し、app factoryより早く評価される。test isolationと依存の可視性が悪化するため採用しない。

### 採用案のトレードオフ

- `.env`変更後にbackend再起動が必要になる。
- endpoint signatureへ`AuthSettings = Depends(...)`が追加される。
- Injectorを持たない手作りRequestでcontroller helperをテストする場合、設定を明示的に渡す必要がある。
- Injectorは未bindの具象classを暗黙に生成できるため、`AuthSettings`のbindingが将来削除されても`injector.get(AuthSettings)`自体は例外にならない。`test_build_container_binds_created_auth_settings_instance`のidentity assertionを、このsilent regressionを検出する必須ガードとして維持する。

これらは設定ライフサイクルが明確になる利点と比較して許容する。

---

## File Structure

### 変更するファイル

- `backend/app/bootstrap/container.py`
  - `AuthSettings`を起動時に生成し、Injectorへsingleton instanceとして登録するcomposition root。
- `backend/app/controllers/auth_dependencies.py`
  - requestからInjector管理の`AuthSettings`を取得するFastAPI dependencyを提供する。
- `backend/app/controllers/auth_controller.py`
  - directな`get_auth_settings()`呼び出しを削除し、dependency injectionされた設定をCookie、TTL、rate-limit responseへ使用する。
- `backend/tests/unit/controllers/test_auth_dependencies.py`
  - request dependencyがInjectorへ`AuthSettings`を要求し、同一インスタンスを返すことを検証する。
- `backend/tests/unit/controllers/test_auth_controller_helpers.py`
  - `is_secure_request()`へ設定を明示的に渡し、production fail-closedとproxy header非信用を維持する。
- `backend/tests/unit/bootstrap/test_container.py`
  - app/container単位で`AuthSettings`がsingleton bindingされることを検証する。
- `backend/tests/integration/test_auth_controller.py`
  - app起動後の環境変数変更が既存appのCookie設定へ反映されない起動時snapshot契約を検証する。
- `backend/AGENTS.md`
  - 認証設定は起動時snapshotであり、変更後にbackend再起動が必要であることを記載する。
- `README.md`
  - `backend/.env`変更後の反映方法を環境変数節へ追記する。
- `documents/plans/20260719-auth-settings-lifecycle.md`
  - 実行中に完了したStepへチェックを付け、検証結果を実測値で追記する。

### 変更しないファイル

- `backend/app/config/auth.py`
  - `AuthSettings`定義と`get_auth_settings()`factoryは現状維持する。
- `backend/app/usecases/auth_usecase.py`
  - 既にconstructorで`AuthSettings`を受け取るため変更不要。
- `backend/app/libraries/auth_rate_limiter.py`
  - M-1の計数仕様は本計画の対象外。
- DB model、repository、Alembic migration
  - 設定ライフサイクル変更にDB schema変更は不要。

---

## 進捗サマリー

各Task配下の全StepとTask固有のExpectedを満たした時点で、対応するTaskへチェックを付ける。

- [x] Task 1: baselineと変更境界を固定する
- [x] Task 2: request settings dependencyの契約をtest-firstで追加する
- [x] Task 3: `AuthSettings`をapp/container単位のsingletonにする
- [x] Task 4: secure判定と全auth endpointを起動時settings snapshotへ統一する
- [x] Task 5: 設定ライフサイクルを開発者向け文書へ反映する
- [x] Task 6: repositoryの全品質ゲートを実行する
- [x] Task 7: scopeと完了条件を最終レビューする

## 具体的なタスク

### Task 1: baselineと変更境界を固定する

**Files:**
- Inspect: `backend/app/config/auth.py`
- Inspect: `backend/app/bootstrap/container.py`
- Inspect: `backend/app/controllers/auth_controller.py`
- Inspect: `backend/app/controllers/auth_dependencies.py`
- Inspect: `backend/tests/`

**Interfaces:**
- Consumes: current working tree上の未コミットauth実装
- Produces: 本計画で変更するファイルと、既存変更を破壊しないためのbaseline記録

- [x] **Step 1.1: branch、HEAD、working treeを記録する**

Repository rootで実行する。

```bash
rtk git branch --show-current
rtk git rev-parse HEAD
rtk git status --short
```

Expected:

- 現在のbranchとHEADが表示される。
- 既存の認証関連変更と`documents/plans/20260719-auth-settings-lifecycle.md`が確認できる。
- 既存変更をreset、checkout、cleanしない。

- [x] **Step 1.2: direct settings生成箇所を再確認する**

```bash
rtk grep -n "get_auth_settings\|AuthSettings" backend/app backend/tests
```

Expected:

- `backend/app/bootstrap/container.py`に起動時生成が1箇所ある。
- `backend/app/controllers/auth_controller.py`にrequest処理から到達するdirect callが4箇所ある。
- `AuthUsecase`がconstructorで`AuthSettings`を受け取っている。

- [x] **Step 1.3: 変更禁止事項を確認する**

Run: なし。

Expected:

- dependency、DB schema、migration、API path、request/response schema、Cookie名を変更しない。
- M-1、M-2、admin seedを本タスクへ混在させない。

### Task 2: request settings dependencyの契約をtest-firstで追加する

**Files:**
- Modify: `backend/tests/unit/controllers/test_auth_dependencies.py`
- Modify: `backend/app/controllers/auth_dependencies.py`

**Interfaces:**
- Consumes: `Request.app.state.injector`、`AuthSettings`
- Produces: `get_request_auth_settings(request: Request) -> AuthSettings`

- [x] **Step 2.1: Injector管理の設定を返すfailing unit testを書く**

`backend/tests/unit/controllers/test_auth_dependencies.py`へ次のtestを追加する。既存のCSRF、IP、user-agent testsは変更しない。

```python
def test_get_request_auth_settings_returns_injector_instance():
    settings = AuthSettings(ENVIRONMENT="production")

    class InjectorStub:

        def get(self, interface):
            assert interface is AuthSettings
            return settings

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/auth/csrf",
        "app": SimpleNamespace(
            state=SimpleNamespace(injector=InjectorStub())),
        "headers": [],
    })

    assert auth_dependencies.get_request_auth_settings(request) is settings
```

同test fileへ次のimportを追加する。

```python
from app.config.auth import AuthSettings
```

- [x] **Step 2.2: testを実行してREDを確認する**

`backend/`で実行する。

```bash
rtk uv run pytest tests/unit/controllers/test_auth_dependencies.py::test_get_request_auth_settings_returns_injector_instance -q
```

Expected: `auth_dependencies`に`get_request_auth_settings`が存在しないためFAILする。import error、fixture error、別のassertion failureならtestを修正して再実行する。

- [x] **Step 2.3: 最小dependencyを実装する**

`backend/app/controllers/auth_dependencies.py`へimportと関数を追加する。

```python
from app.config.auth import AuthSettings


def get_request_auth_settings(request: Request) -> AuthSettings:
    return request.app.state.injector.get(AuthSettings)
```

既存の`get_client_ip()`、`get_user_agent()`、`require_csrf()`、`require_current_session()`の動作は変更しない。

- [x] **Step 2.4: targeted testをGREENにする**

```bash
rtk uv run pytest tests/unit/controllers/test_auth_dependencies.py::test_get_request_auth_settings_returns_injector_instance -q
```

Expected: 1 passed、0 failed。

- [x] **Step 2.5: dependencies unit suiteを確認する**

```bash
rtk uv run pytest tests/unit/controllers/test_auth_dependencies.py -q
```

Expected: 全test passed、0 failed。

### Task 3: AuthSettingsをapp/container単位のsingletonにする

**Files:**
- Create: `backend/tests/unit/bootstrap/test_container.py`
- Modify: `backend/app/bootstrap/container.py`

**Interfaces:**
- Consumes: `get_auth_settings() -> AuthSettings`
- Produces: `Injector.get(AuthSettings) -> AuthSettings`。同じInjectorでは常に同一instanceを返す。

- [x] **Step 3.1: composition rootのfailing unit testを書く**

`backend/tests/unit/bootstrap/test_container.py`を作成する。

```python
from app.bootstrap import container as container_module
from app.config.auth import AuthSettings


def test_build_container_binds_created_auth_settings_instance(monkeypatch):
    settings = AuthSettings(
        ENVIRONMENT="production",
        AUTH_SESSION_ABSOLUTE_TTL_SECONDS=123,
    )
    monkeypatch.setattr(container_module, "get_auth_settings",
                        lambda: settings)

    injector = container_module.build_container()

    assert injector.get(AuthSettings) is settings
    assert injector.get(AuthSettings) is injector.get(AuthSettings)
```

このtestはDBへ接続しない。`build_engine_and_session_factory()`はengine/session factoryを構築するだけで、queryやmigrationを実行しない。

- [x] **Step 3.2: testを実行してREDを確認する**

```bash
rtk uv run pytest tests/unit/bootstrap/test_container.py::test_build_container_binds_created_auth_settings_instance -q
```

Expected: 現行containerが`AuthSettings`を明示bindしていないため、`injector.get(AuthSettings) is settings`がFAILする。

- [x] **Step 3.3: AuthSettings instanceをInjectorへbindする**

`backend/app/bootstrap/container.py`のimportを次へ変更する。

```python
from app.config.auth import AuthSettings, get_auth_settings
```

`auth_settings = get_auth_settings()`の直後へ次を追加する。

```python
binder.bind(AuthSettings, to=auth_settings, scope=singleton)
```

`InMemoryLoginRateLimiter`と`AuthUsecase`のconstructorには、引き続き同じlocal variable `auth_settings`を渡す。設定を再生成しない。

- [x] **Step 3.4: container testをGREENにする**

```bash
rtk uv run pytest tests/unit/bootstrap/test_container.py -q
```

Expected: 全test passed、0 failed。

- [x] **Step 3.5: containerとconfigのunit suiteを確認する**

```bash
rtk uv run pytest tests/unit/bootstrap tests/unit/config -q
```

Expected: 全test passed、0 failed。`test_auth_settings_reads_session_ttl_from_env`も維持され、factory単体では環境変数を読めることを確認できる。

### Task 4: secure判定と全auth endpointを起動時settings snapshotへ統一する

**Files:**
- Modify: `backend/tests/unit/controllers/test_auth_controller_helpers.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/app/controllers/auth_controller.py`

**Interfaces:**
- Consumes: `Request`、`get_request_auth_settings(request) -> AuthSettings`
- Produces: `is_secure_request(request: Request, auth_settings: AuthSettings) -> bool`。`/csrf`、`/register`、`/login`、`/logout`が同じapp/containerのsettings snapshotを使用する。

このTaskではhelperの破壊的signature変更と全call siteの更新を一体で行う。Task完了時にunit helper suiteとauth controller integration suiteの両方をGREENにし、endpointが壊れた中間状態をTask境界へ持ち越さない。

- [x] **Step 4.1: helper testsを新signatureへ変更する**

`backend/tests/unit/controllers/test_auth_controller_helpers.py`へ次のimportを追加する。

```python
from app.config.auth import AuthSettings
```

production testから`monkeypatch`引数と`monkeypatch.setenv()`を削除し、assertionを次へ変更する。

```python
assert is_secure_request(
    request,
    AuthSettings(ENVIRONMENT="production"),
) is True
```

`test_is_secure_request_ignores_untrusted_forwarded_proto`からも`monkeypatch`引数と環境変数操作だけを削除し、assertionを次へ変更する。`X-Forwarded-Proto: https` headerは、このtestの本来のsecurity contractなので削除しない。

```python
assert is_secure_request(
    request,
    AuthSettings(ENVIRONMENT="local"),
) is False
```

HTTPS requestは環境に関係なく`True`になることを明示するtestを追加する。

```python
def test_is_secure_request_accepts_https_in_local_environment():
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/auth/csrf",
        "scheme": "https",
        "headers": [],
    })

    assert is_secure_request(
        request,
        AuthSettings(ENVIRONMENT="local"),
    ) is True
```

- [x] **Step 4.2: helper testsを実行してREDを確認する**

```bash
rtk uv run pytest tests/unit/controllers/test_auth_controller_helpers.py -q
```

Expected: 現行`is_secure_request()`が2つ目の引数を受け取らないためFAILする。

- [x] **Step 4.3: 起動後の環境変数変更を反映しないfailing integration testを書く**

`backend/tests/integration/test_auth_controller.py`へ次のtestを追加する。fixtureの評価順序へ依存させず、環境変数を設定してからappを明示的に生成する。

```python
def test_auth_cookie_security_uses_startup_settings(monkeypatch):
    test_database_url = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("ENVIRONMENT", "local")
    app = create_app()

    with TestClient(app) as client:
        startup_settings = client.app.state.injector.get(AuthSettings)
        assert startup_settings.ENVIRONMENT == "local"
        monkeypatch.setenv("ENVIRONMENT", "production")

        response = client.get("/api/auth/csrf")

        csrf_cookie = SimpleCookie(response.headers["set-cookie"])
        assert csrf_cookie["csrf_token"]["secure"] == ""
        assert client.app.state.injector.get(AuthSettings) is startup_settings
```

同test fileへ次のimportを追加する。既に存在するimportは重複させない。

```python
import os
from http.cookies import SimpleCookie

from fastapi.testclient import TestClient

from app.bootstrap.create_app import create_app
from app.config.auth import AuthSettings
```

このtestは「productionでSecureを付けない」ことを求めているのではない。appがlocal設定で起動済みなら、その後のprocess環境変更で既存appの設定を変えないことを確認する。

共有`client` fixtureは使わないが、`clean_auth_tables`はautouse fixtureなので前後の`TRUNCATE ... CASCADE`が適用される。さらに`DATABASE_URL`を`TEST_DATABASE_URL`へ明示的に揃える。このtestの`GET /csrf`はsession cookieなしではDB query/writeとrate limiterを使用しないため、共有fixture固有のrate limiter resetを必要としない。この前提が変わった場合は共有fixture化または同等のcleanupを追加する。

- [x] **Step 4.4: integration testを実行してREDを確認する**

`backend/`で実行する。

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_controller.py::test_auth_cookie_security_uses_startup_settings -q
```

Expected: 現行controllerがrequest時に`ENVIRONMENT=production`を再読込し、CSRF Cookieへ`Secure`を付けるためFAILする。DB接続、schema、fixtureのerrorならREDとして扱わず、環境を修正する。

- [x] **Step 4.5: is_secure_requestを明示設定引数へ変更する**

`backend/app/controllers/auth_controller.py`で`get_auth_settings`のimportを削除し、`AuthSettings`をimportする。

```python
from app.config.auth import AuthSettings
```

関数を次へ変更する。

```python
def is_secure_request(
    request: Request,
    auth_settings: AuthSettings,
) -> bool:
    if request.url.scheme == "https":
        return True
    return auth_settings.ENVIRONMENT not in {
        "local",
        "development",
        "test",
    }
```

この時点ではendpoint側のcall siteが旧signatureのため、次のStepで続けて更新する。Task 4のGREEN確認は全call site更新後に行う。

- [x] **Step 4.6: controllerへsettings dependencyをimportする**

`backend/app/controllers/auth_controller.py`のdependency importへ`get_request_auth_settings`を追加する。

```python
from app.controllers.auth_dependencies import (
    get_client_ip,
    get_request_auth_settings,
    get_user_agent,
    require_csrf,
    require_current_session,
)
```

- [x] **Step 4.7: get_csrfへAuthSettings dependencyを追加する**

signatureを次へ変更する。

```python
async def get_csrf(
    request: Request,
    response: Response,
    auth_settings: AuthSettings = Depends(get_request_auth_settings),
) -> CsrfTokenResponse:
```

関数内の`auth_settings = get_auth_settings()`を削除し、Cookie発行時は次を使う。

```python
secure=is_secure_request(request, auth_settings)
```

- [x] **Step 4.8: registerへAuthSettings dependencyを追加する**

signatureを次へ変更する。

```python
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    auth_settings: AuthSettings = Depends(get_request_auth_settings),
) -> AuthUserResponse:
```

関数内の`auth_settings = get_auth_settings()`を削除し、secure判定を次へ変更する。

```python
secure = is_secure_request(request, auth_settings)
```

`Retry-After`とCookie `Max-Age`は注入された同じ`auth_settings`から取得する。

- [x] **Step 4.9: loginへAuthSettings dependencyを追加する**

signatureを次へ変更する。

```python
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_settings: AuthSettings = Depends(get_request_auth_settings),
) -> AuthUserResponse:
```

関数内の`auth_settings = get_auth_settings()`を削除し、secure判定を次へ変更する。

```python
secure = is_secure_request(request, auth_settings)
```

`Retry-After`とCookie `Max-Age`は注入された同じ`auth_settings`から取得する。

- [x] **Step 4.10: logoutへAuthSettings dependencyを追加する**

signatureを次へ変更する。

```python
async def logout(
    request: Request,
    response: Response,
    auth_settings: AuthSettings = Depends(get_request_auth_settings),
) -> Response:
```

secure判定を次へ変更する。

```python
secure = is_secure_request(request, auth_settings)
```

- [x] **Step 4.11: controllerからdirect factory callが消えたことを確認する**

```bash
rtk grep -n '\bget_auth_settings\b' backend/app/controllers
```

Expected: 0 matches。exit 1は`rg`互換の「一致なし」を意味するため、このStepでは成功扱いとする。単語境界を指定しているため`get_request_auth_settings`は結果へ含まれない。

- [x] **Step 4.12: helper testsをGREENにする**

```bash
rtk uv run pytest tests/unit/controllers/test_auth_controller_helpers.py -q
```

Expected: 全test passed、0 failed。production fail-closed、HTTPS優先、`X-Forwarded-Proto`非信用の契約を維持する。

- [x] **Step 4.13: startup snapshot integration testをGREENにする**

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_controller.py::test_auth_cookie_security_uses_startup_settings -q
```

Expected: 1 passed、0 skipped、0 failed。

- [x] **Step 4.14: auth controller integration suiteを通す**

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_controller.py -q
```

Expected: 全test passed、0 skipped、0 failed。Cookie属性、rate limit `Retry-After`、register/login/logout、CSRFの既存testも維持される。

### Task 5: 設定ライフサイクルを開発者向け文書へ反映する

**Files:**
- Modify: `backend/AGENTS.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 3〜4で確定した起動時snapshot契約
- Produces: 設定変更時の運用手順と、実装者がrequest単位生成を再導入しないための規約

- [x] **Step 5.1: backendガイドへ設定ライフサイクル規約を追加する**

`backend/AGENTS.md`の「モデル / DB」より前へ、次の内容を「設定」節として追加する。

```markdown
## 設定

- `AuthSettings`は`build_container()`で一度だけ生成し、Injectorのsingletonとして共有する
- controllerは`get_request_auth_settings` dependency経由で起動時snapshotを取得し、requestごとに`AuthSettings`を再生成しない
- `backend/.env`または認証関連環境変数を変更した場合は、backend process/containerを再起動する
- 設定hot reloadは提供しない。必要になった場合は全consumerを同時更新できる別設計として計画する
```

- [x] **Step 5.2: READMEへ再起動要件を追記する**

ルート`README.md`の「環境変数」節へ次の説明を追加する。

````markdown
認証設定はbackend起動時に読み込まれます。`backend/.env`または認証関連環境変数を変更した場合は、既存backend process/containerを再起動してください。

```bash
docker compose up -d --force-recreate backend
```
````

既存のDB migration、`app_test`、quality gate、admin seed関連の記述は削除しない。

- [x] **Step 5.3: 文書と実装の用語を照合する**

```bash
rtk grep -n "起動時snapshot\|get_request_auth_settings\|再起動\|hot reload" backend/AGENTS.md README.md documents/plans/20260719-auth-settings-lifecycle.md
```

Expected:

- `backend/AGENTS.md`と本計画に起動時snapshotとdependency名が記載される。
- `README.md`に設定変更後のbackend再起動手順が記載される。
- requestごとの再読込を推奨する記述がない。

### Task 6: repositoryの全品質ゲートを実行する

**Files:**
- Verify: `backend/app/`
- Verify: `backend/tests/`
- Verify: `backend/alembic/`
- Verify: `frontend/`

**Interfaces:**
- Consumes: Task 2〜5の全変更
- Produces: backend unit、PostgreSQL integration、backend format、frontend test / lint / buildの実測結果

- [x] **Step 6.1: isortを確認する**

`backend/`で実行する。

```bash
rtk uv run isort . --check-only
```

Expected: exit 0。失敗した場合は`rtk uv run isort .`で機械整形し、同じcheckを再実行する。

- [x] **Step 6.2: yapfを確認する**

```bash
rtk uv run yapf -dr app/ tests/ alembic/
```

Expected: exit 0、diffなし。差分がある場合は対象ファイルを`rtk uv run yapf -ir ...`で整形し、同じcheckを再実行する。

- [x] **Step 6.3: PostgreSQL test DBの接続先を確認する**

Repository rootで実行する。

```bash
rtk docker compose exec -T postgres psql -U app -d app_test -tAc "SELECT current_database(), current_user;"
```

Expected: `app_test|app`。`app`、共有DB、database名不一致の場合はtestを実行せず停止する。

- [x] **Step 6.4: backend full suiteをskipなしで実行する**

`backend/`で実行する。

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest
```

Expected: 全test passed、0 skipped、0 failed。件数とwarning件数を本計画の「実行結果」へ記録する。

- [x] **Step 6.5: frontendのformatとlintを確認する**

`frontend/`で実行する。

```bash
rtk npm run check
```

Expected: exit 0、ESLint error 0、warning 0。Prettierによる本計画外ファイルの変更が発生した場合は進行を止め、開始時baselineと差分を確認する。

- [x] **Step 6.6: frontend full testを実行する**

```bash
rtk npm test
```

Expected: 全test file passed、0 skipped、0 failed。file数とtest数を「実行結果」へ記録する。

- [x] **Step 6.7: frontend production buildを確認する**

```bash
rtk npm run build
```

Expected: exit 0。既知warningが出た場合は内容と件数を「実行結果」へ記録し、新規warningなら原因を調査する。

- [x] **Step 6.8: direct factory call境界を最終確認する**

```bash
rtk grep -n '\bget_auth_settings\b' backend/app
```

Expected:

- `backend/app/config/auth.py`のfactory定義
- `backend/app/bootstrap/container.py`の起動時呼び出し
- controller配下は0件

- [x] **Step 6.9: diffのwhitespace errorを確認する**

Repository rootで実行する。

```bash
rtk git diff --check
```

Expected: exit 0、outputなし。

### Task 7: scopeと完了条件を最終レビューする

**Files:**
- Review: `backend/app/bootstrap/container.py`
- Review: `backend/app/controllers/auth_dependencies.py`
- Review: `backend/app/controllers/auth_controller.py`
- Review: `backend/tests/unit/`
- Review: `backend/tests/integration/test_auth_controller.py`
- Review: `backend/AGENTS.md`
- Review: `README.md`
- Modify: `documents/plans/20260719-auth-settings-lifecycle.md`

**Interfaces:**
- Consumes: Task 1〜6の実装・テスト・文書
- Produces: stagingせずにレビュー可能な、scopeが閉じたworking treeと実測記録

- [x] **Step 7.1: 要件をline-by-lineで確認する**

Run: なし。

次をすべて確認する。

- `AuthSettings`生成はapp/container構築時の1回だけである。
- Injectorから取得する設定は同じapp内で同一instanceである。
- `AuthUsecase`、rate limiter、controllerが同じ起動時snapshotを使う。
- controllerは`get_auth_settings()`を直接呼ばない。
- production HTTPは`Secure=True`、local/development/test HTTPは`Secure=False`、HTTPSは環境に関係なく`Secure=True`である。
- `X-Forwarded-Proto`を信用しない。
- `.env`変更後の再起動要件が文書化されている。
- dependency、schema、migration、API、M-1、M-2、admin seedへ変更がない。

- [x] **Step 7.2: 変更ファイルをscopeと照合する**

```bash
rtk git status --short
rtk git diff --stat
rtk git diff -- backend/app/bootstrap/container.py backend/app/controllers/auth_dependencies.py backend/app/controllers/auth_controller.py backend/tests backend/AGENTS.md README.md documents/plans/20260719-auth-settings-lifecycle.md
```

Expected:

- 本計画開始前から存在する認証関連変更は保持される。
- M-3対応として新たに変更した内容はFile Structure記載範囲に限定される。
- generated artifact、secret、`.env`実体、DB dumpが追加されていない。

- [x] **Step 7.3: 実行結果を本計画へ記録する**

本ファイル末尾の「実行結果」へ次を実測値で記入する。

- 実行日時
- branchとHEAD
- targeted REDのfailure理由
- targeted GREENのpassed件数
- backend full pytestのpassed / skipped / failed / warnings件数
- frontend testのfile数とpassed / skipped / failed件数
- isort、yapf、frontend check / build、`git diff --check`のexit status
- 未対応事項または逸脱。なければ「なし」と明記する

推測値、placeholder、未実行結果は記録しない。

- [x] **Step 7.4: stagingとcommitを行っていないことを確認する**

```bash
rtk git diff --cached --stat
```

Expected: 本タスクによるstaged changeがない。既存のstaged changeが表示された場合は操作せず、開始時baselineと照合して報告する。

---

## 完了条件

- [x] `AuthSettings`が`build_container()`で一度生成され、Injectorへsingleton instanceとして登録されている。
- [x] auth controllerの全設定参照が`get_request_auth_settings` dependency経由になっている。
- [x] `is_secure_request()`が注入済み設定だけを使い、関数内部で設定を生成しない。
- [x] app起動後の環境変数変更が既存appの認証設定へ反映されないことを自動testで確認している。
- [x] production fail-closed、HTTPS、proxy header非信用の既存security contractがtestで維持されている。
- [x] backend full pytestがPostgreSQL付きで0 skipped / 0 failedである。
- [x] frontend full test、check、buildが成功している。
- [x] isort、yapf、frontend lint、`git diff --check`がcleanである。
- [x] `backend/AGENTS.md`と`README.md`に起動時snapshotと再起動要件が記載されている。
- [x] dependency、DB schema、migration、API surfaceを変更していない。
- [x] M-1、M-2、admin seedを混在させていない。
- [x] `git add`、`git commit`、`git push`を実行していない。

## 実行結果

- 実行日時: 2026-07-19 10:04:32 JST
- branch / HEAD: `feature/db-auth` / `b8fe01437491b3019e9ffc4d393b1bff7631d4c0`
- Targeted RED:
  - request settings dependency: `get_request_auth_settings`未定義の`AttributeError`で1 failed
  - container binding: `injector.get(AuthSettings) is settings`のidentity不一致で1 failed
  - secure helper: 旧signatureが第2引数を受け取らない`TypeError`で3 failed
  - startup snapshot integration: request時の環境変数再読込によりCSRF Cookieへ`Secure`が付き、`assert "Secure" not in csrf_cookie`で1 failed
- Targeted GREEN:
  - request settings dependency suite: 6 passed
  - container / config suite: 3 passed
  - secure helper suite: 4 passed
  - startup snapshot integration: 1 passed、1 warning
  - auth controller integration suite: 30 passed、4 warnings
- Backend full pytest: 63 passed、0 skipped、0 failed、4 warnings
- Frontend test: 7 files passed、15 tests passed、0 skipped、0 failed
- Quality gate:
  - isort: exit 0（1 file skipped）
  - yapf: exit 0、diffなし
  - frontend check: exit 0、変更なし
  - frontend build: exit 0。`VITE_SITE_URL`未設定warning 3件
  - `git diff --check`: exit 0、outputなし
- 逸脱: 計画のHTTPS helper testは`scheme="https"`だけを持つ相対URL scopeだったため、Starletteがschemeを保持せず最初のGREEN確認で1 failedとなった。実request相当の`server=("testserver", 443)`をtest scopeへ追加し、HTTPS契約を4 passedで確認した。
- 完成時レビュー対応: Composeの`env_file`変更は`restart`では再読込されないため、READMEの反映手順を`docker compose up -d --force-recreate backend`へ修正した。startup snapshot testはrandom token本文との誤一致を避けるため、`SimpleCookie`で`Secure`属性を検証する形へ変更した。
- 再レビュー対応: Injectorが未bindの具象classを暗黙生成するsilent regressionを防ぐidentity assertionについて、削除理由が誤解されないようWHYコメントを追加した。instance bindingに対する`scope=singleton`はcomposition rootのライフサイクル意図を明示し、既存binding様式と揃えるため維持した。独自`TestClient`のDB/rate limiter非依存前提はStep 4.3の注記を維持した。
- 未対応事項: なし

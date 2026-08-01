# Phase 0 レビュー修正 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Worktree、`git add`、`git commit`、`git push`は使用しない。

**Goal:** `documents/reviews/20260801-review.md`のPhase 0で指定された即日修正項目を、既存のFastAPI + SQLModel構成に沿って安全に修正する。

**Architecture:** Phase 0はバックエンドの独立バグ修正として扱う。DB schemaそのものは既存migrationを正とし、SQLModel metadataとAlembic検査をそれに一致させる。静的配信は`backend/static`の有無とcwdに依存しない起動処理へ変える。SPA fallbackはドキュメントナビゲーションだけに限定し、API URLや静的アセット欠落を200 HTMLへ変換しない。

**Tech Stack:** Python 3.12、FastAPI、Starlette StaticFiles、SQLModel、SQLAlchemy、Alembic、Typer、pytest、PostgreSQL 17、Docker Compose

---

## 背景

`documents/reviews/20260801-review.md`では、テンプレート配布前に最優先で直すべき項目として次のPhase 0が提示されている。

- `P0-1`: SQLModel metadataとAlembic migrationの不一致により、次回`alembic revision --autogenerate`で既存の重要indexが削除候補になる。
- `P0-2`: production build後のSPAで`/login`や`/app`を直叩き・リロードすると、`index.html`へfallbackされず404になる。
- `P0-3`: `backend/static/`が無い環境、またはcwdが`backend/`でない環境でbackend appの起動が壊れる。
- `P2-12`: 非ASCII文字を含むCSRF cookie/headerで`secrets.compare_digest(str, str)`が`TypeError`を起こし、未認証でも500を発生させられる。
- `P2-22`: sample / healthz / route / config / usecase周辺に未使用importと、`402: "Forbidden"`という誤ったHTTP status宣言が残っている。

今回の作業対象は、レビュー文書の「4. 推奨修正順序」にある`Phase 0: 即日修正`に限定する。レビュー文書のP0優先度には`P0-4: サインアップUI`も含まれるが、同じレビューの推奨順序では`P0-4`は`P2-30`などのフロント基盤整備後に実施する流れになっている。したがって本計画では`P0-4`を扱わない。

## 現行システムとの整合性

本計画の前提と現行システムに、実装を止める矛盾はない。

- `backend/alembic/versions/20260418_0001_create_auth_tables.py`は、`uq_users_email_lower`、`uq_auth_sessions_session_token_hash`、`ix_auth_audit_logs_event_type`、`users.is_active`の`server_default=sa.true()`を既に作成している。
- `backend/app/models/user.py`、`backend/app/models/auth_session.py`、`backend/app/models/auth_audit_log.py`のmetadata側には、上記の一部が欠落している。
- `backend/app/bootstrap/route.py`は`StaticFiles(directory="static", html=True)`を相対パスでmountしており、cwdと`static/`存在有無に依存している。
- 現在のworking treeには`backend/static/`配下の生成物が存在するが、`.gitignore`は`backend/static/`全体を除外している。clone直後やfrontend未ビルド状態では`index.html`が無い前提でbackend APIが起動できる必要がある。
- `backend/app/controllers/auth_dependencies.py`の`require_csrf()`はcookie/headerの文字列を直接`secrets.compare_digest()`へ渡している。
- `backend/app/controllers/sample_controller.py`は`402`をForbiddenとして宣言している。`healthz_controller.py`、`sample_controller.py`、`create_app.py`、`route.py`、`config/__init__.py`、sample usecase周辺には未使用importがある。

## 方針とその理由

### 採用方針

Phase 0は、後続Phaseの前提になる安全化に絞って進める。

1. 既存migrationを正として、SQLModel metadataをmigrationへ合わせる。
2. Alembicのserver default比較を有効化し、`db-check` CLIとintegration testで「autogenerate差分なし」を継続的に検知する。
3. 静的配信は`backend/static`を絶対パスで解決し、存在しない場合はbackend APIだけで起動できるようにする。
4. SPA fallbackは`index.html`が存在する場合だけ有効にし、`Accept: text/html`または`*/*`のGET/HEADかつ既知静的assetではないURLだけを`index.html`へfallbackさせる。
5. CSRFのtiming-safe比較はUTF-8 bytes同士で行い、非ASCII入力でも500を出さない。
6. 未使用importと誤った`402`宣言は最小限で整理し、sample APIの設計変更は後続の`P2-35`へ残す。

### 採用理由

- `P0-1`は権限管理やOAuthなど、今後のDB作業でautogenerateを使う前提条件である。実DB schemaは既に望ましい形なので、追加migrationではなくmetadataと検査を直すのが最も小さい。
- `P0-2`と`P0-3`はproduction配信とclone直後の起動体験に直接影響する。API route登録とstatic mountの境界を明確にすれば、フロント未ビルドでもbackend開発が止まらない。
- `P2-12`はセキュリティ境界の500化であり、DB不要のunit testで低コストに再発防止できる。
- `P2-22`はテンプレート利用者が真似るサンプルの品質問題である。Phase 0では誤ったHTTP statusと明らかな未使用importだけを除去し、エラーエンベロープやRESTサンプル再設計は別Phaseへ分離する。

## デザイン決定

### 決定1: Phase 0では`P0-4`を実装しない

`P0-4`は優先度上はP0だが、レビュー文書の推奨修正順序ではPhase 3に置かれており、`P1-19`、`P1-18`、`P2-30`などのフロント基盤整備後に実装すると明記されている。本計画はユーザー指定の「Phase 0」を対象にするため、Phase 0一覧に含まれる項目だけを扱う。

### 決定2: `P0-1`では新規migrationを作らない

既存の初回migrationは望ましいindexとserver defaultを既に作成している。問題はモデルmetadataがmigrationに追いついていない点である。新規migrationを作ると、既に存在するindex/defaultを再作成しようとする危険があるため、モデル、Alembic設定、検査のみを追加する。

### 決定3: `backend/static/.gitkeep`は追加せず、SPA mountの条件は`index.html`存在で判定する

`setup_routes()`は`backend/static/index.html`が存在する場合だけSPA static mountを有効化し、存在しない場合は警告ログを出してAPIだけで起動する。この判定にすると`backend/static/` directory自体をtrackedにする必要がないため、`.gitkeep`は追加しない。frontend build成果物をignoreしたまま、clone直後やfrontend未ビルド時のbackend API起動をコード側で保証する。

### 決定4: SPA fallbackはドキュメントナビゲーションだけへ適用する

未知のAPI URLや欠落した静的アセットが`index.html`を返すと、API client、監視、ブラウザのchunk loaderが誤った200を受け取る。`SPAStaticFiles.get_response()`では、`API_PREFIX`配下を事前に404へ落とす。その他の404は、GET/HEAD、`Accept: text/html`または`*/*`、既知の静的asset pathではない、という条件を満たす場合だけ`index.html`へfallbackする。これにより`/login`や`/users/john.doe`のようなSPA deep linkは救済し、`/assets/missing.js`、`/favicon.ico`、`/robots.txt`、`POST /api/unknown`は200 HTMLにしない。

### 決定6: `db-check`はconfig層で明示設定されたDB URLだけを許可する

`DatabaseSettings`には開発用の既定値があるため、`ALEMBIC_DATABASE_URL`未設定のまま`db-check`を実行すると、意図したDBではなく`localhost:5432/app`を検査して緑になる可能性がある。一方で、開発者は`.env`で正しい接続先を設定するため、`os.environ`だけを見ると正当な`.env`設定を拒否してしまう。Phase 0の`db-check`は、`get_database_settings()`で`.env`を含めて解決した値を使い、その値がコード上の既定値と一致する場合だけexit 2でfail-fastする。成功時は資格情報を除いた接続先をstderrへ出力し、どのDBを検査したかをレビューやCIログで確認できるようにする。

### 決定5: `P2-22`ではsample APIのURLやレスポンス形式を変えない

`/api/sample/`の末尾スラッシュ問題や`Status`成功エンベロープは`P2-35`および`P1-8`の対象である。Phase 0で同時に直すとAPI surface変更が混ざり、修正範囲が大きくなる。今回は`402`を`403`に直し、未使用importを消すところまでに留める。

## 逸脱

- レビューの`P0-3`は「存在しなければmountをスキップして警告ログを出す、または`makedirs`」と書いている。本計画では「`index.html`が無ければmountをスキップして警告ログを出す」を採用する。空のstatic directoryをmountすると、frontend build未実施でもstatic mountが有効になり、`/login`などが理由不明の404になるためである。
- レビューの`P0-2`は`route.py`に`SPAStaticFiles`を定義すると書いている。本計画では同じ`route.py`内に定義するが、test容易性のため`setup_routes(app, static_directory=None)`の任意引数も追加する。既存の`setup_routes(app)`呼び出しは維持される。
- レビューの`P2-22`はruff導入にも触れているが、本計画では導入しない。ruffやmypy、CIは`P2-23`のスコープであり、依存追加も必要になるためである。

## トレードオフと不採用案

### 不採用案1: DB schema差分を新規migrationで解消する

既存migrationがすでに正しいschemaを作るため、新規migrationは重複index作成や環境依存の失敗を招く。metadataを修正し、`alembic command.check`相当の検査を追加する方が安全である。

### 不採用案2: static directoryが無ければ自動作成する

起動は成功するが、frontend build成果物が無い状態と空directoryだけある状態を区別しづらくなる。API開発中はstatic mount自体をスキップし、警告ログで理由を知らせる方が明確である。

### 不採用案3: `backend/static/.gitkeep`をtrackedにする

`index.html`存在でmount可否を判定する設計では、`backend/static/` directoryの存在は起動可否に影響しない。`.gitkeep`を残すと、Viteの`emptyOutDir: true`により`npm run build`のたびに消え、復元手順と`.gitignore`例外を恒久的に持つことになる。機能上不要な運用負債を増やすため採用しない。

### 不採用案4: catch-all API routeでSPA fallbackを実装する

FastAPI routeとstatic mountの順序が複雑になり、未知API URLに200を返す事故を起こしやすい。Starletteの`StaticFiles`を継承し、static配信の責務内でfallbackを閉じる。

### 不採用案5: 非ASCII CSRFを400として明示拒否する

生成されるCSRF tokenはASCIIだが、現行のdouble-submit実装は未認証unsafe requestでcookie/header一致を見ている。Phase 0では既存仕様を広げず狭めず、「一致比較で500を出さない」ことに限定する。CSRF token形式の厳格validationは`P1-14`のmiddleware化と同時に設計する。

---

## File Structure

### 変更するファイル

- `backend/app/models/user.py`
  - `uq_users_email_lower`と`is_active.server_default`をSQLModel metadataへ追加する。
- `backend/app/models/auth_session.py`
  - `uq_auth_sessions_session_token_hash`をSQLModel metadataへ追加する。
- `backend/app/models/auth_audit_log.py`
  - `ix_auth_audit_logs_event_type`をSQLModel metadataへ追加する。
- `backend/app/models/status.py`
  - 未使用の`Field` importを削除する。
- `backend/alembic/env.py`
  - online/offline両方の`context.configure()`へ`compare_server_default=True`を追加する。Alembicの`fileConfig()`が既存loggerを無効化しないようにする。
- `backend/alembic.ini`
  - `script_location`を`%(here)s/alembic`、`prepend_sys_path`を`%(here)s`に変更し、Alembic script pathと`app` import pathをcwdではなくiniファイル位置基準で解決する。
- `backend/manage.py`
  - `db-check`コマンドを追加し、Alembic autogenerate差分がないことをCLIで確認できるようにする。`db-check`ではconfig層で解決した`ALEMBIC_DATABASE_URL`が既定値と一致する場合にfail-fastし、成功時は資格情報を除いた接続先を出力する。`db-upgrade` / `db-downgrade` / `db-check`はいずれもTyperのコマンド名を明示し、`db-downgrade`のrevisionは必須引数にする。
- `backend/pyproject.toml`
  - isortで`alembic`をthird-partyとして扱い、`backend/alembic/` directoryとのimport分類衝突を防ぐ。生成済みmigrationはスキーマ正典として扱うため、`alembic/versions/*.py`はisort対象外にする。
- `backend/app/bootstrap/route.py`
  - `SPAStaticFiles`、static directory絶対解決、static未存在時のmount skip、API除外、ドキュメントナビゲーション限定のSPA fallbackを実装する。`Accept: */*`とdotted slugはSPA routeとして許可し、既知の静的asset pathはfallbackしない。
- `backend/app/controllers/auth_dependencies.py`
  - CSRF cookie/headerをUTF-8 bytesへ変換してから`secrets.compare_digest()`へ渡す。
- `backend/app/controllers/sample_controller.py`
  - 未使用importを削除し、`402`を`403`へ修正する。
- `backend/app/controllers/healthz_controller.py`
  - 未使用importと未使用`request`引数を削除する。
- `backend/app/bootstrap/create_app.py`
  - 未使用middleware importを削除する。
- `backend/app/config/__init__.py`
  - Phase 0で安全に消せる未使用importと死に代入を削除する。設定仕様の統合は`P2-20`へ残す。
- `backend/app/usecases/get_sample_index_usecase.py`
  - 未使用`Tuple` importを削除する。
- `backend/app/interfaces/usecases/get_sample_index_usecase_interface.py`
  - 未使用`Tuple` importを削除する。
- `docker-compose.yaml`
  - backend commandから`mkdir -p static &&`を削除し、アプリ側のstatic処理を正とする。
- `backend/tests/unit/models/test_auth_models.py`
  - metadataに必要なindexとserver defaultが登録されていることを検証する。
- `backend/tests/unit/test_manage.py`
  - `db-check`がAlembic checkを呼ぶこと、Alembic configが`manage.py`基準の絶対パスを使うこと、`.env`または環境変数で明示設定された`ALEMBIC_DATABASE_URL`を受け入れること、未設定時にfail-fastすること、DB系コマンド名が明示されていること、`db-downgrade`が明示revisionを要求することを検証する。
- `backend/tests/integration/conftest.py`
  - `require_test_database_url()`を`helpers.py`からimportする形に変更し、helper定義を1箇所へ集約する。
- `backend/tests/integration/helpers.py`
  - integration testで共有する`TEST_DATABASE_URL`必須化ヘルパを置き、`conftest.py`を通常moduleとしてimportしない。
- `backend/tests/integration/test_migration_consistency.py`
  - Alembic上のschema差分がないことを実DBで検証する。
- `backend/tests/unit/bootstrap/test_route.py`
  - static未存在、SPA fallback、`Accept: */*`、dotted slug、API除外、static asset配信、欠落asset 404、非HTML request 404、`POST /api/unknown` 404を検証する。
- `backend/tests/unit/controllers/test_auth_dependencies.py`
  - 非ASCII CSRF mismatchが500ではなく403になること、timing-safe比較がbytesで呼ばれることを検証する。
- `backend/tests/unit/controllers/test_sample_controller.py`
  - sample routerのOpenAPI responsesに`402`が残っていないことを検証する。
- `documents/plans/20260801-phase0-review-fixes.md`
  - 実装中の進捗と検証結果を更新する。

### 変更しないファイル

- `backend/alembic/versions/20260418_0001_create_auth_tables.py`
  - 既存migrationは正しいschemaを作成済みのため変更しない。
- frontend配下
  - Phase 0対象外。`P0-4`、`P2-26`以降は後続Phaseで扱う。
- 認証usecase / repository
  - Phase 0ではCSRF比較前の入力処理だけを直し、session検証や三値戻り値は`P2-14`へ残す。

---

## 進捗サマリー

- [x] Task 1: baselineと変更境界を固定する
- [x] Task 2: モデルmetadataとAlembic検査をtest-firstで追加する
- [x] Task 3: `db-check` CLIを追加する
- [x] Task 4: static配信をcwd非依存かつSPA deep link対応にする
- [x] Task 5: CSRFの非ASCII 500を防ぐ
- [x] Task 6: sample / healthz周辺の明らかなサンプル品質問題を整理する
- [x] Task 7: Docker Composeのstatic directory回避処理を削除する
- [x] Task 8: 品質ゲートを実行し、計画書へ結果を記録する
- [x] Task 9: scopeと未対応事項を最終確認する
- [x] Task 10: Claude Codeレビュー後の残課題を補正する
- [x] Task 11: Claude Code再レビュー後の新規問題を補正する
- [x] Task 12: Claude Code再々レビュー後の`db-check`判定を補正する

## 具体的なタスク

### Task 1: baselineと変更境界を固定する

**Files:**
- Inspect: `documents/reviews/20260801-review.md`
- Inspect: `backend/AGENTS.md`
- Inspect: `backend/app/models/`
- Inspect: `backend/app/bootstrap/`
- Inspect: `backend/app/controllers/`
- Inspect: `backend/tests/`
- Inspect: `.gitignore`
- Inspect: `docker-compose.yaml`

**Interfaces:**
- Consumes: 現在のworking tree、レビュー文書、backend固有ルール
- Produces: Phase 0以外の変更を混ぜないためのbaseline

- [x] **Step 1.1: branch、HEAD、working treeを記録する**

Repository rootで実行する。

```bash
rtk git branch --show-current
rtk git rev-parse HEAD
rtk git status --short
```

Expected:

- 現在のbranchとHEADが表示される。
- 既存の未コミット変更があれば、Phase 0と関係するかを確認する。
- 既存変更をreset、checkout、cleanしない。
- `git add`、`git commit`、`git push`を実行しない。

- [x] **Step 1.2: Phase 0対象を再確認する**

```bash
rtk grep -n "Phase 0|P0-1|P0-2|P0-3|P2-12|P2-22|P0-4" documents/reviews/20260801-review.md
```

Expected:

- Phase 0一覧が`P0-1`、`P0-2`、`P0-3`、`P2-12`、`P2-22`であることを確認する。
- `P0-4`はP0優先度だが、レビュー文書の推奨順序ではPhase 3相当であることを確認する。

- [x] **Step 1.3: 変更対象の現状を確認する**

```bash
rtk grep -n "StaticFiles|compare_digest|server_default|__table_args__|402|Forbidden|compare_server_default|db_check|db-check" backend/app backend/alembic backend/manage.py
```

Expected:

- `StaticFiles(directory="static", html=True)`が相対パスで使われている。
- `require_csrf()`が`secrets.compare_digest(cookie_token, header_token)`を使っている。
- auth model側に必要な`__table_args__`が不足している。
- `alembic/env.py`に`compare_server_default=True`が無い。
- `manage.py`に`db-check`コマンドが無い。
- `sample_controller.py`に`402: ... "Forbidden"`が残っている。

- [x] **Step 1.4: Phase 0の変更禁止事項を明文化してから実装へ進む**

Run: なし。

Expected:

- 新規Alembic revisionは作らない。
- frontend配下は変更しない。
- sample APIのpath、response body形式、usecase同期/非同期設計は変更しない。
- auth session検証、rate limiter、error envelope、production docs制御は変更しない。
- worktree、staging、commitは行わない。

### Task 2: モデルmetadataとAlembic検査をtest-firstで追加する

**Files:**
- Modify: `backend/tests/unit/models/test_auth_models.py`
- Create: `backend/tests/integration/helpers.py`
- Modify: `backend/tests/integration/conftest.py`
- Create: `backend/tests/integration/test_migration_consistency.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/auth_session.py`
- Modify: `backend/app/models/auth_audit_log.py`
- Modify: `backend/alembic/env.py`

**Interfaces:**
- Consumes: `SQLModel.metadata`、既存initial migration、`TEST_DATABASE_URL`
- Produces: migrationとmetadataが一致していることをunit/integration両方で検知する回帰ガード

- [x] **Step 2.1: metadata index/defaultのfailing unit testを書く**

`backend/tests/unit/models/test_auth_models.py`へ次のtestを追加する。

```python
def test_auth_model_metadata_matches_auth_migration_indexes_and_defaults():
    users = SQLModel.metadata.tables["users"]
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]

    assert "uq_users_email_lower" in {index.name for index in users.indexes}
    assert "uq_auth_sessions_session_token_hash" in {
        index.name for index in auth_sessions.indexes
    }
    assert "ix_auth_audit_logs_event_type" in {
        index.name for index in auth_audit_logs.indexes
    }
    assert users.c.is_active.server_default is not None
```

- [x] **Step 2.2: metadata unit testを実行してREDを確認する**

`backend/`で実行する。

```bash
rtk uv run pytest tests/unit/models/test_auth_models.py::test_auth_model_metadata_matches_auth_migration_indexes_and_defaults -q
```

Expected:

- `uq_users_email_lower`、`uq_auth_sessions_session_token_hash`、`ix_auth_audit_logs_event_type`、または`is_active.server_default`の不足によりFAILする。
- import errorや既存test破壊で失敗した場合は、REDとして扱わずtestを直す。

- [x] **Step 2.3: integration test用のDB URL helperを分離する**

`backend/tests/integration/helpers.py`を作成する。

```python
import os

import pytest


def require_test_database_url() -> str:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is required for integration tests")
    return test_database_url
```

`backend/tests/integration/conftest.py`は既存の`require_test_database_url()`定義を削除し、次のimportへ置き換える。

```python
from tests.integration.helpers import require_test_database_url
```

この分離により、通常のtest moduleから`conftest.py`をimportしてpytestのconftest loaderと二重ロードする状態を避ける。

- [x] **Step 2.4: Alembic checkのfailing integration testを書く**

`backend/tests/integration/test_migration_consistency.py`を作成する。

```python
from pathlib import Path

from alembic import command
from alembic.config import Config

from tests.integration.helpers import require_test_database_url


def test_alembic_metadata_has_no_pending_schema_changes(monkeypatch):
    test_database_url = require_test_database_url()
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv(
        "ALEMBIC_DATABASE_URL",
        test_database_url.replace("+asyncpg", ""),
    )

    alembic_config = Config(
        str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)
```

このtestは既存integration fixtureと同じ`TEST_DATABASE_URL`を使う。`command.upgrade()`でheadへ揃えてから`command.check()`を実行するため、schema未作成のtest DBでも実行できる。
この新規testには`pytestmark`を付けない。既存integration testのmarker運用は混在しているため、Phase 0では新しい方針を増やさず、skipをfailにする運用整理は`P1-16`へ残す。

- [x] **Step 2.5: Alembic check integration testを実行してREDを確認する**

`backend/`で実行する。

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest tests/integration/test_migration_consistency.py::test_alembic_metadata_has_no_pending_schema_changes -q
```

Expected:

- autogenerate差分が検出されてFAILする。
- PostgreSQL未起動、`app_test`未作成、接続先不一致による失敗はREDとして扱わず、test DBを準備して再実行する。

- [x] **Step 2.6: `User` metadataへexpression unique indexとserver defaultを追加する**

`backend/app/models/user.py`のSQLAlchemy importを次へ変更する。

```python
from sqlalchemy import Boolean, Column, DateTime, Index, String, text
```

`User` classへ`__table_args__`を追加し、`is_active`のColumnへ`server_default=text("true")`を追加する。

```python
class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(sa_column=Column(String(length=320), nullable=False), )
    password_hash: str = Field(sa_column=Column(String(length=255),
                                                nullable=False), )
    is_active: bool = Field(sa_column=Column(Boolean,
                                             nullable=False,
                                             default=True,
                                             server_default=text("true")), )
```

既存migrationの`sa.true()`と同じPostgreSQL schemaを表すため、DBへ新しい変更は発生しない想定である。

- [x] **Step 2.7: `AuthSession` metadataへsession token unique indexを追加する**

`backend/app/models/auth_session.py`のSQLAlchemy importを次へ変更する。

```python
from sqlalchemy import Column, DateTime, Index, String
```

`AuthSession` classへ`__table_args__`を追加する。

```python
class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index(
            "uq_auth_sessions_session_token_hash",
            "session_token_hash",
            unique=True,
        ),
    )
```

- [x] **Step 2.8: `AuthAuditLog` metadataへevent_type indexを追加する**

`backend/app/models/auth_audit_log.py`のSQLAlchemy importを次へ変更する。

```python
from sqlalchemy import Column, DateTime, Index, String
```

`AuthAuditLog` classへ`__table_args__`を追加する。

```python
class AuthAuditLog(SQLModel, table=True):
    __tablename__ = "auth_audit_logs"
    __table_args__ = (
        Index("ix_auth_audit_logs_event_type", "event_type"),
    )
```

- [x] **Step 2.9: Alembicのserver default比較を有効化する**

`backend/alembic/env.py`のoffline/online両方の`context.configure()`へ`compare_server_default=True`を追加する。

```python
context.configure(
    url=get_database_url(),
    target_metadata=target_metadata,
    literal_binds=True,
    dialect_opts={"paramstyle": "named"},
    compare_type=True,
    compare_server_default=True,
)
```

```python
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    compare_type=True,
    compare_server_default=True,
)
```

- [x] **Step 2.10: metadata unit testをGREENにする**

```bash
rtk uv run pytest tests/unit/models/test_auth_models.py -q
```

Expected:

- 全test passed、0 failed。
- `users`、`auth_sessions`、`auth_audit_logs`がmetadataへ登録されている既存testも維持される。

- [x] **Step 2.11: Alembic check integration testをGREENにする**

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest tests/integration/test_migration_consistency.py -q
```

Expected:

- 1 passed、0 skipped、0 failed。
- `command.check()`がpending schema changeなしで完了する。

### Task 3: `db-check` CLIを追加する

**Files:**
- Modify: `backend/manage.py`
- Modify: `backend/alembic.ini`
- Create or Modify: `backend/tests/unit/test_manage.py`

**Interfaces:**
- Consumes: Alembic `command.check`
- Produces: `python manage.py db-check`でschema差分検査を実行できるCLI

- [x] **Step 3.1: manage CLI test fileの配置を確認する**

Repository rootで実行する。

```bash
rtk find "test_manage.py" backend/tests
```

Expected:

- 既存fileがあればそこへ追記する。
- 無ければ`backend/tests/unit/test_manage.py`を作成する。

- [x] **Step 3.2: `db-check`のfailing unit testを書く**

`backend/tests/unit/test_manage.py`を作成、または既存fileへ追記する。

```python
from pathlib import Path

from typer.testing import CliRunner

import manage


def test_db_check_invokes_alembic_check(monkeypatch):
    calls = []

    class ConfigStub:

        def __init__(self, path):
            calls.append(("config", path))

    class CommandStub:

        @staticmethod
        def check(config):
            calls.append(("check", config))

    monkeypatch.setattr(manage, "AlembicConfig", ConfigStub)
    monkeypatch.setattr(manage, "alembic_command", CommandStub)

    result = CliRunner().invoke(manage.app, ["db-check"])

    assert result.exit_code == 0
    assert calls[0] == (
        "config",
        str(Path(manage.__file__).resolve().parent / "alembic.ini"),
    )
    assert calls[1][0] == "check"
```

このtestを成立させるため、`manage.py`ではAlembic importをmodule top-levelに出す。CLI起動時にDB接続は発生しない。`alembic.ini`はcwdではなく`manage.py`からの絶対パスで解決する。

- [x] **Step 3.3: `db-check` unit testを実行してREDを確認する**

```bash
rtk uv run pytest tests/unit/test_manage.py::test_db_check_invokes_alembic_check -q
```

Expected:

- `db-check`コマンド未定義、または`AlembicConfig`未定義によりFAILする。

- [x] **Step 3.4: `alembic.ini`のscript pathとimport pathをcwd非依存にする**

`backend/alembic.ini`の`script_location`と`prepend_sys_path`を次へ変更する。

```ini
script_location = %(here)s/alembic
prepend_sys_path = %(here)s
```

`%(here)s`はAlembicがiniファイルのあるdirectoryへ展開する。`AlembicConfig`へ絶対パスを渡しても、`script_location = alembic`のままだとprocess cwd基準で`alembic/`を探すため、`manage.py`を別cwdから実行すると壊れる。また`prepend_sys_path = .`のままだと、別cwdから`uv run alembic revision --autogenerate ...`を実行したときに`env.py`の`import app.models`がcwd依存になる。同じ`alembic.ini`内で両方を`%(here)s`基準へ揃える。

このStepでは`.env`探索のcwd依存は直さない。`DatabaseSettings.model_config.env_file = ".env"`と`load_dotenv()`は依然cwd基準なので、別cwdからDB CLIを実行する場合は`DATABASE_URL`と`ALEMBIC_DATABASE_URL`を環境変数で明示する。`.env`探索の統一は`P2-20`または`P3-6`で扱う。

- [x] **Step 3.5: `manage.py`へ`db_check`を実装する**

`backend/manage.py`を次の方針で変更する。

```python
from pathlib import Path

import typer
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

app = typer.Typer()
ALEMBIC_INI = Path(__file__).resolve().parent / "alembic.ini"


def _alembic_config() -> AlembicConfig:
    return AlembicConfig(str(ALEMBIC_INI))
```

既存の`db_upgrade()`と`db_downgrade()`は`_alembic_config()`を使う。

```python
@app.command("db-upgrade")
def db_upgrade(revision: str = "head"):
    alembic_command.upgrade(_alembic_config(), revision)


@app.command("db-downgrade")
def db_downgrade(revision: str = "base"):
    alembic_command.downgrade(_alembic_config(), revision)


@app.command("db-check")
def db_check():
    alembic_command.check(_alembic_config())
```

`serve()`と`version()`の仕様はPhase 0では変更しない。

- [x] **Step 3.6: manage CLI unit testをGREENにする**

```bash
rtk uv run pytest tests/unit/test_manage.py -q
```

Expected:

- 全test passed、0 failed。

- [x] **Step 3.7: 実CLIで`db-check`を別cwdからGREENにする**

Repository rootで実行する。command内でrepository rootを変数化してから`/tmp`へ移動するため、実際の`manage.py`実行cwdは`/tmp`になる。接続先は`.env`に依存させず、環境変数で明示する。

```bash
rtk proxy sh -c 'set -e; REPO_ROOT=$(git rev-parse --show-toplevel); cd /tmp; DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test PYTHONPATH="$REPO_ROOT/backend" uv --project "$REPO_ROOT/backend" run python "$REPO_ROOT/backend/manage.py" db-check'
```

Expected:

- exit 0。
- Alembicがpending schema changeなしを報告する。
- `CommandError: Path doesn't exist: alembic`が出ない。
- `ModuleNotFoundError: No module named 'app'`が出ない。
- 個人環境の絶対パスを計画に埋め込まず、`git rev-parse --show-toplevel`からリポジトリrootを解決している。

### Task 4: static配信をcwd非依存かつSPA deep link対応にする

**Files:**
- Modify: `backend/app/bootstrap/route.py`
- Create: `backend/tests/unit/bootstrap/test_route.py`

**Interfaces:**
- Consumes: FastAPI route登録、Starlette `StaticFiles`
- Produces: static未存在でも起動するbackend、SPA deep link fallback、`/api`除外

- [x] **Step 4.1: route挙動のfailing unit testsを書く**

`backend/tests/unit/bootstrap/test_route.py`を作成する。

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.route import setup_routes


def _client_with_static(static_directory: Path) -> TestClient:
    app = FastAPI()
    setup_routes(app, static_directory=static_directory)
    return TestClient(app)


def test_setup_routes_starts_without_static_directory(tmp_path):
    client = _client_with_static(tmp_path / "missing-static")

    response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "ok"}


def test_setup_routes_skips_static_mount_when_index_html_is_missing(tmp_path, caplog):
    (tmp_path / "placeholder.txt").write_text("", encoding="utf-8")

    with caplog.at_level("WARNING", logger="app.bootstrap.route"):
        client = _client_with_static(tmp_path)

    assert client.get("/api/healthz").status_code == 200
    assert client.get("/login").status_code == 404
    assert "index.html" in caplog.text


def test_spa_deep_link_falls_back_to_index_html(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/login")

    assert response.status_code == 200
    assert response.text == "<main>spa shell</main>"


def test_static_assets_are_served_without_spa_fallback(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.css").write_text("body { color: black; }", encoding="utf-8")
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/assets/app.css")

    assert response.status_code == 200
    assert response.text == "body { color: black; }"


def test_unknown_api_path_does_not_fall_back_to_spa_index(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/api/unknown")

    assert response.status_code == 404
    assert response.text != "<main>spa shell</main>"


def test_uppercase_api_path_does_not_fall_back_to_spa_index(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/API/unknown")

    assert response.status_code == 404
    assert response.text != "<main>spa shell</main>"
```

- [x] **Step 4.2: route unit testsを実行してREDを確認する**

```bash
rtk uv run pytest tests/unit/bootstrap/test_route.py -q
```

Expected:

- 現行`setup_routes()`が`static_directory`引数を受け取らないためFAILする。

- [x] **Step 4.3: `SPAStaticFiles`とstatic directory解決を実装する**

`backend/app/bootstrap/route.py`を次の方針で変更する。

```python
import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from app.controllers.auth_controller import router as auth_router
from app.controllers.healthz_controller import router as healthz_router
from app.controllers.sample_controller import router as sample_router

logger = logging.getLogger(__name__)
STATIC_DIRECTORY = Path(__file__).resolve().parents[2] / "static"


class SPAStaticFiles(StaticFiles):

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            api_path = path.lower()
            # Client-side routes fall back to the SPA shell; API misses must not become 200 HTML.
            if (error.status_code != 404 or api_path == "api"
                    or api_path.startswith("api/")):
                raise
            return await super().get_response("index.html", scope)


def setup_routes(
    app: FastAPI,
    static_directory: Path | None = None,
) -> FastAPI:
    app = _setup_api_routes(app)
    directory = static_directory or STATIC_DIRECTORY
    index_file = directory / "index.html"
    if not index_file.exists():
        logger.warning(
            "Static index.html does not exist; skipping SPA mount: %s",
            index_file,
        )
        return app
    app.mount("/", SPAStaticFiles(directory=directory, html=True), name="static")
    return app
```

WHYコメントは、`SPAStaticFiles.get_response()`またはstatic skipの近くに短く追加する。内容は「client-side routesは`index.html`へ戻すが、APIの404を200へ変えない」で十分である。`/api`除外は小文字化して判定し、`/API/unknown`もfallbackさせない。

- [x] **Step 4.4: route unit testsをGREENにする**

```bash
rtk uv run pytest tests/unit/bootstrap/test_route.py -q
```

Expected:

- 全test passed、0 failed。
- static directoryが無くても`/api/healthz`が200を返す。
- static directoryが存在しても`index.html`が無ければSPA mountをスキップし、`/login`は404、警告ログには`index.html`が含まれる。
- `/login`が`index.html`へfallbackする。
- `/assets/app.css`はassetとしてそのまま返る。
- `/api/unknown`は404のままになる。
- `/API/unknown`も404のままになる。

- [x] **Step 4.5: `create_app()`がcwdに依存しないことを確認する**

`backend/`で実行する。

```bash
rtk uv run python -c "import os, tempfile; from app.bootstrap.create_app import create_app; os.chdir(tempfile.mkdtemp()); app = create_app(); print(bool(app.routes))"
```

Expected:

- exit 0。
- `True`が出力される。
- cwdを一時directoryへ変えても`create_app()`が`RuntimeError: Directory 'static' does not exist`を出さない。

### Task 5: CSRFの非ASCII 500を防ぐ

**Files:**
- Modify: `backend/tests/unit/controllers/test_auth_dependencies.py`
- Modify: `backend/app/controllers/auth_dependencies.py`

**Interfaces:**
- Consumes: CSRF cookie、`X-CSRF-Token` header
- Produces: 非ASCII入力でも500を出さないtiming-safe比較

- [x] **Step 5.1: CSRF test helperをheader override可能にする**

`backend/tests/unit/controllers/test_auth_dependencies.py`のhelper signatureを次へ変更する。

```python
from fastapi import HTTPException


def _request_with_csrf_cookie_and_header(
    token: str,
    session_token: str | None = None,
    app=None,
    header_token: str | None = None,
) -> Request:
    cookie = f"csrf_token={token}"
    if session_token:
        cookie = f"{cookie}; session_token={session_token}"
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/logout",
        "app": app,
        "headers": [
            (b"cookie", cookie.encode("utf-8")),
            (b"x-csrf-token", (header_token or token).encode("utf-8")),
        ],
    })
```

既存testは`header_token`を渡さなければ従来と同じ入力になる。

- [x] **Step 5.2: 非ASCII mismatchのfailing regression testを書く**

同じtest fileへ次を追加する。

```python
@pytest.mark.asyncio
async def test_require_csrf_rejects_non_ascii_mismatch_without_type_error():
    request = Request({
        "type":
        "http",
        "method":
        "POST",
        "path":
        "/api/auth/logout",
        "headers": [
            (b"cookie", b"csrf_token=caf\xe9"),
            (b"x-csrf-token", b"caf\xe8"),
        ],
    })

    with pytest.raises(HTTPException) as error:
        await auth_dependencies.require_csrf(request)

    assert error.value.status_code == 403
```

- [x] **Step 5.3: timing-safe比較testの期待値をbytesへ変更する**

既存の`test_require_csrf_uses_timing_safe_compare`のassertionを次へ変更する。

```python
compare_digest.assert_called_once_with(b"csrf-token", b"csrf-token")
```

- [x] **Step 5.4: CSRF targeted testsを実行してREDを確認する**

```bash
rtk uv run pytest tests/unit/controllers/test_auth_dependencies.py::test_require_csrf_rejects_non_ascii_mismatch_without_type_error tests/unit/controllers/test_auth_dependencies.py::test_require_csrf_uses_timing_safe_compare -q
```

Expected:

- 非ASCII mismatch testは`pytest.raises(HTTPException)`の外へ`TypeError`が出ることでFAILする。
- timing-safe比較testは現行実装がstrを渡すためFAILする。

- [x] **Step 5.5: `require_csrf()`をbytes比較へ変更する**

`backend/app/controllers/auth_dependencies.py`の`require_csrf()`を次の形へ変更する。

```python
async def require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token:
        raise HTTPException(status_code=403, detail="CSRF validation failed")

    if not secrets.compare_digest(
        cookie_token.encode("utf-8"),
        header_token.encode("utf-8"),
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed")

    session_token = request.cookies.get("session_token")
    if not session_token:
        return

    # DB-bound validation remains required for authenticated unsafe requests.
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    is_valid_session_csrf = await usecase.validate_session_csrf(
        session_token=session_token,
        csrf_token=header_token,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    if is_valid_session_csrf is False:
        raise HTTPException(status_code=403, detail="CSRF validation failed")
```

DB-bound CSRF検証へ渡す`csrf_token=header_token`はstrのまま維持する。`hash_token()`がstrを受け取る既存interfaceを変更しないためである。

- [x] **Step 5.6: CSRF unit suiteをGREENにする**

```bash
rtk uv run pytest tests/unit/controllers/test_auth_dependencies.py -q
```

Expected:

- 全test passed、0 failed。
- 非ASCII mismatchは403になり、500にならない。
- `secrets.compare_digest()`はbytes同士で呼ばれる。
- 認証済みunsafe requestでは、引き続き`AuthUsecaseInterface.validate_session_csrf()`で`auth_sessions.csrf_token_hash`とのDB-bound照合を行う。

### Task 6: sample / healthz周辺の明らかなサンプル品質問題を整理する

**Files:**
- Modify: `backend/app/controllers/sample_controller.py`
- Modify: `backend/app/controllers/healthz_controller.py`
- Modify: `backend/app/bootstrap/create_app.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/app/config/__init__.py`
- Modify: `backend/app/usecases/get_sample_index_usecase.py`
- Modify: `backend/app/interfaces/usecases/get_sample_index_usecase_interface.py`
- Create: `backend/tests/unit/controllers/test_sample_controller.py`

**Interfaces:**
- Consumes: sample router OpenAPI metadata
- Produces: Forbidden statusが403で宣言され、既知の未使用importが消えた状態

- [x] **Step 6.1: sample routerの`402`回帰testを書く**

`backend/tests/unit/controllers/test_sample_controller.py`を作成する。

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.sample_controller import router


def test_sample_router_does_not_document_forbidden_as_402():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    responses = client.get("/openapi.json").json()["paths"]["/api/sample/"]["get"][
        "responses"
    ]

    assert "402" not in responses
    assert "403" in responses
```

このtestでは`/api/sample/`のpathを維持する。末尾スラッシュ無し化は`P2-35`の対象である。

- [x] **Step 6.2: sample router testを実行してREDを確認する**

```bash
rtk uv run pytest tests/unit/controllers/test_sample_controller.py::test_sample_router_does_not_document_forbidden_as_402 -q
```

Expected:

- 現行OpenAPI responsesに`402`があるためFAILする。

- [x] **Step 6.3: `sample_controller.py`の未使用importと`402`を修正する**

`backend/app/controllers/sample_controller.py`を次の方針で変更する。

```python
from fastapi import APIRouter, Request
```

responsesは次のようにする。

```python
responses={
    401: Status(success=False, message="Unauthorized").model_dump(),
    403: Status(success=False, message="Forbidden").model_dump(),
    404: Status(success=False, message="Not found").model_dump(),
},
```

- [x] **Step 6.4: `healthz_controller.py`の未使用importと未使用引数を削除する**

`backend/app/controllers/healthz_controller.py`を次の方針で変更する。

```python
from fastapi import APIRouter

from app.models.status import Status
```

handler signatureを次に変更する。

```python
@router.get("/healthz")
async def healthz() -> Status:
    return Status(success=True, message="ok")
```

- [x] **Step 6.5: `create_app.py`の未使用middleware importを削除する**

`backend/app/bootstrap/create_app.py`から次のimportを削除する。

```python
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
```

`create_app()`の戻り値や`environment`引数はPhase 0では変更しない。

- [x] **Step 6.6: `route.py`の未使用`Status` importを削除する**

Task 4で`route.py`を変更済みの場合、`from app.models.status import Status`が残っていないことを確認する。残っていれば削除する。

- [x] **Step 6.7: `Config`の死に代入を最小削除する**

`backend/app/config/__init__.py`から未使用`Optional` importと`__init__()`内の`_env`代入を削除し、既存の`Config` fieldを維持する。

```python
import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Config(BaseSettings):
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")


config = Config()
```

`ENVIRONMENT`の既定値や設定クラス全体の様式統一は`P2-20`へ残す。

- [x] **Step 6.8: sample usecase周辺の未使用`Tuple` importを削除する**

`backend/app/usecases/get_sample_index_usecase.py`と`backend/app/interfaces/usecases/get_sample_index_usecase_interface.py`で、`Tuple`だけを削除する。

```python
from typing import Optional
```

`Optional[Status]`の戻り値型はPhase 0では維持する。sample usecaseのasync化やCRUD化は`P3-8`へ残す。

- [x] **Step 6.9: 既知の未使用importが消えたことを確認する**

```bash
rtk grep -n "HTTPException|Query|CORSMiddleware|GZipMiddleware|Optional, Tuple|, Tuple|from app.models.status import Status" backend/app/bootstrap backend/app/config backend/app/controllers backend/app/usecases backend/app/interfaces
```

Expected:

- `auth_controller.py`と`auth_dependencies.py`など、実際に`HTTPException`を使うfileは表示されてよい。
- `sample_controller.py`、`healthz_controller.py`、`create_app.py`、`route.py`、sample usecase/interfaceに、Task 6で削除対象にした未使用importが残っていない。

- [x] **Step 6.10: sample router testをGREENにする**

```bash
rtk uv run pytest tests/unit/controllers/test_sample_controller.py -q
```

Expected:

- 全test passed、0 failed。
- OpenAPI responsesに`402`が無く、`403`がある。

### Task 7: Docker Composeのstatic directory回避処理を削除する

**Files:**
- Modify: `docker-compose.yaml`

**Interfaces:**
- Consumes: Task 4のstatic未存在時起動safe処理
- Produces: docker-composeが`mkdir -p static`に依存しない状態

- [x] **Step 7.1: docker-compose backend commandの現状を確認する**

```bash
rtk grep -n "mkdir -p static|manage.py serve" docker-compose.yaml
```

Expected:

- backend commandに`mkdir -p static && uv run python manage.py serve ...`がある。

- [x] **Step 7.2: `mkdir -p static &&`を削除する**

`docker-compose.yaml`のbackend commandを次へ変更する。

```yaml
    command:
      - sh
      - -c
      - uv run python manage.py serve --host 0.0.0.0 --port 8000
```

この削除は、Task 4で`index.html`不在時にもAPIだけで起動できるようにすること、および`Dockerfile`がfrontend build成果物をruntime imageへ`COPY --from=frontend-builder /app/backend/static ./static`で焼き込んでいることを前提にする。Compose開発時の`volumes`は`./backend/app`と`./backend/manage.py`だけをmountしており、image内の`/app/backend/static`を上書きしない。

- [x] **Step 7.3: docker-compose設定を構文確認する**

Repository rootで実行する。

```bash
rtk docker compose config
```

Expected:

- exit 0。
- backend commandに`mkdir -p static`が含まれない。

- [x] **Step 7.4: docker-compose backendの実起動を確認する**

Repository rootで実行する。
初回またはimage未作成時は、`build: context: .`によりfrontendの`npm ci`、Vite build、backendの`uv sync`を含むDocker buildが走るため、数分かかる可能性がある。

```bash
rtk docker compose up -d backend
rtk curl -fsS http://localhost:8000/api/healthz
```

Expected:

- `docker compose up -d backend`がexit 0。
- `/api/healthz`が`{"success":true,"message":"ok"}`相当のJSONを返す。
- `mkdir -p static`を削除してもbackendが起動できる。

- [x] **Step 7.5: compose起動ログにstatic起因の起動失敗がないことを確認する**

Repository rootで実行する。

```bash
rtk docker compose logs --tail=80 backend
```

Expected:

- `RuntimeError: Directory 'static' does not exist`が含まれない。
- 通常のDocker imageには`Dockerfile`の`COPY --from=frontend-builder /app/backend/static ./static`により`index.html`が含まれるため、Task 4のstatic警告ログは出ない。
- もしstatic未ビルド相当の環境で起動した場合でも、Task 4の警告ログだけに留まり、起動失敗にはならない。

### Task 8: 品質ゲートを実行し、計画書へ結果を記録する

**Files:**
- Verify: `backend/app/`
- Verify: `backend/tests/`
- Verify: `backend/alembic/`
- Verify: `frontend/`
- Verify: `docker-compose.yaml`
- Modify: `documents/plans/20260801-phase0-review-fixes.md`

**Interfaces:**
- Consumes: Task 2〜7の全変更
- Produces: 実測に基づく完了判定

- [x] **Step 8.1: backend isortを確認する**

`backend/`で実行する。

```bash
rtk uv run isort . --check-only
```

Expected:

- exit 0。
- 失敗した場合は`rtk uv run isort .`で整形し、同じcheckを再実行する。

- [x] **Step 8.2: backend yapfを確認する**

```bash
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
```

Expected:

- exit 0。
- diffがある場合は対象を`rtk uv run yapf -ir ...`で整形し、同じcheckを再実行する。

- [x] **Step 8.3: backend unit testsを実行する**

```bash
rtk uv run pytest tests/unit -q
```

Expected:

- 全test passed、0 failed。

- [x] **Step 8.4: PostgreSQL test DB接続先を確認する**

Repository rootで実行する。

```bash
rtk docker compose exec -T postgres psql -U app -d app_test -tAc "SELECT current_database(), current_user;"
```

Expected:

- `app_test|app`が出力される。
- 接続先が`app`など共有DBの場合はintegration testを実行しない。

- [x] **Step 8.5: backend full pytestをskipなしで実行する**

`backend/`で実行する。

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest
```

Expected:

- 全test passed、0 skipped、0 failed。
- `test_migration_consistency.py`が実行され、Alembic差分なしを確認する。

- [x] **Step 8.6: `db-check` CLIを実DBで実行する**

`backend/`で実行する。

```bash
rtk proxy env DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run python manage.py db-check
```

Expected:

- exit 0。
- pending schema changeなし。

- [x] **Step 8.7: docker-compose configを確認する**

Repository rootで実行する。

```bash
rtk docker compose config
```

Expected:

- exit 0。
- backend commandに`mkdir -p static`が含まれない。

- [x] **Step 8.8: frontend quality gateを実行する**

Phase 0でfrontend sourceは変更しないが、ルートAGENTSの品質ゲートに従い確認する。

`frontend/`で実行する。

```bash
rtk npm run check
rtk npm test
rtk npm run build
```

Expected:

- 全command exit 0。
- 既知warningが出た場合は内容と件数を「実行結果」へ記録する。
- `npm run build`は`frontend/vite.config.ts`の`emptyOutDir: true`により`backend/static/`を空にしてから成果物を生成する。backend static成果物は引き続きbuild artifactとして扱い、コミット対象にしない。
- frontend sourceに意図しない差分が出た場合は停止して報告する。

- [x] **Step 8.9: whitespaceとstagingなしを確認する**

Repository rootで実行する。

```bash
rtk git diff --check
rtk git diff --cached --stat
```

Expected:

- `git diff --check`はexit 0、outputなし。
- 本作業によるstaged changeはない。既存staged changeがある場合は操作せず、開始時baselineと照合して報告する。

- [x] **Step 8.10: 実行結果を本計画へ記録する**

本ファイル末尾の「実行結果」へ次を実測値で記入する。

- 実行日時
- branchとHEAD
- targeted REDのfailure理由
- targeted GREENのpassed件数
- backend unit / full pytestのpassed、skipped、failed、warnings件数
- frontend check / test / buildの結果
- `db-check`、`docker compose config`、`git diff --check`、`git diff --cached --stat`の結果
- 未対応事項または逸脱。なければ「なし」と明記する。

推測値や未実行結果は記録しない。

### Task 9: scopeと未対応事項を最終確認する

**Files:**
- Review: `documents/plans/20260801-phase0-review-fixes.md`
- Review: all changed files

**Interfaces:**
- Consumes: Task 1〜8の変更と検証結果
- Produces: 後続Phaseへ引き継げる明確な完了状態

- [x] **Step 9.1: Phase 0要件をline-by-lineで確認する**

Run: なし。

次をすべて確認する。

- `P0-1`: auth model metadataが既存migrationのindex/defaultと一致している。
- `P0-1`: Alembicのtype/default比較が有効で、integration testと`db-check`で差分なしを検証している。
- `P0-2`: `/login`などのSPA deep linkが`index.html`へfallbackする。
- `P0-2`: `/api`配下の未知URLはSPA fallbackしない。
- `P0-3`: `backend/static/`が無くても`create_app()`とAPI routeが起動する。
- `P0-3`: `backend/static/`が存在しても`index.html`が無ければSPA mountをスキップし、警告ログを出す。
- `P0-3`: static pathがcwdではなく`route.py`から見た`backend/static`基準で解決される。
- `P2-12`: 非ASCII CSRF mismatchが500ではなく403になる。
- `P2-12`: 認証済みunsafe requestのDB-bound CSRF照合が残っている。
- `P2-22`: `402: "Forbidden"`が消え、明らかな未使用importが削除されている。
- worktree、`git add`、`git commit`、`git push`を使っていない。

- [x] **Step 9.2: 後続Phaseへ残す項目を明記する**

Run: なし。

本計画の「未対応事項」へ、少なくとも次を残す。

- `P0-4`: register UI。レビュー推奨順序に従い、`P2-30`などのフロント基盤整備後に扱う。
- `P1-8`: エラーエンベロープ統一。
- `P2-20`: `Config`と`AuthSettings`の設定様式統一。
- `P2-23`: ruff / mypy / CI導入。
- `P2-35`: `/api/sample`末尾スラッシュ、複数形resource、sample CRUD化に向けた設計整理。
- `P3-6`: `.env`探索をcwd依存からbackend directory基準へ統一する。Phase 0では別cwdからのDB CLI実行時に`DATABASE_URL`と`ALEMBIC_DATABASE_URL`を明示する運用で扱う。
- `P3-8`: sampleを実用的CRUDの模範実装へ置き換える。

- [x] **Step 9.3: diffをscopeと照合する**

Repository rootで実行する。

```bash
rtk git status --short
rtk git diff --stat
rtk git diff -- documents/plans/20260801-phase0-review-fixes.md docker-compose.yaml backend
```

Expected:

- 変更はFile Structureの「変更するファイル」に限定される。
- frontend配下に差分がない。
- `backend/static`配下のbuild artifactがtracked対象になっていない。
- secrets、`.env`実体、DB dump、build artifactが追加されていない。

### Task 10: Claude Codeレビュー後の残課題を補正する

**Files:**
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/tests/unit/bootstrap/test_route.py`
- Modify: `backend/manage.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `backend/tests/unit/controllers/test_auth_dependencies.py`
- Modify: `backend/app/models/status.py`
- Modify: `backend/pyproject.toml`
- Modify: `documents/plans/20260801-phase0-review-fixes.md`

**Interfaces:**
- Consumes: Claude Codeレビューで実測された追加指摘
- Produces: static asset欠落、未知API method、`db-check` silent fallback、isort分類、CSRF回帰テストの補正

- [x] **Step 10.1: 追加レビューを精査し、採用/不採用を判断する**

Run: なし。

Expected:

- 「静的アセット欠落が200 HTMLになる」は採用する。ブラウザのchunk load errorや監視で実害があるため。
- 「`db-check`が接続先未指定で既定DBへsilent fallbackする」は採用する。再発防止コマンドが誤接続で緑になるため。
- 「API prefixの定数化」は採用する。`include_router(prefix=...)`とfallback除外条件の二重管理を避けるため。
- 「`POST /api/unknown`がstatic mount時だけ405になる」は採用する。環境差のあるstatus codeを避けるため。
- 「`status.py`の未使用`Field` import削除」は採用する。P2-22の漏れであり、挙動変更がないため。
- 「`db-upgrade` / `db-downgrade`の明示command名」は採用する。Typerの暗黙変換に依存しないため。
- 「isortで`alembic`をthird-party明示」は採用する。将来`backend/alembic/__init__.py`が追加された場合のshadowingリスクを下げるため。
- 「CSRF非ASCIIテストをlatin-1範囲に寄せる」は採用する。ASGI header/cookieの現実的な入力に近づけるため。
- `create_app(environment="local")`の未使用引数削除は不採用とし、`P2-20`へ残す。設定仕様整理に踏み込むため。

- [x] **Step 10.2: routeの追加RED testを書く**

`backend/tests/unit/bootstrap/test_route.py`に次を追加する。

- 欠落した`/assets/missing.js`は`Accept: text/html`でも404で、`index.html`を返さない。
- `Accept: application/json`の`/login`は404で、SPA fallbackしない。
- static mount済みの`POST /api/unknown`は404で、環境により405へ変わらない。
- 既存のSPA deep link testはブラウザnavigationを模すため`Accept: text/html`を明示する。

- [x] **Step 10.3: routeの追加REDを確認する**

```bash
rtk uv run pytest tests/unit/bootstrap/test_route.py::test_missing_static_asset_does_not_fall_back_to_spa_index tests/unit/bootstrap/test_route.py::test_non_html_request_does_not_fall_back_to_spa_index tests/unit/bootstrap/test_route.py::test_unknown_api_post_returns_404_when_spa_static_is_mounted -q
```

Expected:

- 現行実装では欠落assetと非HTML requestが200 HTMLになり、`POST /api/unknown`が405になって3 failed。

- [x] **Step 10.4: `SPAStaticFiles`のfallback条件を修正する**

`backend/app/bootstrap/route.py`を次の方針で変更する。

- `API_PREFIX = "/api"`を定義し、`app.include_router(..., prefix=API_PREFIX)`とAPI除外判定で共有する。
- `SPAStaticFiles.get_response()`は、`API_PREFIX`配下を`super().get_response()`より前に404へ落とす。
- `super().get_response()`が404を返した場合だけfallbackを検討する。
- fallback条件はGET/HEAD、`Accept: text/html`または`*/*`、既知静的asset pathではない、の3条件をすべて満たす場合に限定する。

- [x] **Step 10.5: `db-check` silent fallbackのRED testを書く**

`backend/tests/unit/test_manage.py`に次を追加する。

- `ALEMBIC_DATABASE_URL`未設定で`python manage.py db-check`相当を実行するとexit 2。
- stderrに`ALEMBIC_DATABASE_URL`が含まれる。
- `db-upgrade` / `db-downgrade`のTyper command名が明示されている。
- 既存の`db-check` invocation testは、明示環境変数を設定したうえでAlembic check呼び出しを確認する。

- [x] **Step 10.6: `db-check` silent fallbackの追加REDを確認する**

```bash
rtk uv run pytest tests/unit/test_manage.py::test_db_check_rejects_default_alembic_database_url tests/unit/test_manage.py::test_db_upgrade_and_downgrade_use_explicit_command_names -q
```

Expected:

- 現行実装では未設定でもexit 0になり、command名も`None`で2 failed。

- [x] **Step 10.7: `db-check`をfail-fastへ変更し、DB系command名を明示する**

`backend/manage.py`を次の方針で変更する。

- `db_check()`は`ALEMBIC_DATABASE_URL`が環境変数に無い場合、stderrへ理由を出して`typer.Exit(code=2)`で終了する。
- `db_upgrade`は`@app.command("db-upgrade")`、`db_downgrade`は`@app.command("db-downgrade")`を使う。
- `db-upgrade` / `db-downgrade`は既定DB URLを使う既存挙動を維持する。fail-fastは再発防止用の`db-check`に限定する。

- [x] **Step 10.8: CSRF非ASCII testを現実的なlatin-1 header/cookieへ寄せる**

`backend/tests/unit/controllers/test_auth_dependencies.py`の非ASCII mismatch testは、ASGIのheader bytesとして`b"csrf_token=caf\xe9"`と`b"caf\xe8"`を直接渡す。`あ` / `い`のようにHTTP headerとして通常流れない値は使わない。

- [x] **Step 10.9: P2-22の残り漏れとisort分類を補正する**

- `backend/app/models/status.py`から未使用`Field` importを削除する。
- `backend/pyproject.toml`に`[tool.isort] known_third_party = ["alembic"]`を追加する。
- `known_third_party`追加で生成済みmigrationのimportまで並び替わることを確認したため、`alembic/versions/*.py`を`skip_glob`へ追加し、既存migrationには差分を残さない。

- [x] **Step 10.10: 追加修正のtargeted GREENを確認する**

```bash
rtk uv run pytest tests/unit/bootstrap/test_route.py -q
rtk uv run pytest tests/unit/test_manage.py -q
rtk uv run pytest tests/unit/controllers/test_auth_dependencies.py -q
```

Expected:

- route tests: 9 passed、1 warning。
- manage tests: 3 passed。
- auth dependency tests: 7 passed。

### Task 11: Claude Code再レビュー後の新規問題を補正する

**Files:**
- Modify: `backend/manage.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/tests/unit/bootstrap/test_route.py`
- Modify: `documents/plans/20260801-phase0-review-fixes.md`

**Interfaces:**
- Consumes: Claude Code再レビューで実測された追加指摘
- Produces: `.env`由来の正当なDB設定を拒否しない`db-check`、接続先可視化、`db-downgrade`の破壊的既定値撤廃、過剰でないSPA fallback条件

- [x] **Step 11.1: 再レビュー指摘を精査し、採用/不採用を判断する**

Run: なし。

Expected:

- `db-check`が`.env`を無視して正当な設定を拒否する指摘は採用する。原因は`os.environ`直読みでconfig層をバイパスしていたこと。
- `db-check`成功時に接続先を出力する指摘は採用する。CIログやレビューで、どのDBを検査したかを資格情報なしで確認できるようにするため。
- `db-downgrade`の既定`base`撤廃は採用する。破壊的操作で暗黙に全テーブルdropへ進むのを避けるため。
- `Accept: */*`のSPA fallback許容は採用する。curl、監視、E2E runnerなどの疎通確認を過剰に404へしないため。
- dotted slugをSPA routeとして扱う指摘は採用する。`/users/john.doe`や`/reports/2024.01`は実務上自然なclient routeになりうるため。
- `skip_glob = ["alembic/versions/*.py"]`の恒久的なカバレッジ穴はPhase 0では仕様として残し、未対応事項へ明記する。既存migrationをimport整形だけで触るか、生成済みmigrationをフォーマット対象外にするかはDB運用ルールとして別途決める必要があるため。

- [x] **Step 11.2: `db-check`の`.env`受け入れと接続先出力のRED testを書く**

`backend/tests/unit/test_manage.py`に次を追加・変更する。

- `.env`に`ALEMBIC_DATABASE_URL`がある場合、環境変数未設定でも`db-check`がexit 0になる。
- stderrに資格情報を除いた`host:port/database`が含まれる。
- stderrにpasswordが含まれない。
- 既定URLの場合はexit 2でfail-fastし、stderrに`default`を含む。

- [x] **Step 11.3: `db-downgrade`のrevision必須化RED testを書く**

`backend/tests/unit/test_manage.py`に、`db-downgrade`をrevisionなしで実行するとexit 2になるtestを追加する。

- [x] **Step 11.4: SPA fallbackの`*/*`とdotted slugのRED testを書く**

`backend/tests/unit/bootstrap/test_route.py`に次を追加する。

- `GET /login` with `Accept: */*`は`index.html`へfallbackする。
- `GET /users/john.doe` with `Accept: text/html`は`index.html`へfallbackする。
- 欠落した`/favicon.ico` with `Accept: */*`は404のまま。

- [x] **Step 11.5: 追加REDを確認する**

```bash
rtk uv run pytest tests/unit/test_manage.py::test_db_check_accepts_alembic_database_url_from_dotenv tests/unit/test_manage.py::test_db_downgrade_requires_explicit_revision -q
rtk uv run pytest tests/unit/bootstrap/test_route.py::test_spa_deep_link_accepts_wildcard_accept_header tests/unit/bootstrap/test_route.py::test_spa_deep_link_allows_dotted_slug tests/unit/bootstrap/test_route.py::test_missing_known_static_extension_does_not_fall_back_to_spa_index -q
```

Expected:

- manage追加testは`.env`無視と`db-downgrade`既定`base`により2 failed。
- route追加testは`Accept: */*`とdotted slugが404になり2 failed、`favicon.ico`は既に1 passed。

- [x] **Step 11.6: `db-check`をconfig層解決へ変更する**

`backend/manage.py`を次の方針で変更する。

- `os.environ`直読みをやめ、`get_database_settings()`で`.env`を含む設定解決結果を取得する。
- `DatabaseSettings`のfield defaultと解決済み`ALEMBIC_DATABASE_URL`が一致する場合だけexit 2にする。
- 成功時は`Checking database: postgresql://host:port/database`形式でstderrへ出す。username、passwordは出さない。

- [x] **Step 11.7: `db-downgrade`のrevisionを必須引数にする**

`backend/manage.py`の`db_downgrade()`は`revision: str = typer.Argument(...)`に変更する。`db-upgrade`の既定`head`は維持する。

- [x] **Step 11.8: SPA fallback条件を既知asset判定へ変更する**

`backend/app/bootstrap/route.py`を次の方針で変更する。

- `PurePosixPath(path).suffix`による任意ドット除外をやめる。
- `assets/`配下と既知静的asset拡張子だけをfallback対象外にする。
- `Accept: text/html`または`Accept: */*`をドキュメントナビゲーションとして扱う。

- [x] **Step 11.9: 追加修正のtargeted GREENを確認する**

```bash
rtk uv run pytest tests/unit/test_manage.py -q
rtk uv run pytest tests/unit/bootstrap/test_route.py -q
```

Expected:

- manage tests: 5 passed。
- route tests: 12 passed、1 warning。

### Task 12: Claude Code再々レビュー後の`db-check`判定を補正する

**Files:**
- Modify: `backend/manage.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/tests/unit/bootstrap/test_route.py`
- Modify: `documents/plans/20260801-phase0-review-fixes.md`

**Interfaces:**
- Consumes: Claude Code再々レビューで実測された`.env.example`同値拒否の指摘
- Produces: `.env.example`と同じ値でも明示設定なら通る`db-check`、`.otf` asset欠落時の404固定

- [x] **Step 12.1: 再々レビュー指摘を精査し、採用/不採用を判断する**

Run: なし。

Expected:

- `db-check`が`.env.example`と同じ値を拒否する指摘は採用する。`DatabaseSettings`の既定値と`.env.example`の値は設計上同じであり、値の等価性では「明示設定されたか」を判定できないため。
- `model_fields_set`で`ALEMBIC_DATABASE_URL`が明示設定されたかを見る方針を採用する。`.env`または環境変数に値があれば、既定値と同じ文字列でも設定済みとして扱う。
- `.otf`を既知asset拡張子へ追加する指摘は採用する。`.ttf`、`.woff`、`.woff2`、`.eot`が既に対象で、フォント拡張子として一貫性があるため。
- `db-upgrade`のCLI形状を`db-downgrade`と揃える指摘はPhase 0では不採用にし、未対応事項へ残す。`db-upgrade`は安全側の既定`head`が便利で、`db-downgrade`の破壊的既定`base`とはリスクが異なるため。

- [x] **Step 12.2: `.env.example`同値でも`db-check`が通るRED testを書く**

`backend/tests/unit/test_manage.py`に、`.env`へ`ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app`を置いた場合に`db-check`がexit 0になるtestを追加する。

- [x] **Step 12.3: `.otf`欠落assetのRED testを書く**

`backend/tests/unit/bootstrap/test_route.py`に、`/fonts/x.otf` with `Accept: */*`が`index.html`へfallbackせず404になるtestを追加する。

- [x] **Step 12.4: `db-check`を`model_fields_set`判定へ変更する**

`backend/manage.py`の`db_check()`は、`settings.ALEMBIC_DATABASE_URL`の値ではなく、`"ALEMBIC_DATABASE_URL" in settings.model_fields_set`で明示設定有無を判定する。

- [x] **Step 12.5: `.otf`を既知asset拡張子へ追加する**

`backend/app/bootstrap/route.py`の`_STATIC_ASSET_EXTENSIONS`へ`.otf`を追加する。

- [x] **Step 12.6: 追加修正のtargeted GREENを確認する**

```bash
rtk uv run pytest tests/unit/test_manage.py -q
rtk uv run pytest tests/unit/bootstrap/test_route.py -q
```

Expected:

- manage tests: 6 passed。
- route tests: 13 passed、1 warning。

---

## 完了条件

- [x] `User`、`AuthSession`、`AuthAuditLog`のSQLModel metadataが既存migrationのauth index/defaultと一致している。
- [x] `alembic/env.py`で`compare_server_default=True`がonline/offline両方に設定されている。
- [x] `backend/alembic.ini`で`script_location = %(here)s/alembic`、`prepend_sys_path = %(here)s`が設定されている。
- [x] `backend/tests/integration/test_migration_consistency.py`と`python manage.py db-check`でpending schema changeなしを検証できる。
- [x] 新規Alembic revisionを作っていない。
- [x] `setup_routes()`がcwdに依存せず、static directory未存在でもbackend APIを起動できる。
- [x] `setup_routes()`が`index.html`不在時にSPA mountをスキップし、空またはplaceholderのみのstatic directoryで無言404を作らない。
- [x] `SPAStaticFiles`が`Accept: text/html`または`*/*`のGET/HEADかつ既知静的assetではないclient-side routeだけを`index.html`へfallbackする。
- [x] `SPAStaticFiles`が`/users/john.doe`のようなdotted slugをclient-side routeとしてfallbackする。
- [x] `SPAStaticFiles`が`/api`配下と大文字混在の`/API`配下をfallbackせず、`POST /api/unknown`も404にする。
- [x] 欠落した静的アセットと非HTML requestが`index.html`へfallbackせず404になる。
- [x] 欠落した`.otf` font assetが`index.html`へfallbackせず404になる。
- [x] `db-check`がconfig層で解決した`ALEMBIC_DATABASE_URL`を使い、`.env`または環境変数で明示設定された値を受け入れる。
- [x] `db-check`が`.env.example`と同じ値でも、明示設定されていれば受け入れる。
- [x] `db-check`が未設定時に既定DB URLへsilent fallbackせず、exit 2でfail-fastする。
- [x] `db-check`が成功時に資格情報を除いた接続先を出力する。
- [x] `db-upgrade`、`db-downgrade`、`db-check`のTyper command名が明示されている。
- [x] `db-downgrade`のrevisionが必須引数であり、暗黙の`base` downgradeを行わない。
- [x] docker-compose backend commandから`mkdir -p static &&`が削除されている。
- [x] `require_csrf()`がcookie/headerをUTF-8 bytesでtiming-safe比較し、非ASCII mismatchでも500を返さない。
- [x] `require_csrf()`が認証済みunsafe requestで`auth_sessions.csrf_token_hash`とのDB-bound CSRF照合を維持している。
- [x] `sample_controller.py`のForbidden宣言が`403`になっている。
- [x] Phase 0で対象にした未使用importが削除されている。
- [x] `backend/app/models/status.py`の未使用`Field` importが削除されている。
- [x] isortが`alembic`をthird-partyとして扱う設定になっている。
- [x] backend full pytestがPostgreSQL付きで0 skipped / 0 failedである。
- [x] frontend `npm run check`、`npm test`、`npm run build`が成功している。
- [x] `git diff --check`がcleanである。
- [x] 本作業で`git add`、`git commit`、`git push`を実行していない。

## 実行結果

- 実行日時: 2026-08-01 19:32:25 +07
- branch / HEAD: `feature/db-auth` / `b99ab40bf7570afc8bd7549f0908f29419381c7d`
- Targeted RED:
  - metadata unit test: `uq_users_email_lower`がmetadataに無く1 failed
  - Alembic consistency test: `AutogenerateDiffsDetected`で3件の`remove_index`差分を検出して1 failed
  - `db-check` CLI unit test: `AlembicConfig`未定義で1 failed
  - route unit tests: `setup_routes()`が`static_directory`を受け取らず6 failed
  - CSRF targeted tests: 非ASCII mismatchが`TypeError`、timing-safe比較がstr呼び出しで2 failed
  - sample router test: OpenAPI responsesに`402`があり1 failed
- Targeted GREEN:
  - `tests/unit/models/test_auth_models.py`: 3 passed
  - `tests/integration/test_migration_consistency.py`: 1 passed、1 warning
  - `tests/unit/test_manage.py`: 1 passed
  - `/tmp`からの`python manage.py db-check`: exit 0、`No new upgrade operations detected.`
  - `tests/unit/bootstrap/test_route.py`: 6 passed、1 warning
  - cwd変更後の`create_app()`確認: `True`
  - `tests/unit/controllers/test_auth_dependencies.py`: 7 passed
  - `tests/unit/controllers/test_sample_controller.py`: 1 passed、1 warning
  - `docker compose up -d backend`後の`/api/healthz`: `{"success":true,"message":"ok"}`
  - `docker compose logs --tail=80 backend`: errors 0、warnings 0
- 追加デバッグ:
  - backend full pytest初回は、`alembic.env`の`fileConfig()`が既存loggerを無効化し、route testの`caplog`が空になって1 failed。
  - `fileConfig(..., disable_existing_loggers=False)`へ変更し、`test_migration_consistency.py` + route logger testの順序再現が2 passed。
- Backend quality gate:
  - isort: 初回は`manage.py`と`tests/integration/test_migration_consistency.py`でfailed。`rtk uv run isort .`後、`--check-only` exit 0。
  - yapf: 初回diffあり。`rtk uv run yapf -ir app/ tests/ alembic/ manage.py`後、`-dr` exit 0。
  - backend unit tests: 39 passed、1 warning
  - PostgreSQL接続先確認: `app_test|app`
  - backend full pytest: 74 passed、0 skipped、0 failed、4 warnings
  - `python manage.py db-check`: exit 0、pending schema changeなし
  - `docker compose config`: exit 0、backend commandに`mkdir -p static`なし
- Frontend quality gate:
  - `npm run check`: exit 0、Prettierは全file unchanged、ESLint errorなし
  - `npm test`: 7 files passed、15 tests passed、0 failed
  - `npm run build`: exit 0、`VITE_SITE_URL`未定義warning 3件
- Final checks:
  - `git diff --check`: exit 0、outputなし
  - `git diff --cached --stat`: outputなし
- Claude Codeレビュー後の追加対応:
  - 追加RED route tests: 欠落assetと非HTML requestが200 HTMLになり、`POST /api/unknown`が405になって3 failed。
  - 追加RED manage tests: `ALEMBIC_DATABASE_URL`未設定でも`db-check`がexit 0になり、`db-upgrade` / `db-downgrade`のcommand名が`None`で2 failed。
  - CSRF latin-1非ASCII test: 既存実装で1 passed。修正自体は有効だったため、テスト入力だけを実HTTP経路に近いbytesへ補正した。
  - 追加GREEN targeted tests: `tests/unit/bootstrap/test_route.py`は9 passed、1 warning。`tests/unit/test_manage.py`は3 passed。`tests/unit/controllers/test_auth_dependencies.py`は7 passed。3ファイルまとめ実行では19 passed、1 warning。
  - isort設定補正: `known_third_party = ["alembic"]`追加後、生成済みmigrationも並べ替え対象になったため、`skip_glob = ["alembic/versions/*.py"]`を追加してmigration差分を残さない方針にした。`rtk uv run isort . --check-only`はexit 0、`Skipped 2 files`。
  - yapf追加確認: `rtk uv run yapf -dr app/ tests/ alembic/ manage.py`はexit 0、diffなし。
  - `db-check` fail-fast実CLI確認: `ALEMBIC_DATABASE_URL`未設定ではexit 2、stderrに`ALEMBIC_DATABASE_URL is required for db-check...`を出力。
  - `db-check`明示接続先確認: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test`指定でexit 0、`No new upgrade operations detected.`。
  - backend full pytest再実行: 79 passed、0 skipped、0 failed、4 warnings。
  - Docker runtime HTTP確認: `GET /login` with `Accept: text/html`は`200 text/html`、`GET /assets/nope.js` with `Accept: text/html`は`404 application/json`、`GET /api/unknown`は`404 application/json`、`POST /api/unknown`は`404 application/json`。
  - `/robots.txt` runtime確認: `200 text/plain`。現在のfrontend buildに実ファイルが存在するためで、SPA HTML fallbackではない。
  - Docker backend再起動後ログ: startup complete、上記HTTP requestのみで、再起動後のSyntaxErrorなし。編集中にUvicorn reloaderが一時的な`manage.py`を読みSyntaxErrorを出した古いログは残るが、現在のプロセスでは再発していない。
  - frontend quality gate再実行: `npm run check` exit 0、`npm test`は7 files / 15 tests passed、`npm run build` exit 0、`VITE_SITE_URL`未定義warning 3件。
  - `docker compose config`: exit 0、backend commandに`mkdir -p static`なし。
  - final `git diff --check`: exit 0、outputなし。
  - final `git diff --cached --stat`: outputなし。
- Claude Code再レビュー後の追加対応:
  - 追加RED manage tests: `.env`に`ALEMBIC_DATABASE_URL`がある場合も`db-check`がexit 2になり、`db-downgrade`がrevisionなしでexit 0になって2 failed。
  - 追加RED route tests: `Accept: */*`の`/login`と`/users/john.doe`が404になって2 failed。欠落`/favicon.ico`は既に404で1 passed。
  - 追加GREEN targeted tests: `tests/unit/test_manage.py`は5 passed、`tests/unit/bootstrap/test_route.py`は12 passed、1 warning。2ファイルまとめ実行では17 passed、1 warning。
  - `db-check`値比較による拒否の旧確認: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app`ではexit 2、`ALEMBIC_DATABASE_URL must be set to a non-default database URL for db-check.`を出力。この判定はTask 12で値比較ではなく明示設定有無の判定へ置き換えた。
  - `db-check`明示接続先確認: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test`指定でexit 0、`Checking database: postgresql://localhost:5432/app_test`と`No new upgrade operations detected.`を出力。資格情報は出力していない。
  - backend full pytest再実行: 84 passed、0 skipped、0 failed、4 warnings。
  - Docker runtime HTTP確認: curl既定`Accept: */*`の`GET /login`は`200 text/html`、`GET /users/john.doe` with `Accept: text/html`は`200 text/html`、`GET /favicon-missing.ico` with `Accept: */*`は`404 application/json`、`POST /api/unknown`は`404 application/json`。
- Claude Code再々レビュー後の追加対応:
  - `db-check`判定修正: `settings.ALEMBIC_DATABASE_URL`の値比較をやめ、`settings.model_fields_set`に`ALEMBIC_DATABASE_URL`が含まれるかで明示設定有無を判定するように変更。
  - `.env.example`同値test追加: `.env`に`ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app`を置いた場合でも`db-check`がexit 0になり、`postgresql://localhost:5432/app`を出力することを確認。
  - `.otf` asset test追加: `/fonts/x.otf` with `Accept: */*`が`index.html`へfallbackせず404になることを確認。
  - 追加GREEN targeted tests: `tests/unit/test_manage.py`は6 passed、`tests/unit/bootstrap/test_route.py`は13 passed、1 warning。
  - backend full pytest再実行: 86 passed、0 skipped、0 failed、4 warnings。
  - Docker runtime HTTP確認: `GET /fonts/x.otf` with `Accept: */*`は`404 application/json`、curl既定`Accept: */*`の`GET /login`は`200 text/html`、`POST /api/unknown`は`404 application/json`。
- 未対応事項または逸脱:
  - `.env`探索のcwd依存はPhase 0では直さず、`db-check`はconfig層で`ALEMBIC_DATABASE_URL`が明示設定されたかを確認する。`db-upgrade` / `db-downgrade`やアプリ設定全体の`.env`探索統一は`P3-6`へ残す。
  - Starlette / Vite由来の既存warningは残る。

## 未対応事項

- `P0-4`: register UI。レビュー推奨順序に従い、`P2-30`などのフロント基盤整備後に扱う。
- `P1-8`: エラーエンベロープ統一。
- `P2-20`: `Config`と`AuthSettings`の設定様式統一。
- `P2-23`: ruff / mypy / CI導入。
- `P2-35`: `/api/sample`末尾スラッシュ、複数形resource、sample CRUD化に向けた設計整理。
- `P3-6`: `.env`探索をcwd依存からbackend directory基準へ統一する。
- `P3-7`: isortの`skip_glob = ["alembic/versions/*.py"]`を恒久運用にするか見直す。Phase 0では既存migrationへimport整形だけの差分を残さないため対象外化したが、新規migrationのformat確認をどこで担保するかは別途決める。
- `P3-8`: `db-upgrade`のCLI形状を`db-downgrade`と揃えるか検討する。Phase 0では`db-upgrade`の安全側既定`head`を維持した。
- `P3-9`: sampleを実用的CRUDの模範実装へ置き換える。

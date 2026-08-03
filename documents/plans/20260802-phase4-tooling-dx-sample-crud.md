# Phase 4 ツーリング・DX と sample CRUD 模範実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Worktree、`git add`、`git commit`、`git push` は使用しない。

**Goal:** `documents/reviews/20260801-review.md` の Phase 4 を、レビュー不能な巨大差分にせず、品質ゲート整備と sample CRUD 模範実装の 2 ブロックで安全に進める。

**Architecture:** Phase 4A で CLI、lint/typecheck、frontend scripts、integration gate、CI、Docker DX を固める。Phase 4B で、Phase 1/2/3 の規約に沿った user-owned sample CRUD を backend に追加する。sample CRUD は controller が HTTP DTO を扱い、usecase は domain model / domain error を返す構成にする。

**Tech Stack:** Python 3.12、FastAPI、Typer、SQLModel、SQLAlchemy、Alembic、Injector、pytest、ruff、mypy、YAPF、isort、Docker Compose、GitHub Actions、React 19、TypeScript、Vite、Vitest

---

## 背景

Phase 0 では migration / static / SPA fallback / CSRF / sample controller の即日修正を完了した。Phase 1 では backend の DI、Unit of Work、lifespan、error envelope、docs 制御を整備した。Phase 2 では認証セキュリティと rate limiter を強化した。Phase 3 では frontend の認証 route、query key、error handling、register UI、logout UX を整備した。

Phase 4 の対象は、レビュー文書の「ツーリング・DX」と、Phase 1/3 の未対応事項から Phase 4 に送られた DX 項目である。

- `P1-15`: `manage.py serve` が reload 固定で、本番 container でも watch/reload が走る。
- `P1-16`: `TEST_DATABASE_URL` 未設定でも integration tests が skip され、品質ゲートが緑になる。
- `P2-23`: backend の lint / type check / CI 設定が不足している。`pydantic-settings` も直接 import しているのに直接依存ではない。
- `P2-25`: Docker Compose が production Dockerfile を使うため dev dependencies がなく、tests / alembic も扱いづらい。
- `P3-8` / `P2-35`: sample が実用的な CRUD の模範になっていない。
- `P3-6`: `manage.py` の version ハードコード、`db-revision` 欠如、CLI 品質。
- `P3-15`: frontend の `npm run build` が `vite build && tsc` の順で、型エラーでも成果物が出る。
- `P3-18`: `backend/README.md` が空で、起動手順と品質ゲートが分からない。

Claude Code による Phase 4 計画レビューで、初版計画には実行不能な tooling 設定と、sample CRUD のレイヤ規約違反があることが確認された。特に `yapf column_limit=100` と isort 既定 79 の振動、ruff `I` と isort の競合、FastAPI `Depends()` に対する bugbear `B008`、`models/__init__.py` の意図的な E402、pytest basename 衝突は blocker として扱う。

## 現行コードの分析

- `backend/manage.py` は `serve(host: str, port: str)` で `uvicorn.run(..., reload=True)` 固定になっている。`version()` は `Version: 1.0.0` を出すが、`backend/pyproject.toml` は `0.1.0` である。
- `Dockerfile` production runtime の CMD は `manage.py serve --host 0.0.0.0 --port 8000` であり、現状では本番 image でも reload が有効になる。
- `backend/pyproject.toml` の dev dependencies は `isort`、`pytest`、`pytest-asyncio`、`yapf` のみで、ruff / mypy がない。`pydantic_settings` はコードから直接 import しているが直接依存ではない。
- `backend/tests/integration/helpers.py` は `TEST_DATABASE_URL` 未設定時に `pytest.skip()` するため、`uv run pytest` が integration なしで成功する。
- `docker-compose.yaml` の backend service は production Dockerfile の runtime image を使い、`./backend/app` と `./backend/manage.py` しか mount しない。`backend/tests/`、`backend/alembic/`、`backend/pyproject.toml` の変更を container 内で扱いづらい。
- `frontend/package.json` は `build: vite build && tsc` である。`typecheck` script がなく、`check` に type check も含まれていない。
- 現在の sample は `GET /api/sample/` のみで、`Status(success=True, message=...)` を返す同期 usecase である。Phase 1 後の async / repository / UoW / error envelope の模範になっていない。
- `documents/references/backend-app-structure.md` は古い service locator DI や `repositories/` 予定表記が残っており、Phase 1 後の実装と乖離している。

## 方針とその理由

### 採用方針

1. Phase 4 を同一計画書内で **Phase 4A: ツーリング・DX** と **Phase 4B: sample CRUD** に分ける。4A 完了後に品質ゲートを通し、4B は別レビュー可能な差分として進める。
2. `yapf column_limit=100` はレビュー不能な一括再フォーマットを伴うため、機能変更と混ぜない。実施する場合は Phase 4A の最初に「format-only 変更」として独立させる。実装者はこの Step の開始前に、49 ファイル規模の再フォーマットを進めてよいかユーザー確認を取る。
3. ruff は import sorting を担当しない。既存 isort を正とし、ruff `select` から `I` を外す。isort には `line_length = 100` を設定し、YAPF 100 桁と振動しないようにする。
4. FastAPI の `Depends()` は bugbear `B008` の既知 false positive として `extend-immutable-calls` で許可する。controller に `# noqa` を撒かない。
5. `app/models/__init__.py` の E402 は `configure_metadata()` を model import より前に実行する意図的な順序なので per-file ignore する。Alembic generated migrations は ruff / isort では除外し、YAPF では既存・新規 migration を明示的に整形する。
6. `manage.py serve` は reload 既定を `ENVIRONMENT` から導出し、production Dockerfile の CMD は `--no-reload` を明示する。P1-15 の完了条件は「production image が reload なしで起動すること」とする。
7. `db-revision --autogenerate` は `db-check` と同様に `ALEMBIC_DATABASE_URL` の明示設定を必須にし、DB が head でない場合は拒否する。
8. `pytest-cov` は Phase 4 では追加しない。coverage 閾値を CI に入れる設計がないため、依存だけ増やす状態を避ける。
9. sample CRUD は usecase が HTTP response DTO を返さない。usecase は `SampleItem` / domain list / domain error を返し、controller が `SampleItemResponse` / error envelope へ変換する。
10. sample CRUD の public API JSON は camelCase を正とする。Pydantic alias generator を使い、`populate_by_name=True` は internal / test compatibility として許可するが、ドキュメント上の public request / response 例は camelCase だけにする。
11. sample CRUD は `app/libraries/clock.py` を導入し、既存 `utcnow()` 重複を sample にコピーしない。`updated_at` は `onupdate=utcnow` を持つ。
12. sample list は `ORDER BY created_at DESC, id DESC` を明示し、`limit` と cursor を持つ。最低でも順序非決定な全件取得はしない。

### 採用理由

- Phase 4 は後続の権限管理や OAuth の前に「壊れたら検知できる状態」を作る工程である。sample CRUD を先に作ると、現状の skip される integration tests や CI 不在のまま広い差分を抱える。
- tooling の設定値は相互作用が強い。実測済みの衝突を計画に反映しないまま実装すると、実装者が controller を不要に書き換えたり、format/lint が永続的に収束しない状態になる。
- sample CRUD は「この形をコピーして新しい resource を作る」ための教材である。既存 auth で直したばかりのレイヤ分離に反する実装を sample に入れると、その誤りが派生プロジェクトへ伝播する。
- empty PATCH は no-op 200 とする。`exclude_unset=True` により省略と `null` 明示を区別でき、nullable な `description` を null へクリアできる。422 にするより REST 的に単純で、クライアント実装も扱いやすい。

## スコープ

### 対象

- `P1-15`: `manage.py serve` の reload / workers / port 型 / log level / production reload 修正。
- `P1-16`: integration test 必須化、skip 0 件確認、CI gate。
- `P2-23`: ruff / mypy / pydantic-settings 直接依存、backend tooling 設定、GitHub Actions。
- `P2-25`: Dockerfile dev target、docker-compose backend 開発体験。
- `P3-8` と `P2-35`: sample を `/api/samples` の REST CRUD 模範実装へ置換。
- `P3-1` の一部: `app/libraries/clock.py` を導入し、sample で `utcnow()` を複製しない。
- `P3-6` の一部: `db-revision` 追加、version ハードコード解消、CLI test 強化。
- `P3-15`: frontend `typecheck` と build 順序。
- `P3-18`: backend README の最低限整備。
- Phase 4 に関係する `AGENTS.md` / `backend/AGENTS.md` / `frontend/AGENTS.md` / `documents/references/backend-app-structure.md` の限定更新。

### 対象外

- OAuth / OIDC。
- role / permission / `_admin` layout。
- password reset、email verification、password change。
- sample CRUD の frontend UI。
- `services/` vs `repositories/` の全体改名。Phase 4 では新規 sample repository も既存方針に合わせて `services/` に置き、命名整理は Phase 5 へ残す。
- coverage 閾値導入。`pytest-cov` は Phase 4 では追加しない。
- tests 全体への mypy strict 適用。Phase 4 では `app manage.py` を対象にする。
- 全 docs の完全同期。Phase 5 でまとめて扱う。
- `git add`、`git commit`、`git push`。

## 変更予定ファイル

### Phase 4A で作成するファイル

- `.github/workflows/ci.yml`
  - backend unit / backend integration / frontend / docker verification の CI job を定義する。
- `backend/tests/unit/test_integration_helpers.py`
  - `TEST_DATABASE_URL` 未設定時の fail 契約を検証する。`tests/unit/integration/` は作らない。

### Phase 4A で変更するファイル

- `AGENTS.md`
  - Phase 4 後の品質ゲートと CI 前提を更新する。
- `backend/AGENTS.md`
  - `serve` options、integration test 必須化、tooling、Docker Compose 注意事項を追記する。
- `frontend/AGENTS.md`
  - `typecheck`、`check:ci`、build 順序を更新する。
- `backend/README.md`
  - setup、env、serve、tests、db、Docker Compose の最小手順を書く。
- `backend/manage.py`
  - serve options、version、db-revision を追加する。
- `backend/pyproject.toml`
  - direct dependency と dev dependency、ruff / mypy / yapf / isort 設定を追加する。
- `backend/uv.lock`
  - dependency 追加に伴い更新する。
- `backend/tests/integration/helpers.py`
  - `TEST_DATABASE_URL` 未設定時を skip ではなく fail に変更する。
- `backend/tests/integration/conftest.py`
  - DB cleanup helper を sample table 追加に備えて拡張する。
- `backend/tests/unit/test_manage.py`
  - serve / version / db-revision test を追加する。
- `Dockerfile`
  - backend dev target を追加し、production CMD に `--no-reload` を明示する。
- `docker-compose.yaml`
  - backend service を dev target に切り替え、backend 全体 mount、db-upgrade 起動、Python stdlib healthcheck を整える。
- `frontend/package.json`
  - `typecheck`、`check:ci` を追加し、`build` を `typecheck && vite build` に変更する。
- `frontend/package-lock.json`
  - npm が lockfile metadata を変えた場合のみ差分を確認する。

### Phase 4B で作成するファイル

- `backend/app/libraries/clock.py`
  - timezone-aware `utcnow()` を定義する。
- `backend/app/models/sample_item.py`
  - `sample_items` table model と sample domain dataclass (`SampleItemCursor`、`SampleItemListResult`、`SampleItemUpdateChanges`) を定義する。
- `backend/app/models/sample_item_schemas.py`
  - request / response DTO を定義する。
- `backend/app/models/sample_item_errors.py`
  - `SampleItemNotFoundError` など sample domain error を定義する。
- `backend/app/interfaces/services/sample_item_repository_interface.py`
  - sample item repository の抽象を定義する。
- `backend/app/interfaces/usecases/sample_item_usecase_interface.py`
  - sample item usecase の抽象を定義する。
- `backend/app/services/sample_item_repository.py`
  - SQLModel / UoW を使う永続化実装を定義する。
- `backend/app/usecases/sample_item_usecase.py`
  - owner scope、cursor pagination、CRUD business flow を定義する。
- `backend/alembic/versions/20260802_0002_create_sample_items.py`
  - `sample_items` table を作る migration。実装前にユーザー確認が必要。
- `backend/tests/unit/models/test_sample_item.py`
  - model metadata と DTO validation を検証する。
- `backend/tests/unit/services/test_sample_item_repository.py`
  - repository の session / UoW 契約を検証する。
- `backend/tests/unit/usecases/test_sample_item_usecase.py`
  - usecase の owner scope、not found、pagination、update validation を検証する。
- `backend/tests/integration/test_sample_item_controller.py`
  - PostgreSQL + TestClient で CRUD と owner isolation を検証する。

### Phase 4B で変更するファイル

- `backend/app/models/__init__.py`
  - `SampleItem` を import / export する。E402 は ruff per-file ignore で許可する。
- `backend/app/bootstrap/modules.py`
  - sample repository / usecase を DI binding する。
- `backend/app/bootstrap/route.py`
  - sample router import を REST CRUD controller へ差し替える。
- `backend/app/controllers/sample_controller.py`
  - 旧 message endpoint を REST CRUD controller に置き換える。
- `backend/app/usecases/get_sample_index_usecase.py`
  - 削除する。
- `backend/app/interfaces/usecases/get_sample_index_usecase_interface.py`
  - 削除する。
- `backend/tests/unit/controllers/test_sample_controller.py`
  - 旧 OpenAPI test を `/api/samples` の REST 契約 test へ置き換える。
- `backend/tests/unit/controllers/test_sample_controller_dependency.py`
  - 旧 usecase override test を新 controller override test へ置き換える。
- `documents/references/backend-app-structure.md`
  - Phase 1 後の DI / UoW / dependency / sample CRUD 構成に限定して修正する。
- `backend/AGENTS.md`
  - sample CRUD 複製手順と API JSON camelCase 規約を追記する。
- `backend/README.md`
  - sample CRUD endpoint の curl 例を追記する。

## 進捗サマリー

- [x] Task 1: baseline と Phase 4 境界を固定する
- [x] Task 2: format / lint 設定方針を実測前提で固定する
- [x] Task 3: `manage.py` の CLI と production reload を直す
- [x] Task 4: backend tooling と型検査を導入する
- [x] Task 5: frontend build / typecheck scripts を整える
- [x] Task 6: integration test gate と CI を整える
- [x] Task 7: Docker Compose の開発体験を直す
- [x] Task 8: Phase 4A の品質ゲートを実行し、sample CRUD に進める状態を確認する
- [x] Task 9: sample CRUD の DB schema、clock、DTO、domain error を設計する
- [x] Task 10: sample repository / usecase を実装する
- [x] Task 11: sample controller / route / integration tests を実装する
- [x] Task 12: docs と AGENTS を Phase 4 後の規約へ更新する
- [x] Task 13: 全品質ゲートと smoke を実行する
- [x] Task 14: 実行結果と未対応事項を計画書へ反映する

## 具体的なタスク

### Task 1: baseline と Phase 4 境界を固定する

**Files:**
- Inspect: `documents/reviews/20260801-review.md`
- Inspect: `documents/plans/20260801-phase1-backend-foundation.md`
- Inspect: `documents/plans/20260802-phase2-review-fixes.md`
- Inspect: `documents/plans/20260802-phase3-frontend-structure.md`
- Inspect: `backend/AGENTS.md`
- Inspect: `frontend/AGENTS.md`
- Inspect: `backend/manage.py`
- Inspect: `backend/pyproject.toml`
- Inspect: `frontend/package.json`
- Inspect: `docker-compose.yaml`
- Inspect: `Dockerfile`

- [x] **Step 1.1: working tree と HEAD を確認する**

```bash
rtk git status --short
rtk git branch --show-current
rtk git rev-parse --short HEAD
```

Expected:

- 既存差分がある場合は Phase 4 と関係するかを確認する。
- ユーザーの既存差分は revert しない。
- `git add`、`git commit`、`git push` は実行しない。

- [x] **Step 1.2: Phase 4 対象の review ID を再確認する**

```bash
rtk grep -n "Phase 4|P1-15|P1-16|P2-23|P2-25|P3-8|P3-15|P3-18|P3-6" documents/reviews/20260801-review.md documents/plans/*.md
```

Expected:

- Phase 4 の主対象が `P1-15`、`P1-16`、`P2-23`、`P2-25`、`P3-8` であることを確認する。
- Phase 3 未対応事項の `P3-15` も Phase 4 / DX に含めることを確認する。
- `P3-18` と `P3-6` の CLI / README 部分を Phase 4 に含めることを確認する。

- [x] **Step 1.3: 既存品質ゲートの現状を記録する**

```bash
cd backend
rtk uv run pytest tests/unit -q
cd ../frontend
rtk npm test
rtk npx tsc --noEmit
cd ..
```

Expected:

- 既存の unit / frontend tests が成功する。
- 失敗した場合は Phase 4 実装に入る前に原因を記録する。

- [x] **Step 1.4: Phase 4A / 4B の実行境界を確認する**

Run: なし。

Expected:

- Phase 4A は tooling / CI / Docker / docs の差分だけで完了させる。
- Phase 4B は sample CRUD の DB schema と backend resource 実装だけで進める。
- Phase 4A 完了後、Phase 4B 開始前に差分を人間がレビューできる状態にする。

- [x] **Step 1.5: 変更禁止事項を確認する**

Run: なし。

Expected:

- dependency 追加前にユーザー確認を取る。
- format-only 49 ファイル規模の再フォーマット前にユーザー確認を取る。
- sample CRUD の DB schema 追加前にユーザー確認を取る。
- frontend sample UI は作らない。
- role / OAuth / password reset へ踏み込まない。
- worktree、staging、commit は行わない。

### Task 2: format / lint 設定方針を実測前提で固定する

**Review ID:** `P2-23`

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: format-only 対象ファイル if user approves YAPF 100 reformat

- [x] **Step 2.1: YAPF 100 桁化の扱いをユーザー確認する**

Run: なし。

確認内容:

- `column_limit=100` を導入すると約 49 ファイルの format-only 差分が出ることがレビューで実証済みである。
- 実施する場合は Phase 4A の最初に format-only として独立実行し、機能変更と混ぜない。
- ユーザーが拒否した場合は Phase 4 では `column_limit=79` 相当を維持し、`P2-23` の 100 桁化は別 Phase へ残す。

- [x] **Step 2.2: pyproject の tooling 方針を修正する**

`backend/pyproject.toml` に次を入れる。

```toml
[tool.isort]
known_third_party = ["alembic"]
skip_glob = ["alembic/versions/*.py"]
line_length = 100

[tool.yapf]
based_on_style = "pep8"
column_limit = 100

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["app", "tests"]
extend-exclude = ["alembic/versions"]

[tool.ruff.lint]
select = ["E", "F", "B", "UP", "SIM"]
ignore = []

[tool.ruff.lint.flake8-bugbear]
extend-immutable-calls = [
  "fastapi.Depends",
  "fastapi.Query",
  "fastapi.Path",
  "fastapi.Header",
  "fastapi.Body",
]

[tool.ruff.lint.per-file-ignores]
"app/models/__init__.py" = ["E402"]
"tests/integration/services/test_unit_of_work.py" = ["SIM117"]

[tool.mypy]
python_version = "3.12"
explicit_package_bases = true
mypy_path = "."
check_untyped_defs = true
strict_optional = true
warn_unused_ignores = true
disable_error_code = ["type-abstract"]
```

重要:

- ruff `I` は選ばない。import sorting は isort が担当する。
- Alembic versions は isort と ruff から除外する。YAPF は migration も整形対象に含めるため、既存 migration は Step 2.3 の format-only で、新規 migration は生成直後に整形する。
- `UP047` は無視しない。`app/bootstrap/dependencies.py` の `inject` helper は Python 3.12 の PEP 695 generic function 構文へ更新する。
- `SIM117` は原則修正する。ただし `tests/integration/services/test_unit_of_work.py` は nested context が UoW 契約を表現しているため、per-file ignore で `SIM117` を許可する。
- mypy は `app/__init__.py` を追加せず、namespace package のまま `explicit_package_bases = true` と `mypy_path = "."` で解決する。
- `type-abstract` は Injector の `binder.bind(Interface, to=Implementation)` と FastAPI `inject(Interface)` の標準パターンに構造的に出るため、mypy 設定で error code 単位に無効化する。個別行へ `# type: ignore[type-abstract]` を撒かない。
- `warn_return_any` は Phase 4 では有効化しない。`inject` helper は PEP 695 化に加えて `typing.cast(T, request.app.state.injector.get(interface))` で戻り値型を閉じ、将来 `warn_return_any` を有効化できる形にする。
- mypy `arg-type` は 4 種類に分けて処理する。広域 `# type: ignore[arg-type]` は使わない。
  - FastAPI `responses={...: {"model": ErrorResponse}}` は、controller ごとに dict literal を裸で書かず、共通 helper または型付き alias に閉じる。
  - `app.add_exception_handler(...)` は Starlette の反変制約に合わせ、handler の `exc` 引数を `Exception` へ広げて関数内で `isinstance()` により narrow する。
  - `json_error_response()` の `headers` / `details` は、自プロジェクトの関数シグネチャを `Mapping[str, str] | None` や `Sequence[ErrorFieldDetail | dict[str, Any]] | None` へ広げて直す。
  - `auth_usecase.py` の nullable 値由来の `arg-type` は本物の型不整合として実装を修正する。設定では潰さない。
- `tests/unit/test_pyproject_tooling.py` は作らない。設定値そのものを同一差分で assert する test は実効性が薄いため、実ゲートは ruff / isort / yapf / mypy の実行で担保する。

- [x] **Step 2.3: format-only reformat を実施する**

ユーザーが YAPF 100 桁化を承認した場合だけ実行する。

```bash
cd backend
rtk uv run isort .
rtk uv run yapf -ir app/ tests/ alembic/ manage.py
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
```

Expected:

- `isort --check-only` と `yapf -dr` が同時に exit 0 になる。
- 差分は format-only として記録する。
- この Step では機能変更を入れない。

- [x] **Step 2.4: 振動がないことを再確認する**

```bash
cd backend
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
```

Expected:

- 2 回連続で両方 exit 0。

### Task 3: `manage.py` の CLI と production reload を直す

**Review ID:** `P1-15`, `P3-6`

**Files:**
- Modify: `backend/manage.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `Dockerfile`

- [x] **Step 3.1: serve options の RED test を追加する**

`backend/tests/unit/test_manage.py` に次を追加する。

- `serve --host 127.0.0.1 --port 9000 --no-reload --workers 2` が `uvicorn.run(app="app.main:app", host="127.0.0.1", port=9000, reload=False, workers=2)` を呼ぶ。
- `serve --reload --workers 2` は exit code 2 で、reload と workers の同時指定を拒否する。
- `serve --port not-a-number` は Typer validation で exit code 2 になる。
- `serve --log-level debug` が `log_level="debug"` を渡す。
- `ENVIRONMENT=production` で `serve` を option なし実行すると `reload=False` を渡す。
- `ENVIRONMENT=local` で `serve` を option なし実行すると `reload=True` を渡す。

- [x] **Step 3.2: version と db-revision の RED test を追加する**

`backend/tests/unit/test_manage.py` に次を追加する。

- `version` が `backend/pyproject.toml` の `[project].version` と一致する。
- `db-revision --message "create sample items" --autogenerate --rev-id 20260802_0002` は、`ALEMBIC_DATABASE_URL` が明示設定されていない場合 exit code 2 で拒否する。
- `ALEMBIC_DATABASE_URL` 明示設定済みで DB が head の場合だけ `alembic.command.revision(config, message=..., autogenerate=True)` を呼ぶ。この unit test は DB へ接続せず、head 判定 helper と Alembic command を monkeypatch した stub で検証する。
- message 未指定は exit code 2 になる。

- [x] **Step 3.3: `manage.py` を実装する**

実装方針:

- `reload` option は `bool | None` とし、未指定時は `Config.ENVIRONMENT` が `local` または `development` のときだけ `True`。
- `--reload` と `--workers > 1` は拒否する。
- `version()` は `tomllib` で `backend/pyproject.toml` を読む。
- `db_revision()` は `db_check()` と同じ明示 DB URL チェックを使う。
- autogenerate 前に DB が head であることを確認する helper を置く。unit test では helper を stub 化し、実 DB 接続を要求しない。実装が複雑になる場合でも、「明示 DB URL 必須」は Phase 4 で必ず入れ、head 確認を延期する場合は未対応事項へ理由付きで残す。

- [x] **Step 3.4: production Dockerfile CMD を修正する**

`Dockerfile` runtime CMD は次にする。

```dockerfile
CMD ["uv", "run", "python", "manage.py", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-reload"]
```

workers を production image で固定するかは Phase 4 では決めない。`--no-reload` は必須。

- [x] **Step 3.5: CLI tests を実行する**

```bash
cd backend
rtk uv run pytest tests/unit/test_manage.py -q
```

Expected:

- `test_manage.py` がすべて成功する。

### Task 4: backend tooling と型検査を導入する

**Review ID:** `P2-23`

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Modify: backend app files as required by ruff / mypy

- [x] **Step 4.1: 依存追加のユーザー確認を取る**

Run: なし。

確認する依存:

- runtime: `pydantic-settings`
- dev: `ruff`, `mypy`

Expected:

- ユーザーが承認した場合だけ `uv add pydantic-settings` と `uv add --dev ruff mypy` を実行する。
- `pytest-cov` は追加しない。

- [x] **Step 4.2: 依存を追加する**

ユーザー承認後に実行する。

```bash
cd backend
rtk uv add pydantic-settings
rtk uv add --dev ruff mypy
```

Expected:

- `backend/pyproject.toml` と `backend/uv.lock` が更新される。
- 追加依存以外の不要な lockfile churn がないか確認する。

- [x] **Step 4.3: ruff / mypy の RED を確認する**

```bash
cd backend
rtk uv run ruff check .
rtk uv run mypy app manage.py
```

Expected:

- 初回は未使用 import、型注釈不足、SQLModel / Injector 周辺の型エラーが出る可能性がある。
- FastAPI `Depends()` の B008、`models/__init__.py` の E402、Alembic generated migration の lint は設定で抑制され、controller に `# noqa` を撒かない。

- [x] **Step 4.4: ruff / mypy を通す**

修正方針:

- ruff が指摘する未使用 import と単純な pyupgrade は直す。
- `UP047` は `app/bootstrap/dependencies.py` の `inject` helper を PEP 695 構文へ変更して解消する。例: `def inject[T](interface: type[T]) -> Callable[[Request], T]: ...`
- `inject` helper は `typing.cast(T, request.app.state.injector.get(interface))` で Injector の `Any` を helper 内に閉じ込める。
- `SIM117` は通常の production / unit code では畳む。`tests/integration/services/test_unit_of_work.py` だけは nested context が UoW 契約の読みやすさを担っているため、Step 2.2 の per-file ignore を正とする。
- `type-abstract` は Step 2.2 の mypy 設定で無効化する。Injector / FastAPI dependency に interface type を渡す Phase 1 の標準パターンを壊さないためである。
- mypy `arg-type` は 4 種類に分けて処理する。広域 `# type: ignore[arg-type]` は使わない。
  - FastAPI `responses={...: {"model": ErrorResponse}}` は、`backend/app/controllers/` 内の共通 typed helper または alias で response metadata の型を閉じる。
  - `app.add_exception_handler(...)` は handler の `exc` 引数を `Exception` へ広げ、handler 内で対象 exception 型へ narrow する。
  - `json_error_response()` の `headers` / `details` は `Mapping` / `Sequence` を受けるように自プロジェクトの型を広げる。
  - `auth_usecase.py` の nullable 値由来の `arg-type` は実装を修正する。
- `union-attr`、`return-value` など、nullable 参照や戻り値不一致を示す mypy error は設定で無効化せず、実装を修正する。
- import 並びは isort に任せる。
- mypy で injector / SQLModel 周辺の型が難しい場合は、狭い helper 関数に型を閉じる。広い `# type: ignore` は避け、必要な場合は理由付きで対象行だけにする。
- tests 全体を mypy 対象にしない。

- [x] **Step 4.5: backend tooling checks を実行する**

```bash
cd backend
rtk uv run ruff check .
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
rtk uv run mypy app manage.py
```

Expected:

- すべて exit 0。

### Task 5: frontend build / typecheck scripts を整える

**Review ID:** `P3-15`

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/AGENTS.md`

- [x] **Step 5.1: scripts を変更する**

`frontend/package.json` の方針:

```json
{
  "scripts": {
    "build": "npm run typecheck && vite build",
    "typecheck": "tsc --noEmit",
    "check": "prettier --write . && eslint --fix && npm run typecheck",
    "check:ci": "prettier --check . && eslint . && npm run typecheck"
  }
}
```

既存 `lint` / `format` / `test` は維持する。

- [x] **Step 5.2: frontend checks を実行する**

```bash
cd frontend
rtk npm run check:ci
rtk npm test
rtk npm run build
```

Expected:

- `check:ci` が書き換えなしで成功する。
- `build` は typecheck 後に Vite build を実行する。

### Task 6: integration test gate と CI を整える

**Review ID:** `P1-16`, `P2-23`

**Files:**
- Modify: `backend/tests/integration/helpers.py`
- Modify: `backend/tests/integration/conftest.py`
- Create: `backend/tests/unit/test_integration_helpers.py`
- Create: `.github/workflows/ci.yml`
- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`

- [x] **Step 6.1: integration helper の RED test を追加する**

`backend/tests/unit/test_integration_helpers.py` を作成し、`TEST_DATABASE_URL` 未設定で `require_test_database_url()` が skip ではなく fail することを検証する。

- [x] **Step 6.2: `require_test_database_url()` を fail-fast に変更する**

`backend/tests/integration/helpers.py` の方針:

```python
def require_test_database_url() -> str:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.fail(
            "TEST_DATABASE_URL is required for integration tests. "
            "Run unit tests with `uv run pytest tests/unit`, or start PostgreSQL "
            "and set TEST_DATABASE_URL for integration tests."
        )
    return test_database_url
```

- [x] **Step 6.3: sample_items cleanup を integration conftest に予約する**

Task 9 以降で `sample_items` table を追加するため、cleanup は table 存在時に `sample_items, auth_audit_logs, auth_sessions, users` を `TRUNCATE ... CASCADE` する。table 未作成状態では `UndefinedTableError` を従来どおり許容する。

- [x] **Step 6.4: CI workflow を追加する**

`.github/workflows/ci.yml` の必須仕様:

- `on`
  - `pull_request`
  - `push` on current protected/default branch pattern if repository uses one。branch 名が未確定の場合は `push` 全 branch で開始する。
- `backend-unit`
  - checkout
  - install uv with cache enabled
  - setup Python 3.12
  - `cd backend && uv sync --frozen`
  - `uv run ruff check .`
  - `uv run isort . --check-only`
  - `uv run yapf -dr app/ tests/ alembic/ manage.py`
  - `uv run mypy app manage.py`
  - `uv run pytest tests/unit -q`
- `backend-integration`
  - PostgreSQL 17 service
  - checkout / uv setup / Python setup / `uv sync --frozen`
  - `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run python manage.py db-upgrade`
  - `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration -q -ra`
  - `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run python manage.py db-check`
- `frontend`
  - checkout
  - setup Node 22 with npm cache for `frontend/package-lock.json`
  - `cd frontend && npm ci`
  - `npm run check:ci`
  - `npm test`
  - `npm run build`
- `docker`
  - checkout
  - `docker compose config`
  - production image build: `docker build --target runtime -t python-react-template-backend:ci .`
  - dev target build: `docker build --target backend-dev -t python-react-template-backend-dev:ci .`

- [x] **Step 6.5: CI YAML を静的確認する**

```bash
rtk grep -n "pull_request|backend-unit|backend-integration|frontend|docker|TEST_DATABASE_URL|db-check|check:ci|backend-dev|--target runtime" .github/workflows/ci.yml
```

Expected:

- 4 job が存在する。
- integration job に PostgreSQL service、`uv sync --frozen`、`TEST_DATABASE_URL` がある。
- Docker job が production / dev target を build する。

### Task 7: Docker Compose の開発体験を直す

**Review ID:** `P2-25`

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yaml`
- Modify: `backend/README.md`

- [x] **Step 7.1: Dockerfile に backend dev target を追加する**

方針:

- `backend-base`: `uv` Python image、`WORKDIR /app/backend`、`pyproject.toml` / `uv.lock` / `README.md` を copy。
- `backend-dev`: dev dependencies を含めて `uv sync --frozen --group dev --no-install-project` し、compose mount 前提で使う。
- `runtime`: production は従来どおり no-dev。production CMD には `--no-reload` を明示する。

- [x] **Step 7.2: docker-compose backend service を dev target へ切り替える**

`docker-compose.yaml` の backend 方針:

- `build.target: backend-dev`
- mount は `./backend:/app/backend`
- anonymous volume で `/app/backend/.venv` を分離する
- command は現行 compose と同じ `["sh", "-c", "..."]` 形式で書く。内容は `uv sync --frozen --group dev && uv run python manage.py db-upgrade && uv run python manage.py serve --host 0.0.0.0 --port 8000 --reload`
- healthcheck は curl ではなく Python stdlib を使う

healthcheck 例:

```yaml
healthcheck:
  test:
    - CMD-SHELL
    - python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/healthz', timeout=2).read()"
```

- [x] **Step 7.3: `.venv` anonymous volume の運用注意を書く**

`backend/README.md` に次を明記する。

- `backend/uv.lock` を変更した後に container の依存が古い場合は `docker compose down -v` で anonymous `.venv` volume を消す。
- compose command でも `uv sync --frozen --group dev` を実行するが、解決しない場合は volume を作り直す。

- [x] **Step 7.4: compose 内で alembic と tests が見えることを確認する**

```bash
rtk docker compose config
rtk docker compose up -d postgres backend
rtk docker compose exec backend uv run python manage.py db-check
rtk docker compose exec backend uv run pytest tests/unit/test_manage.py -q
rtk curl -i http://127.0.0.1:8000/api/healthz
rtk docker compose logs --tail=120 backend
```

Expected:

- container 内に `tests/` と `alembic/` が見える。
- dev dependencies がなくて pytest が落ちる状態が解消される。

### Task 8: Phase 4A の品質ゲートを実行し、sample CRUD に進める状態を確認する

**Files:**
- Inspect: whole repository
- Modify: `documents/plans/20260802-phase4-tooling-dx-sample-crud.md`

- [x] **Step 8.1: backend gate を実行する**

```bash
cd backend
rtk uv run ruff check .
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
rtk uv run mypy app manage.py
rtk uv run pytest tests/unit -q
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q -ra
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-check
```

Expected:

- すべて成功する。
- integration tests は skip 0 件。

- [x] **Step 8.2: frontend gate を実行する**

```bash
cd frontend
rtk npm run check:ci
rtk npm test
rtk npm run build
```

Expected:

- すべて成功する。

- [x] **Step 8.3: Docker gate を実行する**

```bash
rtk docker compose config
rtk docker build --target runtime -t python-react-template-backend:phase4a .
rtk docker build --target backend-dev -t python-react-template-backend-dev:phase4a .
```

Expected:

- production / dev image build が成功する。

- [x] **Step 8.4: diff を確認する**

```bash
rtk git diff --stat
rtk git diff --check
rtk git status --short -- ':!.superpowers'
```

Expected:

- Phase 4A の差分だけでレビューできる状態になっている。
- `git diff --stat` の出力を本計画の「実行結果」へ貼り、Phase 4A の差分範囲を後から確認できるようにする。
- `git add` は実行しない。

### Task 9: sample CRUD の DB schema、clock、DTO、domain error を設計する

**Review ID:** `P3-8`, `P2-35`, `P3-1`

**Files:**
- Create: `backend/app/libraries/clock.py`
- Create: `backend/app/models/sample_item.py`
- Create: `backend/app/models/sample_item_schemas.py`
- Create: `backend/app/models/sample_item_errors.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260802_0002_create_sample_items.py`
- Create: `backend/tests/unit/models/test_sample_item.py`
- Modify: `backend/tests/integration/conftest.py`

- [x] **Step 9.1: DB schema 変更のユーザー確認を取る**

Run: なし。

確認内容:

- `sample_items` table を追加する。
- `users.id` への FK を持つ user-owned resource とする。
- 新規 Alembic revision を作る。

- [x] **Step 9.2: clock helper を作る**

`backend/app/libraries/clock.py`:

```python
from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
```

Phase 4 では sample と新規 model でこの helper を使う。既存 `User` / `AuthRepository` / `AuthUsecase` の `timezone.utc` は ruff `UP017` の対象になるため、Step 4.4 で `datetime.UTC` へ auto-fix する。既存 `utcnow()` 関数の共通 helper への全面置換は targeted tests を追加できる場合だけ行い、置換しない場合は未対応事項へ残す。

- [x] **Step 9.3: model / DTO の RED tests を追加する**

`backend/tests/unit/models/test_sample_item.py` で次を検証する。

- `SampleItem.__tablename__ == "sample_items"`
- columns: `id`, `owner_user_id`, `title`, `description`, `is_completed`, `created_at`, `updated_at`
- `owner_user_id` に FK があり、`ondelete="CASCADE"` を持つ。
- `updated_at` column に `onupdate=utcnow` がある。
- `title` は 1 文字以上 120 文字以下。
- `description` は `None` または 1000 文字以下。
- create / update request は JSON alias として `isCompleted` を使う。
- `SampleItemUpdateRequest.model_dump(exclude_unset=True)` で省略 field と `description=None` 明示を区別できる。
- `SampleItemResponse` は `id`, `title`, `description`, `isCompleted`, `createdAt`, `updatedAt` を camelCase で返せる。

- [x] **Step 9.4: SQLModel table を作成する**

`backend/app/models/sample_item.py` の設計:

```python
class SampleItem(SQLModel, table=True):
    __tablename__ = "sample_items"
    __table_args__ = (
        Index("ix_sample_items_owner_user_id_created_at_id", "owner_user_id", "created_at", "id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    title: str = Field(sa_column=Column(String(length=120), nullable=False))
    description: str | None = Field(default=None, sa_column=Column(String(length=1000)))
    is_completed: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false")))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow))
```

- [x] **Step 9.5: request / response DTO と domain error を作成する**

`backend/app/models/sample_item_schemas.py` の設計:

- 共通 base は `ConfigDict(alias_generator=to_camel, populate_by_name=True)` を使う。
- public API と docs は camelCase だけを示す。`populate_by_name=True` により Python field name でも内部生成できるが、snake_case JSON を public contract として扱わない。
- `SampleItemCreateRequest`
  - `title: str = Field(min_length=1, max_length=120)`
  - `description: str | None = Field(default=None, max_length=1000)`
- `SampleItemUpdateRequest`
  - `title: str | None = Field(default=None, min_length=1, max_length=120)`
  - `description: str | None = Field(default=None, max_length=1000)`
  - `is_completed: bool | None = None`
  - レビュー修正で `title` / `is_completed` の明示 `null` は 422 にする。
  - レビュー修正で request DTO は `extra="forbid"` とし、typo field を 422 にする。
- list query は controller の個別 `Query()` parameter で受ける。`SampleItemListQuery` は fallback 後に dead code になったためレビュー修正で削除した。
- `SampleItemResponse`
  - camelCase alias。
  - `from_item(item: SampleItem) -> SampleItemResponse` classmethod を持つ。
- `SampleItemListResponse`
  - `items: list[SampleItemResponse]`
  - Python field は `next_cursor: str | None`
  - JSON alias は `nextCursor`

`backend/app/models/sample_item_errors.py`:

- `SampleItemNotFoundError`
- `InvalidSampleItemCursorError`

`backend/app/models/sample_item.py` には table model に加えて次の domain dataclass を置く。

- `SampleItemCursor(created_at: datetime, id: UUID)`
- `SampleItemListResult(items: list[SampleItem], next_cursor: str | None)`
- `SampleItemUpdateChanges(title: str | None = None, description: str | None = None, is_completed: bool | None = None, fields_set: frozenset[str] = frozenset())`
  - `fields_set` は Python field name の集合に統一する。`{"isCompleted": true}` のような camelCase input でも Pydantic `model_fields_set` は `{"is_completed"}` になるため、domain changes も `is_completed` を使う。

cursor encoding:

- cursor は opaque string とし、JSON `{"createdAt": "<ISO-8601>", "id": "<UUID>"}` を UTF-8 で URL-safe Base64 encode した値にする。
- padding は標準 Base64 のまま許可する。
- decode できない、JSON でない、`createdAt` が timezone-aware datetime でない、`id` が UUID でない場合は `InvalidSampleItemCursorError`。
- DESC keyset 条件は `(created_at < cursor.created_at) OR (created_at = cursor.created_at AND id < cursor.id)` とする。

empty PATCH は error にしない。`exclude_unset=True` の結果が空なら現 item をそのまま返す no-op 200 とする。

- [x] **Step 9.6: migration を作成する**

承認後に実行する。

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-revision --message "create sample items" --autogenerate --rev-id 20260802_0002
```

Expected:

- Alembic revision が 1 つだけ作られる。
- migration は `sample_items` table、FK `ON DELETE CASCADE`、index、server defaults を明示する。
- auth 初期 migration は変更しない。

- [x] **Step 9.7: 生成 migration を整形する**

生成された revision file に対して YAPF を実行する。`<revision-file>` は Step 9.6 で実際に生成されたファイル名へ置き換える。

```bash
cd backend
rtk uv run yapf -i alembic/versions/<revision-file>.py
```

Expected:

- 新規 migration が Task 13.1 の `yapf -dr app/ tests/ alembic/ manage.py` で差分を出さない。

- [x] **Step 9.8: model import と migration consistency を確認する**

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-check
rtk uv run pytest tests/unit/models/test_sample_item.py -q
```

Expected:

- migration 適用が成功する。
- `db-check` が `No new upgrade operations detected.` を出す。

### Task 10: sample repository / usecase を実装する

**Review ID:** `P3-8`

**Files:**
- Create: `backend/app/interfaces/services/sample_item_repository_interface.py`
- Create: `backend/app/interfaces/usecases/sample_item_usecase_interface.py`
- Create: `backend/app/services/sample_item_repository.py`
- Create: `backend/app/usecases/sample_item_usecase.py`
- Modify: `backend/app/bootstrap/modules.py`
- Create: `backend/tests/unit/services/test_sample_item_repository.py`
- Create: `backend/tests/unit/usecases/test_sample_item_usecase.py`

- [x] **Step 10.1: repository interface を定義する**

必要な method:

```python
class SampleItemRepositoryInterface(metaclass=ABCMeta):
    async def list_by_owner(
        self,
        owner_user_id: UUID,
        fetch_limit: int,
        cursor: SampleItemCursor | None,
    ) -> list[SampleItem]: ...
    async def get_by_id_for_owner(self, item_id: UUID, owner_user_id: UUID) -> SampleItem | None: ...
    async def create(self, item: SampleItem) -> SampleItem: ...
    async def update(self, item: SampleItem) -> SampleItem: ...
    async def delete(self, item: SampleItem) -> None: ...
```

`fetch_limit` は repository が返す最大件数であり、repository は黙って `+1` しない。`SampleItemCursor` は `app.models.sample_item` に定義する。

- [x] **Step 10.2: usecase interface を定義する**

usecase は HTTP DTO を返さない。

```python
class SampleItemUsecaseInterface(metaclass=ABCMeta):
    async def list_items(self, owner_user_id: UUID, limit: int, cursor: str | None) -> SampleItemListResult: ...
    async def create_item(self, owner_user_id: UUID, title: str, description: str | None) -> SampleItem: ...
    async def get_item(self, owner_user_id: UUID, item_id: UUID) -> SampleItem: ...
    async def update_item(self, owner_user_id: UUID, item_id: UUID, changes: SampleItemUpdateChanges) -> SampleItem: ...
    async def delete_item(self, owner_user_id: UUID, item_id: UUID) -> None: ...
```

`SampleItemListResult` と `SampleItemUpdateChanges` は domain dataclass として `app.models.sample_item` に置く。HTTP request DTO から domain dataclass への変換は controller が行う。

- [x] **Step 10.3: repository unit tests を追加する**

`backend/tests/unit/services/test_sample_item_repository.py` で次を検証する。

- `list_by_owner()` は `owner_user_id` で絞り、`ORDER BY created_at DESC, id DESC` を使う。
- cursor がある場合は keyset 条件で次ページを返す。
- repository は渡された `fetch_limit` 件まで返し、それ以上は取得しない。
- `get_by_id_for_owner()` は `id` と `owner_user_id` の両方で絞る。
- `create()` / `update()` は transaction session 内では `flush()`、transaction 外では `commit()` する。
- `delete()` は owner scope 済み item だけを受け取り、session delete と persist を行う。

- [x] **Step 10.4: usecase unit tests を追加する**

`backend/tests/unit/usecases/test_sample_item_usecase.py` で次を検証する。

- `create_item()` は `owner_user_id` を必ず item に入れる。
- `list_items()` は request limit に 1 を足した `fetch_limit` を repository に渡す。
- `list_items()` は repository の最大 `limit + 1` 件の結果から、response 用の `items[:limit]` と `next_cursor` を返す。
- `next_cursor` は has-more 時だけ、最後に表示する item から生成する。
- invalid cursor は `InvalidSampleItemCursorError` になる。
- `get_item()` / `update_item()` / `delete_item()` の not found は `SampleItemNotFoundError` になる。
- `update_item()` は `exclude_unset=True` 由来の changes だけ更新する。
- `description=None` 明示で description を clear できる。
- empty changes は no-op として existing item を返す。

- [x] **Step 10.5: repository / usecase を実装する**

実装方針:

- repository は `UnitOfWorkInterface` を注入し、AuthRepository と同じ `_persist()` 方針を使う。
- usecase は repository を注入する。
- usecase は `SampleItemResponse` や `api_error()` を import しない。
- controller が `SampleItemNotFoundError` / `InvalidSampleItemCursorError` を error envelope に変換する。

- [x] **Step 10.6: DI binding を追加する**

`backend/app/bootstrap/modules.py` の `SampleModule` を旧 `GetSampleIndexUsecaseInterface` から新 interface へ変更する。

- [x] **Step 10.7: sample unit tests を実行する**

```bash
cd backend
rtk uv run pytest tests/unit/services/test_sample_item_repository.py tests/unit/usecases/test_sample_item_usecase.py tests/unit/bootstrap/test_container.py -q
```

Expected:

- sample repository / usecase tests が成功する。

### Task 11: sample controller / route / integration tests を実装する

**Review ID:** `P3-8`, `P2-35`

**Files:**
- Modify: `backend/app/controllers/sample_controller.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/tests/unit/controllers/test_sample_controller.py`
- Modify: `backend/tests/unit/controllers/test_sample_controller_dependency.py`
- Create: `backend/tests/integration/test_sample_item_controller.py`
- Delete: `backend/app/usecases/get_sample_index_usecase.py`
- Delete: `backend/app/interfaces/usecases/get_sample_index_usecase_interface.py`

- [x] **Step 11.1: controller unit tests を REST 契約へ更新する**

`backend/tests/unit/controllers/test_sample_controller.py` で OpenAPI / route 契約を検証する。

- `GET /api/samples`
- `POST /api/samples`
- `GET /api/samples/{item_id}`
- `PATCH /api/samples/{item_id}`
- `DELETE /api/samples/{item_id}`
- `/api/sample/` は OpenAPI に出ない。
- error responses は `ErrorResponse` を参照する。

新規 `tests/unit/controllers/test_sample_item_controller.py` は作らない。integration test と basename が衝突するため、既存 `test_sample_controller.py` を更新する。

- [x] **Step 11.2: dependency override unit tests を追加する**

`backend/tests/unit/controllers/test_sample_controller_dependency.py` は次を検証する。

- `SampleItemUsecaseInterface` を dependency override して DB なしで `GET /api/samples` を test できる。
- `require_current_session` 相当の auth context も dependency override できる。
- usecase が `SampleItemNotFoundError` を投げると 404 `SAMPLE_ITEM_NOT_FOUND` になる。
- invalid cursor は 400 `SAMPLE_ITEM_INVALID_CURSOR` になる。

- [x] **Step 11.3: controller を実装する**

`backend/app/controllers/sample_controller.py` の API:

- `GET /api/samples?limit=20&cursor=...` -> `SampleItemListResponse`
- `POST /api/samples` -> `201 SampleItemResponse`
- `GET /api/samples/{item_id}` -> `SampleItemResponse`
- `PATCH /api/samples/{item_id}` -> `SampleItemResponse`
- `DELETE /api/samples/{item_id}` -> `204`

全 endpoint は `AuthenticatedSessionContext = Depends(require_current_session)` を受け取り、`ctx.user.id` を owner として usecase に渡す。unsafe request は Phase 2 の CSRF middleware で守るため、個別 `require_csrf` は書かない。

controller の責務:

- request DTO を domain changes へ変換する。
- usecase result を response DTO へ変換する。
- domain error を `api_error()` で error envelope へ変換する。

- [x] **Step 11.4: 旧 sample usecase を削除する**

削除:

- `backend/app/usecases/get_sample_index_usecase.py`
- `backend/app/interfaces/usecases/get_sample_index_usecase_interface.py`

削除後に次を確認する。

```bash
rtk grep -n "GetSampleIndexUsecase|/api/sample|sample_index" backend/app backend/tests documents
```

Expected:

- 旧 class / endpoint への参照が残らない。
- docs には旧 endpoint 廃止と新 `/api/samples` が書かれている。

- [x] **Step 11.5: integration tests を追加する**

`backend/tests/integration/test_sample_item_controller.py` で次を検証する。

- 未ログイン `GET /api/samples` は 401。
- ログイン済み user は `POST /api/samples` で item を作れる。
- public request / response JSON は camelCase。`populate_by_name=True` により snake_case 入力も内部的には受理されるが、integration test の request body と README の curl 例は camelCase だけを使う。
- `GET /api/samples` は自分の item だけを `createdAt DESC, id DESC` で返す。
- `GET /api/samples?limit=1` は `nextCursor` を返し、次ページを取得できる。
- `GET /api/samples/{id}` は自分の item を返す。
- `PATCH /api/samples/{id}` は指定 field だけ更新する。
- `PATCH /api/samples/{id}` の `{}` は 200 no-op。
- `PATCH /api/samples/{id}` の `{"description": null}` は description を clear する。
- `PATCH /api/samples/{id}` の 121 文字 title は 422 validation error。
- `DELETE /api/samples/{id}` は 204 で、以後 404。
- user A の item を user B が読む / 更新 / 削除すると 404。
- CSRF なし `POST /api/samples` は 403 `CSRF_VALIDATION_FAILED`。

- [x] **Step 11.6: sample endpoint tests を実行する**

```bash
cd backend
rtk uv run pytest tests/unit/controllers/test_sample_controller.py tests/unit/controllers/test_sample_controller_dependency.py -q
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration/test_sample_item_controller.py -q
```

Expected:

- unit tests が成功する。
- integration tests が skip 0 件で成功する。

### Task 12: docs と AGENTS を Phase 4 後の規約へ更新する

**Review ID:** `P2-23`, `P2-25`, `P3-8`, `P3-18`

**Files:**
- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`
- Modify: `frontend/AGENTS.md`
- Modify: `backend/README.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/plans/20260802-phase4-tooling-dx-sample-crud.md`

- [x] **Step 12.1: root AGENTS の品質ゲートを更新する**

追記 / 修正する内容:

- Backend unit: `cd backend && uv run pytest tests/unit`
- Backend integration: PostgreSQL 起動後、`ALEMBIC_DATABASE_URL=... uv run python manage.py db-upgrade` と `TEST_DATABASE_URL=... uv run pytest tests/integration`
- Backend static checks: `ruff`, `isort --check-only`, `yapf -dr`, `mypy app manage.py`, `db-check`
- Frontend: `npm run check:ci`, `npm test`, `npm run build`
- `npm run check` は mutating、CI は `npm run check:ci` を使う。

- [x] **Step 12.2: backend AGENTS を更新する**

追記 / 修正する内容:

- `manage.py serve --reload/--no-reload --workers --log-level`
- production Dockerfile は `--no-reload` を明示する。
- integration tests は DB URL 未設定で fail する。
- sample CRUD を新 resource の模範として参照する。
- API JSON の public contract は request / response とも camelCase を正とする。`populate_by_name=True` により snake_case request も内部互換として受理されるが、docs と新規実装例では camelCase だけを書く。
- 新規 resource 追加時の標準ファイル: model、schemas、domain errors、repository interface、repository、usecase interface、usecase、controller、migration、unit/integration tests。
- schema 変更前には計画書とユーザー確認が必要。

- [x] **Step 12.3: frontend AGENTS を更新する**

追記 / 修正する内容:

- `npm run typecheck`
- `npm run check:ci`
- `npm run build` は typecheck 後に Vite build する。

- [x] **Step 12.4: backend README を書く**

最低限含める内容:

- 前提: Python / uv / PostgreSQL / Docker Compose
- `.env` 作成: `cp .env.example .env`
- local 起動: `uv sync`, `python manage.py db-upgrade`, `python manage.py serve`
- hot reload は `.env` の `ENVIRONMENT=local` が前提。`.env` を作らない場合、既定は production 扱いで reload なしになる。
- Docker 起動: `docker compose up -d postgres backend frontend`
- anonymous `.venv` volume の注意: lock 更新後に問題があれば `docker compose down -v`
- quality gate: unit / integration / ruff / isort / yapf / mypy / db-check
- sample CRUD endpoint の curl 例
- `git add` や commit 手順は書かない。

- [x] **Step 12.5: backend app structure reference を限定更新する**

古い記述を次へ修正する。

- controller は service locator ではなく `Depends(inject(...))` 経由。
- transaction 境界は `UnitOfWorkInterface`。
- `services/` に repository 実装を置いている現状を正とする。
- usecase は HTTP response DTO を返さず、controller が response DTO に変換する。
- sample CRUD をコピー元として案内する。
- `Status` は healthz など限定用途であり、CRUD success envelope の模範ではない。

### Task 13: 全品質ゲートと smoke を実行する

**Files:**
- Inspect: whole repository
- Modify: `documents/plans/20260802-phase4-tooling-dx-sample-crud.md`

- [x] **Step 13.1: backend unit / tooling gate を実行する**

```bash
cd backend
rtk uv run ruff check .
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
rtk uv run mypy app manage.py
rtk uv run pytest tests/unit -q
```

- [x] **Step 13.2: backend integration gate を実行する**

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q -ra
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-check
```

Expected:

- integration tests が成功する。
- skip 0 件である。

- [x] **Step 13.3: frontend gate を実行する**

```bash
cd frontend
rtk npm run check:ci
rtk npm test
rtk npm run build
```

- [x] **Step 13.4: Docker / compose smoke を実行する**

```bash
rtk docker compose config
rtk docker build --target runtime -t python-react-template-backend:phase4 .
rtk docker build --target backend-dev -t python-react-template-backend-dev:phase4 .
rtk docker compose up -d postgres backend
rtk curl -i http://127.0.0.1:8000/api/healthz
rtk docker compose exec backend uv run pytest tests/unit/test_manage.py -q
rtk docker compose logs --tail=120 backend
```

- [x] **Step 13.5: sample CRUD manual smoke を実行する**

curl cookie jar を使って確認する。

```bash
cd backend
rtk curl -c /tmp/phase4-cookies.txt -b /tmp/phase4-cookies.txt http://127.0.0.1:8000/api/auth/csrf
```

以降、取得した CSRF token を `X-CSRF-Token` に入れて次を確認する。

- register -> 201
- `POST /api/samples` -> 201
- `GET /api/samples` -> 作成 item を含む
- `PATCH /api/samples/{id}` -> 200
- `DELETE /api/samples/{id}` -> 204
- `GET /api/samples/{id}` -> 404

- [x] **Step 13.6: repository diff を確認する**

```bash
rtk git diff --check
rtk git status --short -- ':!.superpowers'
```

Expected:

- whitespace error がない。
- `backend/static/` など生成物が status に出ない。
- `git add` は実行しない。

### Task 14: 実行結果と未対応事項を計画書へ反映する

**Files:**
- Modify: `documents/plans/20260802-phase4-tooling-dx-sample-crud.md`

- [x] **Step 14.1: 進捗サマリーを更新する**

完了した Task にチェックを入れる。

- [x] **Step 14.2: 実行結果を追記する**

記録する内容:

- 実行日時
- branch / HEAD
- 変更ファイル一覧
- dependency 追加の承認有無
- format-only reformat の承認有無
- schema 変更の承認有無
- targeted test 結果
- backend unit / integration 結果
- frontend 結果
- Docker smoke 結果
- skip 件数
- 未実行コマンドと理由

- [x] **Step 14.3: 未対応事項を更新する**

Phase 4 後に残す可能性が高いもの:

- sample CRUD の frontend UI。
- `services/` / `repositories/` の命名整理。
- 既存 auth model / repository の `utcnow()` 共通 clock 置換。Phase 4B で sample のみ clock helper を使う場合は残す。
- tests 全体への mypy strict 適用。
- coverage 閾値と `pytest-cov` 導入。
- CI 実行結果の GitHub 上での確認。ローカルでは workflow YAML と同等コマンドまで確認する。
- docs 全面同期。
- `aiosqlite` 依存削除。Phase 4 で pyproject を触る際に一緒に削除できるか確認し、リスクがあれば Phase 5 へ残す。

## 完了条件

- [x] Phase 4A と Phase 4B の差分を分けてレビューできる。
- [x] `manage.py serve` が `--reload/--no-reload`、`--workers`、`--port int`、`--log-level` を扱える。
- [x] `manage.py serve --reload --workers 2` が明示的に失敗する。
- [x] `ENVIRONMENT=production` の `manage.py serve` 既定が reload なしになる。
- [x] production Dockerfile CMD が `--no-reload` を明示する。
- [x] `manage.py version` が `backend/pyproject.toml` と一致する。
- [x] `manage.py db-revision` が `ALEMBIC_DATABASE_URL` 明示設定なしでは autogenerate しない。
- [x] backend に `pydantic-settings` が direct dependency として入っている。
- [x] backend dev dependencies に ruff / mypy が入っている。
- [x] ruff は import sorting を担当せず、isort と競合しない。
- [x] `Depends()` の `B008` と `models/__init__.py` の E402 が設定で正しく扱われている。
- [x] ruff `UP047` は YAPF 0.43 の PEP 695 parse 制約により `inject` helper の `TypeVar` + `cast` を維持し、対象行の狭い `# noqa: UP047` で扱っている。
- [x] UoW の nested context を表現する integration tests だけ `SIM117` が per-file ignore されている。
- [x] mypy が `explicit_package_bases = true` / `mypy_path = "."` により `app` を二重 module として解決せず、`mypy app manage.py` が実際に型検査を実行している。
- [x] mypy の `type-abstract` は DI pattern として設定で扱われ、その他の nullable / return type error は実装で修正されている。
- [x] `ruff check`, `isort --check-only`, `yapf -dr`, `mypy app manage.py` が成功する。
- [x] `TEST_DATABASE_URL` 未設定で integration tests が skip ではなく fail する。
- [x] backend unit tests と integration tests を別々に実行できる。
- [x] `.github/workflows/ci.yml` に backend unit / backend integration / frontend / docker job がある。
- [x] Docker Compose backend が dev target を使い、container 内で pytest / alembic / db-check を実行できる。
- [x] frontend に `typecheck` と `check:ci` がある。
- [x] frontend `build` が `typecheck` 後に Vite build を行う。
- [x] 旧 `/api/sample/` message endpoint が REST CRUD sample に置き換わっている。
- [x] `/api/samples` が authenticated user-owned CRUD resource として動く。
- [x] sample CRUD に model / schema / domain error / repository interface / repository / usecase interface / usecase / controller / migration / unit tests / integration tests がある。
- [x] usecase が HTTP response DTO を返さず、controller が DTO 変換を担当する。
- [x] sample list が order by と limit/cursor pagination を持つ。
- [x] PATCH は `exclude_unset=True` で省略と `null` 明示を区別し、empty body は 200 no-op になる。
- [x] sample API JSON の public contract は request / response とも camelCase で統一されている。snake_case request は `populate_by_name=True` による内部互換としてのみ扱い、docs には出さない。
- [x] `updated_at` が `onupdate=utcnow` を持つ。
- [x] `db-check` が sample migration 後も pending schema change なしで成功する。
- [x] `backend/README.md` に起動、DB、tests、Docker、sample CRUD の手順がある。
- [x] `AGENTS.md`、`backend/AGENTS.md`、`frontend/AGENTS.md` が Phase 4 後の品質ゲートを反映している。
- [x] `documents/references/backend-app-structure.md` の明らかな古い DI / sample 記述が更新されている。
- [x] backend unit / integration / frontend / Docker smoke / sample manual smoke が成功している。
- [x] `git diff --check` が clean である。
- [x] `git add`、`git commit`、`git push` を実行していない。

## 実行結果

### 2026-08-02 22:35:49 +07 Task 1 baseline

- branch: `feature/db-auth`
- HEAD: `7327332`
- working tree: `documents/plans/20260802-phase4-tooling-dx-sample-crud.md` の未追跡差分のみ
- dependency 追加: 未承認 / 未実行
- format-only reformat: 未承認 / 未実行
- schema 変更: 未承認 / 未実行
- `backend`: `rtk uv run pytest tests/unit -q` -> 170 passed, 1 warning
- `frontend`: `rtk npm test` -> 14 files / 78 tests passed
- `frontend`: `rtk npx tsc --noEmit` -> TypeScript errors なし
- Phase 4A / 4B 境界: Phase 4A は tooling / CI / Docker / docs まで、Phase 4B は sample CRUD の DB schema と backend resource 実装として分離する
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-02 22:42:24 +07 Task 2 tooling / format baseline

- format-only reformat: 承認済み / 実行済み
- `backend/pyproject.toml`: isort `line_length=100`、YAPF `column_limit=100`、ruff、mypy 設定を追加
- `backend`: `rtk uv run isort .` -> exit 0
- `backend`: `rtk uv run yapf -ir app/ tests/ alembic/ manage.py` -> exit 0
- `backend`: `rtk uv run isort . --check-only` -> exit 0
- `backend`: `rtk uv run yapf -dr app/ tests/ alembic/ manage.py` -> exit 0
- 振動確認: `isort . --check-only` と `yapf -dr app/ tests/ alembic/ manage.py` を再実行し、ともに exit 0
- 差分規模: `backend/pyproject.toml` を含む backend 50 files changed, 351 insertions, 575 deletions
- dependency 追加: 未承認 / 未実行
- schema 変更: 未承認 / 未実行
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-02 22:45:05 +07 Task 3 CLI / production reload

- `backend/tests/unit/test_manage.py`: serve options、production/local reload default、invalid port、version、db-revision の RED test を追加
- `backend/manage.py`: `--reload/--no-reload`、`--workers`、`--log-level`、int port、pyproject version 読み取り、`db-revision` を実装
- `Dockerfile`: runtime CMD に `--no-reload` を明示
- RED 確認: 実装前 `rtk uv run pytest tests/unit/test_manage.py -q` -> 9 failed, 7 passed
- GREEN 確認: 実装後 `rtk uv run pytest tests/unit/test_manage.py -q` -> 16 passed
- dependency 追加: 未承認 / 未実行
- schema 変更: 未承認 / 未実行
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-02 22:52:47 +07 Task 4 backend tooling / typecheck

- dependency 追加: 承認済み / 実行済み
- runtime dependency: `pydantic-settings`
- dev dependencies: `ruff`, `mypy`
- `backend/pyproject.toml` と `backend/uv.lock` を更新
- RED 確認: 初回 `rtk uv run ruff check .` -> 10 errors
- RED 確認: 初回 `rtk uv run mypy app manage.py` -> 14 errors
- 実装修正: unused import、`datetime.UTC`、nullable narrowing、SQLModel column expression、例外 handler 型、error response metadata 型、`json_error_response()` の `Mapping` / `Sequence` 対応を修正
- 計画との差分: `def inject[T](...)` は現行 YAPF が PEP 695 generic function を parse できず `yapf -ir app/ tests/ alembic/ manage.py` が失敗したため、`TypeVar` + `cast` を維持し、`inject()` の `UP047` だけ対象行の `# noqa: UP047` で抑制した
- `backend`: `rtk uv run ruff check .` -> All checks passed
- `backend`: `rtk uv run isort . --check-only` -> exit 0
- `backend`: `rtk uv run yapf -dr app/ tests/ alembic/ manage.py` -> exit 0
- `backend`: `rtk uv run mypy app manage.py` -> Success: no issues found in 51 source files
- schema 変更: 未承認 / 未実行
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-02 22:53:52 +07 Task 5 frontend build / typecheck scripts

- `frontend/package.json`: `typecheck` と `check:ci` を追加し、`build` を `npm run typecheck && vite build` に変更
- `frontend/package.json`: mutating `check` に `npm run typecheck` を追加
- `frontend`: `rtk npm run check:ci` -> exit 0
- `frontend`: `rtk npm test` -> 14 files / 78 tests passed
- `frontend`: `rtk npm run build` -> typecheck 後に Vite build 成功
- build warning: `%VITE_SITE_URL%` 未定義 warning が 3 件出たが、既存の env placeholder warning で build 自体は成功
- `backend/static`: build 後も `git status --short` に差分なし
- schema 変更: 未承認 / 未実行
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-02 22:55:55 +07 Task 6 integration gate / CI

- `backend/tests/unit/test_integration_helpers.py`: `TEST_DATABASE_URL` 未設定時に skip ではなく fail する契約 test を追加
- RED 確認: 実装前 `rtk uv run pytest tests/unit/test_integration_helpers.py -q` -> 1 failed, 1 passed
- `backend/tests/integration/helpers.py`: `pytest.skip()` から `pytest.fail()` へ変更
- `backend/tests/integration/conftest.py`: cleanup 対象に Phase 4B の `sample_items` を予約
- `.github/workflows/ci.yml`: backend unit、backend integration、frontend、docker job を追加
- `backend`: `rtk uv run pytest tests/unit/test_integration_helpers.py -q` -> 2 passed
- `backend`: `rtk uv run ruff check .` -> All checks passed
- `backend`: `rtk uv run mypy app manage.py` -> Success: no issues found in 51 source files
- `backend`: `rtk uv run isort . --check-only` -> exit 0
- `backend`: `rtk uv run yapf -dr app/ tests/ alembic/ manage.py` -> exit 0
- `.github/workflows/ci.yml`: `rtk grep -n "pull_request|backend-unit|backend-integration|frontend|docker|TEST_DATABASE_URL|db-check|check:ci|backend-dev|--target runtime" .github/workflows/ci.yml` -> 15 matches
- schema 変更: 未承認 / 未実行
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-02 22:59:06 +07 Task 7 Docker Compose DX

- `Dockerfile`: `backend-base` と `backend-dev` target を追加し、`runtime` は `backend-base` から派生
- `Dockerfile`: production `runtime` CMD は引き続き `--no-reload` を明示
- `docker-compose.yaml`: backend service を `build.target: backend-dev` へ変更
- `docker-compose.yaml`: backend mount を `./backend:/app/backend` に変更し、`/app/backend/.venv` anonymous volume を追加
- `docker-compose.yaml`: backend command に `uv sync --frozen --group dev`、`db-upgrade`、`serve --reload` を設定
- `docker-compose.yaml`: backend healthcheck を Python stdlib `urllib.request` に変更
- `backend/README.md`: anonymous `.venv` volume と `docker compose down -v` の注意を追記
- `root`: `rtk docker compose config` -> exit 0
- `root`: `rtk docker build --target backend-dev -t python-react-template-backend-dev:phase4a .` -> exit 0
- `root`: `rtk docker compose up -d postgres backend` -> exit 0
- `root`: `rtk docker compose exec backend uv run python manage.py db-check` -> No new upgrade operations detected
- `root`: `rtk docker compose exec backend uv run pytest tests/unit/test_manage.py -q` -> 16 passed
- `root`: `rtk docker compose ps backend` -> healthy
- `root`: `curl -i http://127.0.0.1:8000/api/healthz` -> 200 OK, `{"success":true,"message":"ok"}`
- note: `rtk curl -i http://127.0.0.1:8000/api/healthz` は exit 7 で詳細が出なかったため、接続切り分け目的で生 `curl` を使用した
- schema 変更: 未承認 / 未実行
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-02 23:03:25 +07 Task 8 Phase 4A quality gate

- `backend`: `rtk uv run ruff check .` -> All checks passed
- `backend`: `rtk uv run isort . --check-only` -> exit 0
- `backend`: `rtk uv run yapf -dr app/ tests/ alembic/ manage.py` -> exit 0
- `backend`: `rtk uv run mypy app manage.py` -> Success: no issues found in 51 source files
- `backend`: `rtk uv run pytest tests/unit -q` -> 182 passed, 1 warning
- `backend`: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade` -> exit 0
- `backend`: 初回 `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q -ra` -> 12 failed, 33 passed。原因は `sample_items` 未作成時に cleanup 全体が失敗し auth tables が残る実装だった
- `backend/tests/integration/conftest.py`: `to_regclass()` で存在する table だけ TRUNCATE するよう修正
- `backend`: 再実行 `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q -ra` -> 45 passed, 4 warnings, skip 0
- `backend`: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-check` -> No new upgrade operations detected
- `frontend`: `rtk npm run check:ci` -> exit 0
- `frontend`: `rtk npm test` -> 14 files / 78 tests passed
- `frontend`: `rtk npm run build` -> exit 0。`%VITE_SITE_URL%` 未定義 warning 3 件は継続
- `root`: `rtk docker compose config` -> exit 0
- `root`: `rtk docker build --target runtime -t python-react-template-backend:phase4a .` -> exit 0。`npm audit` summary は 18 vulnerabilities
- `root`: `rtk docker build --target backend-dev -t python-react-template-backend-dev:phase4a .` -> exit 0
- `root`: `rtk git diff --stat` -> 60 files changed, 863 insertions, 634 deletions
- `root`: `rtk git diff --check` -> exit 0
- `root`: `rtk git status --short -- ':!.superpowers'` -> Phase 4A 差分と新規 `.github/workflows/ci.yml` / `backend/tests/unit/test_integration_helpers.py` / 本計画書を確認
- schema 変更: 未承認 / 未実行
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-02 23:11:36 +07 Task 9 sample schema / DTO

- schema 変更: 承認済み / 実行済み
- `backend/tests/unit/models/test_sample_item.py`: table metadata、FK cascade、`updated_at.onupdate`、camelCase alias、PATCH `exclude_unset`、response serialization の RED test を追加
- RED 確認: 実装前 `rtk uv run pytest tests/unit/models/test_sample_item.py -q` -> `ModuleNotFoundError: app.libraries.clock`
- `backend/app/libraries/clock.py`: timezone-aware `utcnow()` を追加
- `backend/app/models/sample_item.py`: `SampleItem` table、cursor/list/update domain dataclass を追加
- `backend/app/models/sample_item_schemas.py`: create/update/response DTO を追加
- `backend/app/models/sample_item_errors.py`: sample domain errors を追加
- `backend/app/models/__init__.py`: `SampleItem` を metadata import 対象へ追加
- `backend`: 初回 `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-revision --message "create sample items" --autogenerate` -> `alembic/versions/17723dfe9a1b_create_sample_items.py` を生成
- note: レビュー修正で `manage.py db-revision --rev-id` を追加し、sample migration は `alembic/versions/20260802_0002_create_sample_items.py` / revision `20260802_0002` へ修正した
- `backend`: `rtk uv run yapf -i alembic/versions/20260802_0002_create_sample_items.py` -> exit 0
- `backend`: `rtk uv run pytest tests/unit/models/test_sample_item.py -q` -> 4 passed
- `backend`: 初回 `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade` -> `20260418_0001 -> 17723dfe9a1b`
- note: レビュー修正後、既に適用済みのローカル `app_test` DB は `alembic_version` を `20260802_0002` へ更新した。fresh DB では `20260418_0001 -> 20260802_0002` として適用される
- `backend`: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-check` -> No new upgrade operations detected
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-03 02:25:39 +07 Task 10 sample repository / usecase

- `backend/tests/unit/services/test_sample_item_repository.py`: owner scope、DESC order、cursor keyset、persist flush/commit/delete 契約 test を追加
- `backend/tests/unit/usecases/test_sample_item_usecase.py`: owner 設定、limit+1 pagination、cursor decode、invalid cursor、not found、PATCH semantics、no-op update test を追加
- RED 確認: 実装前 `rtk uv run pytest tests/unit/services/test_sample_item_repository.py tests/unit/usecases/test_sample_item_usecase.py -q` -> `ModuleNotFoundError`
- `backend/app/interfaces/services/sample_item_repository_interface.py`: repository interface を追加
- `backend/app/interfaces/usecases/sample_item_usecase_interface.py`: usecase interface を追加
- `backend/app/services/sample_item_repository.py`: SQLModel / UoW repository を追加
- `backend/app/usecases/sample_item_usecase.py`: cursor encode/decode、pagination、CRUD usecase を追加
- `backend/app/bootstrap/modules.py`: sample repository/usecase binding を追加
- `backend/tests/unit/bootstrap/test_container.py`: sample binding singleton test を更新
- `backend`: `rtk uv run pytest tests/unit/services/test_sample_item_repository.py tests/unit/usecases/test_sample_item_usecase.py tests/unit/bootstrap/test_container.py -q` -> 16 passed
- `backend`: `rtk uv run ruff check .` -> All checks passed
- `backend`: 初回 `rtk uv run mypy app manage.py` -> `sample_item_schemas.py` の `model_config` 型 error 1 件
- `backend/app/models/sample_item_schemas.py`: `SQLModelConfig(alias_generator=to_camel, populate_by_name=True)` に変更
- `backend`: 再実行 `rtk uv run mypy app manage.py` -> Success: no issues found in 59 source files
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-03 05:34:29 +07 Task 11 sample controller / integration

- `backend/tests/unit/controllers/test_sample_controller.py`: OpenAPI contract を旧 `/api/sample/` から `/api/samples` CRUD へ更新
- `backend/tests/unit/controllers/test_sample_controller_dependency.py`: `SampleItemUsecaseInterface` と `require_current_session` の dependency override test を追加
- RED 確認: 実装前 controller tests -> 5 failed
- `backend/app/controllers/sample_controller.py`: `/samples` REST CRUD controller へ置換
- `backend/app/usecases/get_sample_index_usecase.py`: 削除
- `backend/app/interfaces/usecases/get_sample_index_usecase_interface.py`: 削除
- `backend/app/interfaces/usecases/__init__.py` / `backend/app/usecases/__init__.py`: 旧 sample export を削除し新 sample usecase を export
- `backend/app/interfaces/services/__init__.py` / `backend/app/services/__init__.py`: sample repository export を追加
- `backend/tests/integration/test_sample_item_controller.py`: auth 必須、camelCase、CRUD、pagination、owner isolation、CSRF 403 の integration test を追加
- `backend`: `rtk uv run pytest tests/unit/controllers/test_sample_controller.py tests/unit/controllers/test_sample_controller_dependency.py -q` -> 5 passed, 1 warning
- `backend`: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade` -> exit 0
- `backend`: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration/test_sample_item_controller.py -q` -> 3 passed, 1 warning
- `backend`: `rtk grep -n "GetSampleIndexUsecase|sample_index" backend/app backend/tests` -> 0 matches
- `backend`: `rtk uv run ruff check .` -> All checks passed
- `backend`: `rtk uv run mypy app manage.py` -> Success: no issues found in 57 source files
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-03 05:37:06 +07 Task 12 docs / AGENTS

- `AGENTS.md`: backend static/unit/integration、frontend `check:ci`、Docker gate を品質ゲートへ反映
- `backend/AGENTS.md`: `serve` options、ruff/isort/yapf/mypy、integration fail-fast、Docker Compose `.venv` volume、sample CRUD 複製手順、camelCase API 規約を追記
- `frontend/AGENTS.md`: `typecheck`、`check:ci`、build は typecheck 後に Vite build することを追記
- `backend/README.md`: setup、DB、quality gate、Docker Compose、sample CRUD curl 例を作成
- `documents/references/backend-app-structure.md`: service locator / 旧 sample / `repositories/` 予定表記を削除し、Phase 4 後の DI / UoW / services repository / sample CRUD 構成へ置換
- `root`: `rtk grep -n "GetSampleIndexUsecase|request.app.state.injector|get_sample_index|/api/sample/|Status.*CRUD|repositories/.*今後" AGENTS.md backend/AGENTS.md frontend/AGENTS.md backend/README.md documents/references/backend-app-structure.md` -> 意図的な禁止/注意記述のみ
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-03 05:46:58 +07 Task 13 full quality gate / smoke

- branch: `feature/db-auth`
- HEAD: `7327332`
- dependency 追加: 承認済み / 実行済み
- format-only reformat: 承認済み / 実行済み
- schema 変更: 承認済み / 実行済み
- `backend`: `rtk uv run ruff check .` -> All checks passed
- `backend`: `rtk uv run isort . --check-only` -> skipped 4 files, exit 0
- `backend`: `rtk uv run yapf -dr app/ tests/ alembic/ manage.py` -> exit 0
- `backend`: `rtk uv run mypy app manage.py` -> Success: no issues found in 57 source files
- `backend`: `rtk uv run pytest tests/unit -q` -> 203 passed, 1 warning
- `backend`: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade` -> exit 0
- `backend`: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q -ra` -> 48 passed, 4 warnings, skip 0
- `backend`: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-check` -> No new upgrade operations detected
- `frontend`: `rtk npm run check:ci` -> exit 0
- `frontend`: `rtk npm test` -> 14 files / 78 tests passed
- `frontend`: `rtk npm run build` -> typecheck 後に Vite build 成功
- `frontend` build warning: `%VITE_SITE_URL%` 未定義 warning 3 件は継続
- `root`: `rtk docker compose config` -> exit 0
- `root`: `rtk docker build --target runtime -t python-react-template-backend:phase4 .` -> exit 0
- `root`: `rtk docker build --target backend-dev -t python-react-template-backend-dev:phase4 .` -> exit 0
- `root`: `rtk docker compose up -d postgres backend` -> postgres healthy / backend running
- `root`: `rtk docker compose ps backend` -> backend healthy
- `root`: `rtk docker compose exec backend uv run pytest tests/unit/test_manage.py -q` -> 16 passed
- `root`: `curl -i http://127.0.0.1:8000/api/healthz` -> 200 OK, `{"success":true,"message":"ok"}`
- note: `rtk curl -i http://127.0.0.1:8000/api/healthz` は exit 7 で詳細が出なかったため、接続切り分け目的で生 `curl` を使用した
- sample manual smoke: `Secure` cookie は HTTP の `httpx` cookie jar では自動送信されないため、compose HTTP smoke では `Cookie` header を明示して確認した
- sample manual smoke 初回: compose backend が Phase 4B migration 生成前から起動していたため、`POST /api/samples` が `sample_items` 未作成で 500。`rtk docker compose exec backend uv run python manage.py db-upgrade` で初回 revision を適用後に再実行した。レビュー修正後の migration revision ID は `20260802_0002`
- sample manual smoke 再実行: register 201、create 201、list 200 items 1、patch 200 `true`、delete 204、get-after-delete 404
- `root`: `rtk docker compose logs --since 20s backend` -> healthcheck の 200 のみで新規 error なし
- `root`: `rtk git diff --check` -> exit 0
- `root`: `rtk git status --short -- ':!.superpowers'` -> Phase 4 差分と新規ファイルを確認。`backend/static/` の差分なし
- `root`: `rtk git diff --stat` -> tracked files 69 files changed, 1305 insertions, 823 deletions。未追跡の新規ファイルは `git status --short` で別途確認
- 未実行コマンド: GitHub Actions 上の CI はローカルでは実行していない。workflow YAML と同等のローカルコマンド、Docker build、compose smoke まで確認した
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-03 05:46:58 +07 Task 14 plan update / residuals

- 進捗サマリー: Task 13 と Task 14 を完了へ更新
- 完了条件: 実測結果に基づき全項目を更新。`UP047` は PEP 695 化ではなく YAPF 0.43 制約による狭い `# noqa: UP047` として完了条件の文言を実装事実へ修正
- 実行結果: full gate、Docker/compose、sample manual smoke、`git diff --check`、status の結果を追記
- 未対応事項: Phase 5 以降に残す項目へ更新
- 禁止事項: worktree、`git add`、`git commit`、`git push` は未実行

### 2026-08-03 Phase 4 code review fixes

- Critical: `PATCH {"title": null}` / `PATCH {"isCompleted": null}` を 422 に変更。schema unit test と integration test を追加
- Critical: request DTO に `extra="forbid"` を設定し、`PATCH {"tittle": "..."}` の typo を 422 に変更
- High: `SampleItemUsecase.update_item()` / `delete_item()` の read-modify-write を `UnitOfWorkInterface.transaction()` で囲むよう修正。unit test で SELECT と UPDATE/DELETE が同一 transaction 境界内にあることを確認
- Medium: sample OpenAPI の error response 宣言を endpoint ごとに分割し、到達不能な 400/403/404 を外した
- Medium: `manage.py db-revision --rev-id` を追加し、sample migration を `20260802_0002_create_sample_items.py` / revision `20260802_0002` に修正
- Low: unused `SampleItemListQuery` を削除
- Low: cursor decode の `except Exception` を `(binascii.Error, KeyError, TypeError, UnicodeError, ValueError)` に限定
- Low: sample repository の write 後 `refresh()` を削除し、keyset 条件の `col(...)` 利用を統一
- Low: sample CRUD integration test をシナリオ単位に分割
- Low: CI に `push.branches: [master]` と `concurrency.cancel-in-progress` を追加
- Low: pytest integration marker 説明を auth 限定から API / persistence 全体へ更新

## 未対応事項

- sample CRUD の frontend UI は対象外のため未実装。backend の模範実装と API contract まで完了。
- `services/` / `repositories/` の命名整理は Phase 4 対象外。現行規約に合わせ、新規 sample repository 実装も `services/` 配下に置いた。
- 既存 auth model / repository / usecase の `utcnow()` 共通 clock helper への全面置換は未実施。Phase 4 では新規 sample model のみ `app/libraries/clock.py` を使う。
- tests 全体への mypy strict 適用は未実施。Phase 4 の gate は `mypy app manage.py`。
- coverage 閾値と `pytest-cov` 導入は未実施。閾値設計なしに依存だけ増やさない方針。
- GitHub Actions 上の CI 実行結果は未確認。ローカルでは workflow YAML と同等の backend unit / integration / frontend / Docker gate を確認済み。
- docs 全面同期は未実施。Phase 4 で触った root/backend/frontend AGENTS、backend README、backend app structure reference に限定更新。
- `aiosqlite` 依存削除は未実施。既存 lock / dependency 影響の切り分けが必要なため Phase 5 候補。
- frontend build の `%VITE_SITE_URL%` 未定義 warning 3 件は継続。既存 placeholder warning で build は成功。
- Docker runtime build 時の npm dependency audit summary で 18 vulnerabilities が表示される。Phase 4 の build gate は成功しているが、frontend 依存更新は別タスクで扱う。
- compose HTTP smoke では auth cookies が `Secure` で返るため、HTTP クライアントによっては cookie jar が自動送信しない。今回の手動 smoke は `Cookie` header を明示して実施した。
- sample CRUD の `update_item` / `delete_item` は read-modify-write を同一 transaction に閉じたが、READ COMMITTED で `SELECT ... FOR UPDATE` は使っていない。SELECT 後 write 前に別 transaction が同じ行を削除した場合の `StaleDataError` 500 化は、Phase 5 以降で pessimistic lock または affected rows ベースの repository API として検討する。

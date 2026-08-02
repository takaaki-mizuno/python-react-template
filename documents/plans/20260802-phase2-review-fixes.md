# Phase 2 最終レビュー対応計画

## 背景

Phase 2 認証セキュリティ強化の実装後レビューで、実装上の Critical 3 件と、テストが mutation を十分に殺せていない問題が指摘された。特に次の3点は、Phase 2のセキュリティ境界そのものに関わるため、Phase 2完了前の追補として扱う。

- CSRF middleware が `scope["path"]` を直接見ており、`root_path` 配下デプロイで `/api` 判定が外れる。
- `InMemoryLoginRateLimiter` が request ごとに全 bucket を走査し、rate limit 自体が同期 DoS 経路になりうる。
- `record_failure()` が audit log INSERT の後にあり、DB が詰まった状況で rate limit 記録が止まる。

## 方針とその理由

- CSRF は `root_path` を剥がした route path で判定する。サブパス配下でも「unsafe `/api` request は routing 前に CSRF 検証」という契約を維持するため。Starlette の private API には依存せず、必要な処理をローカル helper とテストで固定する。
- rate limiter は「触った bucket だけ trim」へ変更し、scope ごとの bucket 数を bounded にする。ただし active bucket を silent eviction すると per-email rate limit をバイパスでき、shared overflow bucket は全体封鎖を作るため使わない。満杯時は oldest bucket から expired bucket を必要な分だけ償却 reclaim し、それでも満杯なら新規 bucket は作らず fail-open と warning に寄せる。
- login/register の失敗 rate 記録は audit INSERT より前に行う。監査ログが落ちても、ブルートフォース防御は落とさない。
- rate limit 到達後の request は audit INSERT を行わず即時に `RateLimitExceededError` を返す。通常失敗は監査しつつ、block 後の連打で DB 書き込みを増幅させないため。
- register の duplicate / weak password 失敗は login の email 単独 bucket へ記録しない。register 409 だけで任意アカウントの login を email 単位にロックアウトできる経路を防ぐため。
- XFF 解決は複数 header、IPv4-mapped IPv6、`ip:port` を扱う。信頼 proxy 対応の目的は spoofing 耐性と実 client IP の維持なので、一般的な proxy 表現で fallback して全ユーザーが proxy IP bucket へ潰れる状態を避ける。
- テストはレビューで指摘された mutation が落ちる具体データに変更する。テスト名だけでなく、壊れた実装が実際に失敗することを受け入れ基準にする。

## 具体的なタスク

- [x] CSRF middleware の path 判定を `root_path` 対応に変更する。
- [x] `TestClient(..., root_path="/backend")` で CSRF なし unsafe `/api` request が 403 になるテストを追加する。
- [x] PUT/PATCH/DELETE の unsafe method も CSRF なしで 403 になるテストを追加する。
- [x] CSRF 比較が bytes の `secrets.compare_digest()` を使うことをテストで固定する。
- [x] 非ASCII CSRF mismatch が 500 ではなく 403 になることを middleware test へ追加する。
- [x] XFF chain test を「左から走査」では通らないデータに変更する。
- [x] 複数 `X-Forwarded-For` header を連結して扱う。
- [x] IPv4-mapped IPv6 の trusted proxy 判定を IPv4 CIDR と照合できるようにする。
- [x] `ip:port` / `[ipv6]:port` 形式の XFF を parse できるようにする。
- [x] rate limiter の request 時全 bucket 走査を廃止し、触った bucket だけ trim する。
- [x] `AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE` を追加し、LRU eviction で bucket 数を bounded にする。
- [x] rate limit 関連設定に正の整数 validation を追加する。
- [x] `record_failure()` を audit INSERT より前に移動する。
- [x] audit INSERT 失敗時にも login/register failure が rate limiter に記録されるテストを追加する。
- [x] registration bucket で block された register の `Retry-After` が registration window になるようにする。
- [x] `backend/AGENTS.md` に rate limiter bucket 上限と初期 migration 書き換え時の drift 検出限界を追記する。

## 再レビュー対応

Claude Code の再レビューで、新しい bucket 上限実装と root_path 回帰テストに対する追加指摘があった。実装は次の方針で追補する。

- [x] `is_allowed()` で bucket 参照時に LRU 順序を更新しないようにする。
- [x] bucket 上限到達時は active bucket を evict せず、expired bucket だけを掃除する。
- [x] expired 掃除後も上限に達している場合は shared overflow bucket へ記録し、warning log を出す。（ラウンド3で全体封鎖リスクが判明したため廃止）
- [x] overflow bucket へ記録された飽和時の失敗が、次回以降の `is_allowed()` 判定にも使われるようにする。（ラウンド3で全体封鎖リスクが判明したため廃止）
- [x] overflow bucket も window に従って trim し、古い飽和記録が残り続けないようにする。（ラウンド3で全体封鎖リスクが判明したため廃止）
- [x] register duplicate / weak password / race duplicate の失敗記録では `include_email_bucket=False` を指定し、login の per-email bucket を汚さない。
- [x] register duplicate が email bucket を増やさないことを usecase と rate limiter のテストで固定する。
- [x] `root_path="/backend"` かつ `path="/backend/api/..."` の raw ASGI scope を middleware に直接流す回帰テストを追加する。
- [x] CSRF path 判定から `starlette._utils` の private import を削除し、ローカル helper へ置き換える。
- [x] XFF の不正 token は chain 全体ではなく token 単位で無視する。
- [x] 全 token が不正な XFF は direct peer へ fallback する。
- [x] `AUTH_TRUSTED_PROXY_IPS` の不正値を settings load 時に validation error にする。
- [x] `AuthSettings` を直接生成する unit test は `_env_file=None` を指定し、ローカル `.env` から隔離する。
- [x] `PasswordHashExecutor` のテストで hash/verify が main thread ではなく `password-hash` worker thread 上で実行されることを検証する。
- [x] rate limit 到達後の login/register request では audit log INSERT を行わない。
- [x] rate-limited request が audit log を作らないことを usecase test で固定する。

## ラウンド3再レビュー対応

Claude Code のラウンド3再レビューで、shared overflow bucket が login 全体封鎖、registration fail-open の非対称、cap 到達時の全走査を作ることが指摘された。Phase 2 の in-memory limiter は single-process の最小防御なので、飽和時は全体封鎖ではなく fail-open を選び、warning で観測する。

- [x] shared overflow bucket を廃止する。
- [x] cap 到達時は active bucket を evict せず、oldest bucket から expired bucket だけを必要な分だけ reclaim する。
- [x] expired reclaim 後も cap に達している場合、新規 login/register bucket は作らず fail-open にする。
- [x] cap 到達時に新規・休眠ユーザー全体を block しないことを rate limiter test で固定する。
- [x] cap 到達後も既存 email bucket の per-email block は維持されることを rate limiter test で固定する。
- [x] registration bucket も login 系 scope と同じ cap 到達時 fail-open にし、shared overflow を作らないことを test で固定する。
- [x] cap 到達時の expired reclaim が no-op にならないことを test で固定する。
- [x] `record_failure()` が既存 bucket の LRU 順序を更新することを test で固定する。
- [x] `reset()` で bucket cap warning の抑制状態も clear し、reset 後に再度 warning が出ることを test で固定する。
- [x] XFF は右から遅延 parse し、不正 token に当たったら direct peer へ fallback する。
- [x] 右端不正 token、trusted hop 後の不正 token、末尾空 token の XFF spoofing 回帰テストを追加する。
- [x] `create_app()` で `AuthSettings` を eager resolve し、trusted proxy 設定不正を起動時に fail-fast させる。
- [x] `AUTH_TRUSTED_PROXY_IPS` の `0.0.0.0/0` と `::/0` を settings validation で拒否する。
- [x] `validate_session_csrf()` を直接呼ぶ unit test を追加し、`NO_SESSION` / `VALID` / `MISMATCH` を固定する。

## ラウンド4再レビュー対応

Claude Code のラウンド4再レビューでは、前回 Critical 3件は実測上すべて解消され、判定はマージ可となった。残る事項はブロッカーではないが、運用者が判断しやすいよう明記と低リスクなテスト隔離だけ行う。

- [x] bucket 上限到達後の fail-open は全体封鎖を避けるためのトレードオフであり、飽和中の新規キーは per-email 防御の追跡対象外になることを `backend/AGENTS.md` に明記する。
- [x] 本番で fail-open リスクを許容できない場合は Redis 等の共有 store または O(1) メモリ方式へ置き換える必要があることを `backend/AGENTS.md` に明記する。
- [x] `.env` が存在しても `test_unset_environment_disables_docs_by_default` がローカル環境値に汚染されないよう、`Config(_env_file=None)` を使う。
- [x] `.env` が存在しても `test_db_check_rejects_default_alembic_database_url` がローカル `.env` に汚染されないよう、空の一時ディレクトリへ移動して実行する。

## 実行結果

- targeted: `tests/unit/bootstrap/test_csrf_middleware.py tests/unit/libraries/test_client_ip.py tests/unit/libraries/test_auth_rate_limiter.py tests/unit/config/test_auth_settings.py tests/unit/usecases/test_auth_usecase.py tests/unit/libraries/test_password_hasher.py tests/unit/controllers/test_auth_controller_helpers.py tests/unit/controllers/test_auth_controller_dependency.py tests/unit/controllers/test_auth_dependencies.py -q` は `99 passed, 1 warning`。
- round4 targeted: `tests/unit/bootstrap/test_create_app.py::test_unset_environment_disables_docs_by_default tests/unit/test_manage.py::test_db_check_rejects_default_alembic_database_url -q` は `2 passed, 1 warning`。
- round3 targeted: `tests/unit/libraries/test_auth_rate_limiter.py tests/unit/libraries/test_client_ip.py tests/unit/config/test_auth_settings.py tests/unit/bootstrap/test_create_app.py tests/unit/usecases/test_auth_usecase.py -q` は `81 passed, 1 warning`。
- previous targeted: `tests/unit/bootstrap/test_csrf_middleware.py tests/unit/libraries/test_client_ip.py tests/unit/libraries/test_auth_rate_limiter.py tests/unit/config/test_auth_settings.py tests/unit/usecases/test_auth_usecase.py tests/unit/controllers/test_auth_controller_dependency.py -q` は `76 passed, 1 warning`。
- backend unit: `tests/unit -q` は `170 passed, 1 warning`。
- PostgreSQL integration: `tests/integration -q` は `45 passed, 4 warnings`。skip 0件。
- `db-check`: `No new upgrade operations detected.`
- `isort . --check-only` と `yapf -dr app/ tests/ alembic/ manage.py` は成功。
- `git diff --check` は clean。

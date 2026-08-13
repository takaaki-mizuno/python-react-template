# Redis Auth Rate Limiter と利用スキル実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: 実装時は `superpowers:test-driven-development` を使い、各タスクを RED -> GREEN -> REFACTOR で進める。skill 作成タスクでは `superpowers:writing-skills` も使う。Worktree は使わず現在のブランチで作業してよいが、この計画作成時の人間指示により `git add` / `git commit` は禁止されている。

**Goal:** 複数 backend worker / instance 間でログイン・登録・OIDC 開始・退会再認証の rate limit 状態を共有できる Redis 実装を追加し、今後 `LoginRateLimiterInterface` と auth rate limit 契約を変更・利用するときに参照する project skill を作る。

**Architecture:** 現在の `LoginRateLimiterInterface` は sync method だが、Redis I/O を request path で扱うには async interface が必要であるため、interface を async 化する。既定は既存互換の in-memory 実装を維持し、`AUTH_RATE_LIMIT_BACKEND=redis` のときだけ Redis 共有 store を使う。Redis 側は sorted set で sliding window bucket を表現し、score の時刻軸は Redis server `TIME` の Unix epoch seconds を正典にする。

**Tech Stack:** FastAPI, Injector, Pydantic Settings, redis-py `redis.asyncio`, Redis Docker official image, pytest, uv, Codex/Claude project skills.

---

## 背景

現在の rate limiter は `backend/app/libraries/auth_rate_limiter.py` の `InMemoryLoginRateLimiter` だけで、`backend/app/bootstrap/modules.py` の DI provider も常にこれを返している。`backend/AGENTS.md` には、in-memory rate limiter は single-process の最小防御であり、複数 worker / 複数 instance の本番運用では共有 store へ置き換える、と明記されている。

複数 backend process が立つ構成では、同じ email / IP の失敗回数が process ごとに分散し、設定値どおりの遮断にならない。逆に、ある process だけで 429 になっても別 process に当たれば通る可能性がある。

既存契約として守るべき点は次の通り。

- login/register 失敗 rate limit は IP、email+IP、email 単独の 3 bucket で判定する。
- bucket への記録は失敗時だけ行う。
- login 成功時は email+IP bucket だけを削除し、IP bucket と email bucket は削除しない。
- duplicate email など register 由来の失敗は login の email 単独 bucket へ記録しない。
- account deletion の password 再認証判定は IP bucket と email+IP bucket だけを読む。
- rate limit 到達後の request は audit log INSERT を行わず 429 へ変換する。
- register 成功 rate limit は login failure とは別 bucket と window で扱う。
- OIDC authorization start は login failure と同じ auth window だが別 bucket で扱う。

## レビュー反映

Claude Code レビューで指摘された内容を現行コードと照合し、次を計画へ反映した。

- `time.monotonic()` は process ごとに原点が異なるため、Redis score には使わない。Redis 実装は Redis server `TIME` の Unix epoch seconds を正典にする。
- check 系で `ZREMRANGEBYSCORE -> ZCARD` を bucket ごとに直列実行しない。check は read-only の `ZCOUNT` を pipeline でまとめ、trim は record 時だけ行う。
- Redis 障害時に request ごとに timeout が積み上がらないよう、1 logical operation 単位の deadline と process-local circuit breaker を追加する。
- Redis memory 方針を「運用に投げる」だけにしない。local compose と docs に rate-limit 用 Redis の `maxmemory` / `maxmemory-policy volatile-ttl` を明記する。
- `anyio.from_thread.run()` は現在の sync pytest fixture では前提が合わないため使わない。default integration fixture は memory backend 前提で sync `reset_for_tests()` による cleanup にする。Redis integration は async fixture で扱う。
- `reset()` を production interface から外し、test cleanup 用の `reset_for_tests()` として実装クラスに持たせる。
- Task 2 と Task 8 の重複を解消し、Task 8 は漏れ確認と integration verification に縮小する。
- skill 作成はユーザー要件に含まれるため同じ計画に残すが、既存 project skill 慣習に合わせて `SKILL.md` 単体に縮小し、`evals/evals.json` は作らない。
- 追加レビューで確認された `backend/tests/integration/test_auth_oidc_controller.py` の直接 `reset()` 呼び出しと、`backend/tests/integration/test_auth_controller.py` の直接 `create_app()` 呼び出しを Task 2 / Task 8 に明記し、grep も direct chain を拾える pattern に広げる。
- integration tests は Redis 専用 module 以外で memory backend を前提にする。個別 fixture へ `monkeypatch.setenv("AUTH_RATE_LIMIT_BACKEND", "memory")` を散らすと新規 `create_app()` 追加時に漏れるため、`tests/integration/conftest.py` の autouse fixture で強制する。Redis 専用 module だけは `redis_rate_limiter` marker で opt-out する。
- `reset_for_tests()` は production interface から外すため、in-memory は sync method、Redis は async method に分ける。memory 前提の sync fixture では `asyncio.run()` を使わない。
- circuit breaker は連続失敗だけを数え、Redis operation 成功時に連続失敗 count を 0 に戻す。既定値は false positive を抑えるため `failures=5`、`cooldown=10s` にする。
- redis-py の async cancellation safety を依存追加時に確認し、deadline 超過後も同一 connection の後続 command response がずれないことを Redis integration test に入れる。false green を避けるため、実接続テストでは `max_connections=1` で connection を固定し、空 list への `BLPOP` と短い deadline で timeout を確実に発生させる。
- Redis connection pool は無制限にしない。`AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS` を設定に追加し、`Redis.from_url(..., max_connections=...)` で worker ごとの同時認証 request 数に合わせて上限を持たせる。
- 実装レビューで確認された connection pool 枯渇の false unavailable を避けるため、Redis provider は非ブロッキング pool ではなく `BlockingConnectionPool` を使う。pool 取得 timeout は operation deadline の半分にし、pool 枯渇由来の `Too many connections` / `No connection available` は circuit breaker の連続失敗に数えない。pool 枯渇 warning は 1 秒に 1 回へ抑制する。

## 現状分析

対象ファイルと責務:

- `backend/app/interfaces/libraries/rate_limiter_interface.py`: login/register/OIDC/account deletion が依存する抽象 interface。現在は全 method が sync で、test cleanup 用の `reset()` も production interface に含まれている。
- `backend/app/libraries/auth_rate_limiter.py`: in-memory 実装。既定 clock は `time.monotonic()`。single-process 用の bounded bucket と fail-open bucket cap を持つ。
- `backend/app/usecases/auth_usecase.py`: register / login で rate limiter を呼ぶ。
- `backend/app/usecases/account_deletion_usecase.py`: password 再認証の rate limit を呼ぶ。
- `backend/app/usecases/oauth_oidc_usecase.py`: OIDC authorization start の rate limit を呼ぶ。
- `backend/app/config/auth.py`: rate limit の window / 閾値 / max bucket 設定を持つ。
- `backend/app/bootstrap/modules.py`: `LoginRateLimiterInterface` の provider。
- `backend/app/bootstrap/create_app.py`: app lifespan で DB engine と password hash executor を shutdown する。Redis client を追加するならここに cleanup が必要。
- `backend/app/bootstrap/cli.py`: CLI container の DB engine cleanup を行う。Redis client を解決する CLI でも cleanup が必要。
- `backend/tests/integration/conftest.py`: sync `TestClient` fixture で test 後に `LoginRateLimiterInterface.reset()` を呼ぶ。
- `backend/tests/integration/test_auth_controller.py`: `test_auth_cookie_security_uses_startup_settings` が fixture を使わず直接 `create_app()` を呼ぶため、`.env` に Redis backend が残っている場合の漏れを autouse fixture で防ぐ必要がある。
- `backend/tests/integration/test_auth_oidc_controller.py`: 独自 fixture が直接 `create_app()` と `LoginRateLimiterInterface.reset()` を呼ぶため、conftest の修正だけでなく direct reset の rename も必要である。
- root `.env.example`: `FRONTEND_PORT` と `BACKEND_PORT` だけがあり、`docker-compose.yaml` が読む `POSTGRES_PORT` は未記載。
- `.agents/skills/` と `.claude/skills/`: 既存 project skill は基本的に `SKILL.md` 単体で mirror されている。

計画の前提で修正が必要な点:

- Redis shared store では process-local `monotonic()` を時刻 score に使えない。
- Redis check path は login の hot path なので、直列 RTT を増やす設計は避ける。
- Redis unavailable 時の fail-closed は認証 availability と latency を大きく落とすため、timeout だけでなく logical deadline と circuit breaker が必要である。
- Redis に global bucket cap を app 側で持ち込むと高コストになるが、代替の memory 方針を compose/docs に書かないと flood 時の挙動が不明確になる。

## 方針とその理由

### 採用方針

1. Redis 実装を `RedisLoginRateLimiter` として追加する。
   - 理由: Redis は複数 process / instance から共有でき、TTL 付き sliding window bucket に向いている。
   - 参考: redis-py は `redis.asyncio` namespace で asyncio 対応 API を提供している。

2. `LoginRateLimiterInterface` を async 化する。
   - 理由: Redis I/O を request path で await できるようにし、event loop blocking を避ける。
   - 影響: usecase と tests の呼び出しに `await` を追加する。派生プロジェクトに対する breaking change なので `backend/AGENTS.md` に互換性メモを追加する。

3. Redis score の時刻軸は Redis server `TIME` の Unix epoch seconds に統一する。
   - 理由: app process の `time.monotonic()` は process ごとに原点が異なり、複数 instance 間の window 比較に使えない。
   - 理由: app server の wall clock を使う案は NTP drift に依存する。Redis server `TIME` を使えば Redis に保存される score と window 境界の時刻軸が同じになる。
   - 注意: Redis server の時刻自体は NTP 等で運用管理する。Redis server clock が大きく飛ぶと window 判定も影響を受ける。

4. Redis check 系は `TIME` 取得後、対象 bucket の `ZCOUNT key window_start +inf` を pipeline でまとめる。
   - 理由: `ZCOUNT` は read-only で、check path で Redis key を trim しないため write amplification を避けられる。
   - 境界: 既存 in-memory は `now - t > window_seconds` のときだけ期限切れにするため、`t == now - window_seconds` は有効である。Redis の `ZCOUNT` min は inclusive にする。

5. Redis record 系は `TIME` 取得後、対象 bucket ごとに `ZREMRANGEBYSCORE key -inf (window_start`、`ZADD`、`EXPIRE` を pipeline でまとめる。
   - 理由: `window_start` ちょうどの record は既存契約上まだ有効なので、trim は exclusive max にする。
   - `EXPIRE` は `window_seconds + 1` 以上にし、記録済み bucket が自然消滅するようにする。

6. Redis key には raw email / IP を入れず、scope と normalized key の SHA-256 digest を使う。
   - 理由: Redis key dump や metrics 上に email address / IP address が直接出ないようにする。
   - 注意: SHA-256 は秘匿ではなく accidental exposure 対策である。Redis 自体へのアクセス制御は運用側で守る。

7. backend 選択は `AUTH_RATE_LIMIT_BACKEND=memory | redis` で行う。
   - 理由: 既定動作を壊さず、本番だけ Redis に切り替えられる。
   - `redis` 選択時は `AUTH_RATE_LIMIT_REDIS_URL` を必須にする。

8. Redis unavailable policy は `AUTH_RATE_LIMIT_REDIS_UNAVAILABLE_POLICY=fail_closed | fail_open` で明示する。既定は `fail_closed`。
   - 理由: Redis を明示選択した環境では、rate limit が効かない状態で brute force を許容するより、認証試行を止める方を安全側の既定にする。
   - トレードオフ: Redis outage 時に正規ユーザーもログインできなくなる。availability 優先の local / staging では `fail_open` を明示できるようにする。
   - 運用上の区別: fail-closed 由来の 429 は通常の bucket 到達とは意味が異なるため、専用 log code `auth_rate_limiter.redis_unavailable` と policy/operation を残す。metric 基盤が追加された派生プロジェクトでは同じ code で count する。

9. Redis operation 全体に deadline と circuit breaker を設ける。
   - 既定値は `AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS=0.25`、`AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS=0.25`、`AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS=0.8`、`AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_FAILURES=5`、`AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_COOLDOWN_SECONDS=10` とする。
   - 理由: Redis がハングしたときに、1 request 内の複数 Redis command timeout が直列に積み上がることを避ける。
   - Redis connection pool は `AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS=100` を既定にし、環境ごとに worker あたりの同時認証 request 数へ合わせて調整する。
   - provider では `BlockingConnectionPool` を使い、pool 枯渇時は operation deadline の半分だけ connection 取得を待つ。
   - 理由: redis-py の既定 pool は実質無制限であり、Redis 遅延時に in-flight 認証 request 数ぶん connection を増やして Redis `maxclients` や共有 Redis の他用途へ影響を広げ得る。一方で非ブロッキング pool に単純な上限を設定すると、枯渇時に即 `ConnectionError` となり、健全な Redis を Redis outage と誤認しやすい。
   - circuit breaker は process-local でよい。Redis outage 中に全 worker が毎 request Redis へ timeout まで待つ状態を避けるための保護であり、rate limit bucket の正確性を担うものではない。
   - breaker は連続失敗で open し、Redis operation が 1 回成功したら連続失敗 count を 0 に戻す。プロセス生存期間中の累計失敗では open しない。
   - 並行実行下では成功 / 失敗の完了順で連続失敗を数えるため、Redis が flapping している場合は breaker が open しにくい。完全 outage では全 operation が失敗するため open する。
   - pool 枯渇由来の `Too many connections` / `No connection available` は request を fail-closed / fail-open policy へ流すが、Redis 自体の連続失敗ではないため circuit breaker の連続失敗には数えない。pool 枯渇 warning は burst 時の log amplification を避けるため 1 秒に 1 回へ抑制する。
   - breaker open 前の worst-case request latency は logical operation 数と同時 in-flight request 数に比例する。既定 deadline 0.8 秒では login 失敗が最大 1.6 秒、register の一部 failure path が最大 2.4 秒まで待ち得る。同時 100 request なら breaker が開く前に 100 request がそれぞれ待つ可能性がある。この残余リスクは breaker が開くまでの短時間に限って許容する。

10. Redis memory は TTL と Redis 側の memory policy で bounded にする。
   - local compose の Redis service は rate limit 検証用として `--maxmemory 128mb --maxmemory-policy volatile-ttl` を設定する。
   - production docs では、rate limit 専用 Redis instance / DB を推奨し、rate limit key が必ず TTL を持つ前提で `volatile-ttl` を推奨する。
   - `allkeys-lru` は rate limit key が攻撃中に evict されて防御が素通りし得るため推奨しない。
   - `noeviction` は write 失敗が fail-closed と組み合わさって認証停止に直結するため、容量監視なしでは推奨しない。

11. `reset()` は `LoginRateLimiterInterface` から外し、実装クラスに `reset_for_tests()` として置く。
   - 理由: production interface に prefix 配下の一括 `SCAN` + `DELETE` 操作を露出しない。
   - tests は duck typing または test-local protocol で `reset_for_tests()` を呼ぶ。

12. `auth-rate-limiting` project skill を `SKILL.md` 単体で追加する。
   - 理由: 既存 project skill の慣習に合わせ、不要な evals directory を増やさない。
   - `.agents` と `.claude` は既存慣習に合わせて mirror する。symlink 化は tooling 互換性の検証が別途必要なため、この計画では採用しない。

13. Redis pipeline は single-node 前提で `transaction=True` を使う。
   - 理由: check 系は read-only なので atomicity は重要ではないが、record 系は trim / add / expire を一まとまりとして扱える方がよい。
   - Redis Cluster はこの計画の対象外であるため、multi-key `MULTI/EXEC` の cluster 制約は受け入れる。cluster 対応が必要になった場合は Lua script または hash tag 設計を別計画で扱う。

### 代替案と不採用理由

- PostgreSQL に rate limit table を作る案:
  - 不採用。auth DB integration と同じ PostgreSQL に brute force traffic の write amplification を載せることになり、rate limit 到達後に audit insert を避けている既存思想と相性が悪い。

- sync Redis client を threadpool なしで呼ぶ案:
  - 不採用。FastAPI async endpoint の event loop をブロックする。

- sync interface を維持し、実装内部だけで `asyncio.run()` する案:
  - 不採用。既存 event loop 上で呼べず、request path で破綻する。

- app process の `time.monotonic()` を Redis score に使う案:
  - 不採用。process ごとに原点が違い、共有 store の時刻比較が破綻する。

- app server の `time.time()` を Redis score に使い、NTP 前提にする案:
  - 不採用。Redis に保存される score と window 境界が各 app server clock に依存し、clock skew で過剰 block / 過少 block が起こり得る。

- Redis check 系で `ZREMRANGEBYSCORE -> ZCARD` を実行する案:
  - 不採用。check path が write になり、3 bucket 判定で RTT と write load が増える。

- Redis Lua script で `TIME` と sorted set 操作を 1 RTT / atomic にまとめる案:
  - 今回は不採用。最も効率はよいが、script body / SHA 管理、Redis Cluster 時の key slot 制約、fake Redis unit test の複雑化が増える。現行計画の `TIME` + pipelined command は 2 RTT だが、deadline と circuit breaker で request path の上限を管理できるため、まずはこちらを採用する。

- Redis key に raw email / IP を入れる案:
  - 不採用。デバッグは楽だが、Redis key listing で個人情報が露出しやすい。

- Redis mode を既定にする案:
  - 不採用。既存 local 開発と CI の前提を壊す。共有 store が必要な環境だけ opt-in にする。

- skill 作成を別計画に分離する案:
  - 不採用。今回の人間指示が「共有 store 実装と、`LoginRateLimiterInterface` を利用するときのスキル」の計画作成であるため、同じ計画に残す。ただし scope を `SKILL.md` 作成と最小検証に縮小する。

## 逸脱・トレードオフ

- `superpowers:writing-plans` の標準では plan を `docs/superpowers/plans/` に置くが、この repository の正典は `AGENTS.md` により `documents/plans/` であるため、`documents/plans/20260813-redis-login-rate-limiter-and-skill.md` に置く。
- `superpowers:writing-plans` の標準には commit step があるが、人間の明示指示によりこの計画では `git add` / `git commit` を含めない。
- Redis 実装では in-memory の `AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE` 相当の app-level global bucket cap を実装しない。Redis は TTL 付き key と Redis memory policy で bounded にする。
- fail-closed Redis outage は通常の bucket 到達と同じ 429 response になり得る。wire contract と Frontend 影響を抑えるため status は維持し、server log / future metric 用 code で区別する。503 に分ける設計は意味論としては正しいが、Frontend feedback と Problem Details registry の追加変更を伴うためこの計画では採用しない。
- Redis pipeline は Redis single-node を前提にし、record 系は `transaction=True` を使う。Redis Cluster で multi-key transaction を使う設計はこの計画の対象外とし、必要になった場合は key hash tag、Lua script、cluster 対応を別計画で扱う。
- 計画初稿では `AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS=0.6` を想定していたが、レビュー反映後の validation は `connect_timeout + 2 * socket_timeout` 以上を要求する。既定の connect/socket timeout がどちらも 0.25 秒のため、0.6 秒では初期値同士が矛盾する。実装では既定 deadline を 0.8 秒に変更し、cold connect を含む最小条件 0.75 秒を満たすようにした。

## 作成・変更予定ファイル

Backend code:

- Modify: `backend/app/interfaces/libraries/rate_limiter_interface.py`
- Modify: `backend/app/libraries/auth_rate_limiter.py`
- Create: `backend/app/libraries/redis_login_rate_limiter.py`
- Modify: `backend/app/config/auth.py`
- Modify: `backend/app/bootstrap/modules.py`
- Modify: `backend/app/bootstrap/create_app.py`
- Modify: `backend/app/bootstrap/cli.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/usecases/account_deletion_usecase.py`
- Modify: `backend/app/usecases/oauth_oidc_usecase.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

Backend tests:

- Modify: `backend/tests/unit/libraries/test_auth_rate_limiter.py`
- Create: `backend/tests/unit/libraries/test_redis_login_rate_limiter.py`
- Modify: `backend/tests/unit/config/test_auth_settings.py`
- Modify: `backend/tests/unit/bootstrap/test_container.py`
- Modify: `backend/tests/unit/bootstrap/test_create_app.py`
- Modify: `backend/tests/unit/bootstrap/test_cli.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_usecase.py`
- Modify: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py`
- Modify: `backend/tests/integration/conftest.py`
- Create: `backend/tests/integration/test_redis_rate_limiter.py`

Local infrastructure and docs:

- Modify: `docker-compose.yaml`
- Modify: `.env.example`
- Modify: `backend/.env.example`
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `documents/references/local-development-start-guide.md`
- Modify: `backend/AGENTS.md`

Skills:

- Create: `.agents/skills/auth-rate-limiting/SKILL.md`
- Create: `.claude/skills/auth-rate-limiting/SKILL.md`

## 具体的なタスク

### Task 1: 現状の rate limiter 契約を regression test として固定する

**Files:**

- Modify: `backend/tests/unit/libraries/test_auth_rate_limiter.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_usecase.py`
- Modify: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py`

- [x] `backend/tests/unit/libraries/test_auth_rate_limiter.py` の既存テスト名を読み、次の契約がすでに coverage されていることを確認する: email+IP bucket、IP bucket、email bucket、register duplicate の email bucket 除外、account deletion の email-only bucket 無視、success 時の email+IP bucket のみ削除、registration bucket、OIDC authorization bucket、bucket cap fail-open。
- [x] 足りない契約があれば、実装変更前に failing test を追加する。追加候補は `test_record_success_does_not_clear_ip_or_email_buckets` とし、success 後も IP bucket / email bucket による block が残ることを明示する。
- [x] in-memory の境界契約を固定する `test_window_boundary_is_inclusive` を追加する。`now - recorded_at == window_seconds` ではまだ allowed 判定の count に残り、`window_seconds + epsilon` で消えることを確認する。
- [x] `cd backend && uv run pytest tests/unit/libraries/test_auth_rate_limiter.py -q` を実行し、変更前の既存実装で pass することを確認する。
- [x] usecase 側で rate limiter が「429 前に audit を書かない」「通常失敗時だけ record する」契約を既存テストで確認する。
- [x] 足りない場合は `test_login_rate_limited_does_not_record_audit_log`、`test_register_rate_limited_does_not_record_audit_log`、`test_oidc_start_rate_limited_does_not_create_state` を追加する。
- [x] `cd backend && uv run pytest tests/unit/usecases/test_auth_usecase.py tests/unit/usecases/test_account_deletion_usecase.py tests/unit/usecases/test_oauth_oidc_usecase.py -q` を実行する。

### Task 2: `LoginRateLimiterInterface` を async 化し、test cleanup を production interface から外す

**Files:**

- Modify: `backend/app/interfaces/libraries/rate_limiter_interface.py`
- Modify: `backend/app/libraries/auth_rate_limiter.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/usecases/account_deletion_usecase.py`
- Modify: `backend/app/usecases/oauth_oidc_usecase.py`
- Modify: `backend/tests/unit/libraries/test_auth_rate_limiter.py`
- Modify: `backend/tests/integration/conftest.py`
- Modify: `backend/tests/integration/test_auth_oidc_controller.py`
- Modify: related usecase tests

- [x] `LoginRateLimiterInterface` の rate limit method を `async def` に変更する。対象は `is_allowed`、`is_account_deletion_reauth_allowed`、`record_failure`、`record_success`、`is_registration_allowed`、`record_registration`、`is_oidc_authorization_allowed`、`record_oidc_authorization`。
- [x] `LoginRateLimiterInterface` から `reset()` を削除する。
- [x] `LoginRateLimiterInterface` に lifecycle cleanup 用の `async def aclose(self) -> None` を追加する。
- [x] `backend/app/libraries/auth_rate_limiter.py` の public rate limit method を async に変更する。内部 helper は sync のままでよい。
- [x] `InMemoryLoginRateLimiter.aclose()` は no-op async method として実装する。
- [x] `InMemoryLoginRateLimiter.reset()` は sync method の `reset_for_tests()` に rename する。production interface からは参照しない。in-memory は `OrderedDict.clear()` だけなので async にしない。
- [x] `AuthUsecase.register()` で `is_allowed`、`is_registration_allowed`、`record_failure`、`record_registration` をすべて `await` する。
- [x] `AuthUsecase.login()` で `is_allowed`、`record_failure`、`record_success` をすべて `await` する。
- [x] `AccountDeletionUsecase` で `is_account_deletion_reauth_allowed` と `record_failure` を `await` する。
- [x] `OAuthOidcUsecase` で `is_oidc_authorization_allowed` と `record_oidc_authorization` を `await` する。
- [x] unit tests の rate limiter 呼び出しに `await` を追加し、必要な test function を `async def` に変更する。
- [x] usecase unit test の stub rate limiter を async method に変更し、`aclose()` は no-op にする。
- [x] `backend/tests/integration/conftest.py` の `LoginRateLimiterInterface.reset()` 呼び出しを `reset_for_tests()` に変える。
- [x] `backend/tests/integration/test_auth_oidc_controller.py` の `LoginRateLimiterInterface.reset()` 直接呼び出しも `reset_for_tests()` に変える。これは conftest と別の fixture なので必ず同じタスクで直す。
- [x] `rg -n "LoginRateLimiterInterface\\)\\.reset\\(|\\.reset\\(\\)" backend/tests/integration backend/tests/unit/libraries/test_auth_rate_limiter.py` を実行し、rate limiter の古い `reset()` 呼び出しが残っていないことを確認する。`unit_of_work.py` など無関係な contextvar reset は対象外にする。
- [x] `cd backend && uv run pytest tests/unit/libraries/test_auth_rate_limiter.py -q` を実行し、in-memory 契約が維持されることを確認する。
- [x] `cd backend && uv run pytest tests/unit/usecases/test_auth_usecase.py tests/unit/usecases/test_account_deletion_usecase.py tests/unit/usecases/test_oauth_oidc_usecase.py -q` を実行する。

### Task 3: Redis 設定を `AuthSettings` に追加する

**Files:**

- Modify: `backend/app/config/auth.py`
- Modify: `backend/tests/unit/config/test_auth_settings.py`
- Modify: `backend/.env.example`
- Modify: `backend/AGENTS.md`

- [x] `AuthSettings` に `AUTH_RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "memory"` を追加する。
- [x] `AuthSettings` に `AUTH_RATE_LIMIT_REDIS_URL: str = ""` を追加する。`AUTH_RATE_LIMIT_BACKEND=redis` のとき空文字なら validation error にする。
- [x] `AuthSettings` に `AUTH_RATE_LIMIT_REDIS_KEY_PREFIX: str = "auth:rate_limit"` を追加する。
- [x] `AuthSettings` に `AUTH_RATE_LIMIT_REDIS_UNAVAILABLE_POLICY: Literal["fail_closed", "fail_open"] = "fail_closed"` を追加する。
- [x] `AuthSettings` に `AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS: float = 0.25` と `AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS: float = 0.25` を追加する。
- [x] `AuthSettings` に `AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS: float = 0.8` を追加する。
- [x] `AuthSettings` に `AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_FAILURES: int = 5` と `AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 10` を追加する。
- [x] `AuthSettings` に `AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS: int = 100` を追加する。既定値は worker あたりの同時認証 request 数を十分に超えるが、Redis `maxclients` を食い潰さない上限として扱う。
- [x] validation で Redis timeout と operation deadline は `0.05` 以上にする。
- [x] validation で operation deadline は `AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS + 2 * AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS` 未満にできないようにする。breaker cooldown 明けや pool 拡張時は connect timeout も直列に加算されるため、deadline が socket timeout 2 回分だけだと cold connect で構造的に成功できない。
- [x] validation で `AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS` は 1 以上にする。
- [x] validation で `AUTH_RATE_LIMIT_REDIS_KEY_PREFIX` は空文字、空白、glob 文字、colon-only 値、改行を拒否する。
- [x] `test_auth_settings_rate_limit_backend_defaults_to_memory` を追加し、既定で Redis URL が不要なことを確認する。
- [x] `test_auth_settings_requires_redis_url_when_backend_is_redis` を追加する。
- [x] `test_auth_settings_reads_redis_rate_limit_settings_from_env` を追加する。
- [x] `test_auth_settings_rejects_invalid_redis_timeout_or_deadline` を追加する。
- [x] `test_auth_settings_rejects_redis_deadline_shorter_than_connect_plus_two_socket_timeouts` を追加する。
- [x] `test_auth_settings_rejects_invalid_redis_max_connections` を追加する。
- [x] `test_auth_settings_rejects_invalid_redis_key_prefix` を追加する。
- [x] `backend/.env.example` に Redis 関連 env と説明コメントを追加する。既定は `AUTH_RATE_LIMIT_BACKEND=memory` とし、Redis URL は空のままにする。
- [x] `backend/AGENTS.md` の rate limiter 節に、Redis mode の設定、async interface、Redis server `TIME` 正典、Redis unavailable policy、circuit breaker、Redis では `AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE` が in-memory 専用であることを追記する。
- [x] `backend/AGENTS.md` に派生プロジェクト向け互換性メモを追加する。内容は「`LoginRateLimiterInterface` は async 化され、`reset()` は production interface から削除され、test cleanup は `reset_for_tests()` を duck typing で呼ぶ」にする。
- [x] `cd backend && uv run pytest tests/unit/config/test_auth_settings.py -q` を実行する。

### Task 4: Redis client dependency を追加する

**Files:**

- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

- [x] 実装前に人間へ依存追加の承認を取る。プロジェクト規約上、`uv add` は確認が必要である。
- [x] 承認後、`cd backend && uv add redis` を実行する。
- [x] `backend/pyproject.toml` に `redis` が追加され、`backend/uv.lock` が更新されていることを確認する。
- [x] `redis.asyncio` の import が成功することを確認する。sandbox 内の `uv run python -c ...` は uv cache / dynamic store の問題で安定しなかったため、同じ `.venv` の `python -c "import redis.asyncio as redis; print(redis.__name__)"` で確認した。
- [x] 導入された redis-py version の async cancellation / timeout 挙動を公式 docs、release notes、または導入済み source で確認する。`asyncio.wait_for()` 等で in-flight command が cancel された場合に connection を破棄し、次の command が前の response を読まない version であることを実装メモに残す。
- [x] 依存追加のライセンスと既知脆弱性の確認方法を PR 本文または実装メモに残す。実装時点の `uv pip audit` はこの uv では未対応 subcommand だったため、最終報告に未実行理由として残す。

### Task 5: `RedisLoginRateLimiter` の unit test を書く

**Files:**

- Create: `backend/tests/unit/libraries/test_redis_login_rate_limiter.py`

- [x] Redis 実装に入る前に、最小 fake Redis を test file 内へ作る。必要な async method は `time`、`pipeline`、`zcount`、`zremrangebyscore`、`zadd`、`expire`、`delete`、`scan_iter`、`aclose` に限定する。
- [x] fake pipeline は command を記録し、`execute()` で一括実行できるようにする。check 系で `zcount` が pipeline に入ることを検証できるようにする。
- [x] deadline / breaker テストでは実時間 sleep を長く使わない。fake Redis の command を `asyncio.Event` で停止させ、test 側で event を解放する方式にする。必要なら Redis operation wrapper または wait function を constructor injection できる形にして、`asyncio.wait_for` の挙動を deterministic に検証する。
- [x] `test_is_allowed_uses_redis_time_and_pipelined_zcount_without_writes` を書く。`is_allowed()` は `time` と pipeline 内の `zcount` だけを呼び、`zremrangebyscore`、`zadd`、`expire` を呼ばないことを確認する。
- [x] `test_is_allowed_counts_window_start_inclusively` を書く。Redis server time が `100.0`、window が `10` のとき score `90.0` は有効、`89.999` は無効であることを確認する。
- [x] `test_record_failure_trims_scores_strictly_older_than_window_start` を書く。record 時の trim が `window_start` より古い score だけを消し、`window_start` ちょうどを残すことを確認する。
- [x] `test_record_failure_blocks_by_email_ip_bucket` を書く。
- [x] `test_record_failure_blocks_by_ip_bucket_across_emails` を書く。
- [x] `test_record_failure_blocks_by_email_bucket_across_ips` を書く。
- [x] `test_register_style_failure_can_skip_email_bucket` を書く。
- [x] `test_account_deletion_reauth_allowed_ignores_email_only_bucket` を書く。
- [x] `test_record_success_deletes_only_matching_email_ip_bucket` を書く。
- [x] `test_registration_bucket_uses_registration_window` を書く。
- [x] `test_oidc_authorization_bucket_uses_auth_window` を書く。
- [x] `test_redis_keys_do_not_contain_raw_email_or_ip` を書き、fake Redis に作られた key に `user@example.com` や `127.0.0.1` が含まれないことを確認する。
- [x] `test_redis_unavailable_fail_closed_blocks_checks_and_logs_unavailable_code` を書く。fake Redis が例外を投げる場合に `is_allowed()` が `False` を返し、log に `auth_rate_limiter.redis_unavailable` が残ることを確認する。
- [x] `test_redis_unavailable_fail_open_allows_checks_and_drops_records` を書く。`fail_open` では check が `True`、record 系は例外を外へ出さないことを確認する。
- [x] `test_operation_deadline_limits_total_redis_wait` を書く。Redis command が deadline を超える場合に、複数 command timeout の合計を待たずに unavailable path へ入ることを確認する。
- [x] `test_deadline_timeout_marks_operation_unavailable_without_running_later_pipeline_commands` を fake Redis で書く。`asyncio.Event` で `TIME` または pipeline execute を停止させ、deadline 超過時に unavailable path へ入り、後続 command queue を実行しないことを deterministic に確認する。
- [x] `test_circuit_breaker_skips_redis_until_cooldown_expires` を書く。連続 failure 後は Redis command を呼ばず policy に従い、cooldown 後に再試行することを確認する。
- [x] `test_circuit_breaker_resets_consecutive_failure_count_after_success` を書く。failure、success、failure の順では累計ではなく連続失敗だけが数えられ、threshold に達しないことを確認する。
- [x] `test_record_failure_pipeline_uses_transaction` を書く。record 系 pipeline は `transaction=True` で作られることを確認する。
- [x] `test_record_failure_pipeline_failure_has_documented_policy` を書く。pipeline 実行失敗時は record 全体を失敗扱いにし、fail_open では no-op、fail_closed では unavailable log を出すことを確認する。
- [x] `cd backend && uv run pytest tests/unit/libraries/test_redis_login_rate_limiter.py -q` を実行し、実装前に expected failure になることを確認する。

### Task 6: `RedisLoginRateLimiter` を実装する

**Files:**

- Create: `backend/app/libraries/redis_login_rate_limiter.py`
- Modify: `backend/tests/unit/libraries/test_redis_login_rate_limiter.py`

- [x] `RedisLoginRateLimiter` constructor は window 秒、registration window 秒、各 max count、Redis client、key prefix、unavailable policy、operation deadline、circuit breaker 設定を受け取る。Redis 実装では app process の `clock` を score 生成に受け取らない。
- [x] circuit breaker の cooldown 判定だけは process-local の monotonic clock を使ってよい。これは Redis score ではなく、同一 process 内の outage backoff に限るため共有 store の時刻軸とは独立である。
- [x] Redis client 型は実装内で `redis.asyncio.Redis` を使う。ただし tests では fake を渡せるよう、constructor 引数は必要 method を持つ protocol として扱う。
- [x] `_redis_time_seconds()` を実装し、Redis `TIME` の seconds + microseconds から float Unix epoch seconds を作る。
- [x] `_bucket_key(scope: str, raw_key: str) -> str` を実装し、`sha256(f"{scope}:{raw_key}".encode()).hexdigest()` を使って `"{prefix}:{scope}:{digest}"` を返す。
- [x] `_count_active(keys, now, window_seconds)` を実装し、`window_start = now - window_seconds`、pipeline 内で各 key に `ZCOUNT key window_start +inf` を積む。min は inclusive にする。
- [x] `_record(keys, now, window_seconds)` を実装し、各 key に対して `ZREMRANGEBYSCORE key -inf (window_start`、`ZADD key {member: now}`、`EXPIRE key window_seconds + 1` を `transaction=True` の pipeline に積む。trim の max は exclusive にする。
- [x] member は `"{now:.6f}:{secrets.token_hex(8)}"` のように同一 timestamp でも衝突しない値にする。
- [x] `is_allowed()` は email+IP、IP、email の 3 key を count し、すべて閾値未満なら `True` を返す。
- [x] `is_account_deletion_reauth_allowed()` は email+IP と IP だけを count し、email key は読まない。
- [x] `record_failure()` は email+IP と IP に記録し、`include_email_bucket=True` のときだけ email に記録する。
- [x] `record_success()` は email+IP key だけを `DELETE` する。
- [x] `is_registration_allowed()` と `record_registration()` は registration window を使う。
- [x] `is_oidc_authorization_allowed()` と `record_oidc_authorization()` は auth rate limit window を使う。
- [x] Redis operation の例外は `redis.exceptions.RedisError`、`TimeoutError`、`OSError`、`asyncio.TimeoutError` を捕捉する。
- [x] すべての logical operation は `asyncio.wait_for(..., timeout=operation_deadline_seconds)` で囲む。
- [x] Redis failure が連続で circuit breaker threshold に達したら breaker を open にし、cooldown 期限まで Redis command を呼ばない。Redis operation が成功したら連続失敗 count を 0 に戻す。
- [x] `fail_closed` の check 系は unavailable 時に `False` を返し、record 系は例外を外へ出さず warning log を出す。log message には `auth_rate_limiter.redis_unavailable`、`policy=fail_closed`、operation 名だけを含め、email、IP、Redis URL は含めない。
- [x] `fail_open` の check 系は unavailable 時に `True` を返し、record 系は no-op として warning log を出す。
- [x] 同じ outage 中の warning が request ごとに無制限に増えないよう、breaker open 中は初回だけ warning を出す。cooldown 後に再失敗した場合は再度 warning を許可する。
- [x] record 系の pipeline 失敗は operation 全体の失敗として扱い、retry はしない。`transaction=True` で Redis 側の部分反映は避けるが、client timeout / connection loss で結果不明になり得るため、成功扱いにはしない。理由は auth request path で Redis write を再試行して遅延と重複記録を増やさないためである。
- [x] `reset_for_tests()` は async method として実装し、prefix 配下 key の一括削除に `SCAN` を使う。production path ではなく Redis integration test cleanup 用であることを docstring に書く。`KEYS` は使わない。
- [x] `aclose()` を実装し、Redis client に `aclose` がある場合は await する。
- [x] `cd backend && uv run pytest tests/unit/libraries/test_redis_login_rate_limiter.py -q` を実行し、pass を確認する。

### Task 7: DI provider と lifecycle cleanup を追加する

**Files:**

- Modify: `backend/app/bootstrap/modules.py`
- Modify: `backend/app/bootstrap/create_app.py`
- Modify: `backend/app/bootstrap/cli.py`
- Modify: `backend/tests/unit/bootstrap/test_container.py`
- Modify: `backend/tests/unit/bootstrap/test_create_app.py`
- Modify: `backend/tests/unit/bootstrap/test_cli.py`

- [x] `AuthModule.provide_rate_limiter()` で `settings.AUTH_RATE_LIMIT_BACKEND == "memory"` のとき `InMemoryLoginRateLimiter` を返す。
- [x] `settings.AUTH_RATE_LIMIT_BACKEND == "redis"` のとき `redis.asyncio.Redis.from_url()` で singleton client を作り、`RedisLoginRateLimiter` を返す。
- [x] Redis client 作成時に socket timeout / connect timeout を settings から渡す。
- [x] Redis client 作成時に `BlockingConnectionPool.from_url(..., max_connections=settings.AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS, timeout=operation_deadline/2)` を使う。redis-py の pool 既定値は実質無制限なので、認証 endpoint flood 時に Redis `maxclients` を食い潰さないため provider 側で必ず上限を設定する。非ブロッキング pool は枯渇時に即 `ConnectionError` を投げるため使わない。
- [x] `test_build_container_binds_memory_rate_limiter_by_default` を追加し、既定で in-memory 実装が返ることを確認する。
- [x] `test_build_container_binds_redis_rate_limiter_when_configured` を追加する。`redis.asyncio.Redis.from_url` を monkeypatch し、URL、socket timeout、connect timeout、`max_connections` が渡ることを確認する。
- [x] `create_app.lifespan` の finally で `await app.state.injector.get(LoginRateLimiterInterface).aclose()` を呼ぶ。
- [x] shutdown 順序は rate limiter、DB engine、PasswordHashExecutor の順にする。rate limiter は DB に依存しないが、認証 request path の外部 I/O を先に閉じる。
- [x] cleanup 失敗時は既存 DB engine cleanup と同じく `logger.exception` し、app_error がない場合は raise する。
- [x] `backend/app/bootstrap/cli.py` でも container を使う CLI 終了時に rate limiter `aclose()` を呼ぶ。CLI が AuthUsecase を解決した場合にも Redis client を閉じるため。
- [x] `test_lifespan_closes_rate_limiter_on_shutdown` を追加する。
- [x] `test_lifespan_logs_rate_limiter_close_failure` を追加する。
- [x] `test_run_with_container_closes_rate_limiter` を追加する。
- [x] `cd backend && uv run pytest tests/unit/bootstrap/test_container.py tests/unit/bootstrap/test_create_app.py tests/unit/bootstrap/test_cli.py -q` を実行する。

### Task 8: async 化の漏れ確認と integration fixture cleanup を修正する

**Files:**

- Modify: `backend/tests/integration/conftest.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/tests/integration/test_auth_oidc_controller.py`
- Modify: `backend/pyproject.toml`

- [x] `rg -n "rate_limiter\\.|LoginRateLimiterInterface\\)\\.|reset_for_tests|\\.reset\\(" backend/app/usecases backend/tests/unit backend/tests/integration` を実行し、production code と stubs の呼び出しに `await` 漏れがないこと、古い `LoginRateLimiterInterface.reset()` 呼び出しが残っていないことを確認する。この pattern は `app.state.injector.get(LoginRateLimiterInterface).reset()` のような direct chain も拾うために広めにする。
- [x] `backend/tests/integration/conftest.py` に autouse fixture `force_memory_rate_limiter_backend(monkeypatch, request)` を追加し、`request.node.get_closest_marker("redis_rate_limiter")` が無い test では `AUTH_RATE_LIMIT_BACKEND=memory` を強制する。`backend/.env` に Redis mode が残っていても controller integration tests は memory backend で動くようにする。
- [x] `backend/pyproject.toml` の pytest marker 定義に `redis_rate_limiter` を追加する。Redis 専用 integration tests だけが autouse fixture の memory 強制を opt-out する。
- [x] `backend/tests/integration/conftest.py` の cleanup では `limiter = app.state.injector.get(LoginRateLimiterInterface)`、`reset = getattr(limiter, "reset_for_tests", None)`、`result = reset()` の形で sync `reset_for_tests()` を呼ぶ。default fixture は memory backend を強制するため `asyncio.run()` は使わない。
- [x] `reset_for_tests()` の戻り値が `inspect.isawaitable(result)` なら即座に fail させる。Redis limiter の async `reset_for_tests()` を sync fixture で誤って呼ぶと coroutine が捨てられる silent failure になるため、RuntimeWarning に頼らず明示的に検出する。
- [x] `backend/tests/integration/test_auth_oidc_controller.py` の独自 fixture は autouse fixture による memory 強制に任せ、個別の `monkeypatch.setenv("AUTH_RATE_LIMIT_BACKEND", "memory")` は追加しない。直接 `LoginRateLimiterInterface.reset()` を呼んでいる箇所だけ sync `reset_for_tests()` に変更する。
- [x] `backend/tests/integration/test_auth_controller.py` の `test_auth_cookie_security_uses_startup_settings` は fixture を使わず直接 `create_app()` するため、autouse fixture で memory backend に固定されることを確認する。個別 test へ `monkeypatch.setenv("AUTH_RATE_LIMIT_BACKEND", "memory")` を足して済ませない。
- [x] `reset_for_tests` が無い limiter の場合は cleanup を skip せず fail させる。理由: shared state cleanup 不能な limiter で controller integration tests を走らせると test isolation が壊れるためである。
- [x] Redis backend を使う integration test は sync `TestClient` fixture に混ぜず、Task 9 の async Redis-specific tests で扱う。
- [x] `cd backend && uv run pytest tests/unit/usecases -q` を実行する。
- [x] `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:${POSTGRES_PORT:-5432}/app_test uv run pytest tests/integration/test_auth_controller.py tests/integration/test_auth_oidc_controller.py -q` を実行する。実行前に PostgreSQL と schema が必要である。

### Task 9: Redis integration test と Docker Compose service を追加する

**Files:**

- Create: `backend/tests/integration/test_redis_rate_limiter.py`
- Modify: `docker-compose.yaml`
- Modify: `.env.example`

- [x] `docker-compose.yaml` に `redis` service を追加する。image は Docker official image の Debian 明示 tag を使う。例: `redis:8-bookworm`。tag は実装時点で Docker Hub の official image tags を確認して選ぶ。
- [x] Redis service に `ports: ["${REDIS_PORT:-6379}:6379"]` を追加する。
- [x] Redis service の command に `redis-server --appendonly no --save "" --maxmemory 128mb --maxmemory-policy volatile-ttl` を設定する。local 検証用であり、本番 Redis sizing は環境に応じて決める。
- [x] Redis service に `redis-cli ping` の healthcheck を追加する。
- [x] root `.env.example` に `POSTGRES_PORT=5432` と `REDIS_PORT=6379` を追加し、`docker-compose.yaml` が読む port env を揃える。
- [x] backend service は既定では Redis に依存させない。`AUTH_RATE_LIMIT_BACKEND=memory` の通常起動を壊さないため。
- [x] `backend/tests/integration/test_redis_rate_limiter.py` は `TEST_REDIS_URL` が未設定なら skip にする。理由: 既存 integration の必須依存は PostgreSQL であり、Redis integration は shared store mode の追加検証として扱う。
- [x] `backend/tests/integration/test_redis_rate_limiter.py` の module または tests に `@pytest.mark.redis_rate_limiter` を付け、Task 8 の autouse fixture が `AUTH_RATE_LIMIT_BACKEND=memory` を強制しないようにする。
- [x] test では Redis DB を `FLUSHDB` せず、test-specific prefix を使い、`reset_for_tests()` で prefix 配下だけ消す。
- [x] `test_redis_rate_limiter_shares_state_between_two_instances` を追加する。2 つの `RedisLoginRateLimiter` instance を同じ Redis URL / prefix で作り、片方で失敗記録、もう片方で block 判定されることを確認する。
- [x] `test_redis_rate_limiter_shares_state_across_processes` を追加する。subprocess で同じ Redis URL / prefix に record し、親 process の limiter で block 判定されることを確認する。これにより同一 process の fake clock ではなく共有 Redis state を検証する。
- [x] `test_redis_rate_limiter_scores_are_redis_epoch_seconds` を追加する。record 後に Redis の zset score を読み、現在の Redis `TIME` 付近の Unix epoch seconds であり、process monotonic の小さい値ではないことを確認する。
- [x] `test_redis_deadline_timeout_does_not_poison_next_command_response` を追加する。実 Redis と redis-py client で deadline 超過を起こした後、同じ client で次の simple command を発行し、前の response ではなく正しい response が返ることを確認する。redis-py の cancellation safety を実接続で検証するため、この test は Redis integration 側に置く。
- [x] 上記 test は `redis.asyncio.Redis.from_url(TEST_REDIS_URL, max_connections=1, socket_timeout=1.0, socket_connect_timeout=1.0)` で dedicated client を作り、connection pool を 1 本に固定する。次の command が別 connection に逃げると検証にならないため、`max_connections=1` は必須条件にする。
- [x] 上記 test の deadline 超過は unique な空 list key に対する `await asyncio.wait_for(client.blpop(key, timeout=1), timeout=0.05)` で発生させる。`DEBUG SLEEP` は Redis server 全体を止め、環境によって無効なため使わない。timeout 後に同じ client で `await client.ping()` または `await client.set(unique_key, "ok")` を実行し、正しい response が返ることを確認する。
- [x] 上記 test は `try/finally` で unique key を `DELETE` し、dedicated client を `await client.aclose()` で閉じる。timeout 後 cleanup も同じ `max_connections=1` pool を通すため、connection が詰まったままなら cleanup 前に test が失敗する。
- [x] `test_redis_rate_limiter_record_success_on_one_instance_clears_email_ip_for_other_instance` を追加する。
- [x] `test_redis_rate_limiter_window_expires_across_instances` を追加する。
- [x] 実行コマンドを確認する: `cd backend && TEST_REDIS_URL=redis://localhost:6379/1 uv run pytest tests/integration/test_redis_rate_limiter.py -q`。
- [x] Compose 内 hostname と host 側 URL の違いを test docstring に書く。backend container からは `redis://redis:6379/0`、host pytest からは `redis://localhost:6379/1` を使う。

### Task 10: local docs と運用メモを更新する

**Files:**

- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `documents/references/local-development-start-guide.md`
- Modify: `backend/AGENTS.md`

- [x] `README.md` の起動構成に Redis service を追加する。ただし既定起動では必須ではないと明記する。
- [x] `README.md` の環境変数節に `AUTH_RATE_LIMIT_BACKEND`、`AUTH_RATE_LIMIT_REDIS_URL`、`AUTH_RATE_LIMIT_REDIS_UNAVAILABLE_POLICY`、Redis timeout/deadline/circuit breaker env、`AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS`、`REDIS_PORT` を追加する。
- [x] Redis mode の local 起動例を追加する: `docker compose up -d redis postgres backend frontend` と `backend/.env` の `AUTH_RATE_LIMIT_BACKEND=redis` / `AUTH_RATE_LIMIT_REDIS_URL=redis://redis:6379/0`。
- [x] host pytest で Redis integration を実行する例は `TEST_REDIS_URL=redis://localhost:${REDIS_PORT:-6379}/1` と書き、Compose 内 hostname との違いを明記する。
- [x] Redis outage 時の挙動を docs に書く。`fail_closed` は正規 login も 429 になり得る、`fail_open` は rate limit を一時的に失う、どちらも `auth_rate_limiter.redis_unavailable` log code で通常の bucket 到達と区別する。
- [x] Redis memory 方針を docs に書く。rate limit 専用 Redis instance / DB、全 rate limit key の TTL、`volatile-ttl`、容量監視を推奨し、`allkeys-lru` と容量監視なしの `noeviction` のリスクを説明する。
- [x] `documents/references/local-development-start-guide.md` に、通常は memory のままでよいこと、複数 worker / instance の検証時だけ Redis を有効化することを追記する。
- [x] `backend/README.md` に Redis rate limiter の設定例と、設定変更後は backend process/container 再起動が必要なことを追記する。
- [x] `backend/AGENTS.md` に今後の rate limiter 変更時の禁止事項を追記する: Redis score に process-local monotonic を使うことの禁止、sync Redis call 禁止、raw email/IP key 禁止、success 時の IP/email bucket 削除禁止、register duplicate の email bucket 記録禁止、check path write 禁止。

### Task 11: `auth-rate-limiting` project skill を作成する

**Files:**

- Create: `.agents/skills/auth-rate-limiting/SKILL.md`
- Create: `.claude/skills/auth-rate-limiting/SKILL.md`

- [x] skill name は `auth-rate-limiting` にする。`login-rate-limiter` は register / OIDC / account deletion を拾いにくいため使わない。
- [x] description は trigger 条件だけを書く。例: `Use when modifying or using LoginRateLimiterInterface, auth rate limit behavior, in-memory or Redis auth rate limiter implementations, login/register/OIDC/account-deletion rate limiting in this FastAPI template.`
- [x] Overview に「rate limiter は認証防御の一部であり、bucket 契約を変えると lockout / brute force 耐性 / audit amplification に影響する」と書く。
- [x] When to Use に `LoginRateLimiterInterface`、`InMemoryLoginRateLimiter`、`RedisLoginRateLimiter`、`AUTH_RATE_LIMIT_*`、login/register/OIDC/account deletion の rate limit を触る場合を列挙する。
- [x] Core Contract に既存契約を箇条書きする: 3 bucket 判定、失敗時のみ記録、success は email+IP だけ clear、register duplicate は email-only に入れない、account deletion は email-only を読まない、rate-limited request は audit insert しない。
- [x] Redis Pattern に async client、Redis server `TIME`、`ZCOUNT` check、record 時 trim、`transaction=True` pipeline、hashed key、TTL、operation deadline、connection pool max、success で reset する連続失敗 circuit breaker、unavailable policy を書く。
- [x] Testing Checklist に unit/integration/docs の必須確認を入れる。特に score が Redis epoch seconds であること、別 process 共有 test、boundary inclusive test、deadline timeout 後の response misalignment 防止確認を含める。
- [x] Common Mistakes に「monotonic を Redis score に使う」「check path で trim する」「raw email/IP を key に入れる」「login success で IP/email bucket も消す」「register duplicate を email-only bucket に入れる」を書く。
- [x] 既存 project skill 慣習に合わせ、`evals/evals.json` は作らない。
- [x] `.claude/skills/auth-rate-limiting/SKILL.md` は `.agents` 版と同内容にする。
- [x] `diff -u .agents/skills/auth-rate-limiting/SKILL.md .claude/skills/auth-rate-limiting/SKILL.md` を実行し、差分がないことを確認する。
- [x] `wc -l .agents/skills/auth-rate-limiting/SKILL.md` を実行し、500 lines 未満であることを確認する。

### Task 12: full verification を実行する

**Files:**

- No source edits expected in this task.

- [x] `cd backend && uv run ruff check .` を実行する。
- [x] `cd backend && uv run isort . --check-only` を実行する。
- [x] `cd backend && uv run yapf -dr app/ tests/ alembic/ manage.py` を実行する。
- [x] `cd backend && uv run mypy app manage.py` を実行する。
- [x] `cd backend && uv run pytest tests/unit` を実行する。
- [x] PostgreSQL 起動後、`cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:${POSTGRES_PORT:-5432}/app_test uv run python manage.py db-upgrade --revision head` を実行する。
- [x] PostgreSQL 起動後、`cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:${POSTGRES_PORT:-5432}/app_test uv run pytest tests/integration -q -ra` を実行する。
- [x] Redis 起動後、`cd backend && TEST_REDIS_URL=redis://localhost:${REDIS_PORT:-6379}/1 uv run pytest tests/integration/test_redis_rate_limiter.py -q` を実行する。
- [x] `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:${POSTGRES_PORT:-5432}/app_test uv run python manage.py db-check` を実行する。
- [x] repository root で `docker compose config` を実行する。
- [x] repository root で `docker build --target runtime -t python-react-template-runtime .` を実行する。
- [x] repository root で `docker build --target backend-dev -t python-react-template-backend-dev .` を実行する。
- [x] 実行できなかった command がある場合は、理由、必要な環境変数、未確認リスクを実装完了報告に書く。

## 実装時の注意

- この計画は DB schema を変更しない。Alembic revision は作らない。
- `redis` 依存追加は実装時に人間の承認を取ってから行う。
- Redis URL は secret になり得るため、実値を docs や test output に残さない。
- Redis key prefix は環境ごとに分ける。shared Redis を使う場合、staging / production / test で同じ prefix を使わない。
- Redis integration test は prefix-scoped cleanup を使い、`FLUSHDB` を使わない。
- Rate limiter log message には email、IP、Redis URL、password、session token、CSRF token を含めない。
- Frontend 表示文言は既存 `login_rate_limited` / `register_rate_limited` / `account_deletion_reauth_rate_limited` を維持する。Redis outage fail-closed でも wire response は既存 429 になるため、Frontend 変更は不要。
- Redis Cluster 対応はこの計画に含めない。必要になった場合は key hash tag と multi-key operation 方針を別計画で扱う。

## レビュー観点

- `AUTH_RATE_LIMIT_BACKEND=memory` の既定動作が既存と同じか。
- Redis score が process-local monotonic ではなく Redis server `TIME` の Unix epoch seconds か。
- Redis mode で別 process 間の失敗回数が共有されるか。
- check 系が `ZCOUNT` + pipeline で、check path に write command がないか。
- window boundary が in-memory と Redis で一致しているか。
- Redis outage policy、deadline、circuit breaker が docs と実装で一致しているか。
- Redis client が `socket_timeout`、`socket_connect_timeout`、`max_connections` を settings から受け取り、connection pool が無制限になっていないか。
- Redis provider が `BlockingConnectionPool` を使い、pool 枯渇を circuit breaker の連続失敗に数えず、pool 枯渇 warning を rate limit しているか。
- circuit breaker が累計失敗ではなく連続失敗で open し、Redis operation 成功時に failure count を reset するか。
- deadline timeout 後に redis-py connection / response がずれないことを version 確認と、`BLPOP` + `max_connections=1` の実接続 test で押さえているか。
- record 系 pipeline が `transaction=True` を使っているか。
- Redis unavailable log が通常の bucket 到達と区別できるか。
- Redis memory policy が compose と docs に明記されているか。
- async interface 化によって sync test fixture や TestClient cleanup が破綻していないか。
- controller integration tests の `create_app()` は autouse fixture で memory backend に固定され、`.env` の Redis 設定に引きずられないか。
- sync cleanup が async `reset_for_tests()` の coroutine を捨てる silent failure を検出できるか。
- `reset_for_tests()` が production interface に露出していないか。
- register duplicate が login email-only bucket を増やしていないか。
- login success が IP bucket / email bucket を消していないか。
- rate-limited request が audit insert を増やしていないか。
- Redis key に raw email / IP が含まれていないか。
- `auth-rate-limiting` skill が future agent に必要な契約を短く正確に伝えているか。

## 参考にした外部一次情報

- Redis Python async docs: https://redis.io/docs/latest/develop/clients/redis-py/async/
- redis-py asyncio examples: https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html
- Docker Redis official image: https://hub.docker.com/_/redis

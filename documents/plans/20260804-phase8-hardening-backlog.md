# Phase 8 Hardening Backlog

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:writing-plans` before turning any item in this backlog into an implementation plan. This file is a backlog for future plans, not an executable implementation plan. 実装時は各 Task を `documents/plans/YYYYMMDD-<topic>.md` の個別計画へ展開してから着手する。

**Goal:** Phase 7 で意図的に対象外へ送った hardening / UX / security 項目を、次フェーズで失わず個別計画へ展開できる粒度で保持する。

**Architecture:** Phase 8 候補は auth retention、rejected session replay、auth form feedback、account lifecycle、large migration playbook に分ける。各 Task は独立した検証単位にし、実装時は Phase 7 完了後のコードに対して対象ファイル、migration 要否、テスト、品質ゲートを再確認する。

**Tech Stack:** FastAPI、SQLModel、PostgreSQL、Alembic、Typer、pytest、React、TanStack Router、TanStack Query、Vitest

---

## 実行順

> 2026-08-06 時点: P8-BE-3 と P8-BE-1 は完了済み。次着手は P8-FE-0。

1. **[x] P8-BE-3**: auth session / audit log retention policy は完了済み。`auth_audit_logs.session_id ON DELETE SET NULL` と session pruning の相互作用を docs / tests で固定した。
2. **[x] P8-BE-1**: CSRF middleware 経路を含む rejected session replay の bounded audit / 集約は完了済み。5 分 window の `detail_json.replay_count` 更新で replay signal を保持する。
3. **[ ] P8-FE-0**: login / register / account deletion に共通する feedback / a11y 契約を `frontend/AGENTS.md` へ先に固定する。
4. **P8-FE-1**: account deletion form の field error、stale error clear、native validation 方針を直す。
5. **P8-FE-2**: `Retry-After` aware な destructive form feedback を追加する。
6. **P8-BE-2**: deleted / inactive user 観測時の session revoke 方針を、admin revoke usecase / CLI 案と比較して決める。
7. **P8-FE-3**: feedback component 抽出を行う。P8-FE-0 の契約に従うだけにし、a11y 方針をここで再決定しない。
8. **P8-BE-4**: INET / auth operational migration の large DB playbook を docs に追加する。
9. **P8-AD-1 / P8-AD-2**: OAuth/OIDC または product-specific deletion lifecycle の要件が出た時点で個別計画化する。

## [x] Task P8-BE-3: Auth session / audit log retention policy

**状態:** Done (2026-08-06)。実装計画: `documents/plans/20260806-phase8-auth-session-retention.md`

**問題:** `db-prune-auth` は expired session と古い audit log を削除できるが、`auth_audit_logs.session_id` は `auth_sessions.id` へ `ON DELETE SET NULL` で紐づいている。そのため session を audit log より短く保持すると、audit log 行は残るが「どの session の操作だったか」という参照が黙って `NULL` になる。revoked-but-unexpired session は absolute TTL 内に自然に expired になるため、主問題は未 expire revoked session そのものより、audit retention と session retention の整合である。

**現状:**

- `AuthRepository.delete_sessions_expired_before(expired_before)` は `AuthSession.expires_at < expired_before` の session だけを削除する。
- `db-prune-auth` は `--expired-sessions-before` と `--audit-logs-before` だけを持つ。
- `auth_audit_logs.session_id` は `ForeignKey("auth_sessions.id", ondelete="SET NULL")`。
- `AuthSession.expires_at` は `min(issued_at + absolute TTL, last_seen_at + idle TTL)` なので、revoked session も absolute TTL を超えて未 expire のまま残らない。
- 追加の `--revoked-sessions-before` は導入せず、expired session pruning に統一した。session 物理削除後の replay は unknown token として扱われ、known rejected session audit は作られないことを docs に明記した。

**対象ファイル候補:**

- 変更: `backend/app/interfaces/services/auth_repository_interface.py`
- 変更: `backend/app/services/auth_repository.py`
- 変更: `backend/manage.py`
- 変更: `backend/AGENTS.md`
- 変更: `README.md`
- テスト: `backend/tests/unit/test_manage.py`
- テスト: `backend/tests/unit/services/test_auth_repository.py`
- テスト: `backend/tests/integration/services/test_auth_repository.py`

**受け入れ条件:**

- Auth session retention と audit log retention の関係が docs に明記されている。
- `README.md` を変更する場合は、grep 用の断片だけを足さず、`db-prune-auth` の運用手順ごと追加する。README に載せない判断をする場合は対象ファイル候補と docs grep から README を外す。
- Audit log の `session_id` を保持したい運用では、session retention が audit log retention 以上であることを要求する、または `SET NULL` による紐付け喪失を明示的に受容する。
- `db-prune-auth` で audit log と session の両方を削除する場合の順序と部分成功時の影響が docs に書かれている。
- repository method 名が実動作と一致する。例: `delete_sessions_expired_before()` のように条件を名前へ含める。
- revoked-but-unexpired session を別 threshold で削除するかどうかを決める。追加する場合は `--revoked-sessions-before <ISO8601>` のように明示 option にする。
- revoked session を pruning した後の replay は `find_session_by_token_hash()` が `None` を返すため unknown token として扱われ、known rejected session audit は作られない。この挙動を docs に書く。
- timezone offset なし datetime は従来どおり CLI で拒否される。

**必要テスト:**

- Unit: CLI が retention policy に沿った option を repository へ渡す。
- Unit / integration: expired session 削除後、関連 audit log の `session_id` が `NULL` になる挙動を意図的な契約として検証する、または session retention 制約で回避する挙動を検証する。
- Unit / integration: active unexpired session は削除されない。
- Docs grep: `backend/AGENTS.md` には `audit log session retention` が存在する。`README.md` は `Auth audit/session pruning` セクション内に `session retention` と `audit log retention` が存在することで判定する。

## [x] Task P8-BE-1: Rejected session replay の bounded audit / 集約

**状態:** Done (2026-08-06)。実装計画: `documents/plans/20260806-phase8-rejected-session-bounded-audit.md`

**問題:** `AuthUsecase._audit_known_rejected_session()` は、既知だが active ではない session token が replay されるたびに `SESSION_REJECTED` audit log を作る。呼び出し元は `authenticate_session()` だけではなく、CSRF middleware 経由の `validate_session_csrf()` にもある。CSRF middleware は routing より前に unsafe `/api` request を検証するため、失効した session cookie と自己整合的な任意の CSRF cookie/header pair を持つ `POST /api/unknown` でも、404 に到達する前に rejected session audit が走る。Session に紐づく正当な CSRF token は不要である。

**現状:**

- `authenticate_session()` で active session が見つからない場合、`find_session_by_token_hash()` により expired / revoked session も検索される。
- `validate_session_csrf()` でも active session が見つからない場合、同じ `_audit_known_rejected_session()` を呼ぶ。
- CSRF middleware は routing 前に走るため、存在しない unsafe `/api` path でも session cookie があり、CSRF cookie/header 同士が一致していれば `validate_session_csrf()` 経路に入る。
- `validate_session_csrf()` が `SessionCsrfStatus.NO_SESSION` を返した場合、middleware は 403 を返さず downstream へ進む。存在しない path では、audit 後に 404 になる。
- unknown random token では `find_session_by_token_hash()` が `None` になり audit log は作られない。
- `authenticate_session()` 経路は `UnitOfWork.transaction()` 内から呼ばれ、repository `_persist()` は `flush()` になる。一方、CSRF middleware 経路は通常の request handling 前で transaction 外から呼ばれ、repository `_persist()` は 1 operation ごとの `commit()` になる。
- `record_rejected_session_replay()` は 5 分 window 内の aggregate `SESSION_REJECTED` row を更新し、`detail_json.replay_count`、`detail_json.last_replayed_at`、`detail_json.last_ip_address`、`detail_json.last_user_agent`、`detail_json.distinct_ip_count`、`detail_json.recent_ip_addresses` を保持する。session id ごとの PostgreSQL `pg_try_advisory_xact_lock` により同時 replay の lost update / duplicate aggregate row を避ける。lock が busy の場合は CSRF middleware 経路を待たせず replay 1 件の記録をスキップする。したがって `replay_count` は実 replay 数の下限値、`distinct_ip_count` は capped recent IP 窓による過大側に振れ得る近似値である。
- Composite index は初期実装では追加しない。window lookup は既存 `session_id` index から session 単位に絞り、template 規模では session あたりの aggregate row が少ないため、migration 追加の費用に見合わないと判断した。production DB で session あたり audit row が増える場合は `(session_id, event_type, created_at)` を EXPLAIN 付きで再評価する。
- in-memory throttle は採用しない。単一 process の DB 往復は減らせるが、複数 worker / 複数 instance では audit signal が割れるため、backend の正規 audit 契約にはしない。

**対象ファイル候補:**

- 変更: `backend/app/usecases/auth_usecase.py`
- 変更: middleware 固有の挙動を変える場合は `backend/app/bootstrap/csrf.py`
- 変更: `backend/app/interfaces/services/auth_repository_interface.py`
- 変更: `backend/app/services/auth_repository.py`
- 任意 migration: aggregate table / column または composite index を追加する場合は `backend/alembic/versions/<revision>.py`
- テスト: `backend/tests/unit/usecases/test_auth_usecase.py`
- テスト: `backend/tests/unit/bootstrap/test_csrf_middleware.py`
- テスト: `backend/tests/integration/services/test_auth_repository.py`
- テスト: `backend/tests/integration/test_auth_controller.py`
- Docs: `backend/AGENTS.md`

**受け入れ条件:**

- `authenticate_session()` と `validate_session_csrf()` の両経路が同じ bounded audit 契約に従う。
- CSRF middleware 経由の rejected replay も、存在しない unsafe `/api` path を含めて bounded になる。
- unknown random token は引き続き audit log を作らない。
- deleted / inactive user の active session を初回に revoke する audit event は抑制しない。
- bounded audit は単純に「window 内 1 件だけ残して残りを捨てる」ではなく、replay 回数の監視 signal を保持する。候補は `detail_json` の count 更新、window 単位の aggregate event、または別集計テーブル。
- DB lookup / update で throttling する場合は、window lookup 用の複合 index を前提にする。既存の `session_id` 単独 index だけで十分か、`(session_id, event_type, created_at)` などが必要かを個別計画で判断する。
- `detail_json` count 更新などの read-modify-write を採用する場合は、CSRF middleware 経路の transaction 外 commit と同時 replay 競合を考慮し、lost update や重複 aggregate row が起きない設計にする。
- in-memory throttle 案も比較対象に含める。DB 往復を減らせる一方、複数 worker / 複数 instance では効かないため、本番運用の限界を docs に書く。
- `backend/AGENTS.md` に「known rejected session replay は bounded audit かつ replay count を保持する」と明記する。

**必要テスト:**

- Unit: 同じ revoked session を `authenticate_session()` に複数回渡しても、audit rows は bounded で、replay count signal は残る。
- Unit: 同じ revoked session を `validate_session_csrf()` に複数回渡しても、同じ bounded 契約に従う。
- Unit: unknown token の replay は audit 0 件。
- Unit / integration: CSRF middleware 経由の unsafe `/api/unknown` replay は downstream の 404 を返しつつ、bounded audit になる。403 を期待しない。
- Integration: DB 上の revoked session token replay で rows / aggregate count が期待どおりになる。

**依存:** P8-BE-3 は完了済み。P8-BE-3 で固定した retention policy を前提にする。

## Task P8-FE-0: Auth form feedback / a11y 契約の確定

**問題:** Login、register、account deletion はそれぞれ error feedback をローカルに描画しており、field-level と form-level の扱い、`aria-describedby`、`aria-invalid`、destructive / unsafe action copy が drift し得る。P8-FE-1 / P8-FE-2 で account deletion form を触る前に、現状挙動を追認する共通契約を決めないと手戻りになる。

**現状:**

- `LoginForm` と `RegisterForm` は form-level `errorMessage` を各 field の `aria-describedby` に渡す。
- `AccountDeletionPanel` は指定された field だけ `aria-invalid` にするが、`errorMessage` があると両方の input が同じ form error を `aria-describedby` で指す。
- `frontend/AGENTS.md` は account deletion の 429 / CSRF では input を invalid にしないと書いているが、form-level error と `aria-describedby` の共通方針は未確定。

**対象ファイル候補:**

- 変更: `frontend/AGENTS.md`
- 任意変更: 実装前に契約を test に固定する場合は対象 component tests

**受け入れ条件:**

- Field-specific error は該当 field だけに `aria-invalid` と `aria-describedby` を付ける方針が docs にある。
- Form-level error は `role="alert"` で表示し、無関係な field を invalid にしない方針が docs にある。
- 429 / CSRF など field に紐づかない error で input が form error を `aria-describedby` で指すかどうかを決め、`frontend/AGENTS.md` に明記する。
- Login / register の invalid credentials や duplicate email は、現状の挙動を追認して field error か form-level error かを docs に書く。ここでは挙動変更を決めない。
- P8-FE-1 / P8-FE-2 / P8-FE-3 はこの契約に従い、別々に a11y 方針を再決定しない。
- FE-0 の検討中に login / register の挙動変更が必要だと判断した場合は、P8-FE-3 に混ぜず、別 Task を追加して対象 component / route tests を明記する。

**必要検証:**

- Docs grep: `field-specific error`、`form-level error`、`aria-describedby` または同等の grep 可能な語句が `frontend/AGENTS.md` に存在する。

## Task P8-FE-1: Account deletion field errors / stale clear / native validation

**問題:** `/app/settings` は backend account deletion errors を user message へ変換するが、空の `confirmEmail` 422 は generic message のままで、input edits も route-level error feedback を次 submit まで消さない。さらに `AccountDeletionPanel` の confirmation email は `type="email"` なので、不正形式では browser native validation が submit を止め、アプリ側の error 表示が出ない可能性がある。jsdom は native validation を再現しないため、Vitest だけでは見落とす。

**現状:**

- `frontend/src/routes/_authenticated.app_.settings.tsx` は account deletion domain error code を message と invalid field へ変換する。
- `AccountDeletionPanel` は input state を持つが、field change を route へ通知できない。
- 422 validation error は generic `入力内容を確認してください。` へ変換される。
- `AccountDeletionPanel` は `required` を渡していないため空文字 submit は backend 422 へ到達する。
- `type="email"` の native validation は、実ブラウザで `abc` のような値の submit を止める可能性がある。

**対象ファイル候補:**

- 変更: `frontend/src/components/organisms/Auth/AccountDeletionPanel.tsx`
- 変更: `frontend/src/routes/_authenticated.app_.settings.tsx`
- 変更: validation details の typed helper が必要な場合は `frontend/src/lib/apiError.ts`
- テスト: `frontend/src/components/organisms/Auth/AccountDeletionPanel.test.tsx`
- テスト: `frontend/src/routes/app.settings.test.tsx`
- 任意検証: `noValidate` 採用時は e2e / browser verification

**受け入れ条件:**

- 空の `confirmEmail` 由来の 422 は confirmation email field-specific message として表示する。
- `confirmEmail` mismatch は confirmation email field だけを invalid にする。
- password missing / invalid は password field だけを invalid にする。
- invalid field を編集したら、次 submit 前に stale field error が消える。
- 別 field の編集で無関係な field-specific error を消すかどうかは P8-FE-0 の契約に従う。
- 429 / CSRF validation failure など field に紐づかない error は form-level error のまま扱う。
- `noValidate` を付けて browser native validation を避けるか、native validation を使うなら不正形式時の UX を実ブラウザで確認する。どちらを選ぶかを個別計画に明記する。

**必要テスト:**

- Component: `AccountDeletionPanel` が changed field name を callback へ渡す。
- Component: `noValidate` を採用する場合、form に `noValidate` が付く。
- Route: 空の confirmation email 422 で field-specific message と invalid state が出る。
- Route: confirmation email 編集で stale confirmation email error が消える。
- Route: password 編集で stale password error が消える。
- Route: 429 / CSRF errors は form-level で、input を invalid にしない。

**依存:** P8-FE-0 を先に完了する。

## Task P8-FE-2: Retry-After aware destructive form feedback

**問題:** Backend account deletion 429 response は `Retry-After` を返すが、frontend の `ApiError` は response headers を保持しない。ユーザーには generic message しか表示されず、server-advised duration に沿った表示や disabled duration を実装できない。

**現状:**

- `ApiError` は status、body、code、detail、details を持つが response headers を持たない。
- `apiClient` は `new ApiError(response.status, body)` だけを作る。
- `toUserMessage()` は status 429 を generic message へ変換する。
- `/app/settings` は `ACCOUNT_DELETION_REAUTH_RATE_LIMITED` を generic message へ変換する。

**対象ファイル候補:**

- 変更: `frontend/src/lib/apiClient.ts`
- 変更: `frontend/src/lib/apiError.ts`
- 変更: `frontend/src/routes/_authenticated.app_.settings.tsx`
- 変更: `frontend/src/components/organisms/Auth/AccountDeletionPanel.tsx`
- テスト: `frontend/src/lib/apiClient.test.ts`
- テスト: `frontend/src/lib/apiError.test.ts`
- テスト: `frontend/src/routes/app.settings.test.tsx`

**受け入れ条件:**

- `ApiError` が numeric `Retry-After` header を `retryAfterSeconds` として公開する。
- `Retry-After` がない場合や不正値の場合、`retryAfterSeconds` は `null` になる。
- Account deletion 429 message は server-provided retry timing を反映する。
- Account deletion submit button を cooldown 中に disabled にするか、message-only にするかを個別計画で選ぶ。
- Cooldown behavior は route-local で、失敗時に unrelated query cache を消さない。

**必要テスト:**

- API client: `Retry-After: 60` の 429 で `ApiError.retryAfterSeconds === 60` になる。
- API client: header なし / 不正値では retry value が `null` になる。
- Route: account deletion 429 with `Retry-After` で retry-aware feedback が出る。
- Route: disabled-duration を選ぶ場合、fake timers で button の disabled / re-enabled を検証する。

**依存:** P8-FE-0 と P8-FE-1 の field/form error 契約に従う。

## Task P8-BE-2: Deleted / inactive user 観測時の session revoke 方針

**問題:** Phase 6 account deletion 成功時は `revoke_sessions_for_user()` で対象 user の全 active session を revoke する。一方で、外部管理や手動運用で `users.deleted_at` / `users.is_active` が後から変わった場合、`authenticate_session()` は観測した session だけを revoke する。ただし、認証ホットパスに bulk UPDATE を入れることが正しいとは限らず、admin 用 revoke usecase / CLI で状態変更時に revoke する設計も比較すべきである。

**現状:**

- `AccountDeletionUsecase.delete_account()` は `mark_user_deleted()` と `revoke_sessions_for_user()` を同一 transaction 内で呼ぶ。
- `AuthUsecase.authenticate_session()` は deleted / inactive user を検知すると `_reject_session()` を呼び、現在の `auth_session.id` だけを revoke する。
- `_reject_session()` は `revoke_session()` の内部 `utcnow()` を使うため、bulk revoke と組み合わせる場合に `revoked_at` timestamp が揃わない可能性がある。

**対象ファイル候補:**

- 変更: `backend/app/usecases/auth_usecase.py`
- 任意作成: 採用方針に応じた admin / user status change usecase または CLI files
- 変更: `backend/tests/unit/usecases/test_auth_usecase.py`
- テスト: `backend/tests/integration/test_auth_controller.py`
- Docs: `backend/AGENTS.md`

**受け入れ条件:**

- 認証時に全 session revoke する案と、user status change / admin revoke usecase / CLI で事前 revoke する案を比較し、採用理由を個別計画に書く。
- 認証ホットパスに bulk UPDATE を入れる場合、deleted / inactive user を観測した時だけ発火し、通常 active session の処理コストを増やさない。
- 全 session revoke を採用する場合、観測 session 自身と他 active session の `revoked_at` timestamp の扱いが明記される。同一 timestamp に揃えるなら repository API を変更する。
- missing user は user id の正当性が保証できないため、従来どおり観測 session だけを revoke する。
- audit log は観測した request / session に対して 1 件だけ残し、revoke された全 session 分の audit log を無条件に作らない。
- P8-BE-1 後、すでに revoked になった token replay は audit log を増幅させない。

**必要テスト:**

- Unit: 採用方針に応じて deleted user / inactive user の session revoke 契約を固定する。
- Unit: missing user は `revoke_sessions_for_user()` を呼ばず、観測 session だけ revoke する。
- Integration: 2 つの session を持つ user を inactive にした場合、採用方針どおりに両 session の `revoked_at` が埋まる、または admin revoke usecase / CLI 経由で埋まる。
- Integration: 通常 active user の `/api/auth/me` では追加 bulk UPDATE が走らないことを、可能なら repository call / SQL count で確認する。

**依存:** P8-BE-1 を先に完了する。

## Task P8-FE-3: Auth feedback component 抽出

**問題:** Login、register、account deletion の feedback markup が form ごとに散っている。P8-FE-0 で契約を固定し、P8-FE-1 / P8-FE-2 で account deletion の挙動を直した後、重複を減らして今後の drift を防ぐ。

**現状:**

- `LoginForm`、`RegisterForm`、`AccountDeletionPanel` がそれぞれ `<p role="alert">` を持つ。
- Field-specific / form-level の契約は P8-FE-0 で決める。
- Account deletion 固有の stale clear / Retry-After は P8-FE-1 / P8-FE-2 で扱う。

**対象ファイル候補:**

- 変更: `frontend/src/components/organisms/Auth/LoginForm.tsx`
- 変更: `frontend/src/components/organisms/Auth/RegisterForm.tsx`
- 変更: `frontend/src/components/organisms/Auth/AccountDeletionPanel.tsx`
- 任意作成: `frontend/src/components/molecules/AuthFormFeedback.tsx`
- テスト: `frontend/src/components/organisms/Auth/LoginForm.test.tsx`
- テスト: `frontend/src/components/organisms/Auth/RegisterForm.test.tsx`
- テスト: `frontend/src/components/organisms/Auth/AccountDeletionPanel.test.tsx`

**受け入れ条件:**

- P8-FE-0 の契約に従う shared feedback component または shared helper がある。
- Login、register、account deletion の alert markup が同じ component / helper 経由になる。
- Field-specific error と form-level error の `aria-invalid` / `aria-describedby` 挙動が既存 tests で固定される。
- 既存 visible copy は日本語の user-facing copy のまま維持し、実装詳細や keyboard shortcut 説明を in-app text に入れない。

**必要テスト:**

- Login: invalid credentials の form-level feedback と field association が P8-FE-0 の契約どおり。
- Register: password validation / mismatch field behavior が維持される。
- Account deletion: 429 / CSRF は form-level で、input を invalid にしない。
- Component tests で accessible alert text と field association を検証する。

**依存:** P8-FE-0、P8-FE-1、P8-FE-2 を先に完了する。

## Task P8-BE-4: INET / auth operational migration の large DB playbook

**問題:** Phase 5 migration `20260803_0003` は `auth_audit_logs.ip_address` と `auth_sessions.ip_address` の全行 UPDATE / `ALTER COLUMN ... TYPE INET`、`auth_sessions.issued_at` / `updated_at` backfill を含む。テンプレート利用直後の小規模 DB では問題になりにくいが、大規模 DB へ適用する派生プロジェクトでは long lock / rewrite の運用リスクがある。

**現状:**

- Migration は `_phase5_try_inet()` を使って不正 IP を `NULL` に寄せた後、全行 UPDATE と `ALTER COLUMN` を行う。
- `documents/references/backend-app-structure.md` には INET 型方針はあるが、online / batch migration 手順はない。

**対象ファイル候補:**

- 変更: `documents/references/backend-app-structure.md`
- 変更: `backend/AGENTS.md`
- 任意変更: `README.md`
- 任意変更: comment のみなら `backend/alembic/versions/20260803_0003_phase5_auth_operational_fields.py`

**受け入れ条件:**

- `20260803_0003` を大規模 production DB にそのまま適用する前に確認すべき row count / lock / maintenance window の判断基準が docs にある。
- 大規模 DB 用の代替手順が docs にある。例: nullable shadow column 追加、batch backfill、dual-write 期間、短時間 lock の column swap、index concurrently 方針。
- 既存テンプレートの fresh DB / small DB では現 migration を維持できることが明記される。
- Alembic migration を書き換える場合は、既存 DB に適用済みの派生プロジェクトへの影響を個別計画で扱うよう明記する。

**必要検証:**

- Docs grep: `large auth migration`、`batch backfill`、`INET` が `documents/references/backend-app-structure.md` に存在する。
- Code change が comment のみなら test は不要。migration logic を変える場合は fresh upgrade / db-check / downgrade smoke を個別計画に含める。

## Task P8-AD-1: OAuth-only account deletion の provider reauthentication

**状態:** OAuth/OIDC client が存在するまで blocked。

**問題:** Phase 6 の現契約では、OAuth-only user (`password_hash IS NULL`) の deletion を OAuth provider reauthentication 実装まで `confirmEmail` のみで許可している。`confirmEmail` は authentication factor ではない。Session と CSRF token の両方を奪取された場合、追加の本人確認なしに不可逆削除できる。

**現状:**

- `AccountDeletionUsecase.delete_account()` は `password_hash is not None` の user だけ password reauthentication を要求する。
- `backend/AGENTS.md` は OAuth-only deletion caveat を明記済み。
- OAuth/OIDC provider、`auth_identities`、provider callback はまだ存在しない。

**OAuth/OIDC 実装後の対象ファイル候補:**

- 変更: `backend/app/usecases/account_deletion_usecase.py`
- 変更: OAuth 実装で追加される OAuth/OIDC usecase / provider callback files
- 変更: `backend/app/models/auth_errors.py`
- 変更: `backend/app/controllers/auth_controller.py`
- 変更: `frontend/src/routes/_authenticated.app_.settings.tsx`
- テスト: account deletion usecase / controller / route tests
- Docs: `backend/AGENTS.md`, `documents/references/backend-app-structure.md`

**受け入れ条件:**

- OAuth-only account deletion が provider-backed reauthentication、recent login、または project-specific replacement control を要求する。
- Reauthentication freshness window が明示される。例: deletion 前 5 分以内に provider reauth が完了している。
- OAuth reauthentication が missing / stale の場合、machine-readable error code を返す。
- Frontend は provider reauth error を明確に表示し、無関係な field を invalid にしない。
- OAuth `state` / nonce / PKCE checks を使う場合、provider redirect における CSRF-equivalent control として docs に書く。
- 派生プロジェクトで OAuth/OIDC を実装しない場合、OAuth-only deletion を disabled にするか、documented caveat のまま許可するかを個別計画で決める。

**必要テスト:**

- Unit: fresh provider reauth がない OAuth-only user は account deletion できない。
- Unit / integration: fresh provider reauth がある OAuth-only user は account deletion できる。
- Integration: stale / missing provider reauth は期待する error envelope を返す。
- Frontend: route が provider reauth error を表示し、失敗時 cache を保持する。

## Task P8-AD-2: Account deletion grace period / restore / email reuse policy

**状態:** product policy dependent。

**問題:** 現在の account deletion は immediate logical user deletion と user-owned sample item physical deletion を行う。Deleted user email は `uq_users_email_lower_active` により再利用できる。将来 restore API / admin recovery UI を追加する場合、grace period、resource retention、email conflict after re-registration の方針なしでは安全に実装できない。

**現状:**

- `users.deleted_at` は即時に設定される。
- 対象 user が所有する `sample_items` は物理削除される。
- Deleted user email は audit/history のため保持されるが、同じ email を新しい active user が登録できる。
- 同じ email が再登録済みの場合、旧 user restore は active partial unique index に衝突する。

**実装する場合の対象ファイル候補:**

- 変更: `backend/app/models/user.py`
- 変更: `backend/app/usecases/account_deletion_usecase.py`
- 変更: `backend/app/services/auth_repository.py`
- 変更: 採用 workflow で追加される account / admin controller files
- 変更: `frontend/src/routes/_authenticated.app_.settings.tsx` または admin UI routes
- Migration: `backend/alembic/versions/<revision>.py`
- Docs: `backend/AGENTS.md`, `documents/references/backend-app-structure.md`

**設計計画の受け入れ条件:**

- Immediate deletion と grace-period deletion のどちらを採用するかが明示される。
- Grace period を採用する場合、scheduled finalization / cancellation / restore の責務が具体的な usecase または CLI command に割り当てられる。
- Deleted email reuse 後の restore behavior が明示される。少なくとも active email conflict が解消されるまで restore は conflict で失敗する。
- User-owned resource retention が table ごとに明示される。現在の `sample_items` physical deletion のままでは sample content は restore できない。
- Requested deletion、finalized deletion、cancellation、restore の audit event が実装前に列挙される。

**実装する場合の必要テスト:**

- Unit: 別 active user が同じ lowercased email を持つ場合、deleted user restore は失敗する。
- Unit / integration: email conflict がない grace period 内 restore は成功する。
- Integration: finalized deletion は explicit admin override がない限り restore できない。
- Account deletion coverage test がすべての user-owned resource に対して更新される。

## 旧メモとの対応

| 旧メモ項目 | 新 Task |
|---|---|
| Revoked session token replay で audit log が無制限に増えないようにする | P8-BE-1 |
| deleted / inactive user 認証時に対象 user の全 active session を revoke するか設計する | P8-BE-2 |
| `db-prune-auth` または repository pruning が revoked but unexpired session をどう扱うか明文化する | P8-BE-3 |
| `delete_sessions_expired_before()` の名前と実動作を確認する | P8-BE-3 |
| INET migration の全行 UPDATE / large DB 方針 | P8-BE-4 |
| OAuth-only user の削除に provider reauthentication を追加する | P8-AD-1 |
| 削除猶予期間 / 即時不可逆削除を選択可能にする | P8-AD-2 |
| Account restore API / admin recovery UI と partial unique index 制約 | P8-AD-2 |
| Account deletion form の空入力 422 を field-specific message にする | P8-FE-1 |
| Account deletion form の入力修正時に stale error 表示を消す | P8-FE-1 |
| 429 response の `Retry-After` を UI message または disabled duration に反映する | P8-FE-2 |
| Field に紐づかない 429 / CSRF error で `aria-describedby` が必要か再評価する | P8-FE-0 |
| Login / register / account deletion errors を共通 feedback component に寄せる | P8-FE-3 |

## Phase 8 計画化時の共通品質ゲート

各 Task を個別実装計画へ展開するときは、変更範囲に応じて次を含める。

- Backend static: `cd backend && uv run ruff check .`、`uv run isort . --check-only`、`uv run yapf -dr app/ tests/ alembic/ manage.py`、`uv run mypy app manage.py`
- Backend unit: `cd backend && uv run pytest tests/unit -q`
- Backend integration: PostgreSQL 起動後、`cd backend && DATABASE_URL=... uv run python manage.py db-upgrade`、`TEST_DATABASE_URL=... uv run pytest tests/integration -q -ra`、`DATABASE_URL=... uv run python manage.py db-check`
- Frontend: `cd frontend && npm run check:ci`、`npm test`、`npm run build`
- Docker / docs を触る場合: `docker compose config` と対象 docs grep

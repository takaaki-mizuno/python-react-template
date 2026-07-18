# Auth Resumption Verification Evidence

## 実行情報

- 記録日時: 2026-07-19 00:24:56 JST
- Branch: `feature/db-auth`
- Base / HEAD: `eb5db180cb78936b57400865e8ddf26beec199ef`
- 検証対象: base commit に対する current uncommitted working tree（tracked / untracked の認証関連差分）

## Migration / PostgreSQL

- PostgreSQL: Docker Compose `postgres:17-bookworm`、database `app_test`
- `db-upgrade --revision head`: exit 0
- `db-downgrade --revision base`: exit 0
- 再度の `db-upgrade --revision head`: exit 0
- 最終schema確認: `users`、`auth_sessions`、`auth_audit_logs` が存在
- Integration test: 実PostgreSQLへ接続し、skipなしで実行

## Backend quality gate

- `uv run pytest`: 59 passed / 0 skipped / 0 failed、exit 0
- Warnings: 4件（TestClient / per-request cookies の既存deprecation warning）
- `uv run isort . --check-only`: exit 0
- `uv run yapf -dr app/ tests/ alembic/`: exit 0、diffなし
- Attempt 5 targeted test: unit 2 passed、PostgreSQL integration 3 passed

検証した主なsecurity contract:

- DUMMY_PASSWORD_HASH自体が実Argon2でcurrent work factorと一致すること
- session / CSRF tokenのentropy・一意性・hashのみの永続化
- Cookie属性と`Cache-Control: no-store`
- 期限切れ／失効Cookieからのlogin・register復旧とCSRF再同期
- 任意tokenはaudit非記録、実在inactive sessionはuser/session ID付きで`session_rejected`
- register / login rollbackと同時transactionのContextVar分離
- session token unique lookup indexとtimezone-aware timestamp

## Frontend quality gate

- `npm test`: 7 files / 15 tests passed / 0 skipped / 0 failed、exit 0
- `npm run check`: exit 0
- Prettier: write後の変更なし
- ESLint: exit 0、warning 0
- `npm run build`: exit 0
- Build warning: 既存の未定義`%VITE_SITE_URL%` warning 3件のみ

検証した主なsecurity contract:

- CSRF bootstrap non-2xxをtyped `ApiError`として伝播し、unsafe requestを送信しない
- logout後にactive user cacheを`null`化し、strict guard cacheを削除
- `/app` guardがcached userを使わず`/api/auth/me`を再取得
- 401のみを未ログインとして扱い、5xx / network errorを保持

## Independent security / code review

### Attempt 1 — `auth_security_review`（Superseded）

- Critical: 0
- Important: 5
- Minor: 4
- Verdict: `Ready to commit: No`
- 採用: proxy trust、stale Cookie / CSRF、transaction、logout cache、security test不足
- 対応: test-firstで修正し、PostgreSQL / frontend回帰テストを追加

### Attempt 2 — `auth_security_rereview`（Superseded）

- Critical: 0
- Important: 3
- Minor: 2
- Verdict: `Ready to commit: With fixes`
- 採用: arbitrary tokenによるaudit増幅、CSRF bootstrap error握り潰し、auth GETの`no-store`不足
- 対応: test-firstで修正。Minorのregister stale-cookieとtransaction同時実行テストも追加

### Attempt 3 — `auth_security_final_review`（Superseded）

- Critical: 0
- Important: 1
- Minor: 0
- Verdict: `Ready to commit: With fixes`
- 採用: arbitrary token非記録と、実在expired / revoked sessionの`session_rejected` auditを区別
- 対応: inactive session lookupと両側のPostgreSQL回帰テストを追加

### Attempt 4 — `auth_security_closeout`（Superseded）

- Critical: 0
- Important: 0
- Minor: 1
- Verdict: `Ready to commit: Yes`
- Minor: positive audit testがuser/session ID一致を直接assertしていない
- Disposition: 採用。`auth_audit_logs`と`auth_sessions`をuser/session IDでjoinするassertへ補強し、対象3 tests passed

### Attempt 5 — Claude Code external review（Current）

- Critical: 0
- Important: 3
- Minor: 5
- Verdict: `Ready to commit: With fixes`
- I-1: 採用。未登録emailのgeneric 401統合テストと、dummy hash引数を直接確認するunit testを追加。
- I-2: 採用。実PostgreSQLの`EXPLAIN`で`email = ...`がseq scan、`lower(email) = ...`が`uq_users_email_lower`のindex scanになることを確認。schema / migrationは変更せずrepository queryを修正。
- I-3: 一部採用。現行実装にsecret保存は見つからないが、検証済みという主張は過大だった。監査行全体にpassword / raw session token / raw CSRF tokenがないことを確認するintegration assertionへ修正。
- M-1: 保留。成功を含む認証試行のrate limitは現行contractであり、失敗時のみ計数する変更は別途製品判断が必要。
- M-2: 保留。requestごとのsession更新はsliding idle TTLの現行contractであり、間引きは期限計算の仕様変更になる。
- M-3: follow-up。per-request settings読込は非効率だが、現時点のcorrectness / security blockerではない。
- M-4: 採用。login 5xxの画面表示と未処理Promise rejectionを回帰テストで再現し、`/app` 5xxがredirectされないroute-level testも追加。
- M-5: 一部採用。`compare_digest`呼び出し確認は維持し、自己比較だけだったtoken hash testを既知SHA-256値の検証へ変更。
- Targeted RED: mixed-case email loginは401、login 5xxはalertなしかつunhandled rejectionを再現。
- Targeted GREEN: backend unit 2 passed、PostgreSQL integration 3 passed、frontend 2 files / 4 tests passed。
- Full gate: backend 59 passed / 0 skipped、frontend 7 files / 15 tests、isort / yapf / Prettier / ESLint / buildすべてexit 0。

## Final review gate（再オープン）

- Critical: 0
- Important: 修正後のfresh review完了まで未確定
- Latest verdict: fresh review待ち（Attempt 5の指摘修正とfull gateは完了）
- Task 7 manual E2E / Task 8 commit: 未実施

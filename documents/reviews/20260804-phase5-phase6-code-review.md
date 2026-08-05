# Phase 5 / Phase 6 実装後コードレビュー (2026-08-04)

## 目的

Phase 7 の上流入力になった Phase 5 / Phase 6 実装後レビューを、リポジトリ内で追跡可能にする。原文は会話上で受領したため、本ファイルでは Phase 7 のスコープ判断に使う High / Medium / Low 指摘を ID 化して要約する。

## 結論

マージブロッカーはない。Phase 5「User Deleted 完全実装」8 条件と Phase 6 の 17 方針は達成され、品質ゲートも全て緑。ただし High 1 件と Medium 複数件はテンプレート配布前の安定化として扱う。

## Phase 7 対象

| ID | 優先度 | 要約 | Phase 7 disposition |
|---|---|---|---|
| U7-1 | High | `DATABASE_URL` に `%` を含むと `backend/alembic/env.py` の `config.set_main_option()` が ConfigParser interpolation で Alembic 起動不能になる。 | Phase 7 Task 1 で修正する。 |
| U7-2 | Medium | `README.md` と `.claude/settings.local.json` は `db-downgrade --revision` を前提にしているが、`backend/manage.py` は positional argument である。 | Phase 7 Task 2 / Task 7 で CLI と docs を揃える。 |
| U7-3 | Medium | `AuthSession.issued_at` ベース expiry は実装済みだが、`created_at` mutation を検出する behavior test がない。 | Phase 7 Task 3 で mutation guard test を追加する。 |
| U7-4 | Medium | Phase 5 migration downgrade は、削除済み email 再登録後に旧 global unique index を再作成できず data-dependent に失敗する。 | Phase 7 Task 4 / Task 7 で明示 error と docs を追加する。 |
| U7-5 | Medium | `mark_user_deleted()` は `deleted_at IS NULL` guard がなく、同時実行 DELETE で `USER_MARKED_DELETED` audit log が二重化し得る。 | Phase 7 Task 5 で repository layer を冪等化する。 |
| U7-6 | Medium | OAuth-only user は session / CSRF token 窃取だけで不可逆削除できる。Phase 6 で意図的に許容したが、テンプレート正典に失敗モードを書くべき。 | Phase 7 Task 6 で docs caveat を追加する。 |
| U7-7 | Medium | `README.md` が品質ゲートや integration test 挙動について root / backend / frontend `AGENTS.md` と矛盾している。 | Phase 7 Task 7 / Task 9 で同期する。 |
| U7-8 | Medium | `/app/settings` の route-specific guard test と、account deletion 失敗時に cache を消さない regression test がない。 | Phase 7 Task 8 で route test を追加する。 |

## Phase 8 以降へ送る項目

- deleted / inactive user 検知時に当該 session だけでなく全 active session を revoke するか。
- revoked token replay で audit log が増え続ける問題。
- revoked だが未 expire の session pruning 方針。
- INET migration の大規模 DB 向け online / batch migration 方針。
- Account deletion の OAuth provider reauthentication、削除猶予期間、restore API。
- Account deletion UI の field-specific 422、stale error clear、429 `Retry-After` 利用、error feedback 共通化。

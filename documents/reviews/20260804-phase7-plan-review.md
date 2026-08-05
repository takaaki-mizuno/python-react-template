# Phase 7 計画レビュー (2026-08-04)

## 目的

`documents/plans/20260804-phase7-review-stabilization.md` の初版に対する Claude Code レビューを、Phase 7 計画の出典として追跡可能にする。原文は Codex attachment として受領したため、本ファイルでは実装計画に必要な指摘を ID 化して要約する。

## 総評

Phase 7 が扱う技術項目の選定は概ね妥当。ただし初版計画には、そのまま実行すると失敗する test、修正前から通る grep、正典より弱い品質ゲート、docs 契約の矛盾が含まれていた。着手前に計画書を改訂し、検証方法を強化する必要がある。

## 指摘 ID

| ID | 優先度 | 要約 | Phase 7 disposition |
|---|---|---|---|
| C7-A | Blocker | Phase 7 の出典レビューが `documents/reviews/` に存在せず、8 項目の根拠と網羅性を第三者が確認できない。 | 本ファイルを追加し、Phase 7 計画に対応表を追加する。 |
| C7-B | Must | Task 5 の unit test は `CapturingSession.exec()` が rowcount=2 固定のため、実装修正後も already-deleted 分岐に入らない。test double 改修を必須ステップ化する。 | Task 5 を改訂する。 |
| C7-C | Must | `mark_user_deleted()` の実リスクは逐次二重 DELETE ではなく同時実行 race。repository 冪等化と account deletion usecase 全体の冪等性を分け、並行 integration test を追加する。 | Task 5 を改訂する。 |
| C7-D | Must | downgrade preflight は offline migration (`--sql`) を壊し得る。offline では preflight DB query を skip し、通常の downgrade SQL は出す。 | Task 4 を改訂する。 |
| C7-E | Must | 20260803_0003 downgrade は email 重複だけでなく `deleted_at`、`issued_at`、`updated_at`、INET 型情報も失う。README / docs で不可逆性を正確に書く。 | Task 4 / Task 7 を改訂する。 |
| C7-F | Must | Task 7.4 / 9.5 の grep は BRE で `|` が効かず、修正前から no matches になる。`rg` または `grep -E` に直す。 | Task 7 / Task 9 を改訂する。 |
| C7-G | Should | Task 1 の dict helper test は `set_main_option()` 復活を検出しない。実 Alembic config に近い regression test と source guard を組み合わせる。helper は Alembic 専用 module に置く。 | Task 1 を改訂する。 |
| C7-H | Must | README / Phase 7 品質ゲートが root `AGENTS.md` より弱く、`db-upgrade`、`db-check`、Docker gate がない。 | Task 7 / Task 9 を改訂する。 |
| C7-I | Must | `mark_user_deleted()` の既存 docs は「常に audit log を作成する」と読める。追記だけでは矛盾が残るため、既存記述を書き換える。 | Task 5 / Task 6 を改訂する。 |
| C7-J | Should | Task 3 は現行実装で PASS する mutation guard であり、TDD の failing test ではない。アサーションも緩い。`issued_at + absolute TTL` の厳密比較にする。 | Task 3 を改訂する。 |
| C7-K | Should | `useAccountDeletion` hook 単体 test は実アプリの QueryCache / MutationCache 経路を通らない。app settings route 側で失敗時 cache 保持を確認する。401 mock は error envelope に揃える。 | Task 8 を改訂する。 |
| C7-L | Should | `db-downgrade --revision` は positional 呼び出しを壊す破壊的 CLI 変更である。Typer の既存 style に合わせ、manual smoke には `DATABASE_URL` と scratch DB 作成手順を書く。 | Task 2 / Task 4 を改訂する。 |
| C7-M | Should | Phase 8 へ送る Low / hardening 項目の受け皿がない。backlog 文書または issue 化が必要。完了条件は grep 可能な語句へ落とす。 | Phase 8 backlog 文書を追加し、Phase 7 計画に参照を追加する。 |

## 検証メモ

- High の Alembic interpolation は現行 `backend/alembic/env.py` の `config.set_main_option()` と `backend/alembic.ini` の `%(here)s` interpolation により再現可能。
- `backend/manage.py` の `db_downgrade()` は positional argument、`db_upgrade()` は default 付き引数のため Typer が option 化している。
- `backend/tests/unit/services/test_auth_repository.py` の `CapturingSession.exec()` は rowcount=2 固定。
- `/app/settings` は `_authenticated` pathless layout 配下にあるため guard 自体は存在する。必要なのは route-specific regression test。

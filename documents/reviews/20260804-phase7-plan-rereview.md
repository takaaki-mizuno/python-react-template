# Phase 7 計画再レビュー (2026-08-04)

## 目的

`documents/plans/20260804-phase7-review-stabilization.md` 改訂版に対する Claude Code 再レビューを ID 化し、最終修正の根拠として残す。

## 結論

13 件中 11 件は実質的に解決済み。着手可能な水準に近いが、`rg` 化に伴う誤検出は Must fix。上流コードレビューの traceability、transaction 内 staleness、scratch DB smoke、語句別 grep、frontend cache assertion は計画に反映すると実行時の失敗を減らせる。

## 指摘 ID

| ID | 優先度 | 要約 | Phase 7 disposition |
|---|---|---|---|
| R7-1 | Must | Task 9.6 の `npm run check$` が `frontend/AGENTS.md` の正しい整形コマンド説明を誤検出し、最終ゲートが必ず失敗する。README 専用 grep に分離する。 | Task 9.6 を修正する。 |
| R7-2 | Should | C7-A は計画レビューの traceability だけで、Phase 5/6 コードレビュー 8 項目の出典が未解決。 | 上流レビューを `documents/reviews/20260804-phase5-phase6-code-review.md` として追加し、Phase 7 に U7 ID 対応表を追加する。 |
| R7-3 | Should | `mark_user_deleted()` の `refresh` 判断が transaction 内の実経路で検証されない。無条件 refresh に決めるか、transaction 内 integration test を追加する。 | Task 5 に transaction 内 integration test と refresh 方針を追加する。 |
| R7-4 | Should | Task 4.4 の scratch DB 作成手順がなく、heredoc が通らない場合の代替がない。 | Task 4.4 に `CREATE DATABASE` と `psql -c` 代替を追加する。 |
| R7-5 | Nit | Step 9.6 の第 2 `rg` は alternation のため全語句の出現を保証しない。語句ごとに分ける。 | Task 9.6 を語句別 `rg` に変更する。 |
| R7-6 | Nit | Step 8.2 は既存 error test と重複し、`queryKeys.auth.me` 保持を検証しない。既存 test に cache seed / assertion を足す方がよい。 | Task 8.2 を既存 test 拡張方針へ変更する。 |
| R7-7 | Nit | Task 1 の source guard は `build_alembic_engine_section` 使用を保証しない。 | Task 1.1 に positive source guard を追加する。 |

## 検証メモ

- `frontend/AGENTS.md` の `npm run check` は「整形」コマンドとして正しい記述であり、削除対象ではない。
- `UnitOfWork.transaction()` 内の `session_scope()` は同一 session を共有する。
- Docker target `runtime` と `backend-dev` は root `Dockerfile` に実在する。

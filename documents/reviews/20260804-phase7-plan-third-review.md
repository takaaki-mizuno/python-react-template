# Phase 7 計画三次レビュー (2026-08-04)

## 目的

`documents/plans/20260804-phase7-review-stabilization.md` 再改訂版に対する Claude Code 三次レビューを ID 化し、最終修正の根拠として残す。

## 結論

R7-2 / R7-4 / R7-5 / R7-6 / R7-7 は解決済み。R7-1 は `npm run check$` だけでなく `TEST_DATABASE_URL.*skip` にも同型の誤検出が残っていたため、negative grep のパターンを誤記だけに寄せる必要がある。transaction 内 refresh guard と一部 unit / frontend test 方針も修正すると実行時の迷いが減る。

## 指摘 ID

| ID | 優先度 | 要約 | Phase 7 disposition |
|---|---|---|---|
| T7-1 | Blocker | `TEST_DATABASE_URL.*skip` が、README に新しく書く正しい「skip ではなく fail」文にも hit する。誤記である `skipされる` だけを探す pattern にする。 | Task 7.4 / Task 9.6 を修正する。 |
| T7-2 | Blocker | `backend/AGENTS.md` の正しい「skip ではなく fail」文も `TEST_DATABASE_URL.*skip` に hit する。negative grep を意味に合わせて分解する。 | Task 9.6 を修正する。 |
| T7-3 | Should | transaction 内 refresh test が同一 session に user を事前 load していないため、`refresh()` を消しても通る。 | Task 5.7 を事前 load 付き test に修正する。 |
| T7-4 | Nit | missing user unit test が、rowcount>0 なのに `session.get()` が None という実 DB で起こりにくい分岐を通る。 | Task 5 に既存 test の `exec_rowcount=0` 更新を追加する。 |
| T7-5 | Nit | Step 8.2 の cache assertion は 1 ケースに限定せず、account deletion API error 全ケースで確認する。 | Task 8.2 を無条件 assertion にする。 |

## 検証メモ

- `rtk rg -n "TEST_DATABASE_URL.*skip|npm run check$|db-downgrade --revision=" README.md backend/AGENTS.md frontend/AGENTS.md documents/references` は、現行 `backend/AGENTS.md` の正しい記述にも hit する。
- `UnitOfWork.transaction()` 内の `session_scope()` は同一 session を共有するため、事前に同じ transaction 内で user を load すれば identity map staleness の guard になる。

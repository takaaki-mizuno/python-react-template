# Phase 8 Hardening Backlog

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:writing-plans` before turning any item in this backlog into an implementation plan. This file is a backlog, not an executable plan.

**Goal:** Phase 7 で意図的に対象外へ送る hardening / UX / security 項目を失わないよう、次フェーズ候補として保持する。

**Architecture:** 各項目は独立した検証単位に分け、実装時は Phase 7 完了後のコードに対して改めて影響範囲、テスト、品質ゲートを定義する。

**Tech Stack:** FastAPI、SQLModel、PostgreSQL、pytest、React、TanStack Router、TanStack Query、Vitest

---

## Backend hardening

- [ ] Revoked session token replay で audit log が無制限に増えないよう、既知 rejected session の監査 throttling を revoked session にも拡張する。
- [ ] deleted / inactive user を認証時に検知した場合、当該 session だけでなく対象 user の全 active session を revoke するかを設計する。
- [ ] `db-prune-auth` または repository pruning が、revoked だが未 expire の session をどう扱うかを明文化し、必要なら削除対象に含める。
- [ ] `delete_expired_sessions()` の名前と実動作が revoked session retention policy と矛盾しないか確認する。
- [ ] INET migration の全行 UPDATE が大規模 DB で重い問題について、online migration 手順または batch migration 方針を追加する。

## Account deletion / OAuth

- [ ] OAuth-only user の削除に provider reauthentication を追加する。
- [ ] Account deletion に削除猶予期間を設けるか、即時不可逆削除を維持するかを派生プロジェクト向けに選択可能にする。
- [ ] Account restore API / admin recovery UI の要否を、削除済み email 再登録後の partial unique index 制約と合わせて設計する。

## Frontend UX / accessibility

- [ ] Account deletion form の空入力 422 を field-specific message として表示する。
- [ ] Account deletion form の入力修正時に stale error 表示を消す。
- [ ] 429 response の `Retry-After` を UI message または disabled duration に反映する。
- [ ] Field に紐づかない 429 / CSRF error で input が `aria-describedby` に error を指す必要があるか再評価する。
- [ ] Login / register / account deletion の destructive or unsafe action errors を共通 feedback component に寄せる。

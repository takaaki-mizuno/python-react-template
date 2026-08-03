# Phase 6 Account Deletion 申し送りメモ

> この文書は実装計画ではなく、Phase 5 から Phase 6 へ送る論点のメモである。後で正式な Phase 6 設計を行う前提で、現時点では実装タスクを定義しない。

## 背景

`documents/plans/20260803-phase5-residual-p2-p3-doc-sync.md` では、User Deleted を backend domain / auth persistence レベルで扱う方針にした。

Phase 5 で扱う User Deleted の範囲は、`users.deleted_at`、`deleted_at IS NULL` filter、認証時の deleted / missing / inactive 判別、既存 session の revoke / audit、email 再登録方針、FK `ON DELETE` 方針までである。

一方、`DELETE /api/auth/me` のような公開 account deletion API は、Phase 5 の「残 P2/P3 とドキュメント同期」という性格を超えるため、Phase 6 に送る。

## 申し送り

- Phase 6 では、公開 API として account deletion を提供するかを最初に判断する。
- 候補 endpoint は `DELETE /api/auth/me`。
- 実装する場合、この endpoint は認証必須かつ CSRF 保護対象にする。
- 成功時は 204 を返し、session cookie と CSRF cookie を clear する設計が候補。
- 削除処理は対象 user の `deleted_at` を設定し、現在の session を含む全 session を revoke する。
- 削除処理は audit log に残す。Phase 5 側の候補 event は `USER_MARKED_DELETED`。
- 削除済み user の古い session が使われた場合は、Phase 5 側の `SESSION_REVOKED_DELETED_USER` と整合させる。
- frontend では account settings UI、削除確認 UI、成功後の logout / redirect 導線が必要になる。

## Phase 6 で必ず決めること

- 削除後も email address を保持するか、匿名化するか。
- 削除済み email の再登録を許可するか。
- 再登録を許可する場合、過去の audit log と新 user をどう区別するか。
- account deletion 前に password 再入力、メール確認、または別の本人確認を要求するか。
- OAuth-only user の削除確認をどう扱うか。
- 削除後の復元を許可するか、不可逆にするか。
- 削除済み user の `is_active` を変更するか、`deleted_at` のみを正とするか。
- audit log に email や user_agent などの個人情報をどこまで残すか。
- sample CRUD など user-owned resource を削除・匿名化・保持のどれにするか。

## Phase 6 まで実装しないこと

- `DELETE /api/auth/me` の route 追加。
- account deletion UI。
- user deletion のメール匿名化。
- user-owned resource の cascade / archive / anonymize 実装。
- password 再入力や OAuth provider re-authentication。


# DB Schema Guideline Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. この計画の実装では、ユーザーが明示するまで `git add` / `git commit` を行わない。

**Goal:** 現在の SQLModel / Alembic schema を `.agents/skills/database-schema-design/SKILL.md` の設計指針へ揃え、未デプロイ前提で初期 migration を 1 本に作り直せる状態にする。

**Architecture:** DB の物理 schema は PostgreSQL / UUID PK / TEXT / business timestamp は BIGINT Unix timestamp / `created_at` と `updated_at` は TIMESTAMPTZ へ統一する。Python domain と public API は既存の `datetime` / ISO 8601 JSON 契約をできる限り保ち、永続化層で BIGINT 変換を吸収する。Alembic は既存の `20260810_0001_initial_schema.py` を置き換え、追加 migration chain は作らない。

**Tech Stack:** FastAPI, SQLModel, SQLAlchemy TypeDecorator, Alembic, PostgreSQL, pytest, React 19, TypeScript, Vitest

---

## 背景

ユーザー指定の設計指針は、DB schema について次を要求している。

- RDBMS は PostgreSQL。
- table 名は複数形、primary key は全 table `id`。
- primary key の型はプロジェクト全体で UUID v4 または BigInt に統一する。
- text column は `VARCHAR` ではなく `TEXT`。
- business timestamp は `BIGINT` の Unix timestamp。
- `created_at` / `updated_at` は例外として `TIMESTAMP` 系を使い、全 table に置く。
- `created_at` / `updated_at` はログ・切り分け用途に限定し、business logic に使わない。
- nullable column は NULL に意味がある場合だけ許容し、理由をコメントで残す。
- FK には必ず index を作る。
- many-to-many relation table でも、project の primary key ルールに従い `id` を持つ。

現在の repository は PostgreSQL / UUID を採用済みで、未適用 migration chain は squash 済みの単一初期 revision `backend/alembic/versions/20260810_0001_initial_schema.py` を正としている。この点は、今回「既存 migration を修正する」のではなく「未デプロイなので初期 migration を作り直す」というユーザー要望と一致している。

一方、現行 schema は設計指針と複数箇所でずれている。主なずれは次のとおり。

| 領域 | 現状 | 指針上の問題 | 方針 |
|---|---|---|---|
| text column | `sa.String(length=...)` / `VARCHAR` が多い | TEXT を使うルールに反する | DB column は `Text` / `sa.Text()` に変更し、長さ制限は Pydantic / config validation で維持する |
| business timestamp | `last_login_at`, `issued_at`, `expires_at`, `deleted_at` などが `DateTime(timezone=True)` | business timestamp は BIGINT Unix timestamp | SQLAlchemy `TypeDecorator` で Python は `datetime`、DB は `BIGINT` にする |
| `created_at` / `updated_at` | 全 table に揃っていない | 全 table に必要 | `auth_audit_logs`, `auth_oidc_authorization_states`, `user_roles` に不足分を追加する |
| `created_at` の業務利用 | `sample_items.created_at` cursor、admin user list sort、`auth_identities.created_at` ordering、audit retention / replay window で使っている | `created_at` / `updated_at` を business logic に使わないルールに反する | business 用 column を追加し、repository / usecase をそちらへ移す |
| `user_roles` PK | `(user_id, role_code)` composite PK | PK column は `id` に統一するルールに反する | `id UUID PK` を追加し、`(user_id, role_code)` は unique index にする |
| FK index | `user_roles.assigned_by_user_id` に index がない | FK には必ず index が必要 | FK column に index を追加する。OIDC state の expected columns は後述の理由で FK ではないため、検索用途が出るまで index は作らない |
| boolean flag | `auth_identities.email_verified` が prefix なし | flag は `is_` / `has_` などの prefix を付ける | DB column は `is_email_verified` へ rename し、provider claim / public code の `email_verified` とは分ける |
| nullable reason | nullable column に DB comment がない | NULL 許容理由をコメントで記述するルールに反する | nullable column に `comment=` を追加し、migration でも反映する |
| timestamp automation | table ごとに `created_at` / `updated_at` の default / onupdate が揃っていない | 自動セット要件が弱い | DB trigger ではなく SQLModel / SQLAlchemy の `default=utcnow` と `onupdate=utcnow` に一本化し、Alembic server default drift を避ける |

## 現行システムとの矛盾・確認結果

- `backend/AGENTS.md` と `documents/references/backend-app-structure.md` は現行 schema の `TIMESTAMPTZ` 前提を多数含む。これは設計指針と矛盾するため、実装時に docs を更新する。
- `documents/plans/20260810-code-managed-authorization.md` と `documents/references/rbac-authorization-operations.md` は `user_roles(user_id, role_code)` 複合 PK 前提で書かれている。code-managed RBAC の方針自体は維持するが、DB shape は `id UUID PK` + unique `(user_id, role_code)` に更新する。
- `documents/plans/20260806-phase8-oauth-oidc-client.md` は `auth_sessions.last_oidc_auth_time_at TIMESTAMPTZ` 前提で書かれている。OAuth/OIDC の業務要件は維持し、column 名と物理型だけを更新する。
- `frontend` は API の `createdAt` / `updatedAt` / `lastLoginAt` を ISO 8601 string として扱っている。DB 物理型を BIGINT にしても public API は `datetime` serialization を維持できるため、フロントエンドの契約は基本的に維持する。
- 既存の `documents/plans/20260810-admin-crud.md` には未完の UI polish 残タスクがあるが、今回の対象は DB schema alignment であり、Admin UI polish は混ぜない。
- `backend/alembic/env.py` は `compare_type=True` と `compare_server_default=True` を有効にしている。migration と SQLModel metadata の server default を厳密に揃えない設計は `db-check` で落ちるため、今回の計画では `created_at` / `updated_at` / business timestamp の DB server default と PostgreSQL `updated_at` trigger を採用しない。既存の boolean flag 用 `server_default` は timestamp 方針とは別に扱う。

## 方針とその理由

### 方針 1: DB は厳密に指針へ寄せ、Python / API 境界は互換性を保つ

`UnixTimestampMillis` のような SQLAlchemy `TypeDecorator` を追加し、Python model field は `datetime` のまま、DB column は `BIGINT` として保存する。

理由:

- 既存 usecase / tests / API schema は `datetime` を前提にしているため、全層を `int` にすると変更範囲が過大になる。
- 指針が求めているのは DB schema の型であり、アプリケーション境界で `datetime` を扱うこととは両立できる。
- PostgreSQL 上では `information_schema.columns.data_type = 'bigint'` で検証できる。

### 方針 2: Unix timestamp は milliseconds を採用する

BIGINT business timestamp は Unix timestamp milliseconds とする。

理由:

- Python `datetime` の sub-second 情報を seconds で丸めると、cursor sort、audit replay window、session expiry 周りで意図しない同値が増える。
- JavaScript / browser API とも相性がよく、BIGINT を採用する意味が seconds より明確である。
- Public API は ISO 8601 string のままなので、frontend に milliseconds 数値を露出しない。
- DB comment には全 business timestamp column で `Unix timestamp in milliseconds.` を明記する。nullable column では NULL の意味も同じ comment に含める。
- Python `datetime` は microseconds 精度だが DB は milliseconds 精度に丸める。TypeDecorator は float を経由せず整数演算で milliseconds へ切り捨て、tests は round-trip 後に下位 3 桁が落ちることを明示する。

### 方針 3: public API の日時 field 名は維持する

DB では `users.registered_at`、`users.modified_at`、`sample_items.registered_at`、`sample_items.modified_at`、`auth_audit_logs.occurred_at` のような business timestamp を追加するが、既存 public response の `createdAt` / `updatedAt` / `lastLoginAt` は互換維持する。たとえば Admin user response の `createdAt` は DB の `registered_at` から、`updatedAt` は DB の `modified_at` から組み立てる。

理由:

- DB 指針準拠のために API 名まで一斉 rename すると、Frontend と test の変更量が増え、今回の目的から外れる。
- `createdAt` は public API としては一般的な表現であり、DB の `created_at` ログ column と同じ意味で扱わない実装にすれば、指針の意図を満たせる。
- `updatedAt` も同様に public API 名として維持するが、DB の `updated_at` ログ column ではなく business timestamp の `modified_at` から返す。これにより `updated_at` を business logic / public contract に使わない指針と矛盾しない。

### 方針 4: `expires_at` は例外的に維持する

`expires_at` は「期限切れ予定時刻」を表す既存契約として維持し、BIGINT 化だけ行う。

理由:

- `expired_at` にすると「実際に期限切れになった時刻」という意味になり、予定時刻である current semantics とずれる。
- 設計指針は過去形の `_at` を推奨しているが、未来の deadline / expiry の命名までは具体例がない。ここは intentional deviation として docs に残す。

### 方針 5: `user_roles` は `id` PK に変更し、assignment uniqueness は unique index で守る

`user_roles` は `id UUID PK` を持たせ、`user_id` / `role_code` は unique index にする。

理由:

- 指針の「primary key は `id`」に合わせるため。
- code-managed RBAC では role catalog が DB にないため、`role_code` は引き続き FK にしない。
- `get_user_role_codes()` など既存 query は `user_id` / `role_code` を使い続けられる。

### 方針 6: 初期 migration を 1 本として作り直す

`backend/alembic/versions/20260810_0001_initial_schema.py` を新 schema に置き換える。新しい revision file は追加しない。

理由:

- この repository は未デプロイで、既存 chain はすでに development-only squash 済み。
- 追加 migration を積むと、未デプロイ schema の歴史を温存するだけで保守コストが増える。
- fresh DB に初期 migration を適用した結果が正である、という template の既存方針と合っている。

### 方針 7: timestamp の source はアプリケーション clock に統一する

`created_at` / `updated_at` / business timestamp はすべて Python 側の `utcnow()` を source of truth にする。migration に `server_default=now()` や `updated_at` trigger は入れない。

理由:

- timestamp の生成元を DB clock と app clock に分けると、同じ row の `created_at` / `registered_at` / `issued_at` などが別 clock 由来になり、テストや運用調査で意味を読み違えやすい。
- `server_default=now()` 自体は SQLModel metadata と migration の両方へ正しく書けば drift しないが、business timestamp の milliseconds epoch default 式は DB 方言依存・表現差分が大きい。timestamp 類はまとめて app clock 管理に寄せ、`db-check` では「timestamp default が存在しない」ことを契約として固定する。
- DB trigger と SQLAlchemy `onupdate=utcnow` を併用すると、timestamp の更新元が DB と Python に分かれ、`updated_at` が logging timestamp なのか business timestamp なのか再び曖昧になる。
- このプロジェクトでは repository が ORM / SQLAlchemy 経由で書き込む前提であり、raw SQL insert / update は timestamp の必須値を明示する運用にする。

## 採用した設計判断・逸脱・トレードオフ

- 設計判断: `created_at` / `updated_at` は全 table に `TIMESTAMPTZ` として残すが、business logic からは参照しない。業務上の登録・発行・発生・削除時刻は別 column に移す。
- 設計判断: `AuthSession.last_oidc_auth_time_at` は `last_oidc_authenticated_at` へ rename する。provider `auth_time` を保存する意味を保ちつつ、日時 column 名をより自然な過去形へ寄せるため。
- 設計判断: `User.last_login_at` と `AuthIdentity.last_login_at` は `last_logged_in_at` へ rename する。public API の `lastLoginAt` は維持する。
- 設計判断: `AuthIdentity.created_at` を linked provider 表示順に使うのをやめ、`linked_at` を追加する。provider identity の link 時刻は business timestamp であり、`created_at` は行作成ログに限定するため。
- 設計判断: `auth_identities.email_verified` は DB column として `is_email_verified` へ rename する。OIDC provider claim の `email_verified` や Python DTO 名は外部仕様に合わせて維持してよいが、DB flag は指針に合わせる。
- 設計判断: `auth_audit_logs.created_at` を audit event の business time として使うのをやめ、`occurred_at` を追加する。retention / replay window / ordering は `occurred_at` を使う。
- 設計判断: `sample_items.created_at` cursor は `sample_items.registered_at` cursor へ移す。public cursor payload の key は既存互換のため `createdAt` を維持してよい。
- 設計判断: public API の `updatedAt` は維持するが、DB の logging column `updated_at` ではなく `users.modified_at` / `sample_items.modified_at` から返す。`modified_at` は admin user profile / role update / logical deletion、および sample item update の business timestamp であり、`updated_at` は ORM が管理する行更新ログに限定する。
- 設計判断: `created_at` と `registered_at` / `linked_at` / `occurred_at` が挿入時に同値になる table があるが、指針どおり business logic で使う timestamp と logging timestamp を分ける。列は増えるが、後から data import や backfill を行う場合にも意味を分離できる。
- 設計判断: `auth_oidc_authorization_states.expected_user_id` と `expected_session_id` は FK にしない。これらは authorization start 時点の security context snapshot であり、session pruning で OIDC state row が CASCADE 削除されると callback failure の分類が変わるため、soft reference として comment だけを付ける。現行 code は `state_hash` で取得した row を Python 側で比較しており、この 2 column を WHERE 句で検索しないため index も作らない。
- 設計判断: `ip_address` は PostgreSQL `INET` のまま維持する。指針の TEXT ルールからの逸脱だが、IP address は自由文ではなくネットワークアドレスであり、既存の `InetString` による正規化・PostgreSQL 型検証を失わない方が安全である。
- 設計判断: Unix timestamp は milliseconds とする。`database-schema-design` skill 本体も Unix timestamp milliseconds を明記済みであり、この計画でも seconds ではなく milliseconds を正とする。
- 逸脱: `expires_at` は過去形ではないが維持する。`expired_at` への rename は意味を変えてしまうため、設計指針の未来時刻命名が未定義な箇所として意図的に残す。
- 逸脱: `ip_address` は `TEXT` ではなく `INET` を維持する。DB comment と docs にこの逸脱を残し、Python model boundary は引き続き `str | None` にする。
- トレードオフ: DB column を BIGINT にしながら Python field を `datetime` に保つため、TypeDecorator のテストが重要になる。永続化層の複雑性は増えるが、API / usecase の変更量を抑えられる。
- トレードオフ: `TEXT` 化により DB 長さ制約は弱くなる。入力長の正は Pydantic request schema、OIDC config validation、role catalog validation に置く。
- トレードオフ: `created_at` / `updated_at` をアプリ clock に統一するため、DB へ raw SQL で直接 insert / update する場合は `id`、`created_at`、`updated_at`、business timestamp の必須値を明示する必要がある。template の repository 経由書き込みを正とし、raw SQL maintenance / seed / integration test では更新者が明示的に値を設定する運用にする。
- トレードオフ: `UnixTimestampMillis` は microseconds を milliseconds へ切り捨てる。永続化後に `session.refresh()` した値は元の `datetime` と完全一致しない可能性があるため、tests は millisecond precision に丸めて比較する。
- トレードオフ: `users.created_at` と `users.registered_at` のように、同じ insert で複数の timestamp default が動く場合でも、別々の `utcnow()` 呼び出しと milliseconds 切り捨てにより値の完全一致は仮定しない。tests は意味ごとに存在・型・順序を検証し、両 column の同値性を要求しない。
- トレードオフ: Admin user list は `users.registered_at, id` で sort するため、初期 schema 作り直しに合わせて `ix_users_registered_at_id` を追加する。現行 `created_at` sort には index がないが、登録順一覧は管理画面の標準導線であり、business timestamp 化のタイミングで query shape に合わせる。
- トレードオフ: `modified_at` を追加すると列数は増えるが、public `updatedAt` を維持しながら DB の `updated_at` を logging timestamp 専用にできる。代替案として public `updatedAt` を `updated_at` のまま返す方法も検討したが、指針の「created_at / updated_at を business logic に使わない」と矛盾し、今後の回帰を招くため採用しない。

## 変更予定ファイル

### Backend model / library

- Modify: `backend/app/libraries/sqlalchemy_types.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/auth_session.py`
- Modify: `backend/app/models/auth_audit_log.py`
- Modify: `backend/app/models/auth_identity.py`
- Modify: `backend/app/models/auth_oidc_state.py`
- Modify: `backend/app/models/sample_item.py`
- Modify: `backend/app/models/authorization.py`
- Modify: `backend/app/models/__init__.py` only if exported names change

### Backend repository / usecase / schemas

- Modify: `backend/app/interfaces/services/auth_repository_interface.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/app/services/sample_item_repository.py`
- Modify: `backend/app/services/admin_user_repository.py`
- Modify: `backend/app/services/authorization_repository.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/usecases/oauth_oidc_usecase.py`
- Modify: `backend/app/usecases/account_deletion_usecase.py`
- Modify: `backend/app/usecases/sample_item_usecase.py`
- Modify: `backend/app/usecases/admin_user_usecase.py`
- Modify: `backend/app/models/auth_context.py`
- Modify: `backend/app/models/admin_user.py`
- Modify: `backend/app/models/admin_user_schemas.py`
- Modify: `backend/app/models/sample_item_schemas.py`
- Modify: `backend/app/libraries/auth_session_issuer.py`
- Modify: `backend/manage.py`

### Migration

- Replace in place: `backend/alembic/versions/20260810_0001_initial_schema.py`

### Backend tests

- Modify: `backend/tests/unit/libraries/test_sqlalchemy_types.py`
- Modify: `backend/tests/unit/models/test_auth_models.py`
- Modify: `backend/tests/unit/models/test_metadata.py`
- Modify: `backend/tests/unit/models/test_sample_item.py`
- Modify: `backend/tests/unit/models/test_admin_user.py`
- Modify: `backend/tests/unit/services/test_auth_repository.py`
- Modify: `backend/tests/unit/services/test_sample_item_repository.py`
- Modify: `backend/tests/unit/services/test_admin_user_repository.py`
- Modify: `backend/tests/unit/services/test_authorization_repository.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_usecase.py`
- Modify: `backend/tests/unit/usecases/test_sample_item_usecase.py`
- Modify: `backend/tests/unit/usecases/test_admin_user_usecase.py`
- Modify: `backend/tests/integration/test_auth_schema.py`
- Modify: `backend/tests/integration/test_migration_consistency.py`
- Modify: `backend/tests/integration/services/test_auth_repository.py`
- Modify: `backend/tests/integration/services/test_sample_item_repository.py`
- Modify: `backend/tests/integration/services/test_authorization_repository.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/tests/integration/test_auth_oidc_controller.py`
- Modify: `backend/tests/integration/test_sample_item_controller.py`
- Modify: `backend/tests/integration/test_admin_user_controller.py`
- Modify: `backend/tests/integration/test_manage_cli.py`

### Frontend tests / docs

- Modify: `frontend/src/lib/adminUsersApi.test.ts`
- Modify: `frontend/src/components/organisms/AdminUsers/AdminUsersPage.test.tsx`
- Modify only if API response changes unexpectedly: `frontend/src/lib/adminUsersApi.ts`
- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/references/rbac-authorization-operations.md`
- Modify: `README.md`
- Add addendum only if necessary: historical plans that currently say `TIMESTAMPTZ` or composite `user_roles` PK

## 具体的なタスク

### Task 0: 実装前の安全確認

- [x] `rtk git status --short` を実行し、既存差分を確認する。現時点では `.agents/skills/database-schema-design/SKILL.md` と `.claude/skills/database-schema-design/SKILL.md` に既存の未コミット差分があるため、実装時に触らない。
- [x] `AGENTS.md`、`backend/AGENTS.md`、`frontend/AGENTS.md` を読み直す。
- [x] `.agents/skills/database-schema-design/SKILL.md` を読み直し、この計画の「逸脱」に書いた箇所以外は指針を優先する。
- [x] `documents/plans/20260811-db-schema-guideline-alignment.md` を読み、今回の実装対象を DB schema alignment に限定する。
- [x] `git add` / `git commit` はユーザーが明示するまで実行しない。
- [x] worktree は作らず、現在のブランチで作業する。
- [x] 作業量が多いため、Task ごとに `rtk git diff --stat` と `rtk git diff --name-only` を確認し、意図しないファイル変更が混ざっていないことを確認する。worktree を使わない前提なので、途中で止める場合もユーザー差分を巻き戻さない。

### Task 1: BIGINT Unix timestamp 型を追加する

- [x] `backend/tests/unit/libraries/test_sqlalchemy_types.py` に `UnixTimestampMillis` のテストを追加する。
- [x] テストでは `datetime(2026, 8, 11, 1, 2, 3, 456000, tzinfo=UTC)` が DB bind 時に `1786410123456` のような millisecond integer になり、result value から同じ UTC aware `datetime` に戻ることを検証する。
- [x] microsecond が millisecond 未満の値を持つ `datetime(2026, 8, 11, 1, 2, 3, 456789, tzinfo=UTC)` は `1786410123456` に切り捨てられ、result value は `456000` microseconds になることを検証する。
- [x] naive `datetime` を bind した場合は `ValueError("UnixTimestampMillis requires timezone-aware datetime")` を投げることを検証する。
- [x] `None` は nullable column 用に `None` のまま roundtrip することを検証する。
- [x] `backend/app/libraries/sqlalchemy_types.py` に `UnixTimestampMillis(TypeDecorator[datetime | None])` を実装する。`impl = BigInteger`、`cache_ok = True` とする。
- [x] `process_bind_param()` は aware datetime を UTC に正規化し、float を経由せず `EPOCH = datetime(1970, 1, 1, tzinfo=UTC)` との差分から整数演算で milliseconds を返す。実装は `delta = value.astimezone(UTC) - EPOCH`、`delta // timedelta(milliseconds=1)` を使う。
- [x] `process_result_value()` は DB integer を `EPOCH + timedelta(milliseconds=value)` で UTC aware `datetime` に戻す。float division は使わない。
- [x] `cd backend && uv run pytest tests/unit/libraries/test_sqlalchemy_types.py -q` を実行し、PASS を確認する。

### Task 2: schema 指針を unit tests に固定する

- [x] `backend/tests/unit/models/test_metadata.py` に、全 table が `id` primary key を持つことを検証する test を追加する。ただし SQLModel metadata に table として存在しない DTO は対象外にする。
- [x] `backend/tests/unit/models/test_metadata.py` の `test_authorization_table_shape_matches_plan` を更新し、`user_roles.c.role_code` が `Text` / `sa.Text` で length を持たないこと、`user_roles.primary_key.columns.keys() == ["id"]`、`user_roles` に unique index `uq_user_roles_user_id_role_code` があること、`ix_user_roles_assigned_by_user_id` があることを期待する。既存の `role_code.type.length == 64` 期待値は削除し、role code の長さ制約は `backend/app/config/authorization.py` 側の validation で守る。
- [x] `backend/tests/unit/models/test_metadata.py` に、全 table が `created_at` と `updated_at` を持ち、両方が timezone-aware `DateTime` であることを検証する test を追加する。
- [x] `backend/tests/unit/models/test_metadata.py` に、nullable column の `comment` が空ではないことを検証する test を追加する。対象 column は手書き list にせず、`for table in SQLModel.metadata.tables.values(): for column in table.c: if column.nullable: assert column.comment` のように metadata から導出する。これにより `auth_audit_logs.user_id` / `session_id` などの追加漏れも検出する。
- [x] `backend/tests/unit/models/test_metadata.py` に、全 business timestamp column の `comment` に `Unix timestamp in milliseconds.` が含まれることを検証する test を追加する。対象 column は手書き list にせず、`isinstance(column.type, UnixTimestampMillis)` または dialect wrapper を考慮した helper で metadata から導出する。`created_at` / `updated_at` は `DateTime` なので対象外にする。
- [x] `backend/tests/unit/models/test_metadata.py` に、FK column が index または unique index の leading column で cover されていることを検証する test を追加する。少なくとも `user_roles.assigned_by_user_id` を明示的に検証する。OIDC state expected columns は FK ではないため、この test ではなく soft reference 専用 test で検証する。
- [x] `backend/tests/unit/models/test_metadata.py` に、`auth_oidc_authorization_states.expected_user_id` と `expected_session_id` は FK を持たない soft reference であり、comment を持つが index は持たないことを検証する test を追加する。`ix_auth_oidc_states_expected_user_id`, `ix_auth_oidc_states_expected_session_id`, `ix_auth_oidc_authorization_states_expected_user_id`, `ix_auth_oidc_authorization_states_expected_session_id` が存在しないことも検証する。
- [x] `backend/tests/unit/models/test_metadata.py` に、`auth_sessions.ip_address` と `auth_audit_logs.ip_address` が引き続き `InetString` / PostgreSQL `INET` であることを検証し、この計画の意図的逸脱を固定する。
- [x] `backend/tests/unit/models/test_auth_models.py` の `test_auth_datetime_columns_are_timezone_aware` を更新し、`created_at` / `updated_at` だけが `DateTime(timezone=True)` で、business timestamp は `UnixTimestampMillis` であることを期待する。
- [x] `backend/tests/unit/models/test_auth_models.py` に、`users.registered_at`, `users.modified_at`, `users.last_logged_in_at`, `users.deleted_at`, `auth_sessions.issued_at`, `auth_sessions.last_seen_at`, `auth_sessions.expires_at`, `auth_sessions.revoked_at`, `auth_sessions.last_oidc_authenticated_at`, `auth_audit_logs.occurred_at`, `auth_identities.linked_at`, `auth_identities.last_logged_in_at` が `UnixTimestampMillis` であることを追加する。
- [x] `backend/tests/unit/models/test_auth_models.py` に、`auth_identities` の boolean flag column が `is_email_verified` であり、`email_verified` column は存在しないことを検証する。
- [x] `backend/tests/unit/models/test_sample_item.py` に、`sample_items.registered_at` が `UnixTimestampMillis` であり、cursor 用 dataclass が `registered_at` を持つことを期待する。
- [x] `cd backend && uv run pytest tests/unit/models/test_metadata.py tests/unit/models/test_auth_models.py tests/unit/models/test_sample_item.py -q` を実行し、現行実装で FAIL することを確認する。

### Task 3: SQLModel table を設計指針へ揃える

- [x] `backend/app/models/user.py` の text columns を `Text` に変更する。`email`, `password_hash` が対象。
- [x] `backend/app/models/user.py` の nullable `password_hash` に `comment=` を追加する。comment は「NULL means the user can authenticate only through external identity providers.」のように、パスワード認証情報が存在しない意味を明示する。
- [x] `backend/app/models/user.py` に `registered_at: datetime = Field(sa_column=Column(UnixTimestampMillis(), nullable=False, default=utcnow, comment="Unix timestamp in milliseconds. Business registration time."))` を追加する。
- [x] `backend/app/models/user.py` の `__table_args__` に `Index("ix_users_registered_at_id", "registered_at", "id")` を追加し、Admin user list の `registered_at DESC, id DESC` sort を支える。PostgreSQL btree の backward scan で DESC order に対応するため、明示的な desc expression index にはしない。
- [x] `backend/app/models/user.py` の `last_login_at` を `last_logged_in_at` に rename し、`UnixTimestampMillis(nullable=True)` にする。DB comment は「Unix timestamp in milliseconds. NULL means the user has never completed a login.」にする。
- [x] `backend/app/models/user.py` の `deleted_at` を `UnixTimestampMillis(nullable=True)` にする。DB comment は「Unix timestamp in milliseconds. NULL means the user is not logically deleted.」にする。
- [x] `backend/app/models/user.py` の `created_at` / `updated_at` は `DateTime(timezone=True)` のまま、`default=utcnow` と `onupdate=utcnow` を設定する。`server_default` は設定しない。
- [x] `backend/app/models/auth_session.py` の `session_token_hash`, `csrf_token_hash`, `user_agent` を `Text` にする。
- [x] `backend/app/models/auth_session.py` の `issued_at`, `last_seen_at`, `expires_at`, `revoked_at`, `last_oidc_auth_time_at` を `UnixTimestampMillis` に変更し、`last_oidc_auth_time_at` は `last_oidc_authenticated_at` へ rename する。
- [x] `backend/app/models/auth_session.py` の business timestamp columns に `Unix timestamp in milliseconds.` を含む `comment=` を追加する。nullable な `revoked_at` は「NULL means the session has not been revoked.」、`last_oidc_authenticated_at` は「NULL means no fresh OIDC authentication has been recorded for this session.」を含める。
- [x] `backend/app/models/auth_session.py` の nullable columns に `comment=` を追加する。`ip_address` は「NULL means the client IP could not be determined or should not be stored. Stored as PostgreSQL INET by intentional schema-guideline deviation.」、`user_agent` は「NULL means the request did not include a user agent.」にする。
- [x] `backend/app/models/auth_audit_log.py` に `occurred_at: datetime` を追加し、既存 event occurrence / retention / replay logic はこの column へ移す。
- [x] `backend/app/models/auth_audit_log.py` に `updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow))` を追加する。`server_default` は設定しない。
- [x] `backend/app/models/auth_audit_log.py` の `event_type`, `user_agent` を `Text` にする。
- [x] `backend/app/models/auth_audit_log.py` の `occurred_at` comment は「Unix timestamp in milliseconds. Business occurrence time of the audit event.」にする。
- [x] `backend/app/models/auth_audit_log.py` の nullable columns に `comment=` を追加する。`user_id` / `session_id` は SET NULL 後にも audit row を残すため nullable であることを書く。`ip_address` には PostgreSQL `INET` を維持する意図的逸脱も書く。
- [x] `backend/app/models/auth_identity.py` の `provider_id`, `provider_subject`, `email` を `Text` にする。
- [x] `backend/app/models/auth_identity.py` の nullable `email` に `comment=` を追加する。comment は「NULL means the identity provider did not return an email address.」のように、provider identity に email が無い意味を明示する。
- [x] `backend/app/models/auth_identity.py` の `email_verified` を `is_email_verified` に rename し、DB column も `is_email_verified` にする。OIDC provider claim や `OidcClaims.email_verified` は外部仕様名なので維持する。
- [x] `backend/app/models/auth_identity.py` に `linked_at: datetime = Field(sa_column=Column(UnixTimestampMillis(), nullable=False, default=utcnow, comment="Unix timestamp in milliseconds. Business time when the provider identity was linked."))` を追加する。
- [x] `backend/app/models/auth_identity.py` の `last_login_at` を `last_logged_in_at` に rename し、`UnixTimestampMillis(nullable=True)` にする。comment は「Unix timestamp in milliseconds. NULL means the identity has never completed a login.」にする。
- [x] `backend/app/models/auth_oidc_state.py` の text columns を `Text` にする。
- [x] `backend/app/models/auth_oidc_state.py` の `expires_at` と `consumed_at` を `UnixTimestampMillis` にする。
- [x] `backend/app/models/auth_oidc_state.py` に `updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow))` を追加する。`server_default` は設定しない。
- [x] `backend/app/models/auth_oidc_state.py` の `expires_at` / `consumed_at` comment に `Unix timestamp in milliseconds.` を含める。`consumed_at` には「NULL means the state has not been consumed.」も含める。
- [x] `backend/app/models/auth_oidc_state.py` の `expected_user_id` と `expected_session_id` は FK にしない。authorization start 時点の security context snapshot として comment だけを追加し、`index=True` や `Index(...)` は設定しない。現行 lookup は `state_hash` 経由であり、この 2 column を検索条件に使わないため index は不要である。
- [x] `backend/app/models/auth_oidc_state.py` の nullable `login_hint` に `comment=` を追加する。comment は「NULL means no login hint was provided to the authorization request.」のように、OIDC authorization request に hint が無い意味を明示する。
- [x] `backend/app/models/sample_item.py` の `title`, `description` を `Text` にする。
- [x] `backend/app/models/sample_item.py` の nullable `description` に `comment=` を追加する。comment は「NULL means the item has no description.」のように、説明未設定の意味を明示する。
- [x] `backend/app/models/sample_item.py` に `registered_at: datetime = Field(sa_column=Column(UnixTimestampMillis(), nullable=False, default=utcnow, comment="Unix timestamp in milliseconds. Business registration time used for cursor ordering."))` を追加し、cursor / list ordering 用 timestamp とする。
- [x] `backend/app/models/sample_item.py` の composite index を `Index("ix_sample_items_owner_user_id_registered_at_id", "owner_user_id", "registered_at", "id")` へ変更する。
- [x] `backend/app/models/authorization.py` の `UserRole` に `id: UUID = Field(default_factory=uuid4, primary_key=True)` を追加する。
- [x] `backend/app/models/authorization.py` の `role_code` は `Text(nullable=False)` にし、primary key から外す。
- [x] `backend/app/models/authorization.py` の `assigned_at` は `UnixTimestampMillis(nullable=False, default=utcnow)` にする。comment は「Unix timestamp in milliseconds. Business time when the role was assigned.」にする。
- [x] `backend/app/models/authorization.py` の nullable `assigned_by_user_id` に `comment=` を追加する。comment は「NULL means the role was assigned by a system process or bootstrap operation.」のように、操作者 user が存在しない意味を明示する。
- [x] `backend/app/models/authorization.py` に `created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow))` と `updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow))` を追加する。`server_default` は設定しない。
- [x] `backend/app/models/authorization.py` の `__table_args__` は `Index("uq_user_roles_user_id_role_code", "user_id", "role_code", unique=True)`, `Index("ix_user_roles_role_code", "role_code")`, `Index("ix_user_roles_assigned_by_user_id", "assigned_by_user_id")` にする。
- [x] `cd backend && uv run pytest tests/unit/models/test_metadata.py tests/unit/models/test_auth_models.py tests/unit/models/test_sample_item.py -q` を実行し、model metadata tests の PASS を確認する。

### Task 4: repository / usecase / domain を新 column 名へ追従する

- [x] `backend/app/interfaces/services/auth_repository_interface.py` の `last_login_at` / `provider_auth_time` / `auth_time` 関連 docstring または引数名を見直し、DB column rename と混同しないようにする。引数型は `datetime` のままでよい。
- [x] `backend/app/services/auth_repository.py` の `record_user_login()` は `User.last_logged_in_at` を更新する。`User.updated_at` には business time を代入しない。
- [x] `backend/app/services/auth_repository.py` の `record_oidc_login()` は `AuthIdentity.last_logged_in_at` と `AuthSession.last_oidc_authenticated_at` を更新する。
- [x] `backend/app/services/auth_repository.py` の `record_oidc_reauth()` は `AuthSession.last_oidc_authenticated_at` を更新する。
- [x] `backend/app/services/auth_repository.py` の `find_identities_by_user_id()` は `order_by(col(AuthIdentity.linked_at), col(AuthIdentity.id))` を使う。`AuthIdentity.created_at` は linked provider 表示順に使わない。
- [x] `backend/app/services/auth_repository.py` の `find_active_session_by_token_hash()` は `AuthSession.expires_at > now` の比較を維持する。`UnixTimestampMillis` が Python `datetime` として比較できることを unit / integration test で確認する。
- [x] `backend/app/services/auth_repository.py` の `mark_user_deleted()` は `User.deleted_at` と `User.modified_at` を更新し、`AuthAuditLog.occurred_at=deleted_at` を明示する。`User.updated_at` には business time を代入しない。
- [x] `backend/app/services/auth_repository.py` の `delete_audit_logs_created_before()` は interface も含めて `delete_audit_logs_occurred_before()` に rename する。CLI option `--audit-logs-before` は互換維持し、内部だけ `occurred_at` 基準へ移す。
- [x] `backend/app/services/auth_repository.py` の rejected session replay aggregate lookup は `AuthAuditLog.occurred_at` を使う。
- [x] `backend/app/services/auth_repository.py` の `record_rejected_session_replay()` で作る `AuthAuditLog(created_at=replayed_at)` を `AuthAuditLog(occurred_at=replayed_at)` に置き換える。lookup / ordering も `occurred_at` にする。
- [x] `backend/app/services/auth_repository.py` の `mark_user_deleted()` で作る `AuthAuditLog(created_at=deleted_at)` を `AuthAuditLog(occurred_at=deleted_at)` に置き換える。
- [x] `backend/app/libraries/auth_session_issuer.py` は `create_session(created_at=issued_at, issued_at=issued_at, ...)` のうち `created_at` 引数を渡さない形へ変更する。`created_at` は logging column default、`issued_at` は business timestamp として分ける。
- [x] `backend/app/interfaces/services/auth_repository_interface.py` と `backend/app/services/auth_repository.py` の `create_session()` signature から `created_at: datetime` を削除する。tests / fakes も同じ signature に更新する。
- [x] `backend/app/usecases/oauth_oidc_usecase.py` の `AuthOidcState(created_at=now, ...)` は `created_at` を渡さず、必要な business timestamp は `expires_at` だけ明示する。
- [x] `backend/app/usecases/auth_usecase.py`, `backend/app/usecases/oauth_oidc_usecase.py`, `backend/app/usecases/authorization_usecase.py`, `backend/app/usecases/admin_user_usecase.py`, `backend/manage.py`, `backend/app/services/auth_repository.py` にある `AuthAuditLog(created_at=...)` をすべて `AuthAuditLog(occurred_at=...)` に置き換える。該当 grep は `rtk rg -n "AuthAuditLog\\(|created_at=" backend/app backend/tests` で確認する。
- [x] `backend/app/services/auth_repository.py` の `create_audit_log()` では、呼び出し元が `occurred_at` を明示していない場合だけ model default の `utcnow()` が使われるようにする。既存の業務時刻を渡す呼び出し元では必ず `occurred_at` を明示する。
- [x] `backend/app/services/auth_repository.py` の OIDC state consume / prune は `expires_at` / `consumed_at` の `UnixTimestampMillis` columns をそのまま比較する。
- [x] `backend/app/services/sample_item_repository.py` の ordering / cursor filter を `SampleItem.registered_at` へ変更する。
- [x] `backend/app/models/sample_item.py` の `SampleItemCursor` を `registered_at: datetime` に変更する。
- [x] `backend/app/usecases/sample_item_usecase.py` の cursor encode / decode は DB 内部名 `registered_at` を使う。ただし cursor payload key は既存互換のため `createdAt` のまま維持してよい。
- [x] `backend/app/models/sample_item_schemas.py` の response `created_at` は `item.registered_at` から作る。
- [x] `backend/app/services/admin_user_repository.py` の list sort は `User.registered_at.desc(), User.id.desc()` へ変更する。
- [x] `backend/app/models/admin_user_schemas.py` の `created_at` response は `record.user.registered_at` から作る。
- [x] `backend/app/models/admin_user_schemas.py` の `last_login_at` response は `record.user.last_logged_in_at` から作る。
- [x] `backend/app/models/admin_user.py` の dataclass / tests が `last_logged_in_at` を使うようにする。ただし public API alias は `lastLoginAt` のまま維持する。
- [x] `backend/app/usecases/account_deletion_usecase.py` の OAuth-only freshness 判定は `auth_context.session.last_oidc_authenticated_at` を読む。
- [x] `backend/app/models/auth_context.py` に含まれる session/user references が renamed fields を参照する test を更新する。
- [x] `backend/app/services/oidc_provider_client.py` と `backend/app/usecases/oauth_oidc_usecase.py` は provider claim / DTO の `email_verified` 名を維持しつつ、`AuthIdentity` 作成時は `is_email_verified=claims.email_verified` を渡す。
- [x] `backend/app/services/auth_repository.py` と tests は `AuthIdentity.is_email_verified` を参照する。DB column / model attribute として `email_verified` は使わない。
- [x] `backend/app/services/authorization_repository.py` は `UserRole.id` 追加後も `get_user_role_codes()`, `replace_user_roles()`, `delete_roles_for_user()` の外部契約を変えない。insert 時は `UserRole(user_id=..., role_code=..., assigned_at=utcnow(), assigned_by_user_id=...)` で `id` は default に任せる。
- [x] `backend/manage.py` の `db-prune-auth` は repository method rename に合わせる。CLI option 名と user-facing help は `--audit-logs-before` のまま維持する。
- [x] `cd backend && uv run pytest tests/unit/services/test_auth_repository.py tests/unit/services/test_sample_item_repository.py tests/unit/services/test_admin_user_repository.py tests/unit/services/test_authorization_repository.py -q` を実行し、PASS を確認する。
- [x] `cd backend && uv run pytest tests/unit/usecases/test_auth_usecase.py tests/unit/usecases/test_oauth_oidc_usecase.py tests/unit/usecases/test_account_deletion_usecase.py tests/unit/usecases/test_sample_item_usecase.py tests/unit/usecases/test_admin_user_usecase.py -q` を実行し、PASS を確認する。

### Task 5: 初期 migration を 1 本に作り直す

- [x] `backend/alembic/versions/20260810_0001_initial_schema.py` を新 schema に合わせて置き換える。新 revision file は追加しない。
- [x] migration の `upgrade()` は table 作成順を `users` -> `auth_sessions` -> `auth_audit_logs` -> `sample_items` -> `auth_identities` -> `auth_oidc_authorization_states` -> `user_roles` にする。FK 依存があるためこの順序を守る。
- [x] すべての table に `id UUID primary key`, `created_at TIMESTAMPTZ NOT NULL`, `updated_at TIMESTAMPTZ NOT NULL` を置く。`created_at` / `updated_at` に migration-level `server_default` は付けない。
- [x] `auth_audit_logs` など実質 append-only の table にも `updated_at` を置く。replay aggregate のように更新される row があるため、append-only と決めつけて省略しない。
- [x] business timestamp columns は `sa.BigInteger()` にする。`registered_at`, `modified_at`, `linked_at`, `last_logged_in_at`, `deleted_at`, `issued_at`, `last_seen_at`, `expires_at`, `revoked_at`, `last_oidc_authenticated_at`, `occurred_at`, `consumed_at`, `assigned_at` が対象。
- [x] business timestamp columns に migration-level `server_default` は付けない。`registered_at`, `linked_at`, `occurred_at`, `assigned_at` も SQLModel / repository の app-side `default=utcnow` または明示引数で必ず値を入れる。
- [x] text columns は `sa.Text()` にする。hash / code / email / provider subject / redirect path / user agent も DB 物理型は `TEXT` に統一する。
- [x] nullable column には NULL の意味を含む `comment=` を設定する。migration 上でも `sa.Column(..., comment="...")` を使う。
- [x] business timestamp column には nullable / non-nullable を問わず `Unix timestamp in milliseconds.` を含む `comment=` を設定する。
- [x] `auth_sessions.ip_address` と `auth_audit_logs.ip_address` は `postgresql.INET()` のままにし、comment に「Stored as PostgreSQL INET by intentional schema-guideline deviation.」を含める。
- [x] `users` の partial unique index は `uq_users_email_lower_active` を維持し、where は `deleted_at IS NULL` のままにする。`deleted_at` が BIGINT になっても NULL semantics は変えない。
- [x] `users` は Admin user list の sort 用に `ix_users_registered_at_id` を作る。旧 `created_at` sort には index が無かったが、business timestamp へ移すタイミングで query shape に合わせる。
- [x] `auth_sessions` は `uq_auth_sessions_session_token_hash`, `ix_auth_sessions_user_id`, `ix_auth_sessions_expires_at` を作る。
- [x] `auth_audit_logs` は `ix_auth_audit_logs_user_id`, `ix_auth_audit_logs_session_id`, `ix_auth_audit_logs_event_type`, `ix_auth_audit_logs_occurred_at` を作る。旧 `ix_auth_audit_logs_created_at` は作らない。
- [x] `sample_items` は `ix_sample_items_owner_user_id` と `ix_sample_items_owner_user_id_registered_at_id` を作る。旧 `ix_sample_items_owner_user_id_created_at_id` は作らない。
- [x] `auth_identities` は `uq_auth_identities_provider_subject` と `ix_auth_identities_user_id` を作る。
- [x] `auth_identities` は `is_email_verified` column を作り、`email_verified` column は作らない。
- [x] `auth_identities` は `linked_at BIGINT NOT NULL` を作り、comment に `Unix timestamp in milliseconds.` を含める。`linked_at` に migration-level `server_default` は付けない。
- [x] `auth_oidc_authorization_states` は `uq_auth_oidc_states_state_hash`, `ix_auth_oidc_states_expires_at`, `ix_auth_oidc_states_consumed_at` を作る。`expected_user_id` / `expected_session_id` の FK constraint は作らず、`ix_auth_oidc_states_expected_user_id` / `ix_auth_oidc_states_expected_session_id` も作らない。
- [x] `user_roles` は `pk_user_roles(id)`, `uq_user_roles_user_id_role_code`, `ix_user_roles_role_code`, `ix_user_roles_assigned_by_user_id` を作る。`uq_user_roles_user_id_role_code` は `sa.UniqueConstraint` ではなく `op.create_index(op.f("uq_user_roles_user_id_role_code"), "user_roles", ["user_id", "role_code"], unique=True)` で作り、SQLModel の `Index(..., unique=True)` と一致させる。
- [x] PostgreSQL trigger function は追加しない。`updated_at` は SQLModel / SQLAlchemy `onupdate=utcnow` に任せ、business time の explicit repository assignment には使わない。
- [x] `downgrade()` は indexes -> tables の順に落とす。trigger / trigger function drop は不要。
- [x] Alembic naming convention と `op.f(...)` の使用を維持し、constraint 名が deterministic になるようにする。
- [x] `cd backend && uv run pytest tests/unit/test_alembic_config.py tests/unit/test_alembic_env.py -q` を実行し、PASS を確認する。

### Task 6: schema integration tests を新 schema に更新する

- [x] `backend/tests/integration/test_auth_schema.py` の `test_auth_expiry_columns_are_timezone_aware` を置き換え、business timestamp columns が `bigint` であることを検証する。
- [x] `backend/tests/integration/test_auth_schema.py` に、`created_at` / `updated_at` が全 table で `timestamp with time zone` であることを検証する test を追加する。
- [x] `backend/tests/integration/test_auth_schema.py` に、nullable columns の PostgreSQL column comment が存在することを検証する test を追加する。
- [x] `backend/tests/integration/test_auth_schema.py` に、business timestamp columns の PostgreSQL column comment に `Unix timestamp in milliseconds.` が含まれることを検証する test を追加する。
- [x] `backend/tests/integration/test_auth_schema.py` に、`user_roles` が `id` PK と unique `(user_id, role_code)` を持つことを検証する test を追加する。
- [x] `backend/tests/integration/test_auth_schema.py` に、FK indexes が存在することを検証する test を追加する。
- [x] `backend/tests/integration/test_auth_schema.py` に、business timestamp columns と `created_at` / `updated_at` に DB server default が存在しないことを検証する test を追加する。`compare_server_default=True` の `db-check` を安定させるための契約である。
- [x] `backend/tests/integration/test_auth_schema.py` に、`auth_oidc_authorization_states.expected_user_id` / `expected_session_id` は comment を持つが FK constraint と index を持たないことを検証する test を追加する。short name と naming convention name のどちらの index も存在しないことを確認する。
- [x] `backend/tests/integration/test_auth_schema.py` に、`auth_identities.is_email_verified` が存在し、`auth_identities.email_verified` が存在しないことを検証する test を追加する。
- [x] `backend/tests/integration/test_auth_schema.py` に、`auth_sessions.ip_address` と `auth_audit_logs.ip_address` が `inet` 型のままであり、comment に意図的逸脱が書かれていることを検証する test を追加する。
- [x] `backend/tests/integration/services/test_auth_repository.py` の `last_login_at` / `last_oidc_auth_time_at` / audit ordering / pruning 期待値を `last_logged_in_at` / `last_oidc_authenticated_at` / `occurred_at` に更新する。
- [x] `backend/tests/integration/services/test_auth_repository.py` の `AuthIdentity.created_at` ordering 期待値を `linked_at` ordering に更新する。
- [x] `backend/tests/integration/services/test_auth_repository.py` の persisted `datetime` equality は millisecond precision に丸めて比較する。`UnixTimestampMillis` は microseconds 下位 3 桁を切り捨てるため、`session.refresh()` 後の値と元の `datetime` は完全一致しない場合がある。
- [x] `backend/tests/integration/services/test_sample_item_repository.py` の ordering 期待値を `registered_at` に更新する。
- [x] `backend/tests/integration/services/test_authorization_repository.py` は `UserRole.id` 追加後も role assignment behavior が変わらないことを確認する。
- [x] `backend/tests/integration/test_auth_controller.py`, `test_auth_oidc_controller.py`, `test_admin_user_controller.py`, `test_sample_item_controller.py`, `test_manage_cli.py` の raw SQL を新 column 名と新物理型へ更新する。`now()` を BIGINT business timestamp column へ直接入れない。たとえば `expires_at`, `revoked_at`, `deleted_at`, `consumed_at`, `assigned_at` へ直接 SQL で値を入れる場合は、Unix timestamp milliseconds の integer literal / bind parameter を使う。
- [x] `backend/tests/integration/test_manage_cli.py` の `INSERT INTO user_roles` は、`id`, `created_at`, `updated_at`, `assigned_at`, `assigned_by_user_id` をすべて明示する。`id` は UUID bind、`created_at` / `updated_at` は `TIMESTAMPTZ` bind、`assigned_at` は Unix timestamp milliseconds の integer bind にする。旧 `VALUES (..., now(), NULL)` は型不一致と NOT NULL 欠落で失敗するため使わない。
- [x] local dev DB を使っている場合は、旧 `20260810_0001` stamp 済み schema が残るため作り直す。保持対象データがなければ `docker compose down` 後に `rm -rf docker/postgres/data` を実行し、`docker compose up -d postgres` で fresh DB を用意する。保持対象データがある場合はこの計画を止め、未デプロイ前提が崩れていないかユーザーに確認する。
- [x] fresh test DB を用意する。既存 `app_test` を使い回さず、drop / recreate または test DB volume の再作成を行ってから `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-upgrade` を実行する。
- [x] 同じ DB で `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-check` を実行し、schema drift がないことを確認する。
- [x] `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_schema.py tests/integration/test_migration_consistency.py -q -ra` を実行し、PASS を確認する。

### Task 7: public API と Frontend 契約の回帰を防ぐ

- [x] `backend/tests/unit/models/test_admin_user.py` で `AdminUserResponse` / `AdminUserListItemResponse` が引き続き `createdAt`, `updatedAt`, `lastLoginAt` を返すことを検証する。
- [x] `backend/tests/unit/models/test_sample_item.py` で `SampleItemResponse.createdAt` が `item.registered_at` 由来であることを検証する。
- [x] `backend/tests/integration/test_admin_user_controller.py` で Admin user list response の `createdAt` と `lastLoginAt` が ISO 8601 string であることを検証する。
- [x] `backend/tests/integration/test_sample_item_controller.py` で sample item response の `createdAt` / `updatedAt` が ISO 8601 string であることを検証する。
- [x] `frontend/src/lib/adminUsersApi.test.ts` と `frontend/src/components/organisms/AdminUsers/AdminUsersPage.test.tsx` を実行し、API field 名変更が不要であることを確認する。
- [x] Frontend 側の source は変更しない方針で進める。`frontend` tests が API response 契約変更を示して失敗した場合は、その時点で実装を止め、public API 互換を保つ backend mapping を先に修正する。
- [x] `cd frontend && npm test -- adminUsersApi.test.ts AdminUsersPage.test.tsx` を実行し、PASS を確認する。

### Task 8: docs を新 schema 契約へ更新する

- [x] `AGENTS.md` のセキュリティ / RBAC / DB schema 記述を更新し、`user_roles` が `id UUID PK` + unique `(user_id, role_code)` であることを書く。
- [x] `backend/AGENTS.md` に、DB schema guideline alignment 後の timestamp ルールを書く。`created_at` / `updated_at` は TIMESTAMPTZ、business timestamp は `UnixTimestampMillis` / DB BIGINT とする。
- [x] `backend/AGENTS.md` に、timestamp source はアプリケーション clock に統一し、DB server default / `updated_at` trigger は採用しないことを書く。
- [x] `backend/AGENTS.md` に、business timestamp は Unix timestamp milliseconds であり、DB comment に単位を必ず書くことを追加する。
- [x] `backend/AGENTS.md` の `AuthSession.issued_at` / `last_oidc_auth_time_at` 記述を `last_oidc_authenticated_at` に更新する。
- [x] `backend/AGENTS.md` に、`ip_address` columns は PostgreSQL `INET` を維持する意図的逸脱であることを書く。
- [x] `documents/references/backend-app-structure.md` の Auth Persistence / OAuth/OIDC / Sample CRUD / Admin CRUD sections を更新する。
- [x] `documents/references/rbac-authorization-operations.md` の DB table section を `user_roles(id, user_id, role_code, assigned_at, assigned_by_user_id, created_at, updated_at)` に更新する。
- [x] `README.md` の `db-prune-auth` 説明を、audit log pruning は `auth_audit_logs.occurred_at` 基準、expired session pruning は `auth_sessions.expires_at` BIGINT 基準であるように更新する。
- [x] historical plan docs は本文を書き換えない。必要な addendum は次の4ファイルの末尾にだけ追加する: `documents/plans/20260418-auth-db-migration.md`, `documents/plans/20260806-phase8-oauth-oidc-client.md`, `documents/plans/20260810-code-managed-authorization.md`, `documents/plans/20260810-admin-crud.md`。文面は「現行 schema は `documents/plans/20260811-db-schema-guideline-alignment.md` の DB schema alignment 方針を優先する」とする。
- [x] `rtk rg -n "last_oidc_auth_time_at|last_login_at|email_verified|AuthIdentity\\.created_at|auth_identities\\.created_at|TIMESTAMPTZ|timestamptz|PRIMARY KEY \\(user_id, role_code\\)|ix_auth_audit_logs_created_at|owner_user_id_created_at_id|ix_auth_oidc_states_expected_|ix_auth_oidc_authorization_states_expected_|server_default=|set_updated_at|updated_at trigger" AGENTS.md backend/AGENTS.md README.md documents/references documents/plans backend/app backend/tests frontend/src` を実行する。
- [x] grep hit を確認し、historical plan と意図的な互換名以外に古い schema 契約が残っていないことを確認する。`server_default=` は `users.is_active`, `sample_items.is_completed`, `auth_identities.is_email_verified` など boolean flag の正当な default も拾うため、timestamp default / trigger の残存確認として判定する。

### Task 9: Backend 品質ゲートを実行する

- [x] `cd backend && uv run ruff check .` を実行し、PASS を確認する。
- [x] `cd backend && uv run isort . --check-only` を実行し、PASS を確認する。
- [x] `cd backend && uv run yapf -dr app/ tests/ alembic/ manage.py` を実行し、差分なしまたは必要な format 差分を確認する。
- [x] `cd backend && uv run mypy app manage.py` を実行し、PASS を確認する。
- [x] `cd backend && uv run pytest tests/unit -q` を実行し、PASS を確認する。
- [x] PostgreSQL が利用できる状態で、既存 `app_test` を drop / recreate して fresh DB に戻す。Task 6 で head になった DB に対する no-op `db-upgrade` は gate として扱わない。
- [x] fresh DB に対して `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-upgrade` を実行し、PASS を確認する。
- [x] 同じ DB で `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration -q -ra` を実行し、PASS を確認する。
- [x] 同じ DB で `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-check` を実行し、PASS を確認する。

### Task 10: Frontend と Docker の品質ゲートを実行する

- [x] `cd frontend && npm run check:ci` を実行し、PASS を確認する。
- [x] `cd frontend && npm test` を実行し、PASS を確認する。
- [x] `cd frontend && npm run build` を実行し、PASS を確認する。
- [x] `docker compose config` を実行し、PASS を確認する。
- [x] `docker build --target runtime -t python-react-template-runtime .` を実行し、PASS を確認する。
- [x] `docker build --target backend-dev -t python-react-template-backend-dev .` を実行し、PASS を確認する。

### Task 11: 最終差分確認

- [x] `rtk git diff --stat` を実行し、変更範囲がこの計画の想定ファイルに収まっていることを確認する。
- [x] `rtk git diff -- backend/alembic/versions/20260810_0001_initial_schema.py` を確認し、初期 migration が 1 本として作り直されていることを確認する。
- [x] `rtk git diff --name-only` を確認し、`.agents/skills/database-schema-design/SKILL.md` と `.claude/skills/database-schema-design/SKILL.md` の既存ユーザー差分を誤って変更していないことを確認する。
- [x] `git add` / `git commit` を実行していないことを確認する。
- [x] 完了報告には、実行した検証コマンド、未実行の検証があれば理由、migration を squash 初期 revision として作り直したことを含める。

### Task 12: Claude Code レビュー指摘への追加対応

- [x] `backend/manage.py` の `db-prune-auth --help` で audit log pruning の基準が `created_at` ではなく `occurred_at` と表示されるように修正する。
- [x] `backend/tests/integration/test_auth_schema.py::test_oidc_expected_context_columns_are_soft_references` の FK 不在検証を `constraint_column_usage` ではなく `table_constraints` + `key_column_usage` へ変更し、子 table 側の FK を正しく検出できるようにする。
- [x] `backend/tests/unit/models/test_sample_item.py` で `registered_at` / `created_at` / `modified_at` / `updated_at` に別々の値を入れ、`SampleItemResponse.createdAt` が `registered_at`、`updatedAt` が `modified_at` 由来であることを検証する。
- [x] `backend/tests/unit/models/test_admin_user.py` で `registered_at` / `created_at` / `modified_at` / `updated_at` に別々の値を入れ、Admin user response の `createdAt` / `updatedAt` が logging timestamp に依存しないことを検証する。
- [x] `backend/tests/unit/models/test_metadata.py` に `String` かつ `Text` でない textual column を禁止する metadata test を追加する。
- [x] `backend/tests/integration/test_auth_schema.py` に DB 実体で `character varying` / `character` が存在しないことを確認する schema test を追加する。
- [x] `backend/tests/unit/test_business_timestamp_usage.py` を追加し、`backend/app/services` / `backend/app/usecases` で `created_at` / `updated_at` を `Attribute` または `update(...).values(...)` keyword として使う回帰を禁止する。
- [x] `backend/app/models/user.py` と `backend/app/models/sample_item.py` に `modified_at` business timestamp を追加し、public `updatedAt` は `modified_at` から返す。`updated_at` は logging / troubleshooting timestamp として残す。
- [x] `backend/app/services/auth_repository.py` の `record_user_login()` / `record_oidc_login()` / `mark_user_deleted()` から business time の `updated_at` 代入を取り除く。logical deletion は `deleted_at` と `modified_at` を更新する。
- [x] `backend/app/services/admin_user_repository.py` は admin user 更新時に `users.modified_at` を更新する。role-only update も public user management record の変更として `modified_at` を更新する。
- [x] `backend/app/services/sample_item_repository.py` は sample item 更新時に `sample_items.modified_at` を更新する。
- [x] `backend/app/services/auth_repository.py` の linked identity sort を `linked_at, id` にし、audit replay aggregation の latest sort を `occurred_at DESC, id DESC` にする。
- [x] `backend/tests/unit/services/test_auth_repository.py` に linked identity sort と audit replay latest sort の SQL assertion を追加する。
- [x] `backend/tests/integration/timestamp_helpers.py` を追加し、test 用 Unix timestamp milliseconds 変換は `UnixTimestampMillis().process_bind_param()` を使う。
- [x] `backend/tests/integration/test_manage_cli.py` / `test_admin_user_controller.py` / `test_auth_controller.py` の test-only BIGINT timestamp bind を shared helper 経由にする。
- [x] `documents/plans/20260811-db-schema-guideline-alignment.md` の milliseconds 記述を、Skill 本体が milliseconds 明記済みである前提へ更新する。
- [x] 追加対応でも新規 migration file は作らず、`backend/alembic/versions/20260810_0001_initial_schema.py` の 1 本だけを更新する。

### Task 13: Claude Code 再レビュー指摘への追加対応

- [x] `modified_at` に `onupdate=utcnow` を付ける案は採用しない。理由は、`User.modified_at` に `onupdate` を付けると login による `last_logged_in_at` 更新でも public `updatedAt` が動き、`updatedAt` を profile / role / logical deletion の変更時刻として扱う設計と衝突するため。
- [x] `backend/tests/unit/services/test_sample_item_repository.py` に、sample item update が `sample_items.modified_at` を更新する regression test を追加する。
- [x] `backend/tests/unit/services/test_admin_user_repository.py` に、admin user update が `users.modified_at` を更新する regression test を追加する。
- [x] `backend/tests/unit/services/test_auth_repository.py` に、logical deletion update SQL が `users.modified_at` を更新する regression assertion を追加する。
- [x] `backend/tests/integration/test_authorization_controller.py` に、`PUT /api/admin/users/{id}/roles` が role 専用経路でも `users.modified_at` を更新する regression test を追加する。
- [x] `backend/app/services/authorization_repository.py` で role assignment に実変更がある場合、同じ変更時刻で `users.modified_at` を更新する。`assigned_at` と `modified_at` は同じ `utcnow()` 呼び出し由来にして、監査時の読み違いを減らす。
- [x] `backend/tests/integration/test_auth_controller.py` に、login は `last_logged_in_at` を更新するが `users.modified_at` は更新しない regression test を追加する。
- [x] `backend/tests/unit/test_business_timestamp_usage.py` の guard 対象に `backend/app/libraries/auth_session_issuer.py` と `backend/manage.py` を追加する。
- [x] `backend/tests/unit/test_business_timestamp_usage.py` の failure message に、`created_at` / `updated_at` は logging timestamp であり `registered_at` / `modified_at` / `occurred_at` / `expires_at` などの business timestamp を使うべきことを明記する。
- [x] `backend/AGENTS.md` に、`registered_at` / `modified_at` / `created_at` / `updated_at` / `last_logged_in_at` / `deleted_at` の使い分けを書く。
- [x] `documents/references/backend-app-structure.md` に、login では public `updatedAt` は動かず、login activity は `lastLoginAt` で表現することを書く。

## Review checklist

- [x] 全 table の primary key が `id` である。
- [x] primary key の型が全 table UUID v4 で統一されている。
- [x] DB text columns が `TEXT` である。
- [x] business timestamp columns が DB 上 `BIGINT` である。
- [x] business timestamp columns の DB comment に `Unix timestamp in milliseconds.` が含まれている。
- [x] `created_at` / `updated_at` が全 table に存在し、`TIMESTAMPTZ` である。
- [x] `created_at` / `updated_at` を business logic の sort / retention / expiry / deletion 判定に使っていない。
- [x] `created_at` / `updated_at` を business logic で使わないことを静的テストで継続的に検証している。
- [x] `created_at` / `updated_at` と business timestamp columns に DB server default がない。
- [x] PostgreSQL `updated_at` trigger を作っていない。
- [x] nullable columns に NULL の意味を説明する DB comment がある。
- [x] FK columns が index または leading unique index で cover されている。
- [x] `user_roles` が `id UUID PK` と unique `(user_id, role_code)` を持つ。
- [x] code-managed RBAC の catalog は DB に戻っていない。
- [x] `auth_identities.is_email_verified` が存在し、`email_verified` DB column は存在しない。
- [x] `auth_sessions.ip_address` / `auth_audit_logs.ip_address` は意図的逸脱として PostgreSQL `INET` を維持し、docs / comments に理由がある。
- [x] `auth_oidc_authorization_states.expected_user_id` / `expected_session_id` は FK と index を持たず、soft reference として comment を持つ。
- [x] `auth_audit_logs.occurred_at` が audit ordering / retention / replay window の基準になっている。
- [x] milliseconds 精度で同値になり得る business timestamp ordering には `id` tie-breaker がある。
- [x] すべての `AuthAuditLog(created_at=...)` 呼び出しが `AuthAuditLog(occurred_at=...)` に置換されている。
- [x] `sample_items.registered_at` が cursor ordering の基準になっている。
- [x] `auth_identities.linked_at` が linked provider ordering の基準になっている。
- [x] Admin user list sort が `users.registered_at` 基準になっている。
- [x] `UnixTimestampMillis` は float を使わず整数演算で milliseconds を保存し、microseconds は millisecond precision に切り捨てられる。
- [x] public API の `createdAt` / `updatedAt` / `lastLoginAt` は必要に応じて互換維持されている。
- [x] public API の `createdAt` / `updatedAt` は DB の `created_at` / `updated_at` ではなく business timestamp 由来であることを単体テストで検証している。
- [x] `modified_at` を手動更新する write path は regression test で保護されている。
- [x] role 専用 endpoint と admin user PATCH のどちらで role を変更しても `users.modified_at` が更新される。
- [x] login activity は `last_logged_in_at` を更新し、`modified_at` は更新しないことを regression test と docs で固定している。
- [x] `backend/alembic/versions/20260810_0001_initial_schema.py` 以外に新規 migration file を作っていない。
- [x] fresh DB で `db-upgrade` / integration tests / `db-check` が通る。
- [x] docs が新 schema 契約へ更新されている。

## 実装結果メモ

- 実装では、既存 `app_test` が旧 `20260810_0001` schema で stamp 済みだったため、保持データを壊さないように `app_schema_alignment_20260811` という専用 fresh DB を新規作成して migration / integration / `db-check` を検証した。既存 `app_test` の drop / recreate は行っていない。
- `uv run` はこの sandbox で `/Users/takaaki/.cache/uv` へのアクセス拒否、および macOS `system-configuration` 周りの panic が発生したため、検証は既存 `.venv/bin/python` / `.venv/bin/ruff` / `.venv/bin/isort` / `.venv/bin/yapf` / `.venv/bin/mypy` で実行した。これは依存 lock や実行対象を変える判断ではなく、ローカル環境制約を回避するための実行経路変更である。
- DB 接続を伴う Python integration / `manage.py db-check` / `manage.py db-upgrade` は sandbox から localhost TCP 接続が拒否されたため、承認付きで実行した。
- `npm run build` は `backend/static/` を出力先にするが、今回の実行後に追跡差分は発生していない。
- `git add` / `git commit` は実行していない。

## 実行した検証

- `PYTHONPYCACHEPREFIX=backend/.cache/pycache backend/.venv/bin/python -m pytest tests/unit -q`: 498 passed, 1 warning.
- `TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5432/app_schema_alignment_20260811 backend/.venv/bin/python -m pytest tests/integration -q -ra`: 147 passed, 15 warnings.
- `DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5432/app_schema_alignment_20260811 backend/.venv/bin/python manage.py db-upgrade`: success.
- `DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5432/app_schema_alignment_20260811 backend/.venv/bin/python manage.py db-check`: `No new upgrade operations detected.`
- `backend/.venv/bin/ruff check .`: pass.
- `backend/.venv/bin/isort . --check-only`: pass.
- `backend/.venv/bin/yapf -dr app/ tests/ alembic/ manage.py`: 差分なし。
- `PYTHONPYCACHEPREFIX=backend/.cache/pycache backend/.venv/bin/mypy app manage.py`: success.
- `frontend npm run check:ci`: pass.
- `frontend npm test`: 29 files / 167 tests passed.
- `frontend npm run build`: pass. `%VITE_SITE_URL%` 未定義 warning は既存の Vite HTML env warning として出力された。
- `docker compose config`: pass.
- `docker build --target runtime -t python-react-template-runtime .`: pass.
- `docker build --target backend-dev -t python-react-template-backend-dev .`: pass.

## 2026-08-11 Claude Code レビュー対応後の実装結果メモ

- Claude Code レビューの指摘を再検証し、CLI help、OIDC soft reference FK 検証、public timestamp 由来検証、TEXT guard、`created_at` / `updated_at` business logic guard、public `updatedAt` の business timestamp 化、milliseconds 同値時の ordering tie-breaker、test timestamp helper 共有化を追加対応した。
- public `updatedAt` は API 互換名として維持し、DB の `updated_at` ではなく `users.modified_at` / `sample_items.modified_at` から返す設計に変更した。これにより `updated_at` は logging / troubleshooting 用の `TIMESTAMPTZ` として残し、business logic から参照しない。
- `modified_at` 追加に伴う schema 変更は、未デプロイ前提どおり新規 migration file を作らず、`backend/alembic/versions/20260810_0001_initial_schema.py` の初期 migration 1 本へ反映した。
- review 後の fresh DB 検証では、既存 DB を壊さないため `app_schema_alignment_review_20260811_codex` を新規作成して `db-upgrade` / integration tests / `db-check` を実行した。
- `git add` / `git commit` は実行していない。`git diff --cached --name-only` は空である。

## 2026-08-11 Claude Code レビュー対応後に実行した検証

- `cd backend && rtk uv run ruff check .`: pass.
- `cd backend && rtk uv run isort . --check-only`: pass.
- `cd backend && rtk uv run yapf -dr app/ tests/ alembic/ manage.py`: 差分なし。途中で format 差分を検出したため、`rtk uv run yapf -ir app/ tests/ alembic/ manage.py` を実行して反映済み。
- `cd backend && rtk uv run mypy app manage.py`: success.
- `cd backend && rtk uv run pytest tests/unit -q`: 502 passed, 1 warning.
- `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5432/app_schema_alignment_review_20260811_codex rtk uv run python manage.py db-upgrade`: success.
- `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5432/app_schema_alignment_review_20260811_codex rtk uv run python manage.py db-check`: `No new upgrade operations detected.`
- `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5432/app_schema_alignment_review_20260811_codex rtk uv run pytest tests/integration -q -ra`: 148 passed, 15 warnings.
- integration tests 後に同じ DB で `db-check` を再実行し、`No new upgrade operations detected.` を確認した。
- `rtk rg --files backend/alembic/versions`: `backend/alembic/versions/20260810_0001_initial_schema.py` の 1 件のみ。

## 2026-08-11 Claude Code 再レビュー対応後の実装結果メモ

- `modified_at` は `onupdate=utcnow` にせず、write path が明示的に更新する設計を維持した。`User.modified_at` に `onupdate` を付けると login 時の `last_logged_in_at` 更新でも public `updatedAt` が動くため、`updatedAt` を profile / role / logical deletion の変更時刻として扱う設計と矛盾する。
- `sample_items.modified_at`、admin user update の `users.modified_at`、logical deletion の `users.modified_at`、role 専用 endpoint の `users.modified_at` を regression tests で固定した。
- `PUT /api/admin/users/{id}/roles` は role assignment に実変更がある場合、`user_roles.assigned_at` と同じ `utcnow()` 由来の値で `users.modified_at` を更新するようにした。これで admin user PATCH 経由と role 専用 endpoint 経由の挙動を揃えた。
- login は `last_logged_in_at` を更新するが `modified_at` は更新しないことを integration test と docs で固定した。public `updatedAt` は最終活動時刻ではなく、管理対象情報の最終変更時刻として扱う。
- business timestamp guard の対象に `backend/app/libraries/auth_session_issuer.py` と `backend/manage.py` を追加し、failure message に logging timestamp ではなく business timestamp を使うべき理由を明記した。
- `backend/AGENTS.md` に user / sample item の timestamp 使い分けを追加した。
- `git add` / `git commit` は実行していない。

## 2026-08-11 Claude Code 再レビュー対応後に実行した検証

- `cd backend && rtk uv run ruff check .`: pass.
- `cd backend && rtk uv run isort . --check-only`: pass.
- `cd backend && rtk uv run yapf -dr app/ tests/ alembic/ manage.py`: 差分なし。
- `cd backend && rtk uv run mypy app manage.py`: success.
- `cd backend && rtk uv run pytest tests/unit -q`: 502 passed, 1 warning.
- `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5432/app_schema_alignment_review_20260811_codex rtk uv run pytest tests/integration -q -ra`: 149 passed, 15 warnings.
- `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5432/app_schema_alignment_review_20260811_codex rtk uv run python manage.py db-check`: `No new upgrade operations detected.`

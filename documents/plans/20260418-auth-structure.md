# 認証基盤 + PostgreSQL 導入設計（2026-04-18）

## 1. 目的

このテンプレート（FastAPI + React）に対し、**本番運用を見据えた認証基盤**を段階導入できるようにする。
今回の計画は、次を満たすことをゴールにする。

- PostgreSQL を正式な永続層として導入する
- 認証方式（セッション/JWT）を比較したうえで、現実的な運用設計を選ぶ
- FastAPI / React で破綻しにくい構成（マイグレーション、秘密鍵管理、監査ログ、将来のOIDC連携）を最初から織り込む
- 実装時に迷わない粒度まで、タスク・順序・論点を明文化する

---

## 2. 現状と設計上の前提

- Backend は FastAPI（Python 3.12, `uv` ベース）
- 既存依存に `sqlmodel` はあるが、実運用の認証機能（ユーザー、セッション、トークン失効、監査）に必要な設計は未実装
- Frontend は React + Vite（SPA）
- まだ DB の本格導入・migration 運用が始まっていない

このため、認証導入は「ログインAPI追加」ではなく、以下を同時に設計する必要がある。

1. データモデル（users / sessions / refresh tokens / audit logs）
2. 署名鍵・秘密情報のライフサイクル
3. クライアント（SPA）との安全なトークン配送方法
4. 将来の SSO（OIDC）拡張余地

---

## 3. 最新ベストプラクティス調査（要点）

本計画は、できるだけ一次情報（公式ドキュメント / RFC / OWASP）に寄せて判断した。

### 3.1 FastAPI の認証実装方針

- FastAPI 公式の JWT チュートリアルは、パスワードハッシュに `pwdlib` + Argon2 を推奨している。
- JWT は「署名されるが暗号化されない」ため、ペイロードに機微情報を入れない設計が必須。

### 3.2 パスワードハッシュ

- OWASP Password Storage Cheat Sheet は Argon2id を第一候補として推奨。
- bcrypt はレガシー互換用途としては有効だが、新規標準は Argon2id で統一する方が妥当。

### 3.3 OAuth/OIDC 系の現在地

- OAuth 2.0 Security BCP（RFC 9700, 2025年1月）は、トークン管理・クライアント設計・リダイレクト周りの強化を明確化。
- JWT Access Token プロファイル（RFC 9068）では、JWT種別の明確化（ID TokenとAccess Tokenの混同防止）が重視される。

### 3.4 PostgreSQL のID戦略

- PostgreSQL 18 では `uuidv7()` が公式サポートされたため、時系列局所性を持つ UUID 採用が現実的。
- 既存環境が PG18 未満の場合は `gen_random_uuid()`（v4）で開始し、将来移行可能な抽象化を作る。

### 3.5 設定管理

- Pydantic Settings（v2系）で環境変数管理を統一し、鍵・DSN・Cookie設定を型付きで扱う。

---

## 4. 今回採用する推奨アーキテクチャ

## 4.1 全体像

- **認証方式**: 「短命 Access Token + 長命 Refresh Token（ローテーション）」
- **配送**: Refresh Token は HttpOnly + Secure Cookie、Access Token はメモリ保持（必要時のみ）
- **永続化**: PostgreSQL にユーザー/認証関連テーブルを集約
- **失効管理**: Refresh Token は DB で一意管理（ハッシュ保存）し、再利用検知を実施
- **将来拡張**: OIDCログイン（Google / Azure AD 等）を `auth_identities` で追加可能に

> 理由: SPA と API の組み合わせで、localStorage 長期保存よりも Cookie + ローテーションのほうが漏えい耐性と運用性のバランスが良い。

## 4.2 ライブラリ選定（Backend）

### 必須

- `SQLAlchemy 2.x` + `alembic`
  - 認証まわりの複雑クエリ・マイグレーション運用を考えると、ORM本体は SQLAlchemy 2 系に寄せる
- `asyncpg`
  - FastAPI の async ハンドラに合わせる
- `pydantic-settings`
  - 環境変数を型安全に扱う
- `pwdlib[argon2]`
  - FastAPI 公式方針に合わせる
- `PyJWT[crypto]` または `authlib`
  - まずは自前JWT発行で `PyJWT`、将来 OIDC/Federation を強めるなら `authlib` を追加

### オプション（要件次第）

- `redis`
  - 高トラフィック時の失効リストキャッシュ、レート制御、OTP 試行回数管理
- `fastapi-users`
  - 早期立ち上げには有効。ただしドメイン要件が濃くなると抽象化を外すコストあり

## 4.3 ライブラリ選定（Frontend）

- 認証状態管理は React Query + アプリ専用 Auth Store（軽量）
- Access Token を永続ストレージに保存しない（再読み込み時は refresh endpoint で再取得）
- 401 応答時の再試行（1回）を共通HTTPクライアントで処理

---

## 5. データモデル設計（PostgreSQL）

## 5.1 最小テーブル

1. `users`
- `id` (uuid, PK)
- `email` (citext推奨, unique)
- `password_hash` (nullable: OIDC専用アカウントを許容)
- `is_active`, `is_verified`
- `created_at`, `updated_at`, `last_login_at`

2. `auth_refresh_tokens`
- `id` (uuid, PK)
- `user_id` (FK)
- `token_hash` (unique) ※生トークンは保存しない
- `issued_at`, `expires_at`, `revoked_at`
- `rotated_from_token_id` (自己参照, 連鎖追跡)
- `user_agent`, `ip_address`（監査用途）

3. `auth_sessions`（任意だが推奨）
- デバイス単位の論理セッションを管理
- 「全端末ログアウト」「特定端末無効化」を実装しやすくする

4. `auth_audit_logs`
- login_success / login_failed / token_refresh / logout / password_changed などを記録

5. `auth_identities`（将来の OIDC 用）
- `provider`（google, azuread等）
- `provider_subject`（sub claim）
- `user_id` への紐付け

## 5.2 インデックス方針

- `users(email)` unique
- `auth_refresh_tokens(token_hash)` unique
- `auth_refresh_tokens(user_id, revoked_at, expires_at)` 複合
- 監査ログは `created_at` で時系列検索最適化

## 5.3 ID方針

- 初期: UUID（v4 または v7）
- PG18 利用時: `uuidv7()` を第一候補
- 重要なのは「外部公開IDと内部参照IDの分離可否」を先に決めること

---

## 6. 認証/認可フロー詳細

## 6.1 ログイン

1. email + password 受領
2. Argon2id で検証
3. Access Token（短命: 5〜15分）発行
4. Refresh Token（長命: 7〜30日）発行
5. Refresh Token は **生値をCookie**、DBには `hash(token)` のみ保存

## 6.2 リフレッシュ

1. Cookie から refresh token 取得
2. DB のハッシュ照合 + 失効/期限確認
3. 問題なければ「旧トークン失効 + 新トークン発行」（ローテーション）
4. 旧トークン再利用を検知したら、そのセッション系列を全失効（盗難対策）

## 6.3 ログアウト

- 単一端末ログアウト: 現在 refresh token を失効
- 全端末ログアウト: user_id の有効refresh tokenを一括失効

## 6.4 認可

- 初期は RBAC（`roles`, `user_roles`）で十分
- 将来 ABAC が必要なら claim + policy engine（例: Oso/Casbin）へ拡張

---

## 7. API I/F（初期セット）

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `POST /api/auth/logout-all`
- `GET /api/auth/me`
- `POST /api/auth/password/change`

エラー設計は最初に統一する（認証失敗時のメッセージを出し分けすぎない）。

---

## 8. セキュリティ設計の必須事項

1. Cookie 設定
- `HttpOnly`, `Secure`, `SameSite=Lax`（クロスサイト要件があるときのみ `None; Secure`）

2. 鍵管理
- JWT 秘密鍵/秘密情報は `.env` 直書きで固定しない
- 開発は `.env`、本番は Secret Manager（クラウドKMS連携）
- 鍵ローテーションを前提に `kid` を持てる設計が望ましい

3. パスワード
- Argon2id
- パスワード再設定トークンは短命・単回利用

4. 防御
- ログイン試行回数制限（IP + アカウント）
- CSRF 対策（Cookie方式時）
- 監査ログの保持

5. 可観測性
- 認証イベントを構造化ログで出力（trace_id, user_id, event_type）

---

## 9. 実装タスク分解（Do フェーズ）

## Phase 0: 基盤準備
- [ ] `docker-compose` に PostgreSQL サービス追加
- [ ] backend に DB 接続設定（`pydantic-settings`）導入
- [ ] SQLAlchemy 2 + Alembic の土台作成

## Phase 1: ユーザーと認証テーブル
- [ ] `users` / `auth_refresh_tokens` / `auth_audit_logs` の migration 作成
- [ ] リポジトリ層実装（user取得・token管理）

## Phase 2: 認証ユースケース
- [ ] register/login/refresh/logout/logout-all 実装
- [ ] password hash/verify を `pwdlib` で統一
- [ ] refresh token ローテーション + 再利用検知実装

## Phase 3: フロント統合
- [ ] Auth API クライアント実装
- [ ] 401 時リフレッシュ再試行
- [ ] ログイン状態復元（初回 `me` 取得）

## Phase 4: セキュリティ・運用
- [ ] レート制御（ミドルウェア）
- [ ] 監査ログ整備
- [ ] 鍵ローテーション手順書作成

## Phase 5: 品質ゲート
- [ ] backend: `uv run pytest`
- [ ] frontend: `npm run check`
- [ ] frontend: `npm run build`
- [ ] frontend: `npm run test`

---

## 10. 議論の観点（レビューで揉めやすい点）

## 10.1 自前認証 vs 外部IdP（Auth0/Clerk/Cognito等）

- 自前認証の利点: コスト制御、データ制御、カスタマイズ性
- 欠点: セキュリティ運用責務が増える
- 判断基準: チームのセキュリティ運用体制・監査要件・多要素認証の必要度

## 10.2 JWT をクライアントのどこに保持するか

- localStorage は実装が楽だが XSS 耐性が弱い
- 本設計は Cookie + 短命Access の折衷（実装コストと安全性のバランス）

## 10.3 ORM を SQLModel 継続するか SQLAlchemy 2 に寄せるか

- SQLModel は単純 CRUD には速い
- 認証基盤は migration / index / 複雑クエリ / トランザクション制御が増えるため、SQLAlchemy 2 へ寄せるほうが長期運用で安定

## 10.4 UUID 戦略（v4/v7/bigint）

- v7 は時系列局所性で有利
- ただし DB バージョンや既存運用との整合が優先
- 「将来 v7 に切替可能な抽象化」を先に作るのが安全

## 10.5 Refresh Token の保存先（DBのみ / Redis併用）

- 初期は DB のみで可
- 高負荷になったら Redis キャッシュを追加（ただし真正性ソースは DB）

---

## 11. なぜこの設計に至ったか（意思決定ログ）

1. **公式・標準準拠を優先**
   - FastAPI 公式の `pwdlib[argon2]` 推奨
   - OWASP の Argon2id 推奨
   - OAuth2 Security BCP（RFC 9700）反映

2. **テンプレート導入コストを現実的に抑制**
   - いきなり外部IdPを必須にせず、自前認証で最小構成を先に作る
   - ただし `auth_identities` を先に用意して、後から OIDC を差し込める形にする

3. **SPA の脅威モデルに合わせる**
   - 「永続ストレージに長命トークンを置かない」を基本線にした
   - refresh token ローテーションと再利用検知を初期要件に含めた

4. **将来の拡張と破壊的変更コストを下げる**
   - migration 前提（Alembic）
   - イベント監査・鍵ローテーション・セッション単位失効を最初から設計

---

## 12. 推奨する次アクション（Act）

1. この計画をレビューし、以下の2点を先に合意する
   - 自前認証で開始するか、初期から外部IdPを採用するか
   - PG バージョン（18を使うか、既存事情で17以下にするか）

2. 合意後、次の実装計画を分割作成する
   - `20260418-auth-db-migration.md`（DBとAlembic）
   - `20260418-auth-backend-flow.md`（register/login/refresh/logout）
   - `20260418-auth-frontend-integration.md`（React統合）

3. 先に最低限のPoCを作り、運用要件（同時ログイン数、監査保持期間、MFA時期）を早期確定する

---

## 参考（一次情報）

- FastAPI Security: OAuth2 + JWT  
  https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- OWASP Password Storage Cheat Sheet  
  https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- RFC 9700: Best Current Practice for OAuth 2.0 Security（2025-01）  
  https://www.rfc-editor.org/rfc/rfc9700
- RFC 9068: JWT Profile for OAuth 2.0 Access Tokens  
  https://datatracker.ietf.org/doc/html/rfc9068
- SQLAlchemy AsyncIO Docs  
  https://docs.sqlalchemy.org/20/orm/extensions/asyncio.html
- PostgreSQL UUID Functions（uuidv7含む）  
  https://www.postgresql.org/docs/current/functions-uuid.html
- Pydantic Settings  
  https://docs.pydantic.dev/latest/concepts/pydantic_settings/

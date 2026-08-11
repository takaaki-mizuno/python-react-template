# Phase 8 OAuth/OIDC Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 汎用 OIDC provider を設定で追加できる OAuth/OIDC ログインを実装し、OAuth-only account deletion の暫定リスクを recent OAuth/OIDC login freshness で閉じる。

**Architecture:** Backend は OIDC provider 設定、OAuth authorization code flow、provider identity 永続化、既存 opaque session cookie 発行を分離して実装する。Frontend は password login/register の既存導線を維持し、OAuth/OIDC 開始ボタンと account deletion reauth 導線を追加する。Provider access token / refresh token は保存せず、`auth_identities` には provider subject と検証済み ID token claims の allowlist だけを保存する。Account deletion freshness は callback 完了時刻ではなく provider `auth_time` と `prompt=login` / `max_age=0` で判定する。

**Tech Stack:** FastAPI、SQLModel、PostgreSQL、Alembic、Injector、pytest、React、TanStack Router、TanStack Query、Vitest

---

## 背景

Phase 8 hardening backlog の `P8-AD-1` は、OAuth/OIDC client が存在しないため blocked になっている。現在の `AccountDeletionUsecase.delete_account()` は password user (`users.password_hash IS NOT NULL`) には password 再認証を要求するが、OAuth-only user (`users.password_hash IS NULL`) には OAuth provider reauthentication を要求できず、`confirmEmail` のみで削除を許可している。

`confirmEmail` は誤操作防止であり、認証要素ではない。Session cookie と CSRF token の両方を奪取された場合、OAuth-only user は追加の本人確認なしに不可逆な account deletion を実行され得る。`backend/AGENTS.md` と `documents/references/backend-app-structure.md` はこの caveat を既に明記しているが、実装で解消するには OAuth/OIDC login flow、provider identity 永続化、recent provider login freshness の契約が必要である。

現行システムの重要な前提は次のとおり。

- Backend auth は `controllers -> usecases -> services -> models` の一方向依存で、controller から repository を直接呼ばない。
- Browser auth の正は opaque `session_token` cookie であり、DB には `auth_sessions.session_token_hash` だけを保存する。
- `users.password_hash` は nullable で、`NULL` は OAuth-only / passwordless user を表す。
- unsafe `/api` request は CSRF middleware が routing 前に検証する。CSRF 除外 path を増やす場合は、なぜ別の state 検証で守られるかを docs に書く必要がある。
- Frontend API は same-origin の `/api/...` 相対 path を正とし、auth query key は `queryKeys.auth.me` の 1 本を正とする。

## 決定済み事項

この計画では、人間の指示により次を採用する。

- Provider 方針: Google 固定ではなく、汎用 OIDC client とし、設定で provider を追加できるようにする。
- OAuth user 作成方針: trusted provider から `email_verified=true` が確認できる場合だけ自動作成を許可する。ただし、環境変数で「既存 user への link のみ許可」に切り替えられるようにする。
- 既存 password user との同一 email 衝突: provider から verified email が返り、同じ email の active user が存在する場合は自動 link する。対象ユースケースでは移行 UX とログイン成功率を優先するため。ただし自動 link は account takeover 境界を広げるため、`link_mode=auto | manual | disabled` を provider 設定に持たせ、既定は人間決定により `auto` とする。`manual` はこの計画では自動 link を拒否するだけで、password 入力後に link する UI / usecase は派生プロジェクトまたは後続計画で実装する。
- Token 保存方針: provider の `access_token` / `refresh_token` は保存しない。ID token claims と provider subject だけ保存する。
- OAuth-only account deletion: 削除用 reauth flow では provider に `prompt=login` または `max_age=0` を送り、ID token の `auth_time` を session に記録する。`AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` 以内の `auth_time` だけ fresh とみなす。既定値は 300 秒とする。
- Callback redirect 方針: 通常 login (`purpose=login`) は成功時に保存済み `redirect_path` へ戻し、失敗時は `/login?oidcError=<machine-code>` へ戻す。Account deletion reauth (`purpose=account_deletion_reauth`) は成功時に保存済み `redirect_path` へ `oidcReauth=success` を merge して戻し、失敗時も同じ `redirect_path` へ `oidcError=<machine-code>` を merge して戻す。退会操作の文脈を失わせないため。
- Browser binding cookie 方針: state ごとに cookie 名を分ける。Cookie 名は `oidc_binding_<state_lookup_id>` 形式、値は random lookup key、属性は `HttpOnly`, `SameSite=Lax`, secure 設定は既存 auth cookie と同じにし、`backend/app/libraries/auth_cookies.py` の `set_auth_cookie()` / `clear_auth_cookie()` を使う。TTL は state expiry と同じにし、callback consume 後または terminal failure 後に削除する。
- OIDC reauth failure audit 方針: 通常の reauth callback failure は `OIDC_REAUTH_FAILED` audit event を 1 件だけ記録する。Start が per-IP rate limit で拒否された request は state を作らず、callback failure audit も追加しない。Invalid / replayed callback で有効な未消費 state に到達しない場合も audit insert を増幅しない。
- Linked provider なしの OAuth-only deletion 方針: `password_hash IS NULL` かつ linked provider details が空の場合も backend は `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` を返す。Frontend は reauth button を表示せず、再認証できる provider がないため support/admin deletion が必要であることを form-level message で示す。Password setup flow はこの計画には含めない。

## 方針とその理由

### 方針 1: OIDC provider identity を既存 `users` と分離する

`auth_identities` を追加し、`users` には引き続き application user の最小属性を置く。`auth_identities` は provider ごとの subject (`sub`) と user の対応を保持する。これにより、password login、session authentication、account deletion の既存契約を崩さずに、外部 IdP の identity mapping だけを追加できる。

理由:

- `users.password_hash` nullable は OAuth-only user の前提として既に導入済みであり、ここに provider 固有情報を詰め込むと複数 provider 対応で破綻する。
- provider subject は email より安定した primary identifier であり、email 変更や再割当の影響を受けにくい。
- user-owned resource cleanup や account deletion は `users.id` を正としているため、外部 identity は user に従属させる方が既存設計に合う。

### 方針 2: OAuth/OIDC flow は専用 usecase に分離する

`AuthUsecase` は password register/login/logout/session authentication を維持し、OAuth/OIDC は `OAuthOidcUsecase` のような専用 usecase と interface に切る。Callback 成功時は既存 session 発行契約と同じ cookie を controller で設定する。

理由:

- password login の rate limiting、dummy password verify、password policy と、OIDC callback の state / nonce / PKCE / claims validation は責務が異なる。
- Account deletion は provider freshness を読むだけでよく、provider token exchange の詳細を知るべきではない。
- Unit tests で OAuth/OIDC の分岐を password auth から独立して検証できる。

### 方針 3: OAuth callback の CSRF 相当防御は `state` / browser binding / `nonce` / PKCE で担保する

OIDC authorization request では `state`、browser binding 用 lookup key cookie、`nonce`、PKCE verifier を発行し、短命 cookie または DB-backed pending authorization record に保存する。Callback では URL の `state` だけでなく、同じ browser が authorization start で受け取った lookup key cookie を持つことを確認し、`nonce`、PKCE、issuer、audience、expiry、signature、`email_verified` を検証してから user / identity / session を確定する。

Backend callback は検証、session cookie / CSRF cookie 発行、最終 redirect まで完結させる。Frontend callback route は作らない。SPA が authorization code や token を受け取らない構成にすることで、frontend state / route log / browser history に provider credential material を露出しない。

Callback redirect は `purpose` ごとに分ける。`purpose=login` の成功は保存済み `redirect_path`、失敗は `/login?oidcError=<machine-code>` に戻す。`purpose=account_deletion_reauth` の成功は保存済み `redirect_path` に `oidcReauth=success` を merge し、失敗は保存済み `redirect_path` に `oidcError=<machine-code>` を merge して戻す。`redirect_path` は start 時に internal path として正規化済みの値だけを使い、外部 URL へ redirect しない。`redirect_path` が `/app/settings?tab=danger#delete` のように既存 query / fragment を含む場合は、query を fragment より前へ追加・更新し、fragment を末尾に保持する。既存の `oidcError` / `oidcReauth` が含まれている場合は callback 結果で上書きし、成功時は `oidcError` を、失敗時は `oidcReauth` を残さない。

理由:

- OAuth/OIDC redirect は通常 browser full-page navigation であり、既存 JSON API 向け CSRF middleware とは性質が違う。
- Callback endpoint を `GET /api/auth/oidc/{provider}/callback` にする場合、既存 CSRF middleware は GET を検証しないため、`state` と browser binding cookie が CSRF 相当の必須制御になる。
- Callback endpoint を `POST` にする場合でも provider から既存 `csrf_token` header は送られないため、CSRF 除外が必要になる。その場合も `state` / browser binding / `nonce` / PKCE を docs に明記して代替制御にする。
- `/reauth` start は GET かつ認証必須で、cross-site navigation から state row を作らせること自体は可能である。Rate limit と browser binding により bounded にし、callback で current session user / session id と state の expected values を照合する。
- Reauth callback の失敗を `/login` へ送ると、認証済み session が残っているユーザーの文脈が失われる。退会再認証は settings / account deletion UI に戻し、そこで user-facing error を表示する。

### 方針 4: Token 非保存を正にする

Callback 内では provider token を検証と最小 claims 抽出にだけ使い、`access_token` / `refresh_token` は DB へ保存しない。将来 provider API を呼ぶ必要が出た場合は、scope 設計、暗号化 key 管理、refresh token rotation、revoke UX を別計画で扱う。

理由:

- 今回の目的は login と account deletion reauthentication であり、provider API 代理呼び出しではない。
- refresh token を保存すると漏洩時の影響、暗号化、運用手順、scope 管理が一気に重くなる。
- テンプレートとしては「外部 IdP でログインできるが provider データは抱えない」状態が最小で扱いやすい。

### 方針 5: OAuth-only deletion は provider `auth_time` freshness で判定する

`auth_sessions` に `last_oidc_auth_time_at` のような timestamp を追加する。通常 login では provider が返した `auth_time` がある場合だけ保存し、削除用 reauth flow では `prompt=login` または `max_age=0` を必ず authorization request に付け、callback で `auth_time` claim を必須にする。`AccountDeletionUsecase` は OAuth-only user の削除時に `now - last_oidc_auth_time_at <= AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` で fresh と判定する。既定値は 300 秒とする。

理由:

- Password user の「現在の password 入力」に近づけるには、callback 完了時刻ではなく provider が実際に user authentication を行った時刻を使う必要がある。
- Provider の SSO cookie だけで無操作 callback が完了した場合、callback 完了時刻を freshness に使うと本人確認として弱い。
- 削除専用 OAuth reauth flow より実装量を抑えつつ、古い session のまま退会できる暫定リスクを閉じられる。
- 300 秒の既定 window は短く、通常 UX と session hijack 耐性のバランスがよい。

### 方針 6: Account deletion では provider identity を物理削除する

`auth_identities` は `users.id` へ FK を張るが、account deletion は user row を logical deletion するため、FK の `ON DELETE CASCADE` だけでは identity row は消えない。削除済み user の provider subject が unique index を占有し続けると、同じ Google / OIDC account で再登録できなくなる。したがって `AccountDeletionUsecase` は user-owned cleanup と同じ transaction で対象 user の `auth_identities` を物理削除し、`backend/tests/unit/usecases/test_account_deletion_coverage.py` の `HANDLED_TABLES` に `auth_identities` を追加する。

理由:

- 既存契約では削除済み user の email は再登録可能である。provider subject でも同じ再登録 UX を保つ必要がある。
- `auth_identities` を残すなら unique index を partial 化する追加状態が必要になるが、identity row 自体に `deleted_at` を持たせるより、account deletion 時に credential binding を削除する方が単純である。
- Audit trail は `USER_MARKED_DELETED` と OIDC link / login audit event で保持し、削除後の provider subject unique 占有は残さない。

### 方針 7: Redirect URI は設定された absolute base URL からだけ作る

OIDC redirect URI は request の `Host` / `X-Forwarded-*` / `base_url` から組み立てない。`AUTH_OIDC_REDIRECT_BASE_URL` のような absolute URL を必須設定にし、provider id と callback path を join して redirect URI を作る。

理由:

- Host header injection により authorization code を攻撃者 controlled origin へ流す経路を作らないため。
- 既存 auth は `AUTH_TRUSTED_PROXY_IPS` で client IP trust boundary を明示しており、OIDC redirect URI も同じく request 由来値を信頼しない設計に揃える。

## 意思決定ログ

### デザインの決定

- 汎用 OIDC provider 設定を採用し、Google 固定実装は採用しない。テンプレート利用先ごとに IdP が異なるため、provider 固定は再利用性を落とす。
- Trusted provider の verified email だけ自動作成を許可し、環境変数で link-only に切り替えられるようにする。公開 sign-up を許す派生プロジェクトと、招待・既存 account 前提の派生プロジェクトの両方に対応するため。
- Verified email が既存 active user と一致する場合は自動 link する。対象ユースケースでは、既存 password user が外部 IdP へ移行する体験を重視するため。ただし provider ごとに `link_mode` を持たせ、派生プロジェクトが `manual` または `disabled` へ落とせる逃げ道を残す。
- Provider token は保存しない。今回の目的に provider API 連携は含まれず、refresh token 保持の運用負担に見合わないため。
- OAuth/OIDC callback 完了時刻ではなく provider `auth_time` を session に保持し、account deletion freshness に使う。SSO cookie による無操作 callback を本人確認として扱わないため。
- Account deletion 時は `auth_identities` を物理削除する。Logical deleted user の identity row が provider subject unique index を占有し、同じ provider account で再登録できなくなることを避けるため。
- OIDC redirect URI は request 由来値ではなく absolute base URL 設定から生成する。Host header injection による authorization code 流出を避けるため。
- Frontend callback route は作らず、backend callback が session 発行後に保存済み internal redirect path へ戻す。Authorization code / token を SPA に渡さないため。
- Reauth callback は成功・失敗とも保存済み settings path へ戻し、成功時は `oidcReauth=success`、失敗時は `oidcError=<machine-code>` を既存 query / fragment を壊さず merge する。退会再認証中のユーザーを login page へ飛ばすと、認証済み redirect によりエラーが消えやすく、操作文脈も失うため。
- Browser binding cookie は state ごとに名前を分け、TTL を state expiry と揃え、callback consume 後または terminal failure 後に削除する。固定名 1 本だと多タブで後続 flow が先行 flow の cookie を上書きするため。
- Linked provider details が空の OAuth-only user には reauth button を出さず、support/admin deletion が必要な form-level message を表示する。Password setup flow は今回の目的から外れるため後続計画に回す。

### 逸脱

- Phase 8 backlog の `P8-AD-1` は「OAuth-only account deletion の provider reauthentication」として記載されていたが、この計画では前提となる OAuth/OIDC client 実装も同じ Plan に含める。`auth_identities` と provider callback が存在しない現状では、再認証だけを実装できないため。
- `documents/plans/20260418-auth-structure.md` は初期認証導入で OIDC を対象外としていた。この計画は Phase 8 の後続計画であり、初期導入スコープから外した機能を後から追加するもので、矛盾ではない。

### トレードオフ

- 自動 link は、明示 link より account takeover 境界が難しい。攻撃者が trusted provider として設定された IdP で被害者 email を `email_verified=true` として提示できる場合、password を知らずに既存 account へ入れる。対象ユースケースでは自動 link を採用するが、`trust_verified_email` と独立した `link_mode`、専用 audit event、派生プロジェクト向け通知要件 docs を必須にする。
- Session freshness は provider が `auth_time` を返し、`prompt=login` または `max_age=0` を尊重する場合に強くなる。IdP が `auth_time` を返さない、または reauth を強制できない場合の fallback は実装前に人間が決める。自己退会不能のまま公開しないよう、password 設定導線、degraded callback-time freshness、または OAuth-only deletion disabled のどれかを明示的に採用する。
- Token 非保存は provider API 連携をできなくする。将来 calendar / drive / profile sync が必要なら追加計画で refresh token 保存、暗号化、scope consent、revoke UI を設計する。
- `auth_identities` 物理削除は削除済み account の provider binding history を DB row としては失う。必要な監査 signal は audit log に残すが、provider subject を平文で長期保持するか、hash だけ残すかは実装時に privacy と audit 要件を確認する。
- OIDC reauth failure audit は「有効な未消費 state に到達した通常失敗を 1 件記録し、それ以外の invalid / rate-limited / replayed request では audit insert を増幅しない」方式にする。`SESSION_REJECTED` と同じ aggregate 方式より監査粒度は粗いが、IdP 認証を経る reauth failure では実装量と DB 書き込み抑制のバランスがよい。
- OIDC client library は `Authlib` を採用する。OIDC discovery / token exchange / claims validation を実績ある library に寄せ、application 側は state、identity linking、session 発行、account deletion freshness に集中するため。人間確認済みで `backend` に `authlib` を追加する。
- `OidcProviderClient` は Authlib の `AsyncOAuth2Client` で authorization URL 生成と token exchange を行い、`OpenIDProviderMetadata` で discovery metadata を検証する。実装時点の `Authlib 1.7.2` では `authlib.jose` が deprecated warning を出すため、ID token JWT/JWK の低レベル署名検証だけ `joserfc` を直接使う。`httpx` と `joserfc` は推移的依存に依存せず、backend の直接依存として宣言する。
- `OidcProviderClient.validate_id_token()` は issuer / audience / nonce / exp / iat / subject / 署名 / reauth 時の `auth_time` 存在と未来 leeway だけを検証し、`email` / `email_verified` の信頼判定は `OAuthOidcUsecase` に委譲する。Provider trust と自動 link / auto-provision 可否は usecase の方が provider 設定・既存 user 状態・identity 状態を同時に見られるため。
- ID token の署名アルゴリズムは discovery の `id_token_signing_alg_values_supported` と application 側の安全 allowlist (`RS*`, `ES*`, `PS*`) の積集合だけを許可する。`none` と `HS*` は discovery が提示しても常に拒否する。IdP metadata をそのまま信頼して `alg=none` を許すと署名なし token による認証バイパスになるため。
- JWKS は通常 cache し、ID token header の `kid` が現行 JWKS に存在しない場合だけ強制再取得する。署名不正や nonce / claims 不正では再取得しない。さらに provider ごとに最小再取得間隔を持たせ、未認証 callback から偽 token 連打で IdP への外向き fetch を増幅できないようにする。
- Authlib の `AsyncOAuth2Client` は `httpx.AsyncClient` を継承するため、authorization URL 生成または token exchange のたびに生成した client は `aclose()` する。timeout は `HTTP_TIMEOUT_SECONDS` を明示して、Authlib client と discovery/JWKS fetch の挙動を揃える。
- Provider 設定の env 形式は provider id 別 env 群を採用する。JSON を環境変数に入れる運用を避けたいという人間判断による。JSON 1 本方式より provider 数追加時の env key は増えるが、個別 secret 管理、dotenv 上の可読性、platform 側の env 設定 UI との相性を優先する。
- Authorization state は DB-backed state を採用する。Callback retry、state 消費済み管理、監査、cookie size 制限に強いため。
- Callback endpoint method は GET を採用する。一般的な authorization code redirect と相性がよく、既存 CSRF middleware の除外を増やさないため。
- Provider trust 初期値は default deny を採用する。各 provider が `trust_verified_email=true` を明示した場合だけ自動作成・自動 link を許可し、provider ごとの email verification semantics をレビューなしで信頼しないため。
- Frontend provider 一覧は `GET /api/auth/oidc/providers` で取得する。Provider 設定の正を backend に置き、frontend build artifact と backend env の drift を避けるため。
- JWKS / discovery は lazy fetch + cache を採用する。IdP 一時障害でアプリ全体の起動を妨げず、OAuth/OIDC login だけを明示エラーにできるため。
- `auth_time` 非対応 IdP では OAuth-only self-service deletion を disabled にする。`callback_time` fallback は SSO cookie だけで freshness が開くため採用しない。Password setup flow と support/admin deletion は後続計画で扱う。
- OIDC `auth_time` future clock skew leeway は固定 60 秒を採用する。ID token の `iat` / `exp` 検証 leeway と揃え、設定項目を増やさず通常の NTP drift だけを吸収するため。

## 実装前に人間確認が必要な項目

実装者は以下を勝手に決めてはいけない。各 Task で選択肢を提示し、人間の指示を受けてから進める。

1. **OIDC client library**
   - Option A: `Authlib` を追加し、metadata discovery / token exchange / claims validation をライブラリに寄せる。
   - Option B: `httpx` と JWT/JWKS 検証ライブラリを組み合わせ、必要最小限を自前で構成する。
   - 推奨: Option A。OIDC の検証面を自前で増やさず、実装範囲を application flow に集中できるため。
2. **Provider 設定の env 形式**
   - Option A: `AUTH_OIDC_PROVIDERS_JSON` のような JSON 1 本で複数 provider を表現する。
   - Option B: `AUTH_OIDC_PROVIDER_GOOGLE_ISSUER` のような provider id 別 env 群で表現する。
   - 推奨: Option A。複数 provider の structured config、trusted email、自動作成 mode、scope を同じ schema で検証できるため。
3. **OAuth authorization state の保存先**
   - Option A: short-lived, HttpOnly, SameSite=Lax cookie に `state` / `nonce` / PKCE verifier / redirect を保存する。
   - Option B: DB の `auth_oidc_authorization_states` に保存し、cookie には lookup key だけを置く。
   - 推奨: Option B。callback retry、state 消費済み管理、監査、cookie size 制限の面で堅い。ただし DB cleanup task が必要になる。
4. **Callback endpoint method**
   - Option A: `GET /api/auth/oidc/{provider_id}/callback` を採用し、`state` / `nonce` / PKCE を CSRF 相当制御にする。
   - Option B: `POST /api/auth/oidc/{provider_id}/callback` を採用し、`AUTH_CSRF_EXEMPT_PATHS` へ完全一致 path を追加する。
   - 推奨: Option A。一般的な authorization code redirect と相性がよく、既存 CSRF middleware の除外を増やさない。
5. **Provider trust の初期値**
   - Option A: default deny。各 provider 設定で `trust_verified_email=true` を明示した場合だけ自動作成・自動 link を許可する。
   - Option B: default allow。`email_verified=true` があれば自動作成・自動 link を許可する。
   - 推奨: Option A。provider ごとの email verification semantics をレビューなしで信頼しないため。
6. **Frontend への provider 一覧の渡し方**
   - Option A: build-time env で frontend に provider id / display name を渡す。
   - Option B: `GET /api/auth/oidc/providers` で enabled provider の public metadata を返す。
   - 推奨: Option B。provider 設定の正を backend に置き、frontend build artifact と backend env の drift を避けるため。
7. **JWKS / discovery の取得方針**
   - Option A: 起動時に discovery / JWKS を取得し、失敗時は起動を落とす。
   - Option B: 初回 login 時に lazy fetch し、timeout と cache TTL を設定する。
   - 推奨: Option B。IdP 一時障害でアプリ全体の起動を妨げず、OAuth/OIDC login だけを明示エラーにできるため。ただし timeout、negative cache、既存 key cache expiry は必ず設定する。
8. **`auth_time` 非対応 IdP での OAuth-only account deletion**
   - Option A: OAuth-only deletion を disabled にし、password 設定導線または support/admin deletion を別計画で用意する。
   - Option B: OAuth-only user が password を設定できる導線を同じ実装に含め、password 再認証経路で削除できるようにする。
   - Option C: `AUTH_OIDC_DELETION_FRESHNESS_MODE=auth_time | callback_time` を追加し、`callback_time` は degraded fallback として明示的に許可された provider だけで使う。
   - 推奨: Option A または B。`callback_time` は SSO cookie だけで freshness が開くため、顧客データや課金を扱う派生プロジェクトでは避ける。
9. **OIDC `auth_time` future clock skew leeway**
   - Option A: 固定 60 秒にする。ID token の `iat` / `exp` 検証 leeway と同じ値に揃え、設定項目を増やさない。
   - Option B: `AUTH_OIDC_AUTH_TIME_FUTURE_LEEWAY_SECONDS` を追加し、環境ごとに調整可能にする。
   - Option C: 採用 OIDC library の既定 leeway に完全に委ねる。
   - 推奨: Option A。削除再認証の安全境界で過度な環境差を作らず、通常の NTP drift だけを吸収できるため。

## Files

- Create: `backend/app/config/oidc.py`
- Create: `backend/app/models/auth_identity.py`
- Create: `backend/app/models/auth_oidc_state.py` または採用する state 保存方式に応じた model
- Create: `backend/app/models/oidc.py`
- Create: `backend/app/models/oidc_errors.py`
- Create: `backend/app/interfaces/usecases/oauth_oidc_usecase_interface.py`
- Create: `backend/app/usecases/oauth_oidc_usecase.py`
- Create: `backend/app/interfaces/services/oidc_provider_client_interface.py`
- Create: `backend/app/services/oidc_provider_client.py`
- Create: `backend/alembic/versions/20260806_0004_add_oidc_auth.py`
- Create: `frontend/src/components/molecules/OidcProviderButton.tsx`
- Modify: `backend/app/config/auth.py` または `backend/app/config/__init__.py`
- Modify: `backend/.env.example`
- Modify: `backend/manage.py`
- Modify: `backend/app/bootstrap/modules.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/bootstrap/error_handlers.py`
- Modify: `backend/app/libraries/auth_cookies.py`
- Modify: `backend/app/interfaces/libraries/rate_limiter_interface.py`
- Modify: `backend/app/libraries/auth_rate_limiter.py`
- Modify: `backend/app/interfaces/services/auth_repository_interface.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/app/usecases/account_deletion_usecase.py`
- Modify: `backend/app/models/auth_errors.py`
- Modify: `backend/app/models/auth_event_type.py`
- Modify: `backend/app/models/auth_session.py`
- Modify: `backend/app/models/auth_schemas.py`
- Modify: `frontend/src/lib/authApi.ts`
- Modify: `frontend/src/lib/apiError.ts`
- Modify: `frontend/src/routes/login.tsx`
- Modify: `frontend/src/routes/register.tsx`
- Modify: `frontend/src/routes/_authenticated.app_.settings.tsx`
- Modify: `README.md`
- Modify: `backend/AGENTS.md`
- Modify: `frontend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/plans/20260804-phase8-hardening-backlog.md`
- Test Create: `backend/tests/unit/config/test_oidc_settings.py`
- Test Create: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py`
- Test Create: `backend/tests/unit/services/test_oidc_provider_client.py`
- Test Create: `backend/tests/integration/test_auth_oidc_controller.py`
- Test Create: `frontend/src/components/molecules/OidcProviderButton.test.tsx`
- Test Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Test Modify: `backend/tests/unit/controllers/test_auth_controller_helpers.py`。Cookie helper を追加または変更する場合だけ対象にする。
- Test Modify: `backend/tests/unit/bootstrap/test_error_handlers.py`
- Test Modify: `backend/tests/unit/libraries/test_auth_rate_limiter.py`
- Test Modify: `backend/tests/unit/usecases/test_account_deletion_usecase.py`
- Test Modify: `backend/tests/unit/usecases/test_account_deletion_coverage.py`
- Test Modify: `backend/tests/unit/test_manage.py`
- Test Modify: `backend/tests/integration/test_auth_controller.py`
- Test Modify: `backend/tests/integration/services/test_auth_repository.py`
- Test Modify: `frontend/src/lib/authApi.test.ts`
- Test Modify: `frontend/src/lib/apiClient.test.ts`
- Test Modify: `frontend/src/lib/apiError.test.ts`
- Test Modify: `frontend/src/routes/login.test.tsx`
- Test Modify: `frontend/src/routes/register.test.tsx`
- Test Modify: `frontend/src/routes/app.settings.test.tsx`

## Task 1: 実装前の選択肢を確定する

- [x] Step 1.1: OIDC client library の選択肢を人間へ提示し、`Authlib` 追加、または `httpx` + JWT/JWKS 検証ライブラリ構成のどちらで進めるか指示を受ける。
- [x] Step 1.2: 依存追加が必要な場合、`backend/AGENTS.md` の「ユーザー確認が必要」に従い、人間確認後に `cd backend && uv add <package>` を実行する計画として記録する。
- [x] Step 1.3: Provider 設定の env 形式を人間へ提示し、JSON 1 本方式か provider id 別 env 群かを確定する。
- [x] Step 1.4: Authorization state 保存先を人間へ提示し、DB-backed state か cookie-only state かを確定する。
- [x] Step 1.5: Callback endpoint method を人間へ提示し、GET callback か POST callback + CSRF exempt かを確定する。
- [x] Step 1.6: Provider trust 初期値を人間へ提示し、default deny か default allow かを確定する。
- [x] Step 1.7: Frontend への provider 一覧の渡し方を人間へ提示し、backend public endpoint か build-time env かを確定する。
- [x] Step 1.8: JWKS / discovery の取得方針を人間へ提示し、起動時 fetch か lazy fetch + cache かを確定する。
- [x] Step 1.9: OIDC `auth_time` future clock skew leeway の選択肢を人間へ提示し、固定 60 秒、環境変数、OIDC library 既定値のどれで進めるかを確定する。
- [x] Step 1.10: 確定した選択肢、採用理由、却下した代替案をこの Plan の「意思決定ログ」へ追記する。

## Task 2: OIDC 設定モデルを追加する

設定は provider ごとの `OidcProviderSettings` と、全 provider 共通の `OidcSettings` に分ける。`OidcProviderSettings` は provider id、display name、issuer URL、client id、client secret、scope、trusted verified email flag、自動作成 mode、link mode、callback path、claims allowlist を持つ。`OidcSettings` は provider collection、`AUTH_OIDC_REDIRECT_BASE_URL`、`AUTH_OIDC_REAUTH_FRESHNESS_SECONDS`、OIDC authorization start rate limit、state retention、Task 1.9 で採用した leeway 設定を持つ。

- [x] Step 2.1: `backend/tests/unit/config/test_oidc_settings.py` を作成し、未設定時は OAuth/OIDC provider が空 tuple になることを検証する。
- [x] Step 2.2: 同 test file に、`OidcProviderSettings` の各項目と `OidcSettings` の global 項目が別々に parse され、provider JSON schema と global env schema が混在しないことを検証する。
- [x] Step 2.3: 同 test file に、不正 provider id、大文字混在 id、重複 provider id、client secret 空文字、issuer URL 不正、redirect base URL 不正または相対 URL、unsupported auto-provision mode、unsupported link mode、非正値 freshness window、Task 1.9 で env 設定を採用した場合の非正値 leeway を起動時 validation error にする test を追加する。
- [x] Step 2.4: 同 test file に、trusted verified email が false の provider では自動作成と自動 link が無効になる test を追加する。
- [x] Step 2.5: 同 test file に、`link_mode=manual` または `link_mode=disabled` では verified email が既存 user と一致しても自動 link しない設定契約を追加する。`manual` は password 入力 flow をこの計画では実装せず、manual link が必要であることを machine-readable error と docs で示す mode とする。
- [x] Step 2.6: `backend/app/config/oidc.py` を作成し、`OidcProviderSettings` と `OidcSettings` を定義する。
- [x] Step 2.7: 採用した env 形式に従い、`get_oidc_settings()` を実装する。JSON 方式なら JSON parse error を provider 設定エラーとして起動時に落とす。
- [x] Step 2.8: Redirect URI 生成 helper は `AUTH_OIDC_REDIRECT_BASE_URL` と provider callback path だけから absolute URL を作り、request `Host` / `base_url` を入力に取らない。
- [x] Step 2.9: `backend/app/bootstrap/modules.py` の `CoreModule` に `@singleton @provider` で `OidcSettings` を追加する。
- [x] Step 2.10: `backend/app/controllers/auth_dependencies.py` に `get_oidc_settings = inject(OidcSettings)` を追加し、controller は `Depends(get_oidc_settings)` で起動時 snapshot を受ける。
- [x] Step 2.11: `backend/.env.example` に OIDC provider 設定、redirect base URL、auto-provision mode、link mode、freshness window、start rate limit、state retention の例を追加する。
- [x] Step 2.12: 「実装前に人間確認が必要な項目」8 で `auth_time` 非対応 IdP の fallback として `callback_time` mode を採用した場合だけ、`AUTH_OIDC_DELETION_FRESHNESS_MODE` を `auth_time | callback_time` として parse / validate する tests と設定実装を追加する。採用しない場合はこの env を作らない。
- [x] Step 2.13: `cd backend && uv run pytest tests/unit/config/test_oidc_settings.py -q` を実行し、設定 tests が pass することを確認する。

## Task 3: DB schema と model を追加する

Task 3 は schema と cleanup 方針の宣言までを扱う。`HANDLED_TABLES` に `auth_identities` を追加しても、Task 8 の `AccountDeletionUsecase` 実装が完了するまでは「宣言はあるが実削除は未実装」のギャップが残るため、この状態で完了扱いにしない。

- [x] Step 3.1: `backend/app/models/auth_identity.py` を作成し、`auth_identities` SQLModel を定義する。必須 column は `id`, `user_id`, `provider_id`, `provider_subject`, `email`, `email_verified`, `claims_json`, `created_at`, `updated_at`, `last_login_at` とする。`email` は保存前に既存 password auth と同じく `strip().lower()` で正規化する。
- [x] Step 3.2: `auth_identities` に unique index `(provider_id, provider_subject)` を追加する。
- [x] Step 3.3: `auth_identities.claims_json` は raw claims dump にしない。保存 allowlist は `iss`, `sub`, `email`, `email_verified`, `auth_time` と、provider 設定で明示許可した追加 claim だけにする。`access_token`, `refresh_token`, raw `id_token`, authorization code は保存禁止にする。
- [x] Step 3.4: `auth_identities.user_id` は `users.id` へ `ON DELETE CASCADE` で FK を張る。ただし account deletion は logical deletion なので、`AccountDeletionUsecase` が identity row を明示的に物理削除する。
- [x] Step 3.5: `backend/app/models/auth_session.py` に OAuth/OIDC account deletion freshness 用 timestamp column を追加する。候補名は `last_oidc_auth_time_at` とし、nullable `DateTime(timezone=True)` にする。Callback 完了時刻ではなく ID token の `auth_time` を保存する。
- [x] Step 3.6: 採用した state 保存方式が DB-backed の場合、`backend/app/models/auth_oidc_state.py` を作成し、`state_hash`, `browser_binding_hash`, `nonce_hash`, recoverable PKCE verifier storage、`provider_id`, `purpose`, `expected_user_id`, `expected_session_id`, `redirect_path`, `login_hint`, `expires_at`, `consumed_at`, `created_at` を持つ table を定義する。PKCE verifier は token exchange に必要なので、hash だけで保存して実装不能にしない。
- [x] Step 3.7: `backend/tests/unit/usecases/test_account_deletion_coverage.py` の `HANDLED_TABLES` に `auth_identities` を追加する。これは cleanup 方針の宣言であり、実際の削除挙動は Task 8.4 の usecase test と Task 8.10 の integration test で保証する。
- [x] Step 3.8: PostgreSQL を明示した `cd backend && DATABASE_URL=... uv run python manage.py db-revision --message "add oidc auth" --autogenerate --rev-id 20260806_0004` で migration skeleton を生成する。
- [x] Step 3.9: `backend/alembic/versions/20260806_0004_add_oidc_auth.py` を確認・修正し、Task 3.1 から 3.7 の schema を migration に反映する。Revision id は `20260806_0004`、down revision は `20260803_0003` とする。
- [x] Step 3.10: Migration downgrade は追加 table / column / indexes を削除する。ただし本番適用済み DB で identities を失う destructive downgrade であることを migration comment と docs に明記する。
- [x] Step 3.11: PostgreSQL が利用可能な環境で `cd backend && DATABASE_URL=... uv run python manage.py db-upgrade` と `cd backend && DATABASE_URL=... uv run python manage.py db-check` を実行する。

## Task 4: Repository 契約を追加する

- [x] Step 4.1: `backend/app/interfaces/services/auth_repository_interface.py` に provider identity lookup / create / link / delete / reauth 用 method を追加する。候補は `find_identity_by_provider_subject()`, `find_identities_by_user_id()`, `find_user_by_verified_email_for_oidc_link()`, `create_auth_identity()`, `delete_auth_identities_for_user()`, `record_oidc_login()`, `record_oidc_reauth()`。
- [x] Step 4.2: `backend/app/services/auth_repository.py` に Task 4.1 の実装を追加する。`find_user_by_verified_email_for_oidc_link()` は `deleted_at IS NULL` と `is_active = true` を必須条件にする。
- [x] Step 4.3: `record_oidc_login()` は user の `last_login_at` と identity の `last_login_at` を `utcnow()` 由来の current login time で更新する。`users.last_login_at` に provider `auth_time` を書いてはいけない。
- [x] Step 4.4: `record_oidc_login()` は provider `auth_time` が検証済みの場合だけ session の `last_oidc_auth_time_at` に provider `auth_time` を保存する。Provider `auth_time` がない通常 login では session freshness を更新しない。
- [x] Step 4.5: `record_oidc_reauth(session_id, auth_time, reauthenticated_at)` を repository interface / implementation に追加する。これは current session の `last_oidc_auth_time_at` だけを更新し、`users.last_login_at` と identity `last_login_at` を変更しない。
- [x] Step 4.6: `find_identities_by_user_id()` は `AccountDeletionUsecase` が account deletion reauth error details 用の linked provider public metadata を組み立てるために使う。Controller は repository を直接呼ばない。Deleted user や別 user の identities を返さない。
- [x] Step 4.7: DB-backed state を採用した場合、`create_oidc_authorization_state()`, `consume_oidc_authorization_state()`, `delete_oidc_states_expired_before()` を repository interface / implementation に追加する。State consume は expired / already consumed / URL state mismatch / browser binding cookie mismatch を区別できる domain result にする。
- [x] Step 4.8: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py` 用の repository stub に、新しい repository method の呼び出し記録を持たせる。現時点では同 test file が未作成のため、Task 6 で usecase test を作成するときに今回追加した repository method を stub へ反映する。
- [x] Step 4.9: `backend/tests/integration/services/test_auth_repository.py` に、identity 作成、provider subject lookup、same provider subject 重複拒否、session の `last_oidc_auth_time_at` 永続化を検証する integration tests を追加する。
- [x] Step 4.10: `backend/tests/integration/services/test_auth_repository.py` に、deleted user / inactive user は OIDC verified email 自動 link 対象にならない test を追加する。
- [x] Step 4.11: `backend/tests/integration/services/test_auth_repository.py` に、`delete_auth_identities_for_user()` が対象 user の identity を削除し、別 user の identity を残す test を追加する。
- [x] Step 4.12: DB-backed state を採用した場合、expired state pruning と consumed state replay 拒否の integration tests を追加する。
- [x] Step 4.13: DB-backed state を採用した場合、`backend/tests/unit/test_manage.py` に `db-prune-auth --oidc-states-before <ISO8601>` が repository の `delete_oidc_states_expired_before()` を呼ぶ test を追加する。
- [x] Step 4.14: DB-backed state を採用した場合、`backend/manage.py` の `db-prune-auth` に `--oidc-states-before` を追加する。Audit log と expired sessions とは独立した repository operation にし、部分成功 semantics を docs に書く。
- [x] Step 4.15: `cd backend && uv run pytest tests/integration/services/test_auth_repository.py -q -ra` と `cd backend && uv run pytest tests/unit/test_manage.py -q` を実行し、repository / CLI tests が pass することを確認する。

## Task 5: OIDC provider client 境界を作る

- [x] Step 5.1: `backend/app/models/oidc.py` を作成し、`OidcAuthorizationRequest`, `OidcCallbackInput`, `OidcVerifiedClaims`, `OidcTokenSetForValidation` のような domain DTO を定義する。DTO に provider token raw value を永続化用途で公開しない。`OidcVerifiedClaims` の email は必須で、保存前に `strip().lower()` された normalized email を持つ。
- [x] Step 5.2: `backend/app/models/oidc_errors.py` を作成し、`OidcProviderNotConfiguredError`, `OidcStateMismatchError`, `OidcBrowserBindingMismatchError`, `OidcTokenExchangeError`, `OidcClaimsValidationError`, `OidcEmailNotVerifiedError`, `OidcProvisioningDisabledError`, `OidcIdentityLinkRequiredError`, `OidcIdentityLinkDisabledError`, `OidcAuthorizationRateLimitedError`, `OidcReauthSubjectMismatchError`, `OidcReauthAuthTimeRequiredError`, `OidcReauthStaleError` を定義する。
- [x] Step 5.3: `backend/app/interfaces/services/oidc_provider_client_interface.py` を作成し、authorization URL 生成、code exchange、ID token claims validation を抽象化する。
- [x] Step 5.4: `backend/tests/unit/services/test_oidc_provider_client.py` を作成し、issuer / audience / expiry / nonce / email_verified / subject missing / email missing / auth_time missing for reauth の validation failure を検証する。
- [x] Step 5.5: 同 test file に、discovery / JWKS fetch の timeout、cache TTL、negative cache、IdP 障害時に app 起動ではなく OAuth/OIDC login だけが失敗する契約を検証する。
- [x] Step 5.6: 同 test file に、authorization URL が absolute redirect base URL 由来の `redirect_uri` を使い、request host 由来値を受け取らないことを検証する。
- [x] Step 5.7: 同 test file に、reauth 用 `auth_time` が Task 1.9 で確定した future leeway を超えて未来の場合は拒否し、過去方向の freshness 判定は `AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` で行う test を追加する。
- [x] Step 5.8: 採用した OIDC library に従い、`backend/app/services/oidc_provider_client.py` を実装する。
- [x] Step 5.9: Provider token response から `access_token` / `refresh_token` を repository DTO に渡していないことを unit test で検証する。
- [x] Step 5.10: Claims persistence allowlist 以外の claim が `claims_json` に入らないことを unit test で検証する。
- [x] Step 5.11: `backend/app/bootstrap/modules.py` に `OidcProviderClientInterface` binding を追加する。
- [x] Step 5.12: `cd backend && uv run pytest tests/unit/services/test_oidc_provider_client.py -q` を実行し、provider client tests が pass することを確認する。

## Task 6: OAuth/OIDC usecase を実装する

- [x] Step 6.1: `backend/app/interfaces/usecases/oauth_oidc_usecase_interface.py` を作成し、`start_authorization(provider_id, redirect_path, purpose, current_session)` と `complete_callback(provider_id, state, code, current_session, request_context)` の interface を定義する。`purpose` は `login` と `account_deletion_reauth` を区別する。現時点では start_authorization を interface に追加済みで、complete_callback は callback 実装着手時に追加する。
- [x] Step 6.2: `backend/tests/unit/libraries/test_auth_rate_limiter.py` に OIDC authorization start 用 per-IP bucket の tests を追加する。Bucket 上限は既存 `AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE` の対象に含め、満杯時は既存 rate limiter と同じ fail-open + warning 契約にする。
- [x] Step 6.3: `backend/app/interfaces/libraries/rate_limiter_interface.py` と `backend/app/libraries/auth_rate_limiter.py` に OIDC authorization start 用 method を追加する。候補名は `is_oidc_authorization_allowed(ip_address)` と `record_oidc_authorization(ip_address)`。
- [x] Step 6.4: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py` に、未設定 provider では provider not configured error を返す test を追加する。
- [x] Step 6.5: 同 test file に、authorization start が per-IP rate limit を確認し、limit 到達時は state row を作らず `OidcAuthorizationRateLimitedError` を返す test を追加する。
- [x] Step 6.6: 同 test file に、authorization start が URL `state`、state ごとの browser binding cookie name、browser binding lookup key cookie value、nonce、PKCE verifier を生成し、redirect path を `normalizeRedirectHref` と同等の internal path 制約で保存する test を追加する。外部 URL、control character、auth page redirect は `/app` に落とす。
- [x] Step 6.7: 同 test file に、`purpose=account_deletion_reauth` では current authenticated session を必須にし、state に expected user id、expected session id、login hint、purpose を保存し、provider authorization URL に `prompt=login` または `max_age=0` を含める test を追加する。
- [x] Step 6.8: 同 test file に、callback の URL state mismatch、browser binding cookie missing、browser binding mismatch、expired state、consumed state reuse を拒否する test を追加する。State ごとの cookie 名により多タブの並行 OIDC flow が互いの browser binding を上書きしないことも検証する。
- [x] Step 6.9: 同 test file に、既存 identity がある場合は該当 user に login し、session を発行し、`OIDC_LOGIN_SUCCESS` audit を記録する test を追加する。
- [x] Step 6.10: 同 test file に、identity がなく、trusted provider の verified email が既存 active user と一致する場合は自動 link し、session を発行する test を追加する。
- [x] Step 6.11: 同 test file に、identity がなく、trusted provider の verified email が新規 email で、auto-provision mode が enabled の場合は `password_hash=None` の user と identity を作成する test を追加する。
- [x] Step 6.12: 同 test file に、auto-provision mode が link-only の場合は新規 user を作らず `OidcProvisioningDisabledError` を返す test を追加する。
- [x] Step 6.13: 同 test file に、`email_verified` が false または provider が trusted verified email ではない場合は自動作成・自動 link を拒否する test を追加する。
- [x] Step 6.14: 同 test file に、既存 deleted / inactive user の email と一致しても自動 link しない test を追加する。
- [x] Step 6.15: 同 test file に、`link_mode=manual` または `link_mode=disabled` では verified email が既存 active user と一致しても自動 link せず、`OidcIdentityLinkRequiredError` または `OidcIdentityLinkDisabledError` を返す test を追加する。
- [x] Step 6.16: 同 test file に、自動 link 成功時は `OIDC_IDENTITY_LINKED` audit event を記録し、新規 user 作成時は `OIDC_USER_PROVISIONED` audit event を記録する test を追加する。
- [x] Step 6.17: 同 test file に、OIDC login failure は raw token / code を含まない `OIDC_LOGIN_FAILED` audit event を記録する test を追加する。有効な未消費 state に到達しない invalid / replayed callback では audit insert を増やさず、start rate limit で拒否された request は state を作らない。
- [x] Step 6.18: 同 test file に、`purpose=account_deletion_reauth` callback では current session が state の expected user id / expected session id と一致し、OIDC claims が同じ user の identity に解決される場合だけ `record_oidc_reauth()` で session freshness を更新する test を追加する。
- [x] Step 6.19: 同 test file に、`purpose=account_deletion_reauth` callback で別 provider account / 別 user に解決された場合は session を置換せず、`OidcReauthSubjectMismatchError` を返し、current user / current session / request IP / user_agent 付きで `OIDC_REAUTH_FAILED` audit event を 1 件だけ記録する test を追加する。有効な未消費 state に到達しない invalid / replayed callback では audit insert を増やさない。
- [x] Step 6.20: 同 test file に、`purpose=account_deletion_reauth` callback で `auth_time` が missing、future leeway 超過、または `AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` より古い場合は session を fresh にせず、`OidcReauthAuthTimeRequiredError` または `OidcReauthStaleError` を返し、current user / current session / request IP / user_agent 付きで `OIDC_REAUTH_FAILED` audit event を 1 件だけ記録する test を追加する。有効な未消費 state に到達しない invalid / replayed callback では audit insert を増やさない。
- [x] Step 6.21: `backend/app/models/auth_event_type.py` に `OIDC_LOGIN_SUCCESS`, `OIDC_LOGIN_FAILED`, `OIDC_IDENTITY_LINKED`, `OIDC_USER_PROVISIONED`, `OIDC_REAUTH_SUCCESS`, `OIDC_REAUTH_FAILED` を追加する。
- [x] Step 6.22: `backend/app/usecases/oauth_oidc_usecase.py` を実装し、usecase tests の Step 6.4 から 6.20 と、rate limiter tests の Step 6.2 から 6.3 を pass させる。
- [x] Step 6.23: 通常 login callback 成功時は既存 `AuthUsecase._replace_session()` と同じ session fixation 対策を満たす。Account deletion reauth callback 成功時は別 user への session 置換を行わず、現在 session の `last_oidc_auth_time_at` だけを更新する。
- [x] Step 6.24: `cd backend && uv run pytest tests/unit/libraries/test_auth_rate_limiter.py tests/unit/usecases/test_oauth_oidc_usecase.py -q` を実行し、rate limiter / usecase tests が pass することを確認する。

## Task 7: 共有 error envelope と Auth controller endpoint を追加する

Step 7.1 から 7.2 の `api_error(details=...)` 拡張は controller endpoint 実装と独立して進められる。ただし Task 8.8 が `api_error(details=...)` を使うため、Task 8 に入る前には完了させる。

- [x] Step 7.1: `backend/tests/unit/bootstrap/test_error_handlers.py` に、`api_error()` の optional `details` parameter を検証する unit test を書く。既存 call sites は変更なしで同じ error envelope を返し、details 指定時だけ `error.details` に list が入る契約にする。
- [x] Step 7.2: `backend/app/bootstrap/error_handlers.py` を実装し、既存 `api_error(status, code, message, headers=...)` 呼び出し互換を維持する。
- [x] Step 7.3: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に `GET /api/auth/oidc/providers` が enabled provider の `providerId` と `displayName` だけを返し、client secret や issuer internal detail を返さない test を追加する。既存の `register_error_handlers` と `dependency_overrides` fixture 構成を拡張し、新規の幽霊 test file を作らない。Task 1 で build-time env を採用した場合はこの step を docs に不採用理由付きで削除する。
- [x] Step 7.4: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に `GET /api/auth/oidc/{provider_id}/start?redirect=/app` が provider authorization URL へ redirect し、`oidc_binding_<state_lookup_id>` 形式の browser binding cookie を `Set-Cookie` する test を追加する。Cookie は `set_auth_cookie()` を使い、`HttpOnly`, `SameSite=Lax`, `Path=/`, secure 設定、state expiry と同じ `Max-Age` を持つ。
- [x] Step 7.5: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に `GET /api/auth/oidc/{provider_id}/reauth?redirect=/app/settings` が authenticated session を要求し、provider authorization URL に reauth purpose と login hint を反映する test を追加する。
- [x] Step 7.6: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に、`purpose=login` callback success が `session_token` と `csrf_token` cookie を設定し、保存済み redirect path へ redirect し、対応する browser binding cookie を削除する test を追加する。
- [x] Step 7.7: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に、`purpose=account_deletion_reauth` callback success は session cookie を別 user に置換せず、既存 session の `csrf_token_hash` を更新し、新しい `csrf_token` cookie を発行し、保存済み redirect path に `oidcReauth=success` を merge して redirect し、対応する browser binding cookie を削除する test を追加する。`redirect_path=/app/settings?tab=danger#delete` なら `/app/settings?tab=danger&oidcReauth=success#delete` になることを検証する。Cookie helper を追加または変更する場合だけ `backend/tests/unit/controllers/test_auth_controller_helpers.py` に helper 単体 test を追加する。
- [x] Step 7.8: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に、`purpose=login` callback failure は `/login?oidcError=<machine-code>` へ redirect し、`purpose=account_deletion_reauth` callback failure は保存済み redirect path に `oidcError=<machine-code>` を merge して redirect し、どちらも provider token や raw error description を URL に含めず、terminal failure では対応する browser binding cookie を削除する test を追加する。`redirect_path=/app/settings?tab=danger#delete` なら `/app/settings?tab=danger&oidcError=OIDC_REAUTH_STALE#delete` になることを検証する。
- [x] Step 7.9: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に、domain error、redirect query error code、audit event type の対応表を固定する test を追加する。例: `OidcReauthSubjectMismatchError -> oidcError=OIDC_REAUTH_SUBJECT_MISMATCH -> OIDC_REAUTH_FAILED`。
- [x] Step 7.10: `backend/app/controllers/auth_controller.py` に providers endpoint、start endpoint、reauth endpoint、callback endpoint を追加する。GET callback 採用時は CSRF exempt path を追加しない。
- [x] Step 7.11: `backend/app/controllers/auth_controller.py` または controller-local helper に redirect result query merge helper を実装する。Relative internal path を fixed dummy origin で parse し、既存 query と fragment を保持したまま `oidcError` / `oidcReauth` を更新する。成功時は既存 `oidcError` を削除し、失敗時は既存 `oidcReauth` を削除する。String concat で `?` を足さない。
- [x] Step 7.12: `backend/app/bootstrap/route.py` は既存 auth router include を維持する。新 router に分ける場合も `/api/auth` prefix 下に置き、SPA fallback より先に登録する。
- [x] Step 7.13: OAuth/OIDC error を `api_error()` ではなく redirect error に変換する場合、domain error、redirect query error code、audit event type、`purpose=login` / `purpose=account_deletion_reauth` ごとの success / failure redirect 先、redirect result query merge helper の契約を `backend/AGENTS.md` に記録する。
- [x] Step 7.14: `cd backend && uv run pytest tests/unit/bootstrap/test_error_handlers.py tests/unit/controllers/test_auth_controller_dependency.py tests/unit/controllers/test_auth_controller_helpers.py -q` を実行し、error handler / controller unit tests が pass することを確認する。

## Task 8: Account deletion freshness を実装する

- [x] Step 8.1: `backend/tests/unit/usecases/test_account_deletion_usecase.py` に、OAuth-only user で `auth_context.session.last_oidc_auth_time_at` が missing の場合は削除を拒否する test を追加する。
- [x] Step 8.2: 同 test file に、`last_oidc_auth_time_at` が `AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` より古い場合は削除を拒否する test を追加する。既定値は 300 秒として検証する。
- [x] Step 8.3: 同 test file に、`last_oidc_auth_time_at` が `AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` 以内の場合は password なしで削除できる test を追加する。
- [x] Step 8.4: 同 test file に、account deletion 成功時に `delete_auth_identities_for_user()` が sample item cleanup、`mark_user_deleted()`、`revoke_sessions_for_user()` と同じ transaction 内で呼ばれる test を追加する。
- [x] Step 8.5: `backend/tests/unit/usecases/test_account_deletion_coverage.py` の `HANDLED_TABLES` に `auth_identities` が含まれていることを確認する。これは cleanup 方針の定数更新であり、挙動保証は Step 8.4 と Step 8.10 で行う。
- [x] Step 8.6: `backend/app/models/auth_errors.py` に `AccountDeletionOidcReauthRequiredError` を追加する。この domain error は `linked_providers` として provider id / display name だけを持ち、provider subject、token、raw claims は持たない。
- [x] Step 8.7: `backend/app/usecases/account_deletion_usecase.py` に `OidcSettings` の DI を追加し、OAuth-only freshness check、linked provider public metadata 解決、identity cleanup を追加する。`find_identities_by_user_id()` はここで呼び、`AccountDeletionOidcReauthRequiredError` に details を載せる。Linked provider details が空でも `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` として扱い、support/admin deletion が必要な状態を frontend が判別できるよう空配列を保持する。既存 unit test の usecase 生成 helper / stub も `OidcSettings` 注入に合わせて更新する。Password user の password 再認証契約は変更しない。
- [x] Step 8.8: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に、`AccountDeletionOidcReauthRequiredError` が `400 ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` と linked provider public metadata の `error.details` へ変換される test を追加する。`backend/app/controllers/auth_controller.py` は error が持つ details を `api_error(details=...)` へ渡すだけにし、controller から repository を直接呼ばない。
- [x] Step 8.9: `frontend/src/lib/apiError.test.ts` と `frontend/src/lib/apiError.ts` を更新し、`ApiError.details` から account deletion reauth provider details を型安全に取り出せる helper を追加する。既存 `toUserMessage()` の fallback 契約は変更しない。
- [x] Step 8.10: `backend/tests/integration/test_auth_oidc_controller.py` に、OIDC login 直後の OAuth-only user は account deletion でき、`auth_identities` が削除され、同じ provider subject で再登録できる test を追加する。
- [x] Step 8.11: `backend/tests/integration/test_auth_controller.py` または OIDC integration test に、stale OIDC session は account deletion で `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` を返す test を追加する。
- [x] Step 8.12: `cd backend && uv run pytest tests/unit/usecases/test_account_deletion_usecase.py tests/unit/usecases/test_account_deletion_coverage.py tests/unit/controllers/test_auth_controller_dependency.py -q` と OIDC integration tests を実行する。

## Task 9: Frontend auth API と login/register UI を追加する

- [x] Step 9.1: `frontend/src/lib/authApi.test.ts` に、採用済み方式で provider 一覧を取得する test を追加する。Backend endpoint 方式なら `GET /api/auth/oidc/providers` から `providerId` と `displayName` だけを読む。
- [x] Step 9.2: `frontend/src/lib/authApi.test.ts` に、`startOidcLogin(providerId, redirect)` が `/api/auth/oidc/{providerId}/start?redirect=...` へ `window.location.assign()` する test を追加する。`redirect=/app/settings?tab=danger#delete` のように query / hash を含む場合、`URLSearchParams` または同等の API で percent-encode され、start endpoint の query string を壊さないことも検証する。
- [x] Step 9.3: `frontend/src/lib/authApi.ts` に provider list helper、`startOidcLogin()`、`startOidcReauth()`、provider id 型を追加する。Start / reauth は JSON API ではなく full-page redirect helper として実装する。Start URL は文字列連結ではなく `URLSearchParams` または同等の API で組み立て、redirect の既存 query / hash を失わない。
- [x] Step 9.4: `frontend/src/components/molecules/OidcProviderButton.tsx` を作成し、provider display name を受け取って OAuth/OIDC 開始 button を描画する。
- [x] Step 9.5: `frontend/src/routes/login.test.tsx` に、login page が OIDC login button を表示し、現在の normalized redirect を引き継いで start endpoint へ遷移する test を追加する。
- [x] Step 9.6: `frontend/src/routes/register.test.tsx` に、register page が同じ OIDC login button を表示し、redirect を引き継ぐ test を追加する。
- [x] Step 9.7: `frontend/src/routes/login.tsx` と `frontend/src/routes/register.tsx` に OIDC login button を追加する。Password form の既存 error / a11y 契約は変更しない。
- [x] Step 9.8: Login/register page は provider list loading / empty / error states を持つ。Provider 未設定時は password form だけを表示し、画面上に実装説明文を出さない。
- [x] Step 9.9: `cd frontend && npm test -- authApi.test.ts login.test.tsx register.test.tsx` を実行し、frontend targeted tests が pass することを確認する。

## Task 10: Frontend deletion reauth UX と callback redirect result を扱う

- [x] Step 10.1: Frontend callback route は作らない。Backend callback が session cookie / CSRF cookie を発行して保存済み internal redirect path へ戻すため、`frontend/src/routes/auth.oidc.callback.tsx` のような route file を追加しないことを実装メモに明記する。
- [x] Step 10.2: `frontend/src/routes/login.test.tsx` に、`/login?oidcError=<machine-code>` を user-facing form-level message に変換する test を追加する。`OIDC_IDENTITY_LINK_REQUIRED` は「既存アカウントでログインしてから連携が必要」、`OIDC_IDENTITY_LINK_DISABLED` は「この provider では既存アカウントへの自動連携不可」として扱う。`ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` は DELETE `/api/auth/me` の JSON error code であり、OIDC callback failure query には使わない。
- [x] Step 10.3: `frontend/src/routes/_authenticated.app_.settings.tsx` に、`ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` を受けた場合の form-level message を追加する。Error details の linked providers が空配列の場合は reauth button を表示せず、再認証できる provider がないため support/admin deletion が必要であることを form-level message として表示する。
- [x] Step 10.4: Account deletion page は `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` の error details から provider id / display name を読み、provider reauth button を表示する。事前に `/api/auth/me` へ `hasPassword` を追加しなくても、エラー後に必要な reauth 導線を出せるようにする。
- [x] Step 10.5: Provider reauth button のクリック時は `startOidcReauth(providerId, '/app/settings')` を呼び、fresh reauth 後に backend が保存済み redirect path へ `oidcReauth=success` を merge して戻す。Settings page は `oidcReauth=success` を account deletion 用の form-level success message に変換する。
- [x] Step 10.6: `frontend/src/components/molecules/OidcProviderButton.test.tsx` に、button が provider display name を表示し、click で渡された handler を呼ぶ test を追加する。
- [x] Step 10.7: `frontend/src/routes/app.settings.test.tsx` に、OIDC reauth required error は input を invalid にせず、form-level message と reauth button を表示する test を追加する。
- [x] Step 10.8: `frontend/src/routes/app.settings.test.tsx` に、`/app/settings?oidcError=OIDC_REAUTH_SUBJECT_MISMATCH`、`/app/settings?oidcError=OIDC_REAUTH_STALE`、`/app/settings?oidcError=OIDC_REAUTH_AUTH_TIME_REQUIRED` を account deletion 用の form-level error message に変換し、login page へ遷移しない test を追加する。
- [x] Step 10.9: `frontend/src/routes/app.settings.test.tsx` に、reauth callback 後の full-page load または query refetch で `queryKeys.auth.me` が stale user のまま削除 submit されないことを検証する。実装が full-page redirect なら initial query fetch で新 session を読むことを確認する。
- [x] Step 10.10: `frontend/src/lib/apiClient.test.ts` または route test に、OAuth/OIDC callback 後に新しい `csrf_token` cookie がある状態で unsafe request が `X-CSRF-Token` を新 cookie から読むことを検証する。
- [x] Step 10.11: `cd frontend && npm test -- login.test.tsx app.settings.test.tsx apiClient.test.ts OidcProviderButton.test.tsx` を実行し、targeted tests が pass することを確認する。

## Task 11: Integration tests と security regression tests を追加する

- [x] Step 11.1: `backend/tests/integration/test_auth_oidc_controller.py` を作成し、fake OIDC provider client を DI container に差し替える fixture を用意する。既存 `backend/tests/integration/conftest.py` と同じく `LoginRateLimiterInterface.reset()` を teardown で呼び、per-IP rate limit test が test 間で干渉しないようにする。
- [x] Step 11.2: Start endpoint が state record を作成し、state ごとの browser binding cookie を設定し、provider authorization URL へ redirect することを検証する。
- [x] Step 11.3: Start endpoint の per-IP rate limit が state row の無制限作成を防ぐことを検証する。
- [x] Step 11.4: Callback success が user / identity / session / audit log を 1 transaction で作成し、cookie を設定することを検証する。
- [x] Step 11.5: Callback success 後、`GET /api/auth/me` が OIDC-created user を返すことを検証する。
- [x] Step 11.6: Provider subject が既存 identity に一致する場合、新規 user を作らず同じ user で login することを検証する。
- [x] Step 11.7: Verified email が既存 password user に一致する場合、自動 link して login できることを検証する。
- [x] Step 11.8: Auto-provision mode を link-only にした場合、新規 verified email では user を作らず error redirect になることを検証する。
- [x] Step 11.9: `email_verified=false`、issuer mismatch、audience mismatch、nonce mismatch、expired state、state replay がそれぞれ session を発行しないことを検証する。
- [x] Step 11.10: Callback に authorization start 時の browser binding cookie がない場合、または別 browser の binding cookie を持つ場合、session を発行しないことを検証する。
- [x] Step 11.11: Callback failure 時に `access_token` / `refresh_token` / authorization code / raw provider error が audit log、URL、JSON response、test output に残らないことを検証する。
- [x] Step 11.12: Account deletion reauth callback で別 provider account / 別 user が返った場合、session を置換せず、保存済み settings redirect path に `oidcError=OIDC_REAUTH_SUBJECT_MISMATCH` を付けた safe error redirect になることを検証する。
- [x] Step 11.13: Account deletion reauth callback で `auth_time` missing / stale / future leeway 超過の場合、session の `last_oidc_auth_time_at` が更新されず、保存済み settings redirect path に `oidcError=OIDC_REAUTH_AUTH_TIME_REQUIRED` または `oidcError=OIDC_REAUTH_STALE` を付けた safe error redirect になり、account deletion が失敗し続けることを検証する。
- [x] Step 11.14: OAuth-only account deletion 成功後、同じ provider subject で再度 OIDC login すると新しい user / identity が作られることを検証する。
- [x] Step 11.15: DB-backed state を採用した場合、`db-prune-auth --oidc-states-before <ISO8601>` が expired / consumed states を削除し、active unconsumed state を残すことを検証する。
- [x] Step 11.16: `cd backend && uv run pytest tests/integration/test_auth_oidc_controller.py -q -ra` を実行し、integration tests が pass することを確認する。

## Task 12: Docs と backlog を更新する

- [x] Step 12.1: `backend/AGENTS.md` に OIDC provider 設定、absolute redirect base URL、trusted verified email、自動作成 mode、link mode、自動 link audit、token 非保存、`auth_time` freshness、`auth_time` 非対応 IdP の fallback 方針、identity cleanup、state pruning、rate limit、`api_error(details=...)` の互換契約、purpose 別 callback redirect 契約、browser binding cookie lifecycle、OIDC failure audit の bounded 方針を追記する。
- [x] Step 12.2: `frontend/AGENTS.md` に OAuth/OIDC login button、backend callback redirect result、account deletion reauth error / success の form-level feedback 契約、linked providers 空配列時の support/admin deletion message 契約を追記する。Frontend callback route は作らず、backend callback が最終 redirect まで完結する理由も書く。
- [x] Step 12.3: `documents/references/backend-app-structure.md` に `auth_identities`、OIDC callback state、browser binding cookie lifecycle、redirect URI 生成、purpose 別 callback redirect、token 非保存、OAuth-only account deletion freshness、same-user reauth 検証、identity deletion policy を追記する。
- [x] Step 12.4: `README.md` に OIDC provider 設定例、redirect URI 登録例、state pruning の運用、token 非保存の制約を追記する。
- [x] Step 12.5: `backend/.env.example` の OIDC 設定例と README の説明が同じ env 名を使っていることを grep で確認する。
- [x] Step 12.6: `documents/plans/20260804-phase8-hardening-backlog.md` の `P8-AD-1` を完了扱いに更新する場合は、実装完了後に追記で status と実装計画ファイルへの参照を追加する。冒頭の実行順サマリ行と Task セクションの両方へ追記し、既存記述を書き換えない。
- [x] Step 12.7: Docs grep を実行し、`trusted verified email`、`token 非保存`、`last_oidc_auth_time_at`、`auth_time`、`AUTH_OIDC_REAUTH_FRESHNESS_SECONDS`、`ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED`、`OIDC_REAUTH_SUBJECT_MISMATCH`、`OIDC_REAUTH_STALE`、`OIDC_REAUTH_AUTH_TIME_REQUIRED`、`AUTH_OIDC_REDIRECT_BASE_URL`、`browser binding`、`oidcReauth=success`、`linked providers` が該当 docs に存在することを確認する。

## Task 13: 品質ゲート

- [x] Step 13.1: Backend static checks を実行する: `cd backend && uv run ruff check .`
- [x] Step 13.2: Backend import check を実行する: `cd backend && uv run isort . --check-only`
- [x] Step 13.3: Backend format check を実行する: `cd backend && uv run yapf -dr app/ tests/ alembic/ manage.py`
- [x] Step 13.4: Backend type check を実行する: `cd backend && uv run mypy app manage.py`
- [x] Step 13.5: Backend unit tests を実行する: `cd backend && uv run pytest tests/unit -q`
- [x] Step 13.6: PostgreSQL 起動後、migration と integration tests を実行する: `cd backend && DATABASE_URL=... uv run python manage.py db-upgrade`
- [x] Step 13.7: PostgreSQL 起動後、integration tests を実行する: `cd backend && TEST_DATABASE_URL=... uv run pytest tests/integration -q -ra`
- [x] Step 13.8: PostgreSQL 起動後、schema drift check を実行する: `cd backend && DATABASE_URL=... uv run python manage.py db-check`
- [x] Step 13.9: Frontend CI checks を実行する: `cd frontend && npm run check:ci`
- [x] Step 13.10: Frontend tests を実行する: `cd frontend && npm test`
- [x] Step 13.11: Frontend build を実行する: `cd frontend && npm run build`
- [x] Step 13.12: Docker config を触った場合だけ `docker compose config` を実行する。
- [x] Step 13.13: `git diff --check` を実行し、whitespace error がないことを確認する。

### 2026-08-07 追記: 品質ゲート実行結果

- Backend static: `uv run ruff check .`、`uv run isort . --check-only`、`uv run yapf -dr app/ tests/ alembic/ manage.py` は pass。
- Backend type: `uv run mypy app manage.py` は pass。
- Backend unit: `uv run pytest tests/unit -q` は 383 passed。
- Backend DB / integration: `db-upgrade` pass、`uv run pytest tests/integration -q -ra` は 111 passed、`db-check` は drift なし。
- Frontend: `npm run check:ci`、`npm test`、`npm run build` は pass。Vitest では既存の jsdom `Window.scrollTo()` warning が出るが failure はない。
- Docker: Docker 設定ファイルはこの OAuth/OIDC 実装で変更していないため `docker compose config` は対象外。
- Whitespace: `git diff --check` は clean。

## 完了条件

- 汎用 OIDC provider を設定で追加できる。
- Trusted provider の verified email だけが自動作成・自動 link に使われる。
- 環境変数で新規 OAuth user 自動作成を link-only に切り替えられる。
- Verified email が既存 active password user と一致する場合、`link_mode=auto` の provider だけ自動 link して login できる。
- 自動 link、user 自動作成、login success / failure、reauth success / failure は専用 audit event で追跡でき、provider token や authorization code を audit に残さない。
- Provider `access_token` / `refresh_token` は DB、audit log、URL、frontend state に保存されない。
- OAuth/OIDC callback 成功時も既存 opaque session cookie と CSRF cookie を発行する。
- `purpose=login` callback は成功時に保存済み `redirect_path`、失敗時に `/login?oidcError=<machine-code>` へ戻る。`purpose=account_deletion_reauth` callback は成功時に保存済み `redirect_path` へ `oidcReauth=success` を merge し、失敗時に保存済み `redirect_path` へ `oidcError=<machine-code>` を merge して戻る。既存 query / fragment は壊さない。
- Redirect URI は `AUTH_OIDC_REDIRECT_BASE_URL` 由来の absolute URL だけで生成され、request host 由来値を使わない。
- Account deletion reauth では current session user と provider identity user の同一性を検証し、別 provider account / 別 user の callback で session を置換しない。
- OIDC callback は URL `state` だけでなく state ごとの browser binding cookie を検証し、別 browser で開始された callback URL を踏ませる login CSRF / session swapping を拒否する。Binding cookie は `HttpOnly`, `SameSite=Lax`, state expiry と同じ TTL で、callback consume 後または terminal failure 後に削除される。
- OAuth/OIDC provider `auth_time` が session の `last_oidc_auth_time_at` に保存される。
- OAuth-only user の account deletion は `AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` 以内の provider `auth_time` freshness がなければ `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` で拒否される。既定値は 300 秒である。
- `auth_time` 非対応 IdP で OAuth-only self-service deletion をどう扱うかが、実装前の人間確認に基づいて docs と挙動に反映されている。
- OAuth-only account deletion 成功時は `auth_identities` が削除され、同じ provider subject で再登録できる。
- OIDC authorization start は既存 in-memory rate limiter の bucket 上限 / fail-open 契約に従って rate limited で、DB-backed state は `db-prune-auth` で pruning できる。Start が rate limit で拒否された request は state を作らず、callback failure audit も追加しない。
- `api_error()` は既存呼び出し互換を維持したまま optional `details` を扱え、account deletion reauth response は linked provider public metadata だけを `error.details` に含める。
- Frontend は OAuth/OIDC login と reauth required / reauth success / reauth failure を user-facing に扱い、field に紐づかない error で input を invalid にしない。Linked provider details が空の場合は reauth button を表示せず、support/admin deletion が必要な message を表示する。
- Frontend は backend callback redirect を前提にし、authorization code / token を SPA route や frontend state に保存しない。
- `backend/AGENTS.md`、`frontend/AGENTS.md`、`documents/references/backend-app-structure.md` に実装契約とトレードオフが追記されている。

## 2026-08-07 追記: Claude Code レビュー Low 指摘の是正判断

### 背景

Claude Code の再レビューで、Critical / High / Medium 指摘は解消済みとされた一方、Low として以下が残った。

- `exchange_code()` 内で `token_endpoint` の metadata error が token exchange error に丸め込まれる。
- Authlib `AsyncOAuth2Client` の `aclose()` 回帰を失敗パスで検知する test がない。
- `AUTH_OIDC_STATE_RETENTION_SECONDS` が parse / `.env.example` / config test に存在するが、実際の state pruning 処理から参照されていない。
- usecase test stub が interface を直接継承していない。
- working tree に他 Plan の変更が混在している。

### 方針とその理由

- `exchange_code()` の `token_endpoint` 取得は token exchange の `try` ブロック外へ出す。Provider metadata 不備は設定ミスまたは攻撃シグナルであり、network / token endpoint failure と同じ `OidcTokenExchangeError` に丸めると audit / redirect error mapping を誤るため。
- OAuth client close は成功パスに加えて、`fetch_token()` 失敗パスでも `aclose()` が呼ばれることを unit test で固定する。HTTP client leak は正常系だけでは検知できず、provider 障害時ほど callback が集中しやすいため。
- `AUTH_OIDC_STATE_RETENTION_SECONDS` は削除する。OIDC state pruning は `db-prune-auth --oidc-states-before <ISO8601>` の明示引数で運用ジョブ側が保持期間を決める契約であり、未使用 env を残すと「設定すれば自動的に保持期間が適用される」と誤解されるため。保持期間の default が必要になった場合は、CLI / scheduler 設計と一緒に別途追加する。
- usecase test stub の interface 継承は今回は変更しない。実 DI 契約は `tests/unit/bootstrap/test_container.py` が検証済みで、stub 継承を強制すると unit test 用 stub に本筋でない method 実装が増えるため。interface 変更検知をさらに強める必要が出た場合は、stub 継承ではなく Protocol / autospec / fixture shared fake の導入として別途扱う。
- working tree 分割はこの作業では行わない。ユーザーから `git add` / `git commit` 禁止が明示されているため、差分整理はレビュー時のファイル単位確認に留める。

### 具体的なタスク

- [x] Step R-LOW.1: `backend/app/services/oidc_provider_client.py` の `exchange_code()` で `_required_metadata_str(metadata, "token_endpoint")` を `try` ブロック外へ移動し、`OidcProviderMetadataError` を `OidcTokenExchangeError` に変換しない。
- [x] Step R-LOW.2: `backend/tests/unit/services/test_oidc_provider_client.py` に、`fetch_token()` が失敗しても OAuth client の `aclose()` が 1 回呼ばれる test を追加する。
- [x] Step R-LOW.3: `backend/tests/unit/services/test_oidc_provider_client.py` に、`token_endpoint` 欠落時の `OidcProviderMetadataError` が preserve され、token exchange が呼ばれない test を追加する。
- [x] Step R-LOW.4: `AUTH_OIDC_STATE_RETENTION_SECONDS` を `backend/app/config/oidc.py` から削除し、未使用設定として公開されないようにする。
- [x] Step R-LOW.5: `backend/tests/unit/config/test_oidc_settings.py` から `AUTH_OIDC_STATE_RETENTION_SECONDS` の parse / assert を削除する。
- [x] Step R-LOW.6: `backend/.env.example` から `AUTH_OIDC_STATE_RETENTION_SECONDS` を削除し、env example と実設定契約を一致させる。
- [x] Step R-LOW.7: `cd backend && uv run pytest tests/unit/services/test_oidc_provider_client.py tests/unit/config/test_oidc_settings.py -q` を実行する。
- [x] Step R-LOW.8: Backend static checks と unit tests を再実行し、今回の是正で品質ゲートが崩れていないことを確認する。
- [x] Step R-LOW.9: `cd backend && TEST_DATABASE_URL=... uv run pytest tests/integration -q -ra` を実行し、既存 integration 契約が崩れていないことを確認する。
- [x] Step R-LOW.10: `cd backend && DATABASE_URL=... uv run python manage.py db-check` を実行し、schema drift がないことを確認する。

## 2026-08-07 追記: 最終レビュー指摘 H1-H3 / M1-M5 / Low の是正

### 背景

Claude Code の最終レビューで、OAuth/OIDC Client 実装は全 Task 完了版として品質ゲート通過が確認された一方、callback / start endpoint の failure UX、callback 例外の扱い、既存 user 契約との整合、frontend feedback の stale 表示に改善余地があると指摘された。

特に以下は実装済み機能の安全性と利用者体験に直接関係するため、Task 完了後の hardening として是正した。

- IdP が `error=access_denied` だけを返す OAuth callback が FastAPI validation error になり、binding cookie も残る。
- OIDC authorization start / reauth start で provider unavailable / metadata invalid が JSON 500 になり得る。
- reauth start を未認証で開いた場合に settings flow ではなく JSON 401 になる。
- callback の失敗がすべて redirect される一方、未知例外の log が残らない。
- usecase が例外オブジェクトの `__dict__` に callback context を後付けしており、例外契約が不明瞭。
- 既存 provider identity または同一 email user が deleted / inactive の場合の OIDC login error が誤分類される。
- URL query 由来の OIDC reauth message が、フォーム操作後に stale feedback として再表示され得る。

### 方針とその理由

- OAuth callback endpoint は `state` / `code` / `error` を optional query として受け、`error` がある場合は `OIDC_PROVIDER_ACCESS_DENIED` として `/login` へ 303 redirect する。IdP 側キャンセルは正常な terminal failure であり、API validation error や raw JSON として利用者に見せるべきではないため。
- OIDC redirect は 303 See Other に統一する。OAuth/OIDC callback は browser navigation の完了処理であり、POST 再送 semantics を持つ 307 より、login/settings 画面を GET で表示する 303 の方が意図と一致するため。
- start / reauth start / callback は既知の OIDC error を machine-readable query code に変換し、未知例外だけ `logger.exception()` で記録する。利用者には token / code / provider detail を漏らさず、運用者には unexpected failure を調査できる材料を残すため。
- callback flow の失敗 context は `OidcCallbackFlowError(error, purpose, redirect_path)` に集約する。例外属性の動的後付けは型検査・レビュー・将来の refactor で見落とされやすいため、専用 model と controller helper で明示する。
- session replacement は `auth_session_issuer.replace_auth_session()` に集約する。password login / register と OIDC login が同じ opaque session / CSRF cookie 契約を守る必要があり、重複実装は expiry 計算や revoke 挙動の drift を生むため。
- OIDC identity または同一 email collision が inactive / deleted user を指す場合は `OIDC_IDENTITY_UNAVAILABLE` にする。auto-link / auto-provision の対象は active non-deleted user だけであり、inactive user への誤 link や IntegrityError 経由の unexpected failure を避けるため。
- frontend settings の query feedback は、ユーザーがフォーム操作または submit を始めた query key だけ dismiss する。callback 直後の message は表示しつつ、操作後に古い success/error が復活する体験を避けるため。

### 具体的なタスク

- [x] Step FINAL.1: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に、`error=access_denied` callback が `/login?oidcError=OIDC_PROVIDER_ACCESS_DENIED` へ 303 redirect し、該当 binding cookie を削除する test を追加する。
- [x] Step FINAL.2: `backend/app/controllers/auth_controller.py` の OIDC callback query を optional にし、IdP error / missing state / missing code を JSON validation error ではなく redirect failure として扱う。
- [x] Step FINAL.3: OIDC redirect helper を 303 に統一し、controller unit / integration test の期待 status code を更新する。
- [x] Step FINAL.4: `start_oidc_login` で `OidcProviderUnavailableError` / `OidcProviderMetadataError` など既知 OIDC error を login redirect code に変換し、unknown は `logger.exception()` 後に generic code へ変換する。
- [x] Step FINAL.5: `start_oidc_reauth` で未認証 session を `/login?oidcError=OIDC_REAUTH_AUTHENTICATION_REQUIRED` へ redirect し、provider error は `/app/settings?oidcError=<code>` へ redirect する。
- [x] Step FINAL.6: `OidcCallbackFlowError` を追加し、usecase callback failure の `purpose` / `redirect_path` を例外属性 smuggling ではなく専用 model で controller に渡す。
- [x] Step FINAL.7: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py` で callback failure は `OidcCallbackFlowError.error` に元の業務例外が保持されることを検証する。
- [x] Step FINAL.8: `backend/app/libraries/auth_session_issuer.py` を追加し、password auth と OIDC login の session replacement / expiry 計算を共通化する。
- [x] Step FINAL.9: `AuthRepositoryInterface.find_user_by_email_for_oidc_collision()` を追加し、inactive non-deleted user との email collision を OIDC auto-provision 前に検知する。
- [x] Step FINAL.10: 既存 provider subject が inactive / deleted user を指す場合と、inactive email collision がある場合は `OidcIdentityUnavailableError` に分類する。
- [x] Step FINAL.11: frontend login に `OIDC_PROVIDER_UNAVAILABLE` / `OIDC_PROVIDER_METADATA_INVALID` / `OIDC_PROVIDER_ACCESS_DENIED` / `OIDC_IDENTITY_UNAVAILABLE` の user-facing message を追加する。
- [x] Step FINAL.12: frontend settings に、フォーム操作後は同じ URL query 由来の stale OIDC feedback を再表示しない state を追加する。
- [x] Step FINAL.13: `AccountDeletionUsecase._linked_provider_details()` の `user_id` に `UUID` 型注釈を追加する。
- [x] Step FINAL.14: `AUTH_OIDC_STATE_RETENTION_SECONDS` が未使用設定として残っていないことを再確認する。保持期間は現状 `db-prune-auth` 呼び出し側が explicit threshold を渡す契約のままとする。
- [x] Step FINAL.15: Backend static checks、unit tests、integration tests、db-check、frontend check/test/build、`git diff --check` を再実行する。

### 検証結果

- Backend static: `uv run ruff check .`、`uv run isort . --check-only`、`uv run yapf -dr app/ tests/ alembic/ manage.py` は pass。
- Backend type: sandbox で `uv` の cache / macOS system configuration 起因の実行失敗があったため、同じ `.venv` の `./.venv/bin/mypy app manage.py` で検証し pass。
- Backend unit: `uv run pytest tests/unit -q --tb=short` は 393 passed。
- Backend integration: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ./.venv/bin/pytest tests/integration -q --tb=short` は 112 passed。
- Backend DB: `DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ./.venv/bin/python manage.py db-upgrade` は pass。`db-check` は "No new upgrade operations detected."。
- Frontend: `npm run check:ci`、`npm test`、`npm run build` は pass。Vitest では既存の jsdom `Window.scrollTo()` warning、build では既存の `%VITE_SITE_URL%` 未設定 warning が出るが failure はない。
- Whitespace: `git diff --check` は clean。

## 2026-08-07 追記: 最終レビュー R1-R3 の是正

### 背景

Claude Code の追加レビューで、H1-H3 / M1-M5 の是正後に以下の残課題が指摘された。

- R1: IdP 同意画面を account deletion reauth 中にキャンセルした場合、callback は `/login?oidcError=OIDC_PROVIDER_ACCESS_DENIED` に戻る。しかしユーザーはまだログイン済みのため login route の beforeLoad で `/app` に弾かれ、settings 文脈と error message が消える。
- R2: `OIDC_PROVIDER_ACCESS_DENIED` と `OIDC_IDENTITY_UNAVAILABLE` を含む redirect query code の対応表が docs に存在せず、Task 7.13 の「domain error / redirect query error code / audit event type の契約を記録する」条件が実質未達。
- R3: settings 側の reauth error message と login 側の `OIDC_REAUTH_AUTHENTICATION_REQUIRED` message が不足している。

### 方針とその理由

- IdP error callback でも `state` が存在する場合は、通常 callback と同じく state row と browser binding cookie を usecase 層で検証・consume する。`purpose=account_deletion_reauth` と保存済み `redirect_path` を復元できるため、`OIDC_PROVIDER_ACCESS_DENIED` は `/login` ではなく保存済み settings path に merge して返す。これにより、ログイン済みユーザーが login page の guard で `/app` に飛ばされて error を見失う回帰を防ぐ。
- state がない、または state context を解決できない場合は reauth 文脈を信用できないため、従来どおり `/login?oidcError=OIDC_STATE_MISMATCH` 等へ戻す。これは browser binding / state mismatch を settings に戻して混乱させないための fail-closed である。
- Provider error callback の audit は、valid state context を consume できた場合だけ `OIDC_LOGIN_FAILED` / `OIDC_REAUTH_FAILED` を記録する。invalid / replayed callback で audit insert を増幅させない既存方針を維持する。
- OIDC error code の正典は `backend/AGENTS.md` に置き、frontend 表示契約は `frontend/AGENTS.md`、backend architecture の補足は `documents/references/backend-app-structure.md` に追記する。テストだけを契約の唯一の根拠にしない。

### 具体的なタスク

- [x] Step FINAL-R1.1: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に、reauth 中の `error=access_denied` callback が保存済み settings path へ `OIDC_PROVIDER_ACCESS_DENIED` を merge し、binding cookie を削除する test を追加する。
- [x] Step FINAL-R1.2: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py` に、provider error callback が state を consume し、`OidcCallbackFlowError` に `purpose` / `redirect_path` / 元 error を保持し、reauth failure audit を記録する test を追加する。
- [x] Step FINAL-R1.3: `OAuthOidcUsecaseInterface` と `OAuthOidcUsecase` に `complete_error_callback()` を追加し、IdP error callback でも state / browser binding 検証と audit を usecase 層で行う。
- [x] Step FINAL-R1.4: `backend/app/controllers/auth_controller.py` の `error` callback 分岐で `complete_error_callback()` を呼び、`OidcCallbackFlowError` を既存 callback failure redirect helper に流す。
- [x] Step FINAL-R1.5: `backend/tests/integration/test_auth_oidc_controller.py` に、reauth cancel が `/app/settings?...oidcError=OIDC_PROVIDER_ACCESS_DENIED#...` に戻り、state が consumed され、`oidc_reauth_failed` audit が 1 件残る test を追加する。
- [x] Step FINAL-R2.1: `backend/AGENTS.md` に OIDC domain error / redirect query code / login redirect / reauth redirect / audit event の対応表を追記する。
- [x] Step FINAL-R2.2: `documents/references/backend-app-structure.md` に、IdP error callback でも state context が解決できる場合は reauth settings path に戻す契約を追記する。
- [x] Step FINAL-R2.3: `frontend/AGENTS.md` に、login/settings が扱う OIDC query code と message 契約を追記する。
- [x] Step FINAL-R3.1: `frontend/src/routes/login.tsx` に `OIDC_REAUTH_AUTHENTICATION_REQUIRED` の user-facing message を追加する。
- [x] Step FINAL-R3.2: `frontend/src/routes/_authenticated.app_.settings.tsx` に `OIDC_PROVIDER_ACCESS_DENIED` / `OIDC_PROVIDER_UNAVAILABLE` / `OIDC_IDENTITY_UNAVAILABLE` の account deletion reauth 用 message を追加する。
- [x] Step FINAL-R3.3: `frontend/src/routes/login.test.tsx` と `frontend/src/routes/app.settings.test.tsx` に不足 message の regression tests を追加する。

### 検証結果

- Backend targeted: `uv run pytest tests/unit/controllers/test_auth_controller_dependency.py tests/unit/usecases/test_oauth_oidc_usecase.py -q --tb=short` は 68 passed。
- Backend integration targeted: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ./.venv/bin/pytest tests/integration/test_auth_oidc_controller.py::test_oidc_reauth_provider_cancel_returns_to_settings_and_records_failure -q --tb=short` は pass。
- Backend static: `uv run ruff check .`、`uv run isort . --check-only`、`uv run yapf -dr app/ tests/ alembic/ manage.py` は pass。
- Backend type: `./.venv/bin/mypy app manage.py` は pass。
- Backend unit: `uv run pytest tests/unit -q --tb=short` は 395 passed。
- Backend integration: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ./.venv/bin/pytest tests/integration -q --tb=short` は 113 passed。

## 2026-08-11 現行 schema 注記

この計画は historical plan である。現行 schema は `documents/plans/20260811-db-schema-guideline-alignment.md` の DB schema alignment 方針を優先する。
- Backend DB: `DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ./.venv/bin/python manage.py db-check` は "No new upgrade operations detected."。
- Frontend targeted: `npm test -- login.test.tsx app.settings.test.tsx` は 35 passed。
- Frontend all: `npm test` は 142 passed。`npm run check:ci` は pass。`npm run build` は pass。

## 2026-08-08 追記: 最終 Low 指摘の是正

### 背景

Claude Code の最終 Low 指摘として、以下 5 点が残った。

- `complete_error_callback()` は必ず raise するのに return type が `None` であり、controller 側に実質到達不能な fallback return が残っている。
- `auth_controller.py` に型ナローイング目的の `assert binding_cookie_name is not None` があり、`python -O` で消える `assert` を request handler の制御に使う形になっている。
- OIDC auto-provision の collision check と `create_user()` の間に TOCTOU があり、同一 email の並行 callback で `EmailAlreadyRegisteredError` が `OIDC_UNEXPECTED_ERROR` に落ちる。
- IdP callback の `error_description` を URL に出さないのは正しいが、server log にも残らず、IdP 側失敗理由の切り分けが難しい。
- usecase test stub が interface を直接継承していない。

### 方針とその理由

- `complete_error_callback()` は interface / 実装とも `NoReturn` にする。provider error callback は成功 result を返す workflow ではなく、state context を解決したうえで必ず `OidcCallbackFlowError` を raise して controller の failure redirect helper に渡す契約であるため。
- controller の到達不能 fallback return は削除する。`NoReturn` によって型上も「ここには戻らない」ことを表現し、不要な defensive branch を残さない。
- `binding_cookie_name` は `state is None` 分岐後に通常代入で再計算する。`assert` に runtime 制御や型ナローイングを依存させない。
- `create_user()` が `EmailAlreadyRegisteredError` を返した場合は、並行 callback による email collision とみなし `OidcIdentityUnavailableError` に変換する。fail-closed を維持しつつ、ユーザー向け code と audit detail を `OIDC_IDENTITY_UNAVAILABLE` / `OidcIdentityUnavailableError` に揃える。
- `error_description` は URL、frontend state、audit には残さない。server log の `extra` にだけ `provider_id`、`oidc_error`、正規化済み `oidc_error_description` を入れる。外部入力なので空白正規化し、512 文字を超える場合は切り詰める。
- usecase test stub の interface 継承は今回も採用しない。実 DI 契約は `tests/unit/bootstrap/test_container.py` で検証されており、stub 継承を強制すると unit test 用の補助 fake が本質でない abstract method 実装に引きずられる。必要になった場合は shared fake / autospec / Protocol 化として別計画で扱う。

### 具体的なタスク

- [x] Step FINAL-LOW.1: `OAuthOidcUsecaseInterface.complete_error_callback()` の return type を `NoReturn` に変更する。
- [x] Step FINAL-LOW.2: `OAuthOidcUsecase.complete_error_callback()` の return type を `NoReturn` に変更する。
- [x] Step FINAL-LOW.3: `backend/app/controllers/auth_controller.py` の provider error callback 分岐から到達不能 fallback return を削除する。
- [x] Step FINAL-LOW.4: `backend/app/controllers/auth_controller.py` の `assert binding_cookie_name is not None` を通常代入へ置き換える。
- [x] Step FINAL-LOW.5: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py` に、`create_user()` が duplicate email で失敗した場合に `OidcIdentityUnavailableError` へ変換され、audit detail も `OidcIdentityUnavailableError` になる test を追加する。
- [x] Step FINAL-LOW.6: `backend/app/usecases/oauth_oidc_usecase.py` で `EmailAlreadyRegisteredError` を捕捉し、`OidcIdentityUnavailableError` へ変換する。
- [x] Step FINAL-LOW.7: `backend/tests/unit/controllers/test_auth_controller_dependency.py` に、`error_description` が redirect URL に出ず、server log の `extra` にだけ残る test を追加する。
- [x] Step FINAL-LOW.8: `backend/app/controllers/auth_controller.py` で IdP callback error を `logger.info(..., extra={...})` に記録し、`error_description` を空白正規化・長さ制限する helper を追加する。
- [x] Step FINAL-LOW.9: `assert binding_cookie_name` が残っていないことを grep で確認する。
- [x] Step FINAL-LOW.10: Backend static checks、unit tests、integration tests を再実行する。

### 検証結果

- RED 確認: `test_complete_callback_maps_duplicate_email_race_to_identity_unavailable` は修正前に `EmailAlreadyRegisteredError` のまま `OidcCallbackFlowError.error` に入って失敗した。
- RED 確認: `test_oidc_callback_provider_error_redirects_and_clears_binding_cookie` は修正前に `logger.infos == []` で失敗した。
- Targeted unit: `uv run pytest tests/unit/usecases/test_oauth_oidc_usecase.py::test_complete_callback_maps_duplicate_email_race_to_identity_unavailable tests/unit/controllers/test_auth_controller_dependency.py::test_oidc_callback_provider_error_redirects_and_clears_binding_cookie -q --tb=short` は pass。
- `assert binding_cookie_name` は `rtk grep -n "assert binding_cookie_name|complete_error_callback\\(" ...` で該当 assert が残っていないことを確認した。
- Backend static: `uv run ruff check .`、`uv run isort . --check-only`、`uv run yapf -dr app/ tests/ alembic/ manage.py` は pass。
- Backend type: `./.venv/bin/mypy app manage.py` は pass。
- Backend unit: `uv run pytest tests/unit -q --tb=short` は 396 passed。
- Backend OIDC integration: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ./.venv/bin/pytest tests/integration/test_auth_oidc_controller.py -q --tb=short` は 17 passed。
- Backend integration: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ./.venv/bin/pytest tests/integration -q --tb=short` は 113 passed。
